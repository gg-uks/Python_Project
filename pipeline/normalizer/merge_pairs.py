"""손으로 정한 재료 합치기 — omm_dict/merge_pairs.csv (from,to,memo)
  python merge_pairs.py            # 시험: 무엇이 어디로 합쳐지는지만 출력 (아무것도 안 바꿈)
  python merge_pairs.py --apply    # 별칭 추가 · 옮기기 · raw_std 교체 (그다음 daily.sh)
  python merge_pairs.py --cleanup  # daily.sh 뒤에: 레시피에서 안 쓰게 된 from 재료 행 삭제

merge_junk.py 는 '지저분한 이름'을 자동으로 합치고, 이건 '같은 재료로 보기로 정한 것'(대하 = 새우, 늙은호박 = 호박)을 합침.
merge_pairs.csv 는 지우지 말고 계속 쌓아 둠 (나중에 정제를 처음부터 다시 해도 같은 결정이 남도록).
합치면 from 은 to 의 별칭이 됨 → '새우'를 빼면 대하 레시피도 빠지고, '대하'로 검색해도 새우로 찾음.
"""
import csv, os, sys, glob, shutil, datetime
import psycopg2

PAIRS = 'omm_dict/merge_pairs.csv'
RAW_STD = 'omm_dict/raw_std.csv'
UNIT_G = 'omm_dict/unit_grams.csv'
KAMIS_MAP = 'omm_dict/kamis_item_map.csv'
CHAM = 'omm_dict/cham_targets.csv'
NOW = datetime.datetime.now().strftime('%Y%m%d_%H%M')
conn = psycopg2.connect(''); cur = conn.cursor()


def q(sql, *a):
    cur.execute(sql, a); return cur.fetchall()


def read(path):
    return list(csv.DictReader(open(path, encoding='utf-8-sig', newline='')))


if '--cleanup' in sys.argv:
    files = sorted(glob.glob('logs/merge_pairs_*.csv'))
    if not files: sys.exit('합친 기록(logs/merge_pairs_*.csv)이 없어요')
    junk = [int(r['from_id']) for r in read(files[-1]) if r['from_id']]
    refs = ['omm_recipe_ingredients', 'omm_ingredient_aliases', 'omm_unit_conversions', 'omm_kamis_items', 'omm_price_monthly',
            'omm_trend_keywords', 'omm_fs_recipe_ingredients', 'omm_price_interest_corr', 'omm_ingredient_network_nodes']
    cond = ' AND '.join(f'NOT EXISTS (SELECT 1 FROM {t} x WHERE x.ingredient_id = i.ingredient_id)' for t in refs)
    dead = [r[0] for r in q(f"""SELECT i.ingredient_id FROM omm_ingredients i WHERE i.ingredient_id = ANY(%s::int[]) AND {cond}
              AND NOT EXISTS (SELECT 1 FROM omm_ingredient_network_edges x WHERE i.ingredient_id IN (x.ingredient_a, x.ingredient_b))
              AND NOT EXISTS (SELECT 1 FROM omm_ingredient_substitutes x WHERE i.ingredient_id IN (x.ingredient_id, x.substitute_id))""", junk)]
    cur.execute('DELETE FROM omm_ingredient_interest_monthly WHERE ingredient_id = ANY(%s)', (dead,))
    cur.execute('DELETE FROM omm_ingredients WHERE ingredient_id = ANY(%s)', (dead,))
    conn.commit()
    print(f'합친 재료 {len(junk)}개 중 {len(dead)}개 삭제 (나머지는 아직 어딘가에서 쓰여서 남김: {sorted(set(junk) - set(dead))})')
    print('다음: python sync_mongo_dict.py --apply   (몽고 · ES에서도 지움. 안 하면 다음 20:30에 반영)')
    sys.exit()

ing = {n: (i, c) for i, n, c in q('SELECT ingredient_id, name, recipe_count FROM omm_ingredients')}
id2name = {i: n for n, (i, c) in ing.items()}
alias = dict(q('SELECT alias, ingredient_id FROM omm_ingredient_aliases WHERE is_active'))

pairs, bad = [], []
for r in read(PAIRS):
    f, t = (r.get('from') or '').strip(), (r.get('to') or '').strip()
    if not f or not t or f == t: continue
    if t not in ing: bad.append(f'{f} → {t}: to 재료가 PG에 없음'); continue
    if f in ing and ing[f][0] == ing[t][0]: continue
    pairs.append((f, t))
froms = {f for f, _ in pairs}
for f, t in pairs:
    if t in froms: bad.append(f'{f} → {t}: {t} 도 다른 곳으로 합쳐짐 (to를 최종 재료로 적어 주세요)')
if bad:
    print('merge_pairs.csv 확인 필요:'); [print('  ', b) for b in bad]; sys.exit(1)

m = dict(pairs)

# ── 사전 파일도 같이 맞춤 (from 이름이 남아 있으면 load_team 이 '가격 있는 재료'로 from 재료 행을 다시 만듦) ──
# unit_grams: from 에만 있는 단위는 to 로 옮겨 붙임 (새우살 컵 200g → 새우 컵), 같은 단위는 to 값을 씀(차이는 출력)
ug_rows = read(UNIT_G)
ug = {}
for r in ug_rows: ug.setdefault(r['std_name'], {})[r['unit']] = r['g_per_unit']
ug_add, ug_diff = [], []
for f, t in pairs:
    for u, g in (ug.get(f) or {}).items():
        tg = (ug.get(t) or {}).get(u)
        if tg is None:
            if (t, u) not in {(a, b) for a, b, _ in ug_add}: ug_add.append((t, u, g))
        elif float(tg) != float(g):
            ug_diff.append(f'{f} {u} {float(g):g}g → {t} {u} {float(tg):g}g')
# kamis_item_map: to 줄이 있으면 from 줄 삭제, 없으면 from → to 로 이름만 바꿈
km_rows = read(KAMIS_MAP)
km_has = {r['ingredient'] for r in km_rows}
km_del = [r['ingredient'] for r in km_rows if r['ingredient'] in m and m[r['ingredient']] in km_has]
km_ren = [r['ingredient'] for r in km_rows if r['ingredient'] in m and m[r['ingredient']] not in km_has]
# cham_targets: 이름은 to 로, 찾는 말(keyword)이 비어 있으면 from 으로 (상품 이름에서 계속 찾게)
ch_rows = read(CHAM)
ch_ren = [r['ingredient'] for r in ch_rows if r['ingredient'] in m]

print(f'합칠 것 {len(pairs)}개')
for f, t in pairs:
    fi = ing.get(f)
    moved = [a for a, i in alias.items() if fi and i == fi[0]]
    print(f'  {f} ({fi[1] if fi else "재료 없음 · 별칭만"} 레시피) → {t} ({ing[t][1]} 레시피)'
          + (f' | 같이 옮길 별칭 {len(moved)}개: {moved[:8]}' if moved else '')
          + (f' | 지금 별칭 {f} → {id2name.get(alias[f])}' if f in alias and not fi else ''))
print(f'\n[unit_grams] to 에 없는 단위 {len(ug_add)}줄 추가:', [f'{t} {u} {float(g):g}g' for t, u, g in ug_add])
print(f'[unit_grams] 같은 단위인데 값이 달라 to 값을 쓰게 되는 것 {len(ug_diff)}개:')
for d in ug_diff: print('   ', d)
print(f'[kamis_item_map] from 줄 삭제 {len(km_del)}개(to 줄이 이미 있음): {km_del}')
print(f'[kamis_item_map] from → to 이름 바꿈 {len(km_ren)}개: {km_ren}')
print(f'[cham_targets] from → to 이름 바꿈 {len(ch_ren)}개: {ch_ren}')

if '--apply' not in sys.argv:
    print('\n시험 실행이라 아무것도 안 바꿨어요. 반영: python merge_pairs.py --apply'); sys.exit()

for f, t in pairs:
    tid = ing[t][0]
    for a in {f, f.replace(' ', '')}:
        cur.execute("""INSERT INTO omm_ingredient_aliases (alias, ingredient_id, source) VALUES (%s, %s, 'SRC_MANUAL')
                       ON CONFLICT (alias) DO UPDATE SET ingredient_id = EXCLUDED.ingredient_id, is_active = true, updated_at = now()""", (a, tid))
    if f in ing:
        cur.execute('UPDATE omm_ingredient_aliases SET ingredient_id = %s, updated_at = now() WHERE ingredient_id = %s', (tid, ing[f][0]))
conn.commit()

os.makedirs('backups/20261125/omm_dict', exist_ok=True)
for p in (RAW_STD, UNIT_G, KAMIS_MAP, CHAM):
    shutil.copy(p, f'backups/20261125/omm_dict/{os.path.basename(p)}.bak_{NOW}')


def write(path, header, rows):                                # 원래 파일처럼 BOM 없음 · CRLF
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=header, lineterminator='\r\n'); w.writeheader(); w.writerows(rows)


rows = list(csv.reader(open(RAW_STD, encoding='utf-8-sig', newline='')))
changed = 0
for r in rows[1:]:
    if len(r) >= 2 and r[1] in m: r[1] = m[r[1]]; changed += 1
csv.writer(open(RAW_STD, 'w', encoding='utf-8', newline=''), lineterminator='\r\n').writerows(rows)

hdr = list(ug_rows[0].keys())
write(UNIT_G, hdr, [r for r in ug_rows if r['std_name'] not in m]
      + [dict(zip(hdr, (t, u, g))) for t, u, g in ug_add])
out = []
for r in km_rows:
    if r['ingredient'] in km_del: continue
    if r['ingredient'] in m:
        r = dict(r, ingredient=m[r['ingredient']], memo=f"{r['memo']} (merge_pairs: {r['ingredient']}→{m[r['ingredient']]})")
    out.append(r)
write(KAMIS_MAP, list(km_rows[0].keys()), out)
out = []
for r in ch_rows:
    if r['ingredient'] in m:
        r = dict(r, keyword=(r.get('keyword') or r['ingredient']), ingredient=m[r['ingredient']])
    out.append(r)
write(CHAM, list(ch_rows[0].keys()), out)

os.makedirs('logs', exist_ok=True)
with open(f'logs/merge_pairs_{NOW}.csv', 'w', encoding='utf-8', newline='') as fh:
    w = csv.writer(fh); w.writerow(['from_id', 'from', 'to_id', 'to', 'recipes'])
    w.writerows([ing[f][0] if f in ing else '', f, ing[t][0], t, ing[f][1] if f in ing else 0] for f, t in pairs)
print(f'\n반영: 별칭 {len(pairs)}개 · raw_std {changed}줄 교체 · unit_grams +{len(ug_add)}줄 · kamis_item_map 삭제 {len(km_del)}·이름 {len(km_ren)} · '
      f'cham_targets {len(ch_ren)} · 백업 backups/20261125/omm_dict/*.bak_{NOW} · 기록 logs/merge_pairs_{NOW}.csv')
print('다음: nice -n 10 ./daily.sh  →  python merge_pairs.py --cleanup  →  python sync_mongo_dict.py --apply')