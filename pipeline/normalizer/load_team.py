"""팀 공유 데이터(omm_team_data_YYYYMMDD.zip을 푼 폴더) → OMM v4 PostgreSQL 적재

  python load_team.py --team-dir omm_team_data            (바뀐 것만, 재료 · 메뉴 번호 유지)
  python load_team.py --team-dir omm_team_data --full     (수집 · 분석 테이블을 비우고 다시. 번호 · 회원 · 주문은 유지)
  · 적재 후:  psql -f mart_build_v4.sql  →  python mart_python_v4.py  →  python charts_v4.py   (run_team.bat 이 한 번에)

팀 데이터를 그대로 따르는 것: 레시피 · 재료 표준명(std_name) · 1인분 g · 메뉴 사전(menu_seed) · 레시피 → 메뉴 ·
  월별 g당 가격(KAMIS 소매 → 참가격 → KAMIS 도매) · 메뉴 영양성분 · 유튜브 트렌드 영상
OMM 쪽에서 계산하는 것: 수량 표기 분류(정량/모호, 분석 8) · 재료 분류 · 요리 종류 · 마트(군집 · 네트워크 · 관심도 …)
"""
import os, sys, re, argparse, collections, datetime
import psycopg2
from psycopg2.extras import execute_values
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from load_v4 import read, to_int, to_num, guess_cat, full_reset, CATS, TASTES, LEVELS
from norm_v4 import UNITS, parse_amount

NOW = datetime.datetime.now().isoformat(timespec='seconds')
MIN_ING = int(os.getenv('MIN_ING', '2'))          # 레시피 2개 이상에 나온 재료만 표준 재료로 (나머지 재료 줄은 ingredient_id 비움)
PSRC = {'KAMIS 소매': 'PSRC_KAMIS_RETAIL', '참가격': 'PSRC_CHAMGAGYEOK', 'KAMIS 도매': 'PSRC_KAMIS_WHOLESALE'}

DISH_FIX = {'오이소박이': '김치', '가지말이': '반찬·메인', '감바스': '반찬·메인', '강정': '반찬·메인', '계란말이': '반찬·메인', '곤약말이': '반찬·메인', '깐풍기': '반찬·메인', '낙지말이': '반찬·메인', '냉채': '반찬·메인', '닭가슴살말이': '반찬·메인', '닭강정': '반찬·메인', '동그랑땡': '반찬·메인', '두루치기': '반찬·메인', '마파두부': '반찬·메인', '무생채': '반찬·메인', '밀푀유나베': '반찬·메인', '방아잎말이': '반찬·메인', '방울토마토소박이': '반찬·메인', '배추말이': '반찬·메인', '백김치말이': '반찬·메인', '베이컨말이': '반찬·메인', '비트절임': '반찬·메인', '삼겹살': '반찬·메인', '생선말이': '반찬·메인', '샤브샤브': '반찬·메인', '소고기말이': '반찬·메인', '실치절임': '반찬·메인', '양배추말이': '반찬·메인', '양파절임': '반찬·메인', '오이고추소박이': '반찬·메인', '오이절임': '반찬·메인', '유린기': '반찬·메인', '유부절임': '반찬·메인', '잡채': '반찬·메인', '족발': '반찬·메인', '짜글이': '반찬·메인', '찜닭': '반찬·메인', '치킨': '반찬·메인', '탕수': '반찬·메인', '토마토소박이': '반찬·메인', '프리타타': '반찬·메인', '함초말이': '반찬·메인', '오이탕탕이': '반찬·메인', '두부말이': '반찬·메인', '토마토절임': '반찬·메인', '묵은지말이': '반찬·메인', '닭꼬치': '반찬·메인', '치킨데리야끼': '반찬·메인', '치킨무': '반찬·메인', '무초절임': '반찬·메인', '단무지': '반찬·메인', '깻잎절임': '반찬·메인', '오징어말이': '반찬·메인', '어묵말이': '반찬·메인', '무쌈말이': '반찬·메인', '통닭': '반찬·메인', '과메기': '반찬·메인', '계란후라이': '반찬·메인', '게장': '반찬·메인', '당근라페': '반찬·메인', '라이스페이퍼말이': '반찬·메인', '야채찜': '반찬·메인', '숙주찜': '반찬·메인', '구운계란': '반찬·메인', '삶은계란': '반찬·메인', '계란장': '반찬·메인', '새우장': '반찬·메인', '강된장': '반찬·메인', '쌈장': '반찬·메인', '고추지': '반찬·메인', '콘치즈': '반찬·메인', '육회': '반찬·메인', '라따뚜이': '반찬·메인', 'LA갈비': '반찬·메인', '돼지갈비': '반찬·메인', '주물럭': '반찬·메인', '닭발': '반찬·메인', '순두부장': '반찬·메인', '에그인헬': '반찬·메인', '동파육': '반찬·메인', '칠리새우': '반찬·메인', '양장피': '반찬·메인', '문어숙회': '반찬·메인', '오징어숙회': '반찬·메인', '생선조림': '반찬·메인', '소고기소보로': '반찬·메인', '약고추장': '반찬·메인', '김부각': '반찬·메인', '연어장': '반찬·메인', '연어회': '반찬·메인', '미트볼': '반찬·메인', '차지키소스': '반찬·메인', '후무스': '반찬·메인', '규동': '밥·죽', '누룽지': '밥·죽', '약식': '밥·죽', '오야코동': '밥·죽', '카레': '밥·죽', '카레라이스': '밥·죽', '텐동': '밥·죽', '하이라이스': '밥·죽', '밥버거': '밥·죽', '고구마누룽지': '밥·죽', '오차즈케': '밥·죽', '떡꼬치': '면·분식', '또띠아': '면·분식', '라자냐': '면·분식', '만두': '면·분식', '딤섬': '면·분식', '수제비': '면·분식', '알리오올리오': '면·분식', '팟타이': '면·분식', '짜파구리': '면·분식', '토스트': '면·분식', '샌드위치': '면·분식', '피자': '면·분식', '햄버거': '면·분식', '핫도그': '면·분식', '타코': '면·분식', '고로케': '면·분식', '베이글': '면·분식', '라이스페이퍼꼬치': '면·분식', '라이스페이퍼떡': '면·분식', '장떡': '면·분식', '길감자': '면·분식', '간짜장': '면·분식', '짜파게티': '면·분식', '감자옹심이': '면·분식', '육개장': '국·찌개', '닭개장': '국·찌개', '청국장': '국·찌개', '닭백숙': '국·찌개', '닭한마리': '국·찌개', '물회': '국·찌개', '스키야키': '국·찌개', '석박지': '김치', '동치미': '김치', '오이지': '김치', '김장김치': '김치', '갓김치': '김치', '떡': '디저트·음료', '찹쌀떡': '디저트·음료', '치즈떡': '디저트·음료', '감자떡': '디저트·음료', '고구마떡': '디저트·음료', '버터떡': '디저트·음료', '쑥떡': '디저트·음료', '설기': '디저트·음료', '백설기': '디저트·음료', '호박설기': '디저트·음료', '콩설기': '디저트·음료', '피자설기': '디저트·음료', '경단': '디저트·음료', '모찌': '디저트·음료', '과일찹쌀떡': '디저트·음료', '찹쌀초콜릿': '디저트·음료', '카스테라': '디저트·음료', '마카롱': '디저트·음료', '탕후루': '디저트·음료', '빼빼로': '디저트·음료', '츄러스': '디저트·음료', '젤라또': '디저트·음료', '크레페': '디저트·음료', '화과자': '디저트·음료', '과일산도': '디저트·음료', '비스코티': '디저트·음료', '크로플': '디저트·음료', '호떡': '디저트·음료', '커피': '디저트·음료', '팬케익': '디저트·음료', '바나나말이': '디저트·음료', '호두말이': '디저트·음료', '두쫀쿠': '디저트·음료', '군고구마': '디저트·음료', '찐고구마': '디저트·음료', '군밤': '디저트·음료', '삶은밤': '디저트·음료', '찐감자': '디저트·음료', '찐옥수수': '디저트·음료', '식혜': '디저트·음료', '수정과': '디저트·음료', '뱅쇼': '디저트·음료', '그릭요거트': '디저트·음료', '콩물': '디저트·음료', '밤조림': '디저트·음료', '감말랭이': '디저트·음료', '과일청': '디저트·음료', '해독주스': '디저트·음료', '쉐이크': '디저트·음료', '꼬치전': '전·튀김'}

def dish_type(menu):
    if menu in DISH_FIX: return DISH_FIX[menu]   # 3단계: 직접 지정한 요리 종류 먼저
    """메뉴 이름 끝말로 요리 종류 (팀 메뉴 사전에는 종류가 없어서)"""
    for pat, t in ((r'(국|찌개|탕|전골|스튜|수프|스프)$', '국·찌개'), (r'(김치|깍두기|겉절이|섞박지|장아찌|피클)$', '김치'),
                   (r'(볶음밥|덮밥|비빔밥|김밥|주먹밥|밥|죽|리조또|유부초밥|초밥|포케|오므라이스)$', '밥·죽'),
                   (r'(국수|면|라면|우동|파스타|스파게티|냉면|짬뽕|짜장면|칼국수|쌀국수|떡볶이|라볶이)$', '면·분식'),
                   (r'(빵|케이크|쿠키|머핀|스콘|타르트|파이|와플|브라우니|마들렌|휘낭시에|도넛|빙수|푸딩|젤리|아이스크림|라떼|에이드|스무디|청|잼)$', '디저트·음료'),
                   (r'(샐러드)$', '샐러드'), (r'(전|부침개|튀김|까스|가스|커틀릿)$', '전·튀김'),
                   (r'(나물|무침|조림|볶음|구이|찜|장조림|샐러드|쌈|수육|보쌈|불고기|갈비|스테이크)$', '반찬·메인')):
        if re.search(pat, menu or ''): return t
    return '기타'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--team-dir', required=True, help='omm_team_data zip을 푼 폴더 (DATA_GUIDE.md 가 있는 곳)')
    ap.add_argument('--full', action='store_true')
    a = ap.parse_args()
    td = a.team_dir
    if not os.path.exists(os.path.join(td, 'data', 'clean', 'recipes_clean.csv')):
        sys.exit(f'{td}/data/clean/recipes_clean.csv 가 없어요. zip을 푼 폴더(DATA_GUIDE.md 있는 곳)를 주세요.')
    P = lambda *x: os.path.join(td, *x)
    conn = psycopg2.connect(host=os.getenv('PGHOST', 'localhost'), port=os.getenv('PGPORT', '5432'), dbname=os.getenv('PGDATABASE', 'omm_insight'),
                            user=os.getenv('PGUSER', 'postgres'), password=os.getenv('PGPASSWORD'))
    cur = conn.cursor()
    ins = lambda sql, rows: execute_values(cur, sql, rows, page_size=2000) if rows else None
    def idmap(sql):
        cur.execute(sql); return {r[0]: r[1] for r in cur.fetchall()}
    if a.full:
        full_reset(cur)
        cur.execute('DELETE FROM omm_price_monthly'); cur.execute('DELETE FROM omm_menu_nutrition')
    cur.execute('SELECT count(*) FROM omm_common_codes WHERE code_id = %s', ('PSRC_CHAMGAGYEOK',))
    if cur.fetchone()[0] == 0:
        sys.exit('공통코드가 예전 버전이에요. 새 omm_schema_v4.sql 로 DB를 다시 만들어 주세요.')
    ins('INSERT INTO omm_ingredient_categories (category_id, name, sort_order) VALUES %s ON CONFLICT (category_id) DO NOTHING', [(i, n, i) for i, n in CATS])
    report = []

    # ───── 1. 재료 사전 → 표준 재료 · 별칭 ─────
    dic = read(P('data', 'clean', 'ingredient_dictionary.csv'))
    priced = {r.get('key') for r in read(P('data', 'price', 'ingredient_price_monthly.csv'))}   # 가격이 있는 재료는 레시피 1개여도 남김 (재료비 계산용)
    keep = {r['std_name']: r for r in dic if r.get('std_name') and ((to_int(r.get('recipes')) or 0) >= MIN_ING or r['std_name'] in priced)}
    have = idmap('SELECT name, ingredient_id FROM omm_ingredients')
    rows, upd = [], []
    for n, r in keep.items():
        seas = (to_num(r.get('seasoning_share')) or 0) >= 0.5 or n in {'바질가루', '사골육수', '레드와인', '원당', '맥주', '스틱육수', '파프리카가루', '전분가루', '소주', '알룰루스', '파슬리가루', '유자청', '참치액', '막걸리', '시나몬파우더', '미원', '화이트발사믹', '생수', '오레가노', '조청', '홍초', '레몬즙', '코인육수', '연두', '채수', '매실청', '치킨스톡', '요리당', '화이트와인', '홀그레인머스타드', '생강청', '아보카도오일', '다시팩', '청주', '뜨거운물', '얼음', '차가운물', '월계수잎', '뉴슈가', '쯔유', '페페론치노', '다시마물', '매실액', '코코넛오일', '베이킹파우더', '베이킹소다', '알롤로스', '올리브오일', '한알육수', '다시다', '멸치육수', '현미유', '알룰로스', '쌀뜨물', '가루육수', '홀그레인머스터드', '바닐라익스트랙', '꿀', '카레가루', '빵가루', '발사믹글레이즈', '스테비아', '냉면육수'}   # 4단계: 소스 · 조미료 · 육수 · 기름은 재료비에서 뺌
        if n[:50] in have: upd.append((have[n[:50]], to_int(r['recipes']) or 0, seas))
        else: rows.append((n[:50], 9 if seas else guess_cat(n), seas, to_int(r['recipes']) or 0))
    ins('INSERT INTO omm_ingredients (name, category_id, is_seasoning, recipe_count) VALUES %s ON CONFLICT (name) DO NOTHING', rows)
    if upd: execute_values(cur, 'UPDATE omm_ingredients i SET recipe_count = v.c, is_seasoning = v.s FROM (VALUES %s) v(id, c, s) WHERE i.ingredient_id = v.id', upd)
    ing_id = idmap('SELECT name, ingredient_id FROM omm_ingredients')
    alias = {}
    for n, r in keep.items():
        for raw in [n] + (r.get('raw_examples') or '').split('|'):
            k = re.sub(r'\s+', '', raw)[:100]
            if k and n[:50] in ing_id: alias.setdefault(k, ing_id[n[:50]])
    for r in read(P('dict', 'tables', 'spelling_norm.csv')):          # 달걀 → 계란 같은 표기 통일
        if r.get('to') in ing_id and r.get('from'): alias.setdefault(re.sub(r'\s+', '', r['from'])[:100], ing_id[r['to']])
    # 사전 원본 = DB. 이미 있는 별칭(관리자가 고친 것 · 지운 것 포함)은 건드리지 않고 새 표기만 추가
    ins('INSERT INTO omm_ingredient_aliases (alias, ingredient_id, source) VALUES %s ON CONFLICT (alias) DO NOTHING',
        [(k, v, 'SRC_TEAM') for k, v in alias.items()])
    report.append(f'표준 재료 {len(keep):,} (사전 {len(dic):,}개 중 레시피 {MIN_ING}개 이상 또는 가격 있음) · 별칭 {len(alias):,}')

    # ───── 2. 메뉴 사전 ─────
    seed = read(P('dict', 'menu_seed.csv'))
    rmenu = {to_int(r['recipe_id']): (r.get('menu') or '').strip() for r in read(P('data', 'clean', 'recipe_menu.csv'))}
    seed += [{'menu': m} for m in sorted(set(rmenu.values()) - {r.get('menu') for r in seed}) if m]   # 사전에 없지만 레시피에 쓰인 메뉴
    have = idmap('SELECT name, menu_id FROM omm_menus')
    mrows = []
    for r in seed:
        m = (r.get('menu') or '').strip()
        if not m: continue
        kws = [m] + [x.strip() for x in (r.get('aliases') or '').split('|') if x.strip()]
        mrows.append((m[:50], dish_type(m), kws))
    ins('INSERT INTO omm_menus (name, dish_type, match_keywords) VALUES %s ON CONFLICT (name) DO NOTHING', [x for x in mrows if x[0] not in have])
    # 사전 원본 = DB. 기존 메뉴의 match_keywords 는 관리자 API 가 고치는 값이라 덮어쓰지 않음 (요리 종류만 갱신)
    upd = [(have[x[0]], x[1]) for x in mrows if x[0] in have]
    if upd: execute_values(cur, 'UPDATE omm_menus m SET dish_type = v.d FROM (VALUES %s) v(id, d) WHERE m.menu_id = v.id', upd)
    menu_id = idmap('SELECT name, menu_id FROM omm_menus')

    # ───── 3. 레시피 · 분류 ─────
    info = {}
    for r in read(P('data', 'clean', 'recipes_clean.csv')):
        rid = to_int(r.get('recipe_id'))
        if not rid: continue
        reg = (r.get('published_date') or '')[:10]
        rating = to_num(r.get('rating'))
        info[rid] = (rid, menu_id.get(rmenu.get(rid, '')), (r.get('title') or '')[:200] or f'레시피 {rid}', r.get('description') or None,
                     (r.get('image') or '')[:500] or None, reg if re.match(r'\d{4}-\d{2}-\d{2}$', reg) else None,
                     to_int(r.get('servings')), to_int(r.get('time_min')), LEVELS.get((r.get('difficulty_raw') or '').strip()),
                     to_int(r.get('views')), rating if rating is not None and 0 <= rating <= 5 else None,
                     to_int(r.get('review_count')) or 0, r.get('crawled_at') or NOW, (r.get('situation') or '').strip())
    ins('INSERT INTO omm_recipes (recipe_id, menu_id, title, intro, image_url, registered_at, servings, cook_time_min, difficulty, '
        'view_count, avg_rating, review_count, collected_at) VALUES %s ON CONFLICT (recipe_id) DO UPDATE SET '
        'menu_id = EXCLUDED.menu_id, title = EXCLUDED.title, intro = EXCLUDED.intro, image_url = EXCLUDED.image_url, '
        'registered_at = EXCLUDED.registered_at, servings = EXCLUDED.servings, cook_time_min = EXCLUDED.cook_time_min, '
        'difficulty = EXCLUDED.difficulty, view_count = EXCLUDED.view_count, avg_rating = EXCLUDED.avg_rating, '
        'review_count = EXCLUDED.review_count, collected_at = EXCLUDED.collected_at', [x[:13] for x in info.values()])
    sits = sorted({x[13] for x in info.values() if x[13]})
    ins('INSERT INTO omm_recipe_category_codes (cat_type, code, name) VALUES %s ON CONFLICT (cat_type, code) DO UPDATE SET name = EXCLUDED.name',
        [('CATTYPE_SITUATION', s[:10], s[:30]) for s in sits])
    cat_id = idmap("SELECT code, category_id FROM omm_recipe_category_codes WHERE cat_type = 'CATTYPE_SITUATION'")
    rc = sorted({(x[0], cat_id[x[13][:10]]) for x in info.values() if x[13] and x[13][:10] in cat_id})
    if info: cur.execute('DELETE FROM omm_recipe_categories WHERE recipe_id = ANY(%s)', (list(info),))
    ins('INSERT INTO omm_recipe_categories VALUES %s ON CONFLICT DO NOTHING', rc)

    # ───── 4. 레시피 재료 (팀의 표준명 · g 그대로, 수량 표기 분류만 OMM 기준) ─────
    lines = []
    for r in read(P('data', 'clean', 'recipe_ingredients_clean.csv')):
        rid, seq = to_int(r.get('recipe_id')), to_int(r.get('line_no'))
        raw = (r.get('raw_name') or '').strip()
        if rid not in info or not seq or not raw: continue
        std = (r.get('std_name') or '').strip()
        cls = parse_amount(r.get('raw_amount'), std)[3]
        lines.append((rid, seq, (r.get('group') or '')[:30] or None, raw[:100], (r.get('raw_amount') or '')[:50] or None,
                      to_int(r.get('material_id')), ing_id.get(std[:50]), to_num(r.get('qty')), (r.get('unit') or '')[:20] or None,
                      to_num(r.get('grams')), 'AMOUNT_' + cls))
    lines = list({(x[0], x[1]): x for x in lines}.values())
    if info: cur.execute('DELETE FROM omm_recipe_ingredients WHERE recipe_id = ANY(%s)', (list(info),))
    ins('INSERT INTO omm_recipe_ingredients VALUES %s', lines)

    # ───── 5. 후기 ─────
    revs = {}
    for r in read(P('data', 'clean', 'reviews_clean.csv')):
        vid, rid = to_int(r.get('review_id')), to_int(r.get('recipe_id'))
        at = (r.get('written_at') or '')[:10]
        if not vid or rid not in info or not re.match(r'\d{4}-\d{2}-\d{2}$', at): continue
        st = to_int(r.get('stars'))
        revs[vid] = (vid, rid, at, st if st and 1 <= st <= 5 else None, r.get('text') or None)
    ins('INSERT INTO omm_reviews VALUES %s ON CONFLICT (review_id) DO UPDATE SET rating = EXCLUDED.rating, body = EXCLUDED.body', list(revs.values()))
    report.append(f'레시피 {len(info):,} (메뉴 연결 {sum(1 for x in info.values() if x[1]):,}) · 재료줄 {len(lines):,} · 메뉴 {len(mrows):,} · 후기 {len(revs):,}')

    # ───── 6. 시세: 팀이 고른 월별 g당 가격 (KAMIS 소매 → 참가격 → KAMIS 도매) ─────
    km = {(r['key'], r['month']): r for r in read(P('data', 'price', 'kamis_monthly.csv'))}
    pm = {}
    for r in read(P('data', 'price', 'ingredient_price_monthly.csv')):
        iid = ing_id.get((r.get('key') or '')[:50]); wpg = to_num(r.get('won_per_g'))
        if not iid or not re.match(r'\d{4}-\d{2}$', r.get('month') or '') or wpg is None: continue
        src = PSRC.get(r.get('source'), 'PSRC_KAMIS_RETAIL')
        k = km.get((r['key'], r['month'])) if src == 'PSRC_KAMIS_RETAIL' else None
        pm[(iid, r['month'], 'MARKET_RETAIL')] = (iid, r['month'] + '-01', 'MARKET_RETAIL', to_int(r.get('price')) or round(wpg * 100),
                                                  (r.get('unit') or '-')[:20], round(wpg * 100, 1), to_int(k.get('retail_normal')) if k else None,
                                                  to_num(k.get('vs_normal_pct')) if k else None, None, 0, src)
    for (key, month), r in km.items():                   # 도매 월평균 (단위는 KAMIS 도매 단위라 100g당 가격은 비움)
        iid = ing_id.get(key[:50]); w = to_int(r.get('wholesale_avg'))
        if iid and w and re.match(r'\d{4}-\d{2}$', month):
            pm[(iid, month, 'MARKET_WHOLESALE')] = (iid, month + '-01', 'MARKET_WHOLESALE', w, '도매 단위', None, to_int(r.get('wholesale_normal')),
                                                    None, None, 0, 'PSRC_KAMIS_WHOLESALE')
    ins('''INSERT INTO omm_price_monthly (ingredient_id, ym, market_type, avg_price, unit_label, price_per_100g, normal_price, vs_normal_pct, yoy_pct, day_count, price_source)
           VALUES %s ON CONFLICT (ingredient_id, ym, market_type) DO UPDATE SET avg_price = EXCLUDED.avg_price, unit_label = EXCLUDED.unit_label,
           price_per_100g = EXCLUDED.price_per_100g, normal_price = EXCLUDED.normal_price, vs_normal_pct = EXCLUDED.vs_normal_pct, price_source = EXCLUDED.price_source''',
        list(pm.values()))
    cur.execute('''UPDATE omm_price_monthly p SET yoy_pct = round((p.avg_price::numeric / NULLIF(q.avg_price, 0) - 1) * 100, 1)
                   FROM omm_price_monthly q WHERE q.ingredient_id = p.ingredient_id AND q.market_type = p.market_type
                   AND q.ym = p.ym - interval '1 year' AND p.price_source IS NOT NULL''')
    srcs = collections.Counter(v[10] for v in pm.values())
    report.append('월별 시세 ' + ' · '.join(f'{k.replace("PSRC_", "")} {v:,}' for k, v in srcs.items()))

    # ───── 7. 메뉴 영양성분 ─────
    nut = []
    for r in read(P('data', 'nutrition', 'menu_nutrition.csv')):
        mid = menu_id.get((r.get('menu') or '').strip()[:50])
        if not mid: continue
        d = (r.get('research_ymd') or '')[:10]
        nut.append((mid, (r.get('value_kind') or '')[:30] or None, r.get('food_names') or None, to_num(r.get('serving_g')),
                    *[to_num(r.get(k)) for k in ('energy_kcal_serving', 'protein_g_serving', 'fat_g_serving', 'carb_g_serving', 'sugar_g_serving',
                                                  'sodium_mg_serving', 'energy_kcal_100g')],
                    d if re.match(r'\d{4}-\d{2}-\d{2}$', d) else None))
    ins('''INSERT INTO omm_menu_nutrition VALUES %s ON CONFLICT (menu_id) DO UPDATE SET value_kind = EXCLUDED.value_kind, food_names = EXCLUDED.food_names,
           serving_g = EXCLUDED.serving_g, kcal_serving = EXCLUDED.kcal_serving, protein_g_serving = EXCLUDED.protein_g_serving, fat_g_serving = EXCLUDED.fat_g_serving,
           carb_g_serving = EXCLUDED.carb_g_serving, sugar_g_serving = EXCLUDED.sugar_g_serving, sodium_mg_serving = EXCLUDED.sodium_mg_serving,
           kcal_100g = EXCLUDED.kcal_100g, research_date = EXCLUDED.research_date''', nut)
    report.append(f'메뉴 영양성분 {len(nut)}')

    # ───── 8. YouTube 트렌드 영상 (넓은 검색어 + 제목 속 메뉴) ─────
    yv = read(P('data', 'youtube', 'trend_videos.csv'))
    yv.sort(key=lambda r: r.get('run_date') or '')                # 같은 영상은 가장 최근 회차 값
    kws = {}
    for r in yv:
        q = (r.get('query') or '').strip()
        if q: kws[q] = ('KWKIND_QUERY', None, None)
        m = (r.get('title_menu') or '').strip()
        if m: kws[m] = ('KWKIND_MENU', menu_id.get(m[:50]), None)
    ins('''INSERT INTO omm_trend_keywords (keyword, kind, menu_id, ingredient_id) VALUES %s ON CONFLICT (keyword) DO UPDATE SET
           kind = EXCLUDED.kind, menu_id = EXCLUDED.menu_id''', [(k[:50], *v) for k, v in kws.items()])
    kw_id = idmap('SELECT keyword, keyword_id FROM omm_trend_keywords')
    vids, vk = {}, set()
    for r in yv:
        v = r.get('video_id')
        if not v or not r.get('published_at'): continue
        vids[v] = (v[:11], (r.get('title') or '')[:300], r['published_at'], None,           # 채널은 이름만 있어서 저장 안 함 (ID만 저장 원칙)
                   to_int(r.get('views')), to_int(r.get('likes')), to_int(r.get('comments')), (r.get('run_date') or NOW[:10]))
        if r.get('query') in kw_id: vk.add((v[:11], kw_id[r['query']], 'MATCH_SEARCH'))
        if (r.get('title_menu') or '').strip()[:50] in kw_id: vk.add((v[:11], kw_id[r['title_menu'].strip()[:50]], 'MATCH_TITLE'))
    ins('INSERT INTO omm_youtube_videos VALUES %s ON CONFLICT (video_id) DO UPDATE SET view_count = EXCLUDED.view_count, '
        'like_count = EXCLUDED.like_count, comment_count = EXCLUDED.comment_count, collected_at = EXCLUDED.collected_at', list(vids.values()))
    ins('INSERT INTO omm_youtube_video_keywords (video_id, keyword_id, matched_by) VALUES %s ON CONFLICT DO NOTHING', sorted(vk))
    report.append(f'YouTube 검색어 · 메뉴 키워드 {len(kws)} · 영상 {len(vids):,}')

    # ───── 8-2. YouTube 요즘 뜨는 음식 (회차별 growth) ─────
    # collector youtube_trend.py 의 trend_foods.csv 와 같은 계산: 최근 vs 이전, 기간마다 표본 안 비중끼리 비교
    runs = collections.defaultdict(dict)                         # 회차 → {(영상, 기간): 행}  여러 검색어에 걸린 같은 영상은 한 번만
    for r in yv:
        if r.get('run_date') and r.get('video_id') and r.get('period') in ('최근', '이전'):
            runs[r['run_date'][:10]].setdefault((r['video_id'], r['period']), r)
    tf = []
    for rd, rows in runs.items():
        n = collections.Counter(p for _, p in rows)
        n_recent, n_before = max(n['최근'], 1), max(n['이전'], 1)
        cnt = collections.defaultdict(lambda: {'최근': 0, '이전': 0, 'views': 0, 'example': '', 'channels': set()})
        for (_, period), r in rows.items():
            for food in {f.strip()[:50] for f in (r.get('foods') or '').split('|') if f.strip()}:
                c = cnt[food]
                c[period] += 1
                if period == '최근':
                    c['views'] += to_int(r.get('views')) or 0
                    c['channels'].add(r.get('channel'))
                    c['example'] = c['example'] or (r.get('title') or '')[:300]
        for food, c in cnt.items():
            mid = menu_id.get(food)
            # 한 채널이 자기 해시태그를 반복한 건 트렌드가 아님 → 최근 채널 2곳 이상 (사전에 없는 이름은 3곳 이상)
            if len(c['channels']) < (2 if mid else 3):
                continue
            tf.append((rd, food, mid, c['최근'], c['이전'], len(c['channels']), n_recent, n_before,
                       round(((c['최근'] + 0.5) / n_recent) / ((c['이전'] + 0.5) / n_before), 2), c['views'], c['example'] or None))
    if runs:
        cur.execute('DELETE FROM omm_youtube_trend_foods WHERE run_date = ANY(%s::date[])', (sorted(runs),))   # 다시 계산한 회차는 통째로 새로
    ins('INSERT INTO omm_youtube_trend_foods VALUES %s', tf)
    report.append(f'YouTube 뜨는 음식 {len(runs)}회차 · {len(tf):,}행')

    # ───── 9. 기본값: 단위 환산 · 맛 표현 · 취향 태그 ─────
    ins('INSERT INTO omm_unit_conversions (unit, grams, amount_class) VALUES %s ON CONFLICT ON CONSTRAINT cs_omm_unit_conversions_1 DO UPDATE SET grams = EXCLUDED.grams, amount_class = EXCLUDED.amount_class',
        [(u, g, 'AMOUNT_' + c) for u, (c, g) in UNITS.items()])
    ins('INSERT INTO omm_taste_words (word, taste_group) VALUES %s ON CONFLICT (word) DO UPDATE SET taste_group = EXCLUDED.taste_group', [(w, g) for g, ws in TASTES.items() for w in ws])
    cur.execute("SELECT taste_id FROM omm_taste_words WHERE word = '얼큰'")
    tag = [('얼큰한 국물', 'TAGKIND_WANT', 'RULE_TASTE', cur.fetchone()[0], 1),
           ('고기', 'TAGKIND_WANT', 'RULE_INGREDIENT_CATEGORY', 4, 2), ('해산물', 'TAGKIND_EXCLUDE', 'RULE_INGREDIENT_CATEGORY', 5, 2)]
    if '오이' in ing_id: tag.append(('오이', 'TAGKIND_EXCLUDE', 'RULE_INGREDIENT', ing_id['오이'], 1))
    if '초스피드' in cat_id: tag.append(('간단한 한 그릇', 'TAGKIND_WANT', 'RULE_RECIPE_CATEGORY', cat_id['초스피드'], 5))
    ins('INSERT INTO omm_filter_tags (label, kind, rule_type, rule_ref_id, sort_order) VALUES %s ON CONFLICT DO NOTHING', tag)

    report.insert(0, ('전체 다시 넣기' if a.full else '바뀐 것만') + f' · {os.path.basename(os.path.abspath(td))}')
    cur.execute("INSERT INTO omm_etl_runs (source, job, finished_at, status, row_count, message) VALUES ('SRC_TEAM', 'load_team', now(), 'ETL_OK', %s, %s)",
                (len(info) + len(lines) + len(revs) + len(pm), ' | '.join(report)))
    conn.commit()
    print('팀 데이터 적재 완료\n  ' + '\n  '.join(report))
    print('다음:  psql -f mart_build_v4.sql  →  python mart_python_v4.py  →  python charts_v4.py')

if __name__ == '__main__':
    main()
