"""수집한 파일 → OMM v4 PostgreSQL 적재
  기본: 바뀐 것만 (새 행 추가 · 바뀐 행 수정 · 재료/메뉴 번호 유지) → 매일 자동 실행용
  --full: 수집 · 분석 테이블을 비우고 다시 넣기 (재료 · 메뉴 번호, 회원 · 주문 · 컬리 · 식약처 레시피는 유지)

  python load_v4.py --recipe-dir 만개폴더 --kamis-dir kamis_out --nutrition nutrition_foods.csv --youtube-dir 유튜브폴더
  · 폴더/파일은 있는 것만 주면 됨 (없는 출처는 비워 둠)
  · 접속: 환경변수 PGHOST · PGPORT · PGDATABASE · PGUSER · PGPASSWORD
  · 적재 후:  psql -f mart_build_v4.sql  →  python mart_python_v4.py

만개 폴더: recipe_info.csv · recipe_ingredients.csv (없으면 recipes.csv) · recipe_categories.csv · reviews.csv · recipe_tags.csv
KAMIS 폴더: kamis_items.csv · kamis_daily.csv            (kamis_monthly.py 결과)
유튜브 폴더: youtube_keywords.csv · youtube_videos.csv · youtube_video_keywords.csv   (collect_youtube.py 결과)
"""
import os, sys, csv, re, argparse, collections, datetime
import psycopg2
from psycopg2.extras import execute_values
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from norm_v4 import normalize, SEASONING, NOT_BUY, UNITS, PIECE_G, parse_amount, menu_of, servings_of, cook_min_of

NOW = datetime.datetime.now().isoformat(timespec='seconds')
MIN_ING = int(os.getenv('MIN_ING', '2'))     # 레시피 2개 이상에 나온 재료만 표준 재료로
MIN_MENU = int(os.getenv('MIN_MENU', '3'))   # 레시피 3개 이상 모인 요리 이름만 메뉴로
CATS = [(1, '채소'), (2, '과일'), (3, '곡류'), (4, '육류'), (5, '수산'), (6, '콩·두부'), (7, '유제품·계란'), (8, '가공식품'), (9, '양념'), (10, '기타')]
KAMIS_CAT = {'식량작물': 3, '채소류': 1, '특용작물': 1, '과일류': 2, '축산물': 4, '수산물': 5}
KAMIS_ALIAS = {'돼지': '돼지고기', '소': '소고기', '한우': '소고기', '닭': '닭고기', '호박': '애호박', '파': '대파', '계란': '계란', '달걀': '계란'}
TASTES = {'매운맛': ['매콤', '얼큰', '칼칼', '매운', '화끈', '알싸'], '단맛': ['달달', '달콤', '단짠'], '짠맛': ['짭짤', '짭조름'],
          '고소함': ['고소'], '담백함': ['담백', '깔끔'], '새콤함': ['새콤', '상큼'], '국물': ['시원', '진한', '뜨끈']}
LEVELS = {'아무나': 'DIFF_ANYONE', '초급': 'DIFF_BEGINNER', '중급': 'DIFF_INTERMEDIATE', '고급': 'DIFF_ADVANCED', '신의경지': 'DIFF_MASTER'}   # 공통코드
CAT_TYPES = {'종류별': 'CATTYPE_KIND', '상황별': 'CATTYPE_SITUATION', '재료별': 'CATTYPE_INGREDIENT', '방법별': 'CATTYPE_METHOD'}

def read(path):
    if not path or not os.path.exists(path): return []
    for enc in ('utf-8-sig', 'cp949'):
        try: return list(csv.DictReader(open(path, encoding=enc)))
        except UnicodeDecodeError: continue
    return []

def to_int(v):
    try: return int(float(str(v).replace(',', '').strip()))
    except (ValueError, TypeError): return None

def to_num(v):
    try: return float(str(v).replace(',', '').strip())
    except (ValueError, TypeError): return None

def guess_cat(name):
    if name in SEASONING: return 9
    for pat, c in ((r'고기|삼겹|목살|갈비|등심|안심|베이컨|차돌|닭|오리|우삼겹|다짐육|항정', 4),
                   (r'새우|오징어|문어|낙지|주꾸미|조개|바지락|홍합|굴$|전복|멸치|고등어|연어|참치|명태|동태|황태|북어|생선|게$|꽃게|미역|다시마|김$|어묵|맛살|크래미', 5),
                   (r'두부|콩$|콩나물|숙주|유부', 6), (r'계란|달걀|메추리알|우유|치즈|버터|요거트|생크림', 7),
                   (r'쌀|밀가루|부침가루|튀김가루|당면|국수|면$|떡$|떡국떡|빵|식빵|오트밀|감자전분', 3),
                   (r'햄|소시지|스팸|라면|만두|피자치즈|통조림|캔$', 8),
                   (r'사과|배$|딸기|바나나|레몬|귤|오렌지|키위|블루베리|포도|망고|복숭아|자몽', 2)):
        if re.search(pat, name): return c
    return 1 if re.search(r'[가-힣]', name) else 10

# --full 때 지우는 테이블 (수집 원본 + 분석 마트). 여기에 없는 테이블은 절대 건드리지 않음:
#   번호를 몽고 · 회원 데이터가 참조하는 재료 · 메뉴 · 취향 태그 · 맛 표현 · 분류 코드,
#   회원 · 주문 · 컬리 상품 · 식약처 레시피, 공통코드, 실행 기록
# omm_ingredient_aliases 는 사전 원본(관리자 수정 포함)이라 --full 에서도 지우지 않음
FULL_RESET = ['omm_nutrition_foods', 'omm_recipes', 'omm_recipe_categories', 'omm_recipe_ingredients',
              'omm_reviews', 'omm_recipe_tags', 'omm_kamis_items', 'omm_kamis_prices', 'omm_price_monthly', 'omm_trend_keywords',
              'omm_youtube_videos', 'omm_youtube_video_keywords', 'omm_unit_conversions', 'omm_menu_clusters', 'omm_recipe_metrics',
              'omm_recipe_tastes', 'omm_ingredient_interest_monthly', 'omm_menu_interest_monthly', 'omm_keyword_trend_monthly',
              'omm_price_interest_corr', 'omm_ingredient_network_nodes', 'omm_ingredient_network_edges', 'omm_menu_similarities',
              'omm_ingredient_substitutes', 'omm_menu_nutrition']

def full_reset(cur):
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    exist = {r[0] for r in cur.fetchall()}
    wipe = [t for t in FULL_RESET if t in exist]
    # 남기는 테이블이 지울 테이블을 가리키는 칸 (재료.nutr_food_cd, 메뉴.rep_recipe_id) → 먼저 비움
    cur.execute("""SELECT c.conrelid::regclass::text, a.attname, c.confrelid::regclass::text
                   FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
                   WHERE c.contype = 'f' AND c.confrelid::regclass::text = ANY(%s) AND NOT (c.conrelid::regclass::text = ANY(%s))""", (wipe, wipe))
    held = cur.fetchall()
    for tbl, col, _ in held:
        cur.execute(f'UPDATE {tbl} SET {col} = NULL WHERE {col} IS NOT NULL')
    later = sorted({ref for _, _, ref in held})            # 이 테이블들은 TRUNCATE 대신 DELETE (남는 테이블의 FK가 걸려 있어서)
    now = [t for t in wipe if t not in later]
    if now: cur.execute(f"TRUNCATE {', '.join(now)} RESTART IDENTITY")
    for t in later:
        cur.execute(f'DELETE FROM {t}')
    print(f'--full: {len(wipe)}개 테이블을 비웠어요. 재료 · 메뉴 번호와 회원 · 주문 · 컬리 · 식약처 레시피는 그대로예요.')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--recipe-dir'); ap.add_argument('--kamis-dir'); ap.add_argument('--nutrition'); ap.add_argument('--youtube-dir'); ap.add_argument('--full', action='store_true', help='전부 지우고 다시 넣기')
    a = ap.parse_args()
    if not any([a.recipe_dir, a.kamis_dir, a.nutrition, a.youtube_dir]): ap.print_help(); return
    conn = psycopg2.connect(host=os.getenv('PGHOST', 'localhost'), port=os.getenv('PGPORT', '5432'), dbname=os.getenv('PGDATABASE', 'omm_insight'),
                            user=os.getenv('PGUSER', 'postgres'), password=os.getenv('PGPASSWORD'))
    cur = conn.cursor()
    ins = lambda sql, rows: execute_values(cur, sql, rows, page_size=2000) if rows else None
    if a.full:
        full_reset(cur)
    cur.execute('SELECT count(*) FROM omm_common_codes')
    if cur.fetchone()[0] == 0:
        sys.exit('공통코드(omm_common_codes)가 비어 있어요. omm_schema_v4.sql 끝부분의 공통코드 INSERT 를 다시 실행하세요.')
    ins('INSERT INTO omm_ingredient_categories (category_id, name, sort_order) VALUES %s ON CONFLICT (category_id) DO NOTHING', [(i, n, i) for i, n in CATS])
    def idmap(sql):
        cur.execute(sql); return {r[0]: r[1] for r in cur.fetchall()}
    report = []

    # ───── 1. 영양성분 ─────
    foods = []
    for r in read(a.nutrition):
        if r.get('food_cd') and r.get('food_nm'):
            foods.append((r['food_cd'], r['food_nm'][:100], (r.get('food_group') or '')[:50] or None,
                          *[to_num(r.get(k)) for k in ('energy_kcal', 'protein_g', 'fat_g', 'carb_g', 'sugar_g', 'fiber_g', 'sodium_mg', 'calcium_mg', 'iron_mg')],
                          (r.get('data_date') or '')[:10] or None))
    foods = list({f[0]: f for f in foods}.values())
    ins('''INSERT INTO omm_nutrition_foods VALUES %s ON CONFLICT (food_cd) DO UPDATE SET food_nm = EXCLUDED.food_nm, food_group = EXCLUDED.food_group,
           energy_kcal = EXCLUDED.energy_kcal, protein_g = EXCLUDED.protein_g, fat_g = EXCLUDED.fat_g, carb_g = EXCLUDED.carb_g, sugar_g = EXCLUDED.sugar_g,
           fiber_g = EXCLUDED.fiber_g, sodium_mg = EXCLUDED.sodium_mg, calcium_mg = EXCLUDED.calcium_mg, iron_mg = EXCLUDED.iron_mg, data_date = EXCLUDED.data_date''', foods)
    report.append(f'영양성분 {len(foods):,}')

    # ───── 2. 만개의레시피 ─────
    rd = a.recipe_dir or ''
    info = read(os.path.join(rd, 'recipe_info.csv')); ings = read(os.path.join(rd, 'recipe_ingredients.csv'))
    if not info and os.path.exists(os.path.join(rd, 'recipes.csv')):          # 나누기 전 파일만 있을 때
        rows = read(os.path.join(rd, 'recipes.csv'))
        info = list({r['recipe_id']: r for r in rows}.values()); ings = [r for r in rows if r.get('ingredient_name')]
    info = {to_int(r['recipe_id']): r for r in info if to_int(r.get('recipe_id'))}
    cats = read(os.path.join(rd, 'recipe_categories.csv'))

    # 재료 정규화 → 표준 재료
    std_of, cnt = {}, collections.defaultdict(set)
    for r in ings:
        raw = (r.get('ingredient_name') or '').strip()
        if not raw: continue
        if raw not in std_of:
            n = normalize(raw)
            std_of[raw] = n if n and not NOT_BUY.search(n) else None
        if std_of[raw]: cnt[std_of[raw]].add(r['recipe_id'])
    names = sorted(n for n, s in cnt.items() if len(s) >= MIN_ING or n in SEASONING)
    # 이름 기준으로 번호 유지: 있던 재료는 그대로(개수만 갱신), 새 재료만 새 번호
    have = idmap('SELECT name, ingredient_id FROM omm_ingredients')
    ins('INSERT INTO omm_ingredients (name, category_id, is_seasoning, grams_per_unit, recipe_count) VALUES %s',
        [(n[:50], guess_cat(n), n in SEASONING, PIECE_G.get(n), len(cnt[n])) for n in names if n[:50] not in have])
    upd = [(have[n[:50]], len(cnt[n]), n in SEASONING) for n in names if n[:50] in have]
    if upd: execute_values(cur, 'UPDATE omm_ingredients i SET recipe_count = v.c, is_seasoning = v.s FROM (VALUES %s) v(id, c, s) WHERE i.ingredient_id = v.id', upd)
    ing_id = idmap('SELECT name, ingredient_id FROM omm_ingredients')
    aliases = {re.sub(r'\s+', '', raw)[:100]: ing_id[s] for raw, s in std_of.items() if s in ing_id}
    for n, i in ing_id.items(): aliases.setdefault(n, i)
    ins('INSERT INTO omm_ingredient_aliases (alias, ingredient_id, source) VALUES %s ON CONFLICT (alias) DO NOTHING',
        [(k, v, 'SRC_MANGAE') for k, v in aliases.items() if k])

    # 분류 코드 · 레시피 분류
    code_id, rc = {}, set()
    for r in cats:
        t, v = (r.get('category_type') or '').strip(), (r.get('category_value') or '').strip()
        rid = to_int(r.get('recipe_id'))
        if t not in CAT_TYPES or not v or rid not in info: continue
        t = CAT_TYPES[t]                                     # 종류별 → CATTYPE_KIND (공통코드)
        k = (t, (r.get('category_code') or v).strip()[:10])
        code_id.setdefault(k, v[:30]); rc.add((rid, k))
    ins('INSERT INTO omm_recipe_category_codes (cat_type, code, name) VALUES %s ON CONFLICT (cat_type, code) DO UPDATE SET name = EXCLUDED.name',
        [(t, c, n) for (t, c), n in code_id.items()])
    cur.execute('SELECT cat_type, code, category_id, name FROM omm_recipe_category_codes')
    code_id = {(t, c): (i, n) for t, c, i, n in cur.fetchall()}
    rc = {(rid, code_id[k][0]) for rid, k in rc}

    # 메뉴 (제목 끝 요리 이름) · 요리 종류 = 그 메뉴 레시피들의 가장 흔한 종류별 분류
    kind_of = collections.defaultdict(collections.Counter)
    id2name = {i: (t, n) for (t, c), (i, n) in code_id.items()}
    for rid, cid in rc:
        if id2name[cid][0] == 'CATTYPE_KIND': kind_of[rid][id2name[cid][1]] += 1
    menu_name = {rid: menu_of(r.get('title')) for rid, r in info.items()}
    mcount = collections.Counter(m for m in menu_name.values() if m)
    omm_menus = sorted(m for m, c in mcount.items() if c >= MIN_MENU)
    dish = {m: collections.Counter() for m in omm_menus}
    for rid, m in menu_name.items():
        if m in dish: dish[m].update(kind_of[rid])
    have = idmap('SELECT name, menu_id FROM omm_menus')
    mrows = [(m[:50], (dish[m].most_common(1)[0][0] if dish[m] else '기타')[:20], [m]) for m in omm_menus]
    ins('INSERT INTO omm_menus (name, dish_type, match_keywords) VALUES %s', [r for r in mrows if r[0] not in have])
    upd = [(have[r[0]], r[1]) for r in mrows if r[0] in have]
    if upd: execute_values(cur, 'UPDATE omm_menus m SET dish_type = v.d FROM (VALUES %s) v(id, d) WHERE m.menu_id = v.id', upd)
    menu_id = idmap('SELECT name, menu_id FROM omm_menus')      # 예전에 만든 메뉴도 포함 (번호 유지)

    rec = []
    for rid, r in info.items():
        lv = (r.get('level') or '').strip()
        reg = (r.get('reg_date') or '')[:10]
        rating = to_num(r.get('avg_stars'))
        rec.append((rid, menu_id.get(menu_name[rid]), (r.get('title') or '')[:200] or f'레시피 {rid}', r.get('intro') or None,
                    (r.get('image_url') or '')[:500] or None, reg if re.match(r'\d{4}-\d{2}-\d{2}$', reg) else None,
                    servings_of(r.get('servings')), cook_min_of(r.get('cook_time')), LEVELS.get(lv),
                    to_int(r.get('views')), rating if rating is not None and 0 <= rating <= 5 else None,
                    to_int(r.get('review_count')) or 0, r.get('crawled_at') or None))
    ins('INSERT INTO omm_recipes (recipe_id, menu_id, title, intro, image_url, registered_at, servings, cook_time_min, difficulty, '
        'view_count, avg_rating, review_count, collected_at) VALUES %s ON CONFLICT (recipe_id) DO UPDATE SET '
        'menu_id = EXCLUDED.menu_id, title = EXCLUDED.title, intro = EXCLUDED.intro, image_url = EXCLUDED.image_url, '
        'registered_at = EXCLUDED.registered_at, servings = EXCLUDED.servings, cook_time_min = EXCLUDED.cook_time_min, '
        'difficulty = EXCLUDED.difficulty, view_count = EXCLUDED.view_count, avg_rating = EXCLUDED.avg_rating, '
        'review_count = EXCLUDED.review_count, collected_at = EXCLUDED.collected_at', [x[:12] + (x[12] or NOW,) for x in rec])
    ins('INSERT INTO omm_recipe_categories VALUES %s ON CONFLICT DO NOTHING', sorted(rc))

    # 레시피 재료 (원문 + 표준 재료 + 수량 파싱)
    lines, seq = [], collections.Counter()
    for r in ings:
        rid = to_int(r.get('recipe_id')); raw = (r.get('ingredient_name') or '').strip()
        if rid not in info or not raw: continue
        seq[rid] += 1
        std = std_of.get(raw); iid = ing_id.get(std)
        qty, unit, grams, cls = parse_amount(r.get('ingredient_qty'), std)
        lines.append((rid, seq[rid], (r.get('group_name') or '')[:30] or None, raw[:100], (r.get('ingredient_qty') or '')[:50] or None,
                      to_int(r.get('material_no')), iid, qty, (unit or '')[:20] or None, grams, 'AMOUNT_' + cls))
    if info: cur.execute('DELETE FROM omm_recipe_ingredients WHERE recipe_id = ANY(%s)', (list(info),))   # 파일에 있는 레시피만 새로 씀
    ins('INSERT INTO omm_recipe_ingredients VALUES %s', lines)

    # 후기 · 태그
    revs = {}
    for r in read(os.path.join(rd, 'reviews.csv')):
        vid, rid = to_int(r.get('review_id')), to_int(r.get('recipe_id'))
        at = (r.get('written_at') or '')[:10]
        if not vid or rid not in info or not re.match(r'\d{4}-\d{2}-\d{2}$', at): continue
        st = to_int(r.get('stars'))
        revs[vid] = (vid, rid, at, st if st and 1 <= st <= 5 else None, r.get('text') or None)
    ins('INSERT INTO omm_reviews VALUES %s ON CONFLICT (review_id) DO UPDATE SET rating = EXCLUDED.rating, body = EXCLUDED.body', list(revs.values()))
    tags = {(to_int(r.get('recipe_id')), (r.get('tag') or '').strip()[:50]) for r in read(os.path.join(rd, 'recipe_tags.csv'))}
    ins('INSERT INTO omm_recipe_tags VALUES %s ON CONFLICT DO NOTHING', [t for t in tags if t[0] in info and t[1]])
    report.append(f'레시피 {len(rec):,} · 재료줄 {len(lines):,} · 표준재료 {len(names):,} · 메뉴 {len(omm_menus):,} · 후기 {len(revs):,}')

    # ───── 3. KAMIS ─────
    kd = a.kamis_dir or ''
    items = read(os.path.join(kd, 'kamis_items.csv')); daily = read(os.path.join(kd, 'kamis_daily.csv'))
    # 품종마다 가장 흔한 (등급, 단위)만 씀 (등급 · 단위가 섞이면 월평균이 튐)
    combo = collections.defaultdict(collections.Counter)
    for d in daily: combo[(d['item_cd'], d['vrty_cd'])][(d.get('grd_cd') or '', d.get('unit') or '')] += 1
    best = {k: c.most_common(1)[0][0] for k, c in combo.items()}

    def find_ing(it):
        for n in (it.get('vrty_nm'), it.get('item_nm'), KAMIS_ALIAS.get(it.get('vrty_nm') or ''), KAMIS_ALIAS.get(it.get('item_nm') or '')):
            for c in (n, normalize(n or '') if n else None, re.sub(r'\s+', '', n or '')):
                if c and c in ing_id: return ing_id[c]
                if c and c in aliases: return aliases[c]
        return None
    kitems, by_ing = [], collections.defaultdict(list)
    for it in items:
        k = (it['item_cd'], it['vrty_cd'])
        unit_s = best.get(k, ('', ''))[1]
        m = re.match(r'^\s*([\d.]+)?\s*(.*)$', unit_s); sz = to_num(m.group(1)) if m and m.group(1) else 1.0; u = (m.group(2) if m else '').strip()
        iid = find_ing(it)
        name = next((n for n, i in ing_id.items() if i == iid), None)
        gpu = sz * 1000 if u.lower() == 'kg' else sz if u.lower() == 'g' else (sz * PIECE_G[name] if name in PIECE_G else None)
        kitems.append([it['item_cd'], it['vrty_cd'], (it.get('ctgry_nm') or '-')[:20], (it.get('item_nm') or '-')[:30], (it.get('vrty_nm') or '')[:30] or None,
                       u[:10] or None, sz, gpu, iid, False])
        if iid: by_ing[iid].append((it.get('vrty_nm') == name, combo[k].total(), len(kitems) - 1))
        if iid and it.get('ctgry_nm') in KAMIS_CAT:
            cur.execute('UPDATE omm_ingredients SET category_id = %s WHERE ingredient_id = %s AND NOT is_seasoning', (KAMIS_CAT[it['ctgry_nm']], iid))
    for iid, cands in by_ing.items():
        kitems[max(cands)[2]][9] = True                        # 대표 품종 = 이름이 같은 품종 → 데이터 많은 품종
    kitems = list({(x[0], x[1]): tuple(x) for x in kitems}.values())
    if kitems: cur.execute('UPDATE omm_kamis_items SET is_primary = false')     # 대표 품종을 새로 정하기 전에 초기화
    ins('''INSERT INTO omm_kamis_items VALUES %s ON CONFLICT (item_cd, vrty_cd) DO UPDATE SET ctgry_nm = EXCLUDED.ctgry_nm, item_nm = EXCLUDED.item_nm,
           vrty_nm = EXCLUDED.vrty_nm, unit = EXCLUDED.unit, unit_sz = EXCLUDED.unit_sz, grams_per_unit = EXCLUDED.grams_per_unit,
           ingredient_id = EXCLUDED.ingredient_id, is_primary = EXCLUDED.is_primary''', kitems)
    known = {(x[0], x[1]) for x in kitems}
    prices = {}
    for d in daily:
        k = (d['item_cd'], d['vrty_cd'])
        if k not in known or (d.get('grd_cd') or '', d.get('unit') or '') != best.get(k): continue
        p = to_int(d.get('avg_price'))
        if p and p > 0: prices[(d['date'], *k)] = (d['date'], *k, 'MARKET_RETAIL', d.get('grd_cd') or '', '전국', p)
    ins('INSERT INTO omm_kamis_prices (exmn_ymd, item_cd, vrty_cd, se_cd, grd_cd, mrkt_nm, price) VALUES %s '
        'ON CONFLICT (exmn_ymd, item_cd, vrty_cd, se_cd, grd_cd, mrkt_nm) DO UPDATE SET price = EXCLUDED.price', list(prices.values()))
    report.append(f'KAMIS 품종 {len(kitems):,} (재료 연결 {len(by_ing)}) · 일별 가격 {len(prices):,}')

    # 재료 ↔ 영양성분: "감자, 생것"처럼 첫 단어가 같은 식품 중 '생것' 우선
    if foods:
        by_first = collections.defaultdict(list)
        for f in foods:
            first = re.split(r'[,(]', f[1])[0].strip()
            for k in {first, normalize(first) or first}: by_first[k].append(f)   # 달걀 → 계란 (동의어)
        links = []
        for n, i in ing_id.items():
            c = by_first.get(n) or by_first.get(n.replace('고기', '')) or []
            if c:
                c.sort(key=lambda f: (0 if '생것' in f[1] else 1, len(f[1])))
                links.append((c[0][0], i))
        if links: execute_values(cur, 'UPDATE omm_ingredients i SET nutr_food_cd = v.cd FROM (VALUES %s) v(cd, id) WHERE i.ingredient_id = v.id', links)
        report.append(f'재료-영양 연결 {len(links)}')

    # ───── 4. YouTube ─────
    yd = a.youtube_dir or ''
    kws = read(os.path.join(yd, 'youtube_keywords.csv'))
    menu_by = {m.replace(' ', ''): i for m, i in menu_id.items()}
    kw_id = {}
    for r in kws:
        k = (r.get('keyword') or '').strip()
        if not k or k in kw_id: continue
        kind = (r.get('kind') or 'MENU').upper(); kind = 'KWKIND_' + (kind if kind in ('MENU', 'INGREDIENT', 'STYLE') else 'MENU')
        kw_id[k] = (kind, menu_by.get(k.replace(' ', '')), ing_id.get(k))
    ins('''INSERT INTO omm_trend_keywords (keyword, kind, menu_id, ingredient_id) VALUES %s ON CONFLICT (keyword) DO UPDATE SET
           kind = EXCLUDED.kind, menu_id = EXCLUDED.menu_id, ingredient_id = EXCLUDED.ingredient_id''', [(k, *v) for k, v in kw_id.items()])
    kw_id = {k: (i,) for k, i in idmap('SELECT keyword, keyword_id FROM omm_trend_keywords').items()}
    vids = {}
    for r in read(os.path.join(yd, 'youtube_videos.csv')):
        if r.get('video_id') and r.get('published_at'):
            vids[r['video_id']] = (r['video_id'], (r.get('title') or '')[:300], r['published_at'], r.get('channel_id') or None,
                                   to_int(r.get('view_count')), to_int(r.get('like_count')), to_int(r.get('comment_count')), r.get('collected_at') or NOW)
    ins('INSERT INTO omm_youtube_videos VALUES %s ON CONFLICT (video_id) DO UPDATE SET view_count = EXCLUDED.view_count, '
        'like_count = EXCLUDED.like_count, comment_count = EXCLUDED.comment_count, collected_at = EXCLUDED.collected_at', list(vids.values()))
    vk = {(r['video_id'], kw_id[r['keyword']][0]) for r in read(os.path.join(yd, 'youtube_video_keywords.csv'))
          if r.get('video_id') in vids and r.get('keyword') in kw_id}
    ins("INSERT INTO omm_youtube_video_keywords (video_id, keyword_id) VALUES %s ON CONFLICT DO NOTHING", sorted(vk))
    report.append(f'YouTube 키워드 {len(kw_id)} · 영상 {len(vids):,}')

    # ───── 5. 기본값: 단위 환산 · 맛 표현 · 취향 태그 ─────
    ins('INSERT INTO omm_unit_conversions (unit, grams, amount_class) VALUES %s ON CONFLICT ON CONSTRAINT cs_omm_unit_conversions_1 DO UPDATE SET grams = EXCLUDED.grams, amount_class = EXCLUDED.amount_class',
        [(u, g, 'AMOUNT_' + c) for u, (c, g) in UNITS.items()])
    ins('INSERT INTO omm_taste_words (word, taste_group) VALUES %s ON CONFLICT (word) DO UPDATE SET taste_group = EXCLUDED.taste_group', [(w, g) for g, ws in TASTES.items() for w in ws])
    tag = []
    cur.execute("SELECT taste_id FROM omm_taste_words WHERE word = '얼큰'"); tag.append(('얼큰한 국물', 'TAGKIND_WANT', 'RULE_TASTE', cur.fetchone()[0], 1))
    tag += [('고기', 'TAGKIND_WANT', 'RULE_INGREDIENT_CATEGORY', 4, 2), ('해산물', 'TAGKIND_EXCLUDE', 'RULE_INGREDIENT_CATEGORY', 5, 2)]
    if '오이' in ing_id: tag.append(('오이', 'TAGKIND_EXCLUDE', 'RULE_INGREDIENT', ing_id['오이'], 1))
    for (t, c), (i, n) in code_id.items():
        if t == 'CATTYPE_KIND' and re.search(r'면', n): tag.append(('면 요리', 'TAGKIND_WANT', 'RULE_RECIPE_CATEGORY', i, 4))
        if t == 'CATTYPE_SITUATION' and re.search(r'스피드|간단', n): tag.append(('간단한 한 그릇', 'TAGKIND_WANT', 'RULE_RECIPE_CATEGORY', i, 5))
    ins('INSERT INTO omm_filter_tags (label, kind, rule_type, rule_ref_id, sort_order) VALUES %s ON CONFLICT DO NOTHING', tag)

    report.insert(0, '전체 다시 넣기' if a.full else '바뀐 것만')
    cur.execute("INSERT INTO omm_etl_runs (source, job, finished_at, status, row_count, message) VALUES ('SRC_MART', 'load_v4', now(), 'ETL_OK', %s, %s)",
                (len(rec) + len(lines) + len(revs) + len(prices), ' | '.join(report)))
    conn.commit()
    print('적재 완료\n  ' + '\n  '.join(report))
    print('다음:  psql -U postgres -d omm_insight -f mart_build_v4.sql   →   python mart_python_v4.py')

if __name__ == '__main__':
    main()
