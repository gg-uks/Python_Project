"""PG(원본) → 몽고 OMM_ingredient_dictionary · OMM_menus 맞추기
  python sync_mongo_dict.py           # 시험: 바뀔 내용만 출력
  python sync_mongo_dict.py --apply   # 실제 반영
재료: PG에 없는 문서는 삭제. 메뉴: 삭제하지 않음(nutrition·core_ingredients·parent_menu 보존)
별칭: PG에는 원문 매칭용으로 양·메모가 붙은 표기도 있음 → 검색 사전(몽고·ES)에는 이름다운 것만 보냄
"""
import os, re, sys, datetime
from pymongo import MongoClient, UpdateOne, DeleteOne
try:
    import psycopg2 as pg
except ImportError:
    import psycopg as pg

APPLY = '--apply' in sys.argv
NOW = datetime.datetime.now(datetime.timezone.utc)
JUNK = re.compile(r'[0-9A-Za-z]|약$|반$|숟가락|숟갈|수저|스푼|큰술|작은술|듬뿍|듬쁙|가득|생략|선택|취향|기준|적당|조금|약간|정도|아빠|엄마|또는|/|\(|\)|다지기|갈기')
INV = re.compile(r'[\u200b-\u200f\ufeff]')
BLANK = re.compile(r'^[\s\u200b-\u200f\ufeff]*$')
cur = pg.connect('').cursor()


def q(sql):
    cur.execute(sql)
    return cur.fetchall()


def good_aliases(name, al):
    out = set()
    for x in al:
        x = INV.sub('', x).strip()                      # 보이지 않는 문자 제거
        if not x or x == name or JUNK.search(x):
            continue
        if x.count(name) >= 2:                          # 마늘다진마늘 · 다진마늘큐브마늘 같은 겹친 표기
            continue
        out.add(x)
    return sorted(out)

ING = q("""
SELECT i.ingredient_id, i.name, i.is_seasoning, i.recipe_count,
       coalesce(a.al, '{}'), coalesce(s.mats, '{}'), s.g
FROM omm_ingredients i
LEFT JOIN (SELECT ingredient_id, array_agg(alias ORDER BY alias) AS al
           FROM omm_ingredient_aliases WHERE is_active GROUP BY 1) a USING (ingredient_id)
LEFT JOIN (SELECT ri.ingredient_id,
                  array_agg(DISTINCT ri.material_no) FILTER (WHERE ri.material_no IS NOT NULL) AS mats,
                  round(avg(ri.grams / r.servings) FILTER (WHERE ri.grams > 0 AND r.servings > 0), 1) AS g
           FROM omm_recipe_ingredients ri JOIN omm_recipes r USING (recipe_id) GROUP BY 1) s USING (ingredient_id)
""")
MENU = q("""
SELECT m.name, m.dish_type, m.recipe_count, coalesce(m.match_keywords, '{}'), m.rep_recipe_id, r.title, coalesce(v.c, 0)
FROM omm_menus m
LEFT JOIN omm_recipes r ON r.recipe_id = m.rep_recipe_id
LEFT JOIN (SELECT x.menu_id, count(*) AS c FROM omm_reviews rv JOIN omm_recipes x USING (recipe_id) GROUP BY 1) v
       ON v.menu_id = m.menu_id
""")

db = MongoClient(os.environ['MONGO_URI'])[os.environ['MONGO_DB']]

# ── 재료 사전 ──
D = db.OMM_ingredient_dictionary
old = {d['_id']: d for d in D.find({}, {'aliases': 1, 'ingredient_id': 1})}
ops, pg_names, pg_al, skipped, alias_changed = [], set(), {}, [], 0
for iid, name, seas, cnt, al, mats, g in ING:
    if BLANK.match(name):
        skipped.append((iid, repr(name)))
        continue
    pg_names.add(name)
    al = good_aliases(name, al)
    pg_al[name] = al
    if name in old and sorted(old[name].get('aliases') or []) != al:
        alias_changed += 1
    ops.append(UpdateOne({'_id': name}, {
        '$set': {'std_name': name, 'ingredient_id': iid, 'aliases': al, 'recipes': cnt,
                 'is_seasoning': bool(seas), 'material_ids': sorted(mats),
                 'avg_grams_per_serving': float(g) if g is not None else None, 'loaded_at': NOW},
        '$setOnInsert': {'seasoning_share': None}}, upsert=True))
dels = sorted(k for k in old if k not in pg_names)
ops += [DeleteOne({'_id': k}) for k in dels]
new = sorted(n for n in pg_names if n not in old)

print(f'[재료] 몽고 {len(old):,} → PG {len(pg_names):,} | 갱신 {len(pg_names) - len(new):,} (별칭 바뀜 {alias_changed:,}) | 추가 {len(new):,} | 삭제 {len(dels):,}')
print('  빈 이름이라 건너뜀:', skipped)
print('  추가 예:', new[:10])
print('  삭제 예:', dels[:10])
for n in ('다진마늘', '마늘', '굴', '굴소스', '닭안심'):
    print(f'  {n}: {sorted((old.get(n) or {}).get("aliases") or [])[:8]} → {pg_al[n][:8] if n in pg_al else "없음"}')

# ── 메뉴 ──
M = db.OMM_menus
oldm = {d['_id']: d for d in M.find({}, {'rep_recipe_id': 1})}
ops2, pg_menus, rep_changed = [], set(), 0
for name, dt, cnt, kw, rep, title, rv in MENU:
    pg_menus.add(name)
    if name in oldm and oldm[name].get('rep_recipe_id') != rep:
        rep_changed += 1
    ops2.append(UpdateOne({'_id': name}, {
        '$set': {'menu': name, 'aliases': sorted({k for k in kw if k != name}), 'dish_type': dt, 'recipes': cnt,
                 'reviews': rv, 'rep_recipe_id': rep, 'rep_title': title, 'loaded_at': NOW},
        '$setOnInsert': {'parent_menu': name, 'core_ingredients': [], 'nutrition': None}}, upsert=True))
newm = sorted(n for n in pg_menus if n not in oldm)
only_m = sorted(n for n in oldm if n not in pg_menus)
print(f'[메뉴] 몽고 {len(oldm):,} → PG {len(pg_menus):,} | 추가 {len(newm):,} | 대표 레시피 바뀜 {rep_changed:,} | 몽고에만 있음 {len(only_m):,}(그대로 둠)')
print('  추가 예:', newm[:15])
print('  몽고에만:', only_m[:15])

if APPLY:
    r1 = D.bulk_write(ops, ordered=False)
    r2 = M.bulk_write(ops2, ordered=False)
    print('반영: 재료', r1.modified_count, '수정', r1.upserted_count, '추가', r1.deleted_count, '삭제',
          '| 메뉴', r2.modified_count, '수정', r2.upserted_count, '추가')
else:
    print('\n시험 실행이라 몽고는 그대로입니다. 반영하려면 --apply')