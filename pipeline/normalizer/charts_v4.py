"""OMM v4 분석 차트 8종 → charts/ 폴더 (PNG + 7번 네트워크는 마우스로 볼 수 있는 HTML + 전체 모음 index.html)

  pip install matplotlib
  python charts_v4.py          (접속: PGHOST · PGDATABASE · PGUSER · PGPASSWORD, run_all.bat 다음에 실행)
  → charts/index.html 을 브라우저로 열면 전체 차트를 한 번에 볼 수 있음
"""
import os, sys, math, html, json
import numpy as np, pandas as pd, psycopg2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'charts')
os.makedirs(OUT, exist_ok=True)

# ── 색 (검증된 기본 팔레트) · 글꼴 ──
S = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']
INK, INK2, MUTED, GRID, SURF = '#0b0b0b', '#52514e', '#8a8984', '#e6e5e0', '#fcfcfb'
for f in ('Malgun Gothic', 'AppleGothic', 'NanumGothic', 'Noto Sans CJK KR', 'Noto Sans KR'):
    if any(f == x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams['font.family'] = f; break
plt.rcParams.update({'axes.unicode_minus': False, 'figure.facecolor': SURF, 'axes.facecolor': SURF, 'axes.edgecolor': GRID,
                     'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2, 'axes.grid': True, 'grid.color': GRID,
                     'grid.linewidth': 0.8, 'axes.axisbelow': True, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.titlesize': 14, 'axes.titleweight': 'bold', 'axes.titlecolor': INK, 'axes.titlelocation': 'left',
                     'font.size': 11, 'legend.frameon': False, 'savefig.dpi': 150, 'savefig.bbox': 'tight'})

DEC = psycopg2.extensions.new_type(psycopg2.extensions.DECIMAL.values, 'D2F', lambda v, c: float(v) if v is not None else None)
psycopg2.extensions.register_type(DEC)
conn = psycopg2.connect(host=os.getenv('PGHOST', 'localhost'), port=os.getenv('PGPORT', '5432'), dbname=os.getenv('PGDATABASE', 'omm_insight'),
                        user=os.getenv('PGUSER', 'postgres'), password=os.getenv('PGPASSWORD'))
def q(sql):
    cur = conn.cursor(); cur.execute(sql)
    return pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])

made = []   # (파일, 분석 번호, 제목, 설명)
def save(fig, name, no, title, note):
    fig.savefig(os.path.join(OUT, name)); plt.close(fig); made.append((name, no, title, note)); print(f'  ✔ {name}')

def empty(name, no, title, why):
    fig, ax = plt.subplots(figsize=(8, 3)); ax.axis('off')
    ax.text(0.5, 0.55, title, ha='center', fontsize=14, weight='bold', color=INK)
    ax.text(0.5, 0.35, f'데이터가 아직 없어요 · {why}', ha='center', color=MUTED)
    save(fig, name, no, title, why)

def note(ax, text):
    ax.text(0, -0.16, text, transform=ax.transAxes, color=MUTED, fontsize=9, va='top')

won = lambda v, p=None: f'{v:,.0f}원'
from matplotlib.ticker import FixedLocator, NullFormatter, FuncFormatter
def logticks(axis, ticks, fmt):
    lo, hi = axis.get_view_interval()                       # 데이터 범위 안의 1 · 2 · 5 눈금만
    ticks = [m * 10 ** k for k in range(-1, 8) for m in (1, 2, 5) if lo <= m * 10 ** k <= hi]
    if len(ticks) > 7: ticks = [t for t in ticks if str(int(t))[0] in '15'] if len(ticks) <= 14 else [t for t in ticks if str(int(t))[0] == '1']
    axis.set_major_locator(FixedLocator(ticks)); axis.set_major_formatter(FuncFormatter(fmt)); axis.set_minor_formatter(NullFormatter())

# ───────────── 1. 조리시간 × 재료비 군집 ─────────────
def chart1():
    d = q("""SELECT r.cook_time_min AS t, rm.cost_per_serving AS c, mc.name AS cl, mc.center_cook_min AS ct, mc.center_cost_won AS cc
             FROM omm_recipes r JOIN omm_recipe_metrics rm USING (recipe_id) JOIN omm_menu_clusters mc USING (cluster_id)
             WHERE rm.cost_per_serving > 0 AND r.cook_time_min > 0""")
    if d.empty: return empty('1_군집.png', 1, '조리시간 × 1인분 재료비 군집', 'mart_python_v4.py를 먼저 실행')
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14, 6), gridspec_kw={'width_ratios': [2.2, 1]})
    names = sorted(d.cl.unique(), key=lambda n: d[d.cl == n].ct.iloc[0] * 1e6 + d[d.cl == n].cc.iloc[0])
    rng = np.random.default_rng(0)
    for i, n in enumerate(names):
        g = d[d.cl == n]
        ax.scatter(g.t * np.exp(rng.normal(0, 0.06, len(g))), g.c, s=26, color=S[i], alpha=0.55, edgecolor=SURF, linewidth=0.6,
                   marker='ospD'[i % 4], label=f'{n} ({len(g):,})')
        ax.scatter(g.ct.iloc[0], g.cc.iloc[0], s=260, marker='X', color=S[i], edgecolor=INK, linewidth=1.2, zorder=5)
        ax.annotate(n, (g.ct.iloc[0], g.cc.iloc[0]), xytext=(10, 8), textcoords='offset points', weight='bold', color=INK, fontsize=12)
    ax.set_xscale('log'); ax.set_yscale('log')
    logticks(ax.xaxis, [5, 10, 15, 20, 30, 60, 90, 120, 180], lambda v, p: f'{v:.0f}분')
    logticks(ax.yaxis, [300, 500, 1000, 2000, 3000, 5000, 10000, 20000], won); ax.set_xlabel('조리시간 (로그)'); ax.set_ylabel('1인분 재료비 (로그)')
    ax.set_title('① 조리시간 × 1인분 재료비 — 메뉴 4유형'); ax.legend(loc='upper left', fontsize=10)
    note(ax, '점 = 레시피 · X = 군집 중심 · K-means(로그 스케일 표준화) · 가격을 60% 이상 찾은 레시피만')
    cnt = d.cl.value_counts().reindex(names)
    ax2.barh(cnt.index, cnt.values, color=[S[i] for i in range(len(names))], height=0.6)
    for y, v in enumerate(cnt.values): ax2.text(v, y, f'  {v:,}', va='center', color=INK2)
    ax2.invert_yaxis(); ax2.set_title('유형별 레시피 수'); ax2.grid(axis='y', visible=False)
    save(fig, '1_군집.png', 1, '조리시간 × 재료비 군집', '메뉴를 자취형 · 대접형 등 4유형으로 나눈 결과')

# ───────────── 2. 별점 vs 재료비 ─────────────
def chart2():
    sql = """SELECT r.title, r.avg_rating AS r, r.review_count AS n, rm.cost_per_serving AS c
             FROM omm_recipes r JOIN omm_recipe_metrics rm USING (recipe_id) WHERE r.review_count >= {} AND rm.cost_per_serving >= 300 AND rm.priced_ratio >= 0.6 AND r.avg_rating IS NOT NULL"""
    MINREV = 5
    d = q(sql.format(MINREV))
    if len(d) < 30: MINREV = 1; d = q(sql.format(MINREV))        # 최근 1년 레시피처럼 후기가 적으면 후기 1개 이상으로 낮춤
    if len(d) < 3: return empty('2_별점_재료비.png', 2, '별점 vs 재료비', '후기 있는 레시피가 부족')
    rr = np.corrcoef(np.log(d.c), d.r)[0, 1]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14, 6), gridspec_kw={'width_ratios': [1.4, 1]})
    ax.scatter(d.c, d.r, s=20 + np.clip(d.n, 5, 200) * 1.2, color=S[0], alpha=0.45, edgecolor=SURF, linewidth=0.6)
    b = np.polyfit(np.log(d.c), d.r, 1); xs = np.linspace(np.log(d.c).min(), np.log(d.c).max(), 50)
    ax.plot(np.exp(xs), b[0] * xs + b[1], color=INK2, lw=2, ls='--')
    ax.set_xscale('log'); logticks(ax.xaxis, [300, 500, 1000, 2000, 3000, 5000, 10000, 20000], won); ax.set_xlabel('1인분 재료비 (로그)'); ax.set_ylabel('평균 별점')
    strength = '거의 없음' if abs(rr) < 0.1 else '약함' if abs(rr) < 0.3 else '보통' if abs(rr) < 0.5 else '강함'
    ax.set_title(f'② 별점 vs 1인분 재료비 — 상관 r = {rr:.2f} ({strength})')
    note(ax, f'점 크기 = 후기 수 · 점선 = 추세선 · 후기 {MINREV}개 이상 · 가격 붙은 재료 60% 이상 · 1인분 300원 이상 ({len(d):,}개) · 상관이 약하면 "싸도 만족도 높은 메뉴"를 추천할 근거')
    cut = d.c.quantile(0.25)
    top = d[d.c <= cut].sort_values(['r', 'n'], ascending=False).head(12)[::-1]
    ax2.barh([t[:16] for t in top.title], top.r, color=S[2], height=0.6)
    for y, (v, c) in enumerate(zip(top.r, top.c)): ax2.text(v, y, f'  ★{v:.2f} · {c:,.0f}원', va='center', fontsize=9, color=INK2)
    ax2.set_xlim(max(0, top.r.min() - 0.6) if len(top) else 0, 5.6); ax2.set_title(f'싸도 만족도 높은 레시피 (하위 25% ≤ {cut:,.0f}원)')
    ax2.grid(axis='y', visible=False)
    save(fig, '2_별점_재료비.png', 2, '별점 vs 재료비', f'상관 r = {rr:.2f}')

# ───────────── 3. 사람 이름 vs 조회수 · 별점 ─────────────
def chart3():
    d = q("""SELECT (rm.person_name IS NOT NULL) AS p, rm.person_name AS nm, r.view_count AS v, r.avg_rating AS r
             FROM omm_recipes r JOIN omm_recipe_metrics rm USING (recipe_id) WHERE r.view_count > 0""")
    if d.empty or d.p.nunique() < 2: return empty('3_사람이름.png', 3, '사람 이름 vs 조회수 · 별점', '사람 이름이 든 레시피가 없음')
    fig, axs = plt.subplots(1, 3, figsize=(15, 5.5), gridspec_kw={'width_ratios': [1.3, 1, 1]})
    grp = [d[~d.p].v, d[d.p].v]; lab = [f'이름 없음\n(n={len(grp[0]):,})', f'이름 있음\n(n={len(grp[1]):,})']
    bp = axs[0].boxplot(grp, tick_labels=lab, patch_artist=True, widths=0.5, showfliers=False, medianprops={'color': INK, 'lw': 2})
    for p, c in zip(bp['boxes'], [S[0], S[1]]): p.set_facecolor(c); p.set_alpha(0.5); p.set_edgecolor(c)
    for i, g in enumerate(grp, 1): axs[0].text(i + 0.3, g.median(), f'중앙 {g.median():,.0f}', va='center', fontsize=9, color=INK2)
    axs[0].set_yscale('log'); logticks(axs[0].yaxis, [100, 1000, 10000, 100000, 1000000], lambda v, p: f'{v:,.0f}'); axs[0].set_title('③ 조회수 (로그)')
    m = [d[~d.p].r.mean(), d[d.p].r.mean()]
    axs[1].bar(['이름 없음', '이름 있음'], m, color=[S[0], S[1]], width=0.5)
    for i, v in enumerate(m): axs[1].text(i, v, f'★{v:.2f}', ha='center', va='bottom', color=INK)
    axs[1].set_ylim(max(0, min(m) - 0.8), 5.2); axs[1].set_title('평균 별점'); axs[1].grid(axis='x', visible=False)
    t = d[d.p].groupby('nm').agg(n=('v', 'size'), v=('v', 'median')).sort_values('n').tail(10)
    axs[2].barh(t.index, t.n, color=S[1], height=0.6)
    for y, (n, v) in enumerate(zip(t.n, t.v)): axs[2].text(n, y, f'  {n}개 · 중앙 {v:,.0f}회', va='center', fontsize=9, color=INK2)
    axs[2].set_title('많이 나온 이름'); axs[2].grid(axis='y', visible=False)
    note(axs[0], '사람 이름 = 제목에 백종원 · 류수영 등 사전에 있는 이름이 들어간 레시피')
    save(fig, '3_사람이름.png', 3, '사람 이름 vs 조회수 · 별점', '이름 있는 레시피와 없는 레시피 비교')

# ───────────── 4. 맛 표현별 주요 재료 ─────────────
def chart4():
    d = q("""SELECT t.taste_group AS g, i.name AS ing, count(DISTINCT rt.recipe_id) AS n,
                    (SELECT count(DISTINCT rt2.recipe_id) FROM omm_recipe_tastes rt2 JOIN omm_taste_words t2 USING (taste_id) WHERE t2.taste_group = t.taste_group) AS tot
             FROM omm_recipe_tastes rt JOIN omm_taste_words t USING (taste_id) JOIN omm_recipe_ingredients ri USING (recipe_id)
             JOIN omm_ingredients i ON i.ingredient_id = ri.ingredient_id AND NOT i.is_seasoning GROUP BY t.taste_group, i.name""")
    if d.empty: return empty('4_맛표현_재료.png', 4, '맛 표현별 주요 재료', '맛 표현이 든 레시피가 없음')
    d['pct'] = d.n / d.tot * 100
    cols = d.groupby('ing').n.sum().sort_values(ascending=False).head(14).index
    m = d.pivot_table(index='g', columns='ing', values='pct', fill_value=0).reindex(columns=cols, fill_value=0)
    m = m.loc[d.groupby('g').tot.first().sort_values(ascending=False).index]
    fig, ax = plt.subplots(figsize=(max(9, len(cols) * 0.85), 1.2 + len(m) * 0.7))
    im = ax.imshow(m.values, cmap='Blues', aspect='auto', vmin=0)
    ax.set_xticks(range(len(cols)), cols, rotation=40, ha='right'); ax.set_yticks(range(len(m)), [f'{g} ({int(d[d.g == g].tot.iloc[0]):,})' for g in m.index])
    ax.grid(False)
    for y in range(m.shape[0]):
        for x in range(m.shape[1]):
            v = m.values[y, x]
            if v >= 5: ax.text(x, y, f'{v:.0f}', ha='center', va='center', fontsize=9, color='white' if v > m.values.max() * 0.6 else INK)
    ax.set_title('④ 맛 표현별 주요 재료 — 그 맛 레시피 중 재료가 들어간 비율(%)')
    fig.colorbar(im, ax=ax, shrink=0.8, label='%')
    note(ax, '맛 표현 = 제목 · 소개 · 후기에서 찾은 단어 (매콤 · 얼큰 → 매운맛 …) · 괄호 = 레시피 수')
    save(fig, '4_맛표현_재료.png', 4, '맛 표현별 주요 재료', '"매콤한 거" → 어떤 재료가 들어간 메뉴인지')

# ───────────── 5. 트렌드 키워드 ─────────────
def chart5():
    d = q("""SELECT k.keyword, kt.ym, kt.yt_video_cnt AS yt, kt.yt_view_sum AS views, kt.recipe_cnt AS rc
             FROM omm_keyword_trend_monthly kt JOIN omm_trend_keywords k USING (keyword_id) WHERE kt.ym <= date_trunc('month', current_date) ORDER BY kt.ym""")
    if d.empty: return empty('5_트렌드.png', 5, '최근 레시피 트렌드 키워드', 'YouTube 수집 후 다시 실행')
    d['ym'] = pd.to_datetime(d.ym)
    top = d.groupby('keyword').views.sum().sort_values(ascending=False).head(4).index.tolist()
    color = {k: S[i] for i, k in enumerate(top)}
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
    for k in top:
        g = d[d.keyword == k]
        a1.plot(g.ym, g.views / 1e4, color=color[k], lw=2, marker='o', ms=4, label=k)
        a1.annotate(k, (g.ym.iloc[-1], g.views.iloc[-1] / 1e4), xytext=(6, 0), textcoords='offset points', color=INK, va='center')
        a2.plot(g.ym, g.rc, color=color[k], lw=2, marker='o', ms=4, label=k)
    a1.set_title('⑤ 트렌드 키워드 — YouTube 월 게시 영상 조회수 합 (만 회)'); a1.legend(loc='upper left', ncol=4)
    a2.set_title('같은 키워드가 제목에 든 만개 신규 레시피 수'); a2.set_ylabel('레시피 수')
    note(a2, '조회수 합 상위 4개 키워드 · 키워드 × 월마다 조회수 상위 50개 영상 기준 · 두 지표는 단위가 달라 따로 그림')
    g = d.groupby('keyword').views.sum().sort_values().tail(12) / 1e4
    fig2, ax = plt.subplots(figsize=(9, 0.5 + len(g) * 0.45))
    ax.barh(g.index, g.values, color=[color.get(k, MUTED) for k in g.index], height=0.6)
    for y, v in enumerate(g.values): ax.text(v, y, f'  {v:,.0f}만', va='center', color=INK2, fontsize=9)
    ax.set_title('키워드별 전체 조회수 합 (만 회)'); ax.grid(axis='y', visible=False)
    save(fig, '5_트렌드.png', 5, '트렌드 키워드 월별 흐름', 'YouTube 조회수와 만개 레시피 수를 같은 색으로 비교')
    save(fig2, '5_트렌드_순위.png', 5, '트렌드 키워드 순위', '전체 기간 조회수 합')

# ───────────── 6. 재료비 대비 영양 효율 ─────────────
def chart6():
    d = q("""SELECT i.name, nf.protein_g / pm.price_per_100g * 1000 AS p, nf.energy_kcal / pm.price_per_100g * 1000 AS k
             FROM omm_ingredients i JOIN omm_nutrition_foods nf ON nf.food_cd = i.nutr_food_cd
             JOIN omm_price_monthly pm ON pm.ingredient_id = i.ingredient_id AND pm.market_type = 'MARKET_RETAIL' AND pm.ym = (SELECT max(ym) FROM omm_price_monthly)
             WHERE pm.price_per_100g > 0 AND nf.protein_g IS NOT NULL""")
    unit = '재료'
    if d.empty:                                   # 재료별 영양성분이 없으면(팀 공유 데이터) 메뉴 영양성분 × 레시피 재료비로
        d = q("""SELECT m.name, percentile_cont(0.5) WITHIN GROUP (ORDER BY rm.protein_per_1000won) AS p,
                        percentile_cont(0.5) WITHIN GROUP (ORDER BY rm.kcal_per_1000won) AS k
                 FROM omm_recipe_metrics rm JOIN omm_recipes r USING (recipe_id) JOIN omm_menus m USING (menu_id)
                 WHERE rm.protein_per_1000won IS NOT NULL AND rm.priced_ratio >= 0.6 AND rm.cost_per_serving >= 500
                 GROUP BY m.name HAVING count(*) >= 5""")
        unit = '메뉴'
    if d.empty: return empty('6_영양효율.png', 6, '재료비 대비 영양 효율', '영양성분과 재료비가 함께 있는 재료 · 메뉴가 없음')
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(15, max(6, min(len(d), 20) * 0.35)))
    t = d.sort_values('p').tail(20)
    ax.barh(t.name, t.p, color=S[0], height=0.6)
    for y, v in enumerate(t.p): ax.text(v, y, f'  {v:.1f}g', va='center', fontsize=9, color=INK2)
    ax.set_title(f'⑥ 1,000원으로 살 수 있는 단백질 (g) · {unit}별'); ax.grid(axis='y', visible=False)
    ax2.scatter(d.k, d.p, s=50, color=S[0], alpha=0.7, edgecolor=SURF, linewidth=1)
    mk, mp = d.k.median(), d.p.median()
    ax2.axvline(mk, color=MUTED, ls=':', lw=1); ax2.axhline(mp, color=MUTED, ls=':', lw=1)
    lab = pd.concat([d.nlargest(6, 'p'), d.nlargest(4, 'k'), d.nsmallest(3, 'p')]).drop_duplicates('name')
    for _, r in lab.iterrows(): ax2.annotate(r['name'], (r.k, r.p), xytext=(5, 4), textcoords='offset points', fontsize=9, color=INK)
    ax2.text(0.98, 0.98, '단백질 · 열량 모두 가성비 ↑', transform=ax2.transAxes, ha='right', va='top', color=INK2, fontsize=9)
    ax2.text(0.02, 0.02, '둘 다 비쌈', transform=ax2.transAxes, color=INK2, fontsize=9)
    ax2.set_xlabel('1,000원당 열량 (kcal)'); ax2.set_ylabel('1,000원당 단백질 (g)'); ax2.set_title('열량 · 단백질 가성비 사분면')
    note(ax, '최근 월 KAMIS 소매가 · 식약처 100g당 영양성분 · 가격과 영양이 모두 연결된 재료만' if unit == '재료' else
             '메뉴별 식약처 1인분 영양성분 ÷ 레시피 1인분 재료비 · 레시피 5개 이상 메뉴의 중앙값 (가격 붙은 재료 60% 이상 · 1인분 500원 이상)')
    save(fig, '6_영양효율.png', 6, '재료비 대비 영양 효율', '1,000원당 단백질 · 열량')

# ───────────── 7. 재료 ↔ 메뉴 공유 네트워크 ─────────────
def net_data(n_menu=12, n_ing=14, min_share=0.4):
    d = q("""SELECT m.menu_id, m.name AS menu, m.recipe_count AS mc, i.name AS ing, count(DISTINCT r.recipe_id) AS n
             FROM omm_menus m JOIN omm_recipes r USING (menu_id) JOIN omm_recipe_ingredients ri USING (recipe_id)
             JOIN omm_ingredients i ON i.ingredient_id = ri.ingredient_id AND NOT i.is_seasoning
             GROUP BY m.menu_id, m.name, m.recipe_count""".replace('GROUP BY m.menu_id, m.name, m.recipe_count', 'GROUP BY m.menu_id, m.name, m.recipe_count, i.name'))
    if d.empty: return None
    d['share'] = d.n / d.mc
    omm_menus = d.drop_duplicates('menu').nlargest(n_menu, 'mc').menu.tolist()
    e = d[d.menu.isin(omm_menus) & (d.share >= min_share)]
    deg = e.groupby('ing').menu.nunique()
    ings = deg[deg >= 2].sort_values(ascending=False).head(n_ing).index.tolist() or deg.sort_values(ascending=False).head(n_ing).index.tolist()
    e = e[e.ing.isin(ings)]
    omm_menus = [m for m in omm_menus if m in set(e.menu)]
    # 선이 덜 겹치게: 연결된 반대편 순서의 평균으로 여러 번 정렬
    for _ in range(8):
        pos = {m: i for i, m in enumerate(omm_menus)}
        ings.sort(key=lambda x: e[e.ing == x].menu.map(pos).mean())
        pos = {g: i for i, g in enumerate(ings)}
        omm_menus.sort(key=lambda x: e[e.menu == x].ing.map(pos).mean())
    return ings, omm_menus, e

def chart7():
    nd = net_data()
    if not nd: return empty('7_네트워크.png', 7, '레시피 간 식재료 공유 네트워크', '메뉴 · 재료 데이터 없음')
    ings, omm_menus, e = nd
    H = max(len(ings), len(omm_menus))
    yi = {g: (i + 0.5) * H / len(ings) for i, g in enumerate(ings)}; ym = {m: (i + 0.5) * H / len(omm_menus) for i, m in enumerate(omm_menus)}
    fig, ax = plt.subplots(figsize=(11, 1.4 + H * 0.95)); ax.axis('off'); ax.grid(False)
    for _, r in e.iterrows():
        ax.plot([0.12, 0.86], [yi[r.ing], ym[r.menu]], color='#9b9a95', lw=0.6 + r.share * 3, alpha=0.35 + r.share * 0.4, solid_capstyle='round', zorder=1)
    for g in ings:
        ax.scatter(0.08, yi[g], s=2200, color='#dbe9fb', edgecolor=S[0], linewidth=2, zorder=3)
        ax.text(0.08, yi[g], g, ha='center', va='center', color='#1d4f9a', weight='bold', fontsize=11, zorder=4)
    for m in omm_menus:
        ax.text(0.92, ym[m], m, ha='center', va='center', color='#0b5d1e', weight='bold', fontsize=12, zorder=4,
                bbox=dict(boxstyle='round,pad=0.6,rounding_size=0.8', fc='#e2f7e6', ec='#1a9a3c', lw=2))
    ax.set_xlim(0, 1); ax.set_ylim(H + 0.5, -0.6)
    ax.text(0.08, -0.45, '식재료', ha='center', color=INK2); ax.text(0.92, -0.45, '메뉴', ha='center', color=INK2)
    ax.set_title('⑦ 레시피 간 식재료 공유 네트워크 — 재료 ↔ 메뉴', loc='left')
    ax.text(0, -0.02, '선 = 그 메뉴 레시피의 40% 이상에 들어가는 재료 · 선이 굵을수록 비율 ↑ · 메뉴 2개 이상에 걸친 재료만 (양념 제외) · 마우스로 보려면 7_네트워크.html',
            transform=ax.transAxes, color=MUTED, fontsize=9)
    save(fig, '7_네트워크.png', 7, '재료 ↔ 메뉴 공유 네트워크', '같은 재료를 쓰는 메뉴끼리 이어짐')
    net_html(ings, omm_menus, e)
    n = q("""SELECT i.name, n.degree, n.betweenness, n.community_id FROM omm_ingredient_network_nodes n JOIN omm_ingredients i USING (ingredient_id)
             ORDER BY n.degree DESC, n.betweenness DESC LIMIT 15""")
    if not n.empty:
        fig, ax = plt.subplots(figsize=(9, 0.6 + len(n) * 0.42)); n = n[::-1]
        ax.barh(n.name, n.degree, color=S[0], height=0.6)
        for y, (dg, b) in enumerate(zip(n.degree, n.betweenness)): ax.text(dg, y, f'  {dg}개 재료와 연결 · 매개 {b:.2f}', va='center', fontsize=9, color=INK2)
        ax.set_title('만능 재료 — 함께 쓰이는 재료 수 (연결 중심성)'); ax.grid(axis='y', visible=False)
        note(ax, '매개 중심성이 높을수록 서로 다른 요리군을 잇는 "다리" 재료')
        save(fig, '7_중심성.png', 7, '만능 재료 순위', '연결 · 매개 중심성')

def net_html(ings, omm_menus, e):
    W, row = 760, 64; H = max(len(ings), len(omm_menus)) * row + 40
    yi = {g: 30 + (i + 0.5) * (H - 40) / len(ings) for i, g in enumerate(ings)}; ym = {m: 30 + (i + 0.5) * (H - 40) / len(omm_menus) for i, m in enumerate(omm_menus)}
    esc = html.escape
    lines = ''.join(f'<line x1="130" y1="{yi[r.ing]:.0f}" x2="560" y2="{ym[r.menu]:.0f}" data-i="{esc(r.ing)}" data-m="{esc(r.menu)}" '
                    f'stroke-width="{1 + r.share * 4:.1f}"><title>{esc(r.ing)} → {esc(r.menu)}: 레시피의 {r.share * 100:.0f}%</title></line>' for _, r in e.iterrows())
    nodes = ''.join(f'<g class="ing" data-i="{esc(g)}"><circle cx="90" cy="{yi[g]:.0f}" r="28"/><text x="90" y="{yi[g]:.0f}">{esc(g)}</text></g>' for g in ings)
    nodes += ''.join(f'<g class="menu" data-m="{esc(m)}"><rect x="560" y="{ym[m] - 22:.0f}" width="170" height="44" rx="12"/><text x="645" y="{ym[m]:.0f}">{esc(m)}</text></g>' for m in omm_menus)
    rows = ''.join(f'<tr><td>{esc(r.ing)}</td><td>{esc(r.menu)}</td><td>{r.share * 100:.0f}%</td></tr>' for _, r in e.sort_values(['menu', 'share'], ascending=[True, False]).iterrows())
    page = f'''<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>⑦ 재료 ↔ 메뉴 공유 네트워크</title><style>
body{{margin:0;padding:24px;background:#fcfcfb;color:#0b0b0b;font-family:"Malgun Gothic","Apple SD Gothic Neo",sans-serif}}
h1{{font-size:20px;margin:0 0 4px}} p{{color:#52514e;margin:0 0 16px;font-size:14px}}
svg line{{stroke:#9b9a95;stroke-opacity:.45;stroke-linecap:round;transition:.15s}}
svg text{{text-anchor:middle;dominant-baseline:central;font-weight:700;font-size:14px;pointer-events:none}}
.ing circle{{fill:#dbe9fb;stroke:#2a78d6;stroke-width:2}} .ing text{{fill:#1d4f9a}}
.menu rect{{fill:#e2f7e6;stroke:#1a9a3c;stroke-width:2}} .menu text{{fill:#0b5d1e}}
.ing,.menu{{cursor:pointer}} .dim{{opacity:.15}} line.on{{stroke:#2a78d6;stroke-opacity:.9}}
details{{margin-top:16px}} table{{border-collapse:collapse;font-size:13px}} td{{padding:3px 10px;border-bottom:1px solid #e6e5e0}}
</style></head><body><h1>⑦ 레시피 간 식재료 공유 네트워크</h1>
<p>왼쪽 재료나 오른쪽 메뉴에 마우스를 올리면 연결된 것만 강조돼요 · 선 굵기 = 그 메뉴 레시피 중 재료가 들어간 비율 · 선 위에 올리면 비율이 보여요</p>
<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}"><text x="90" y="12" style="font-weight:400;fill:#52514e">식재료</text>
<text x="645" y="12" style="font-weight:400;fill:#52514e">메뉴</text>{lines}{nodes}</svg>
<details><summary>표로 보기</summary><table><tr><td><b>재료</b></td><td><b>메뉴</b></td><td><b>비율</b></td></tr>{rows}</table></details>
<script>
const L=[...document.querySelectorAll('line')],G=[...document.querySelectorAll('.ing,.menu')];
function hi(key,val){{const on=new Set();L.forEach(l=>{{const h=l.dataset[key]===val;l.classList.toggle('on',h);l.classList.toggle('dim',!h);if(h){{on.add('i:'+l.dataset.i);on.add('m:'+l.dataset.m)}}}});
G.forEach(g=>g.classList.toggle('dim',!on.has(g.dataset.i!==undefined?'i:'+g.dataset.i:'m:'+g.dataset.m)))}}
function off(){{L.forEach(l=>l.classList.remove('on','dim'));G.forEach(g=>g.classList.remove('dim'))}}
G.forEach(g=>{{g.addEventListener('mouseenter',()=>g.dataset.i!==undefined?hi('i',g.dataset.i):hi('m',g.dataset.m));g.addEventListener('mouseleave',off)}});
</script></body></html>'''
    open(os.path.join(OUT, '7_네트워크.html'), 'w', encoding='utf-8').write(page); print('  ✔ 7_네트워크.html')

# ───────────── 8. 수량 표기 신뢰도 ─────────────
def chart8():
    a = q("SELECT amount_class AS c, count(*) AS n FROM omm_recipe_ingredients GROUP BY 1")
    if a.empty: return empty('8_신뢰도.png', 8, '수량 표기 신뢰도', '레시피 재료 데이터 없음')
    lab = {'AMOUNT_MEASURED': '정량 (g · T · 컵)', 'AMOUNT_COUNTED': '개수 (개 · 모 · 대)', 'AMOUNT_VAGUE': '모호 (약간 · 넉넉히)', 'AMOUNT_MISSING': '수량 없음'}
    col = {'AMOUNT_MEASURED': S[0], 'AMOUNT_COUNTED': S[2], 'AMOUNT_VAGUE': S[1], 'AMOUNT_MISSING': MUTED}
    a = a.set_index('c').reindex(list(lab)).fillna(0)
    g = q("""SELECT rm.reliability_grade AS g, count(*) AS n, avg(r.avg_rating) AS r, percentile_cont(0.5) WITHIN GROUP (ORDER BY r.view_count) AS v
             FROM omm_recipe_metrics rm JOIN omm_recipes r USING (recipe_id) WHERE rm.reliability_grade IS NOT NULL GROUP BY 1 ORDER BY 1""")
    v = q("SELECT unit AS u, count(*) AS n FROM omm_recipe_ingredients WHERE amount_class = 'AMOUNT_VAGUE' AND unit IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 10")
    fig, axs = plt.subplots(1, 4, figsize=(19, 5.5), gridspec_kw={'width_ratios': [1.2, 1, 1, 1]})
    w, _ = axs[0].pie(a.n, colors=[col[c] for c in a.index], startangle=90, counterclock=False,
                      wedgeprops={'width': 0.38, 'edgecolor': SURF, 'linewidth': 2})
    tot = a.n.sum()
    axs[0].legend(w, [f'{lab[c]}  {n / tot * 100:.1f}%' for c, n in zip(a.index, a.n)], loc='upper center', bbox_to_anchor=(0.5, 0.02), ncol=2, fontsize=9)
    axs[0].text(0, 0, f'재료줄\n{tot:,.0f}', ha='center', va='center', color=INK, weight='bold'); axs[0].set_title('⑧ 재료 수량 표기 방식')
    gc = {'REL_A': S[0], 'REL_B': S[2], 'REL_C': S[3], 'REL_D': S[1]}
    g['lbl'] = g.g.str.replace('REL_', '', regex=False)     # 화면에는 A · B · C · D
    axs[1].bar(g.lbl, g.n, color=[gc[x] for x in g.g], width=0.6)
    for i, n in enumerate(g.n): axs[1].text(i, n, f'{n:,}', ha='center', va='bottom', color=INK2)
    axs[1].set_title('레시피 신뢰도 등급'); axs[1].grid(axis='x', visible=False)
    axs[2].bar(g.lbl, g.r, color=[gc[x] for x in g.g], width=0.6)
    for i, r in enumerate(g.r): axs[2].text(i, r, f'★{r:.2f}', ha='center', va='bottom', color=INK)
    axs[2].set_ylim(max(0, g.r.min() - 0.8) if len(g) else 0, 5.2); axs[2].set_title('등급별 평균 별점'); axs[2].grid(axis='x', visible=False)
    vv = v[::-1]
    axs[3].barh(vv.u, vv.n, color=S[1], height=0.6)
    for y, n in enumerate(vv.n): axs[3].text(n, y, f'  {n:,}', va='center', color=INK2, fontsize=9)
    axs[3].set_title('자주 쓰는 모호한 표현'); axs[3].grid(axis='y', visible=False)
    note(axs[1], '등급 = 정량 · 개수로 적은 재료 비율 · A ≥ 90% · B ≥ 70% · C ≥ 50% · D < 50%')
    save(fig, '8_신뢰도.png', 8, '수량 표기 신뢰도', '"약간 · 넉넉히"처럼 대충 적은 레시피 비율과 별점')

def index():
    cards = ''.join(f'<section><h2>{no}. {html.escape(t)}</h2><p>{html.escape(n)}</p><img src="{f}" alt="{html.escape(t)}">'
                    + ('<p><a href="7_네트워크.html">마우스로 보는 네트워크 열기 →</a></p>' if f == '7_네트워크.png' else '') + '</section>'
                    for f, no, t, n in made)
    open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(
        f'''<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>OMM 분석 차트</title><style>
body{{margin:0;padding:32px;background:#f5f4ef;font-family:"Malgun Gothic","Apple SD Gothic Neo",sans-serif;color:#0b0b0b}}
section{{background:#fcfcfb;border:1px solid #e6e5e0;border-radius:12px;padding:20px;margin:0 0 24px;max-width:1300px}}
h1{{margin:0 0 20px}} h2{{margin:0 0 4px;font-size:18px}} p{{margin:0 0 12px;color:#52514e}} img{{max-width:100%}}</style></head>
<body><h1>OMM 분석 차트 (분석 1~8)</h1>{cards}</body></html>''')
    print(f'\n차트 {len(made)}개 → {os.path.join(OUT, "index.html")} 을 브라우저로 여세요')

if __name__ == '__main__':
    for fn in (chart1, chart2, chart3, chart4, chart5, chart6, chart7, chart8):
        try: fn()
        except Exception as ex: print(f'  ✘ {fn.__name__}: {ex}')
    index()
