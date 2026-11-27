"""합칠 후보 찾기 (읽기만 함)
  python find_merge_candidates.py              # 이름 끝이 다른 재료 이름인 것 → logs/merge_candidates_날짜.csv
  python find_merge_candidates.py 호박 새우    # 그 글자가 들어간 재료 · 별칭 전부 보기

후보 CSV 를 열어 '같은 재료로 볼 것'만 남기고 from,to,memo 세 칸을 omm_dict/merge_pairs.csv 에 붙여 넣기.
예: 늙은호박 → 호박 (같음, 남김)  /  애호박 → 호박 (다름, 지움)  /  건새우 → 새우 (가격 · 쓰임이 달라서 지움)
"""
import csv, os, sys, datetime
import psycopg2

conn = psycopg2.connect(''); cur = conn.cursor()
cur.execute('SELECT ingredient_id, name, recipe_count, is_seasoning FROM omm_ingredients')
ing = {n: (i, c, s) for i, n, c, s in cur.fetchall()}
cur.execute('SELECT alias, ingredient_id, is_active FROM omm_ingredient_aliases')
aliases = cur.fetchall()
id2name = {i: n for n, (i, c, s) in ing.items()}

words = [w for w in sys.argv[1:] if not w.startswith('-')]
if words:
    for w in words:
        print(f'\n[{w}] 이름에 들어간 재료')
        for n, (i, c, s) in sorted(ing.items(), key=lambda x: -x[1][1]):
            if w in n:
                al = sorted(a for a, j, on in aliases if j == i and on and a != n)
                print(f'  {n} (id {i}, 레시피 {c}{", 양념" if s else ""}) 별칭 {len(al)}개: {al[:10]}')
        print(f'[{w}] 별칭에 들어간 것 (별칭 → 재료)')
        print('  ', sorted(f'{a}→{id2name.get(j)}{"" if on else "(꺼짐)"}' for a, j, on in aliases if w in a)[:40])
    sys.exit()

# 이름 끝이 다른 재료 이름 (늙은호박 → 호박, 흰다리새우 → 새우). 기준 재료는 레시피 10개 이상 · 2글자 이상 · 양념 아님
bases = sorted((n for n, (i, c, s) in ing.items() if c >= 10 and len(n) >= 2 and not s), key=len, reverse=True)
rows = []
for n, (i, c, s) in ing.items():
    if c < 1 or s: continue
    b = next((b for b in bases if n != b and n.endswith(b) and len(n) > len(b)), None)
    if b: rows.append([n, b, c, ing[b][1], ''])
rows.sort(key=lambda r: -r[2])

os.makedirs('logs', exist_ok=True)
out = f"logs/merge_candidates_{datetime.datetime.now():%Y%m%d_%H%M}.csv"
with open(out, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f); w.writerow(['from', 'to', 'from_recipes', 'to_recipes', 'memo']); w.writerows(rows)
print(f'후보 {len(rows)}개 → {out}  (레시피 많은 순, 위 60개)')
for r in rows[:60]: print(f'  {r[0]} ({r[2]}) → {r[1]} ({r[3]})')