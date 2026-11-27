"""몽고 → ES 맞추기 (인덱스·매핑·분석기 그대로)
  python es_reload.py                  # 시험: 문서 수 · 안 보내는 필드만 출력
  python es_reload.py --apply          # 전체 반영
  python es_reload.py --apply recipes  # 이름에 recipes가 들어간 인덱스만
문서를 비우지 않고 덮어쓴 뒤, 몽고에 없는 문서만 지움 → 반영 중에도 검색이 비지 않음
매핑에 있는 필드만 보냄 → 지금 ES 문서 모양 유지
더해서 보내는 칸 (es_search_setup.py 로 매핑에 추가한 것만, PG 기준)
  메뉴 · 재료: chosung · jamo (이름 + 깨끗한 별칭의 초성 · 자모, 자동완성용), 메뉴 recipe_count
  레시피: menu (메뉴 이름) · ingredient_std (표준 재료명)  → 대하 · 손질새우로 적힌 레시피도 '새우'로 찾음
"""
import os, re, sys, json, urllib.request
from pymongo import MongoClient
from hangul import chosung, jamo

ES = os.environ.get('ES_URL', 'http://10.0.10.102:9200')
APPLY = '--apply' in sys.argv
ONLY = [a for a in sys.argv[1:] if not a.startswith('--')]
PAIRS = [('OMM_ingredient_dictionary', 'omm_ingredients'), ('OMM_menus', 'omm_menus'),
         ('OMM_mangae_recipes_raw', 'omm_recipes'), ('OMM_mangae_reviews_raw', 'omm_reviews')]
BATCH = 500


def es(method, path, body=None, nd=False):
    data = None
    if body is not None:
        data = (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)).encode('utf-8')
    req = urllib.request.Request(ES + path, data=data, method=method,
                                 headers={'Content-Type': 'application/x-ndjson' if nd else 'application/json'})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def jdump(x):
    return json.dumps(x, ensure_ascii=False, default=lambda o: o.isoformat() if hasattr(o, 'isoformat') else str(o))


def bulk(idx, lines):
    r = es('POST', f'/{idx}/_bulk', '\n'.join(lines) + '\n', nd=True)
    if r.get('errors'):
        err = next(list(x.values())[0]['error'] for x in r['items'] if 'error' in list(x.values())[0])
        print(f'  오류: {err}')
        sys.exit(1)


def es_ids(idx):
    ids = set()
    r = es('POST', f'/{idx}/_search?scroll=2m', {'size': 5000, '_source': False, 'query': {'match_all': {}}})
    while r['hits']['hits']:
        ids.update(h['_id'] for h in r['hits']['hits'])
        r = es('POST', '/_search/scroll', {'scroll': '2m', 'scroll_id': r['_scroll_id']})
    try:
        es('DELETE', '/_search/scroll', {'scroll_id': r['_scroll_id']})
    except Exception:
        pass
    return ids


db = MongoClient(os.environ['MONGO_URI'])[os.environ['MONGO_DB']]
CLEAN = re.compile(r'[가-힣A-Za-z]{1,15}')
_pg = None


def pg():
    """PG 에서 레시피 → (메뉴, 표준 재료명), 메뉴 → 레시피 수 (한 번만 읽음)"""
    global _pg
    if _pg is None:
        import psycopg2
        cur = psycopg2.connect('').cursor()
        cur.execute("""SELECT r.recipe_id, m.name, array_remove(array_agg(DISTINCT i.name), NULL)
                       FROM omm_recipes r LEFT JOIN omm_menus m USING (menu_id)
                       LEFT JOIN omm_recipe_ingredients ri USING (recipe_id) LEFT JOIN omm_ingredients i USING (ingredient_id)
                       GROUP BY 1, 2""")
        rec = {rid: (menu, ings) for rid, menu, ings in cur.fetchall()}
        cur.execute('SELECT name, recipe_count FROM omm_menus')
        _pg = (rec, dict(cur.fetchall()))
    return _pg


def enrich(idx, d, props):
    """매핑에 새 칸이 있을 때만 채움 (es_search_setup.py 전에는 아무것도 안 더함)"""
    if 'jamo' in props and idx in ('omm_menus', 'omm_ingredients'):
        main = d.get('menu') or d.get('std_name') or ''
        names = [main] + [a.replace(' ', '') for a in (d.get('aliases') or []) if isinstance(a, str)
                          and CLEAN.fullmatch(a.replace(' ', '')) and a.replace(' ', '') != main]
        d['chosung'] = list(dict.fromkeys(chosung(n) for n in names if n))
        d['jamo'] = list(dict.fromkeys(jamo(n) for n in names if n))
        if 'recipe_count' in props and idx == 'omm_menus':
            d['recipe_count'] = pg()[1].get(main)
    elif 'ingredient_std' in props and idx == 'omm_recipes':
        menu, ings = pg()[0].get(int(d.get('recipe_id') or 0), (None, []))
        d['menu'], d['ingredient_std'] = menu, ings
    return d


for col, idx in PAIRS:
    if ONLY and not any(o in idx for o in ONLY):
        continue
    props = set(es('GET', f'/{idx}/_mapping')[idx]['mappings'].get('properties', {}))
    print(f'[{idx}] ES {es("GET", f"/{idx}/_count")["count"]:,} → 몽고 {db[col].estimated_document_count():,}')
    if not APPLY:
        d = db[col].find_one() or {}
        print('  안 보내는 필드(매핑에 없음):', sorted(set(d) - props - {'_id'}))
        continue

    old = es_ids(idx)
    seen, lines = set(), []
    for d in db[col].find(batch_size=BATCH):
        _id = str(d.pop('_id'))
        seen.add(_id)
        d = enrich(idx, d, props)
        lines += [jdump({'index': {'_id': _id}}), jdump({k: v for k, v in d.items() if k in props})]
        if len(lines) >= BATCH * 2:
            bulk(idx, lines)
            lines = []
    if lines:
        bulk(idx, lines)
    stale = sorted(old - seen)
    for i in range(0, len(stale), 1000):
        bulk(idx, [jdump({'delete': {'_id': x}}) for x in stale[i:i + 1000]])
    es('POST', f'/{idx}/_refresh')
    print(f'  반영 후 문서 수: {es("GET", f"/{idx}/_count")["count"]:,} (덮어씀 {len(seen):,} · 지움 {len(stale):,})')

if not APPLY:
    print('\n시험 실행이라 ES는 그대로입니다. 반영하려면 --apply')