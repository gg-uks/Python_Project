"""지저분한 재료 이름을 기존 재료로 합치기 (주기 점검용)
  python merge_junk.py            # 시험: 합칠 목록만 출력
  python merge_junk.py --apply    # 별칭 추가 · raw_std 교체 (그다음 daily.sh 실행)
  python merge_junk.py --cleanup  # daily.sh 뒤에: 레시피에서 안 쓰게 된 합친 재료 행 삭제
규칙: 띄어쓰기 없앤 이름 → clean() → 마지막 단어 → 첫 단어 순으로, 깨끗한 기존 재료(또는 그 별칭)가 있으면 거기로
"""
import csv, os, re, sys, glob, shutil, datetime
import psycopg2
from clean_name import clean

MESSY = re.compile(r'[ 0-9A-Za-z()/+]|생략|선택|취향|조금|약간|적당|숟가락|큰술|작은술|가능|약$')
KEEP = {'LA갈비', '곤약', '실곤약'}              # 지저분해 보여도 진짜 재료
RAW_STD = 'omm_dict/raw_std.csv'
NOW = datetime.datetime.now().strftime('%Y%m%d_%H%M')
conn = psycopg2.connect(''); cur = conn.cursor()


def q(sql, *a):
    cur.execute(sql, a); return cur.fetchall()


if '--cleanup' in sys.argv:
    files = sorted(glob.glob('logs/merge_junk_*.csv'))
    if not files: sys.exit('합친 기록(logs/merge_junk_*.csv)이 없어요')
    junk = [r['junk_id'] for r in csv.DictReader(open(files[-1], encoding='utf-8'))]
    refs = ['omm_recipe_ingredients', 'omm_ingredient_aliases', 'omm_unit_conversions', 'omm_kamis_items', 'omm_price_monthly',
            'omm_trend_keywords', 'omm_fs_recipe_ingredients', 'omm_price_interest_corr', 'omm_ingredient_network_nodes']
    cond = ' AND '.join(f'NOT EXISTS (SELECT 1 FROM {t} x WHERE x.ingredient_id = i.ingredient_id)' for t in refs)
    dead = [r[0] for r in q(f"""SELECT i.ingredient_id FROM omm_ingredients i WHERE i.ingredient_id = ANY(%s::int[]) AND {cond}
              AND NOT EXISTS (SELECT 1 FROM omm_ingredient_network_edges x WHERE i.ingredient_id IN (x.ingredient_a, x.ingredient_b))
              AND NOT EXISTS (SELECT 1 FROM omm_ingredient_substitutes x WHERE i.ingredient_id IN (x.ingredient_id, x.substitute_id))""", junk)]
    cur.execute('DELETE FROM omm_ingredient_interest_monthly WHERE ingredient_id = ANY(%s)', (dead,))
    cur.execute('DELETE FROM omm_ingredients WHERE ingredient_id = ANY(%s)', (dead,))
    conn.commit()
    print(f'합친 재료 {len(junk)}개 중 {len(dead)}개 삭제 (나머지는 아직 어딘가에서 쓰여서 남김)')
    sys.exit()

ing = {n: (i, c) for i, n, c in q('SELECT ingredient_id, name, recipe_count FROM omm_ingredients')}
id2name = {i: n for n, (i, c) in ing.items()}
good = {n for n in ing if n in KEEP or not MESSY.search(n)}
alias = dict(q('SELECT alias, ingredient_id FROM omm_ingredient_aliases WHERE is_active'))


GENERIC_LAST = {'물'}                                          # 마지막 단어가 이거면 첫 단어부터 봄
MEMO_TAIL = re.compile(r'(생략가능|대체가능|가능|선택|조금|약간|듬뿍|정도|적당량|약)+$')


def strip_memo(n):
    s = n.replace(' ', '')
    s = re.split(r'또는|or|/', s)[0]                           # '또는' 뒤 버림
    s = re.sub(r'^\d+배', '', s)                               # 2배식초 → 식초
    s = re.sub(r'\d.*$', '', s)                                # 숫자부터 끝까지 버림 (갈비살약1kg → 갈비살약)
    return MEMO_TAIL.sub('', s)                                # 끝의 메모 버림 (갈비살약 → 갈비살)


def target(n):
    # 1) 이름 전체로: 띄어쓰기 없앤 것 · clean() · 메모 뗀 것 → 재료 이름이나 별칭
    for c in (n.replace(' ', ''), clean(n), strip_memo(n)):
        if not c or c == n: continue
        if c in good: return c
        t = id2name.get(alias.get(c))
        if t in good and t != n: return t
    # 2) 단어 하나로: 재료 이름과 정확히 같을 때만 (별칭은 안 거침 — '육수'→코인육수 같은 오연결 방지)
    parts = n.split()
    if len(parts) > 1:
        order = [parts[0], parts[-1]] if parts[-1] in GENERIC_LAST else [parts[-1], parts[0]]
        for c in order:
            if c in good and c != n: return c
    return None


pairs = sorted(((n, t) for n in ing if n not in good for t in [target(n)] if t), key=lambda p: -ing[p[0]][1])
left = sorted((n for n in ing if n not in good and not target(n)), key=lambda n: -ing[n][1])
print(f'합칠 것 {len(pairs)}개 (레시피 많은 순)')
for n, t in pairs[:60]: print(f'  {n} ({ing[n][1]}) → {t}')
print(f'\n대상을 못 찾아 그대로 둘 것 {len(left)}개:', [f'{n}({ing[n][1]})' for n in left[:30]])

if '--apply' not in sys.argv:
    print('\n시험 실행이라 아무것도 안 바꿨어요. 반영: python merge_junk.py --apply'); sys.exit()

for n, t in pairs:
    jid, tid = ing[n][0], ing[t][0]
    for a in {n, n.replace(' ', '')}:
        cur.execute("""INSERT INTO omm_ingredient_aliases (alias, ingredient_id, source) VALUES (%s, %s, 'SRC_MANUAL')
                       ON CONFLICT (alias) DO UPDATE SET ingredient_id = EXCLUDED.ingredient_id, is_active = true, updated_at = now()""", (a, tid))
    cur.execute('UPDATE omm_ingredient_aliases SET ingredient_id = %s, updated_at = now() WHERE ingredient_id = %s', (tid, jid))
conn.commit()

m = dict(pairs)
shutil.copy(RAW_STD, f'backups/20261124/bak/omm_dict/raw_std.csv.bak_{NOW}')
rows = list(csv.reader(open(RAW_STD, encoding='utf-8-sig', newline='')))
changed = 0
for r in rows[1:]:
    if len(r) >= 2 and r[1] in m: r[1] = m[r[1]]; changed += 1
csv.writer(open(RAW_STD, 'w', encoding='utf-8', newline='')).writerows(rows)

os.makedirs('logs', exist_ok=True)
with open(f'logs/merge_junk_{NOW}.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f); w.writerow(['junk_id', 'junk', 'target_id', 'target', 'recipes'])
    w.writerows([ing[n][0], n, ing[t][0], t, ing[n][1]] for n, t in pairs)
print(f'\n반영: 별칭 {len(pairs)}개 재료 연결 · raw_std {changed}줄 교체 · 기록 logs/merge_junk_{NOW}.csv')
print('다음: nice -n 10 ./daily.sh  →  python merge_junk.py --cleanup')