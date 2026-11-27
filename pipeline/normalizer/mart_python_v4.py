"""OMM v4 Python 마트: SQL로 하기 어려운 분석 결과를 DB에 넣음 (mart_build_v4.sql 다음에 실행)
   ① 메뉴 군집 (분석 1, K-means 4개)  ② 재료 네트워크 (분석 7)  ③ 비슷한 메뉴
   ④ 대체 재료 (네트워크 이웃 유사)  ⑤ 가격-관심도 시차 상관

실행:  pip install pandas scikit-learn networkx psycopg2-binary
       set PGHOST=10.0.56.101 / PGDATABASE=omm / PGUSER=omm / PGPASSWORD=... (비밀번호는 환경변수로만)
       python mart_python_v4.py
"""
import os, collections
from itertools import combinations, permutations
import numpy as np, pandas as pd, networkx as nx, psycopg2
from psycopg2.extras import execute_values
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

conn = psycopg2.connect(host=os.getenv('PGHOST', 'localhost'), dbname=os.getenv('PGDATABASE', 'omm'),
                        user=os.getenv('PGUSER', 'postgres'), password=os.getenv('PGPASSWORD'))
DEC2FLOAT = psycopg2.extensions.new_type(psycopg2.extensions.DECIMAL.values, 'DEC2FLOAT',
                                         lambda v, c: float(v) if v is not None else None)
psycopg2.extensions.register_type(DEC2FLOAT)   # NUMERIC → float
cur = conn.cursor()
def q(sql):
    cur.execute(sql)
    return pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])

# ① 군집: 조리시간 × 1인분 재료비 (로그) → 4개, 중심 위치로 이름 붙이기
df = q("""SELECT r.recipe_id, r.cook_time_min, rm.cost_per_serving FROM omm_recipes r JOIN omm_recipe_metrics rm USING (recipe_id)
          WHERE r.cook_time_min IS NOT NULL AND rm.cost_per_serving > 0 AND rm.priced_ratio >= 0.6""")
k = min(4, len(df))
if k >= 2:
    X = StandardScaler().fit_transform(np.log1p(df[['cook_time_min', 'cost_per_serving']]))
    df['c'] = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(X)
    cen = df.groupby('c')[['cook_time_min', 'cost_per_serving']].median()
    t_mid, c_mid = df.cook_time_min.median(), df.cost_per_serving.median()
    NAMES = {(0, 0): ('자취형', '빠르고 싸요'), (0, 1): ('간편 고급형', '빠르지만 재료비가 들어요'),
             (1, 0): ('주말 요리형', '오래 걸리지만 싸요'), (1, 1): ('대접형', '오래 걸리고 재료비도 들어요')}
    # 군집 4개에 이름 4개를 겹치지 않게: 중심(로그 · 표준화)과 네 모서리의 거리 합이 가장 작은 배정
    z = np.log1p(cen); z = (z - z.mean()) / z.std(ddof=0).replace(0, 1)
    corners = list(NAMES)
    best = min(permutations(corners, len(cen)), key=lambda perm: sum(
        (z.iloc[i].cook_time_min - (1 if t else -1)) ** 2 + (z.iloc[i].cost_per_serving - (1 if c else -1)) ** 2 for i, (t, c) in enumerate(perm)))
    rows = []
    for (c, r), corner in zip(cen.iterrows(), best):
        name, desc = NAMES[corner]
        rows.append((int(c) + 1, name, desc, float(r.cook_time_min), int(r.cost_per_serving), int((df.c == c).sum())))
    cur.execute("UPDATE omm_recipe_metrics SET cluster_id = NULL; DELETE FROM omm_menu_clusters;")
    execute_values(cur, "INSERT INTO omm_menu_clusters VALUES %s", rows)
    execute_values(cur, "UPDATE omm_recipe_metrics rm SET cluster_id = v.c FROM (VALUES %s) v(id, c) WHERE rm.recipe_id = v.id",
                   [(int(a), int(b) + 1) for a, b in zip(df.recipe_id, df.c)])

# ② 재료 네트워크 (양념 제외): 함께 쓰인 횟수 · Lift · PMI, 중심성 · Louvain 커뮤니티
ri = q("""SELECT DISTINCT ri.recipe_id, ri.ingredient_id FROM omm_recipe_ingredients ri
          JOIN omm_ingredients i USING (ingredient_id) WHERE NOT i.is_seasoning""")
N = ri.recipe_id.nunique()
cnt = ri.ingredient_id.value_counts()
pairs = {}
for _, g in ri.groupby('recipe_id'):
    for a, b in combinations(sorted(g.ingredient_id), 2):
        pairs[(a, b)] = pairs.get((a, b), 0) + 1
MIN_CO = int(os.getenv('MIN_CO', '1' if N < 3000 else '3'))   # 레시피가 많으면 드문 쌍(우연) 제거
edges = []
for (a, b), co in pairs.items():
    if co < MIN_CO: continue
    lift = co * N / (cnt[a] * cnt[b])
    edges.append((int(a), int(b), int(co), round(float(lift), 3), round(float(np.log2(lift)), 3)))
G = nx.Graph()                                   # 연결이 하나도 없는 재료는 빼고 그림 (커뮤니티가 1개짜리로 잘게 쪼개지지 않게)
G.add_weighted_edges_from((a, b, lift) for a, b, _, lift, _ in edges)
if len(G) == 0: G.add_nodes_from(int(i) for i in cnt.index)
deg_c = nx.degree_centrality(G)
btw = nx.betweenness_centrality(G, k=min(300, len(G)), seed=42) if len(G) > 300 else nx.betweenness_centrality(G)   # 노드가 많으면 표본 300개로 근사
comms = nx.community.louvain_communities(G, weight='weight', seed=42) if G.number_of_edges() else [{n} for n in G]
comm_of = {n: i + 1 for i, c in enumerate(comms) for n in c}
cur.execute("DELETE FROM omm_ingredient_network_edges; DELETE FROM omm_ingredient_network_nodes;")
if edges: execute_values(cur, "INSERT INTO omm_ingredient_network_edges VALUES %s", edges)
execute_values(cur, "INSERT INTO omm_ingredient_network_nodes (ingredient_id, recipe_count, degree, degree_centrality, betweenness, community_id) VALUES %s",
               [(n, int(cnt[n]), G.degree(n), round(float(deg_c[n]), 4), round(float(btw[n]), 4), comm_of[n]) for n in G])

# ③ 비슷한 메뉴: 대표 레시피 재료 Jaccard 상위 5
mi = q("""SELECT m.menu_id, ri.ingredient_id FROM omm_menus m JOIN omm_recipe_ingredients ri ON ri.recipe_id = m.rep_recipe_id
          JOIN omm_ingredients i USING (ingredient_id) WHERE NOT i.is_seasoning""")
sets = mi.groupby('menu_id').ingredient_id.apply(set).to_dict()
sim = []
for m in sets:
    sc = sorted(((len(sets[m] & sets[o]) / len(sets[m] | sets[o]), o) for o in sets if o != m), reverse=True)
    sim += [(int(m), int(o), round(float(s), 3), r) for r, (s, o) in enumerate([x for x in sc if x[0] > 0][:5], 1)]
cur.execute("DELETE FROM omm_menu_similarities")
if sim: execute_values(cur, "INSERT INTO omm_menu_similarities VALUES %s", sim)

# ④ 대체 재료 (NETWORK): 이웃 재료가 비슷한데 함께는 잘 안 쓰는 재료 = 서로 바꿔 쓰는 재료
#    score = 이웃 Jaccard × (1 - 함께 쓰인 비율)  · REVIEW / TREND 근거는 후기 · 관심도 분석 후 같은 표에 추가
subs = []
nbr = {n: set(G[n]) for n in G}
for a in G:
    na = nbr[a]
    if len(na) < 3: continue
    for b in G:                                   # 이웃이 하나라도 겹치는 재료만 후보
        if a == b: continue
        nb = nbr[b]
        if len(nb) < 3 or not (na & nb): continue
        j = len((na - {b}) & (nb - {a})) / max(1, len((na | nb) - {a, b}))
        together = pairs.get(tuple(sorted((a, b))), 0) / min(cnt[a], cnt[b])
        s = j * (1 - together)
        if s > 0.25 and len(na & nb) >= 3: subs.append((int(a), int(b), 'BASIS_NETWORK', None, round(float(s), 3), len(na & nb)))
# 재료마다 점수 높은 5개만 (화면에는 2~3개면 충분)
top = collections.defaultdict(list)
for x in subs: top[x[0]].append(x)
subs = [y for v in top.values() for y in sorted(v, key=lambda z: -z[4])[:5]]
cur.execute("DELETE FROM omm_ingredient_substitutes WHERE basis = 'BASIS_NETWORK'")
if subs: execute_values(cur, "INSERT INTO omm_ingredient_substitutes VALUES %s", subs)

# ⑤ 시차 상관: 평년 대비 가격(%) vs k개월 뒤 관심도 작년 대비(%), 재료별 + 전체
pi = q("""SELECT pm.ingredient_id, pm.ym, pm.vs_normal_pct AS p, ii.yoy_pct AS i, pm.price_per_100g AS pp, ii.interest_cnt AS ic
          FROM omm_price_monthly pm JOIN omm_ingredient_interest_monthly ii USING (ingredient_id, ym)
          WHERE pm.market_type = 'MARKET_RETAIL' ORDER BY 1, 2""")
pi['ym'] = pd.to_datetime(pi.ym)
# 1년치 데이터라 평년 · 작년 대비가 비면, 그 재료의 기간 평균 대비(%)로 대신 계산
for col, raw in (('p', 'pp'), ('i', 'ic')):
    pi[raw] = pd.to_numeric(pi[raw], errors='coerce')
    alt = (pi[raw] / pi.groupby('ingredient_id')[raw].transform('mean') - 1) * 100
    pi[col] = pd.to_numeric(pi[col], errors='coerce')
    if pi[col].notna().sum() < len(pi) * 0.3: pi[col] = alt
rows = []
def corr_rows(d, ing):
    d = d.set_index('ym').sort_index()
    for lag in range(4):
        x = pd.concat([d.p, d.i.shift(-lag)], axis=1).dropna()
        if len(x) >= 6 and x.p.std() > 0 and x.i.std() > 0:
            rows.append((ing, lag, round(float(x.p.corr(x.i)), 3), len(x), x.index.min().date(), x.index.max().date()))
for ing, d in pi.groupby('ingredient_id'): corr_rows(d[['ym', 'p', 'i']], int(ing))
corr_rows(pi.groupby('ym')[['p', 'i']].mean().reset_index(), None)
cur.execute("DELETE FROM omm_price_interest_corr")
if rows: execute_values(cur, "INSERT INTO omm_price_interest_corr (ingredient_id, lag_month, corr, n_months, period_from, period_to) VALUES %s", rows)

cur.execute("INSERT INTO omm_etl_runs (source, job, finished_at, status, row_count) VALUES ('SRC_MART', 'mart_python_v4', now(), 'ETL_OK', %s)",
            (len(edges) + len(sim) + len(subs) + len(rows),))
conn.commit()
print(f'군집 {k} · 엣지 {len(edges)} · 노드 {G.number_of_nodes()} · 커뮤니티 {len(comms)} · 비슷한 메뉴 {len(sim)} · 대체 {len(subs)} · 시차 상관 {len(rows)}')
