"""MongoDB 원문(OMM DB, *_raw 컬렉션) → 정제 → load_team.py 가 읽는 폴더 구조로 저장

  python mongo_extract.py --peek                          컬렉션마다 문서 1개의 필드 · 값 형태만 출력 (처음 한 번 확인용)
  python mongo_extract.py --out mongo_stage               정제해서 mongo_stage/ 에 저장
  python mongo_extract.py --out mongo_stage --verify team_data   팀 zip 결과와 비교 (일치율 출력)
  → python load_team.py --team-dir mongo_stage [--full]   (run_all.sh 가 OMM_SOURCE=mongo 일 때 자동으로)

접속: 환경변수 MONGO_URI (예: mongodb://omm:비밀번호@10.0.56.201:27017/?replicaSet=omm-rs&authSource=admin) · MONGO_DB (기본 OMM)
      비밀번호는 omm.env 에만 (chmod 600). 테스트용으로 --jsonl-dir 폴더(<컬렉션>.jsonl)에서 읽을 수도 있음
정제 기준: 메뉴 키워드 · 재료 별칭은 PostgreSQL(omm_menus · omm_ingredient_aliases)이 원본,
          나머지는 omm_dict/ (make_dicts.py 로 팀 정제 결과에서 뽑은 사전) + norm_v4.py 규칙
읽기만 하고 몽고에는 아무것도 쓰지 않음
"""
import os, sys, re, csv, json, argparse, datetime, statistics, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clean_name import clean, INVIS   # 2단계: 메모 · 양 · 보이지 않는 문자 정리 규칙
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from norm_v4 import normalize, parse_amount, servings_of, cook_min_of, SEASONING

HERE = os.path.dirname(os.path.abspath(__file__))
C_RECIPE, C_REVIEW, C_KAMIS, C_CHAM, C_NUTR, C_YT = ('OMM_mangae_recipes_raw', 'OMM_mangae_reviews_raw', 'OMM_kamis_prices_raw',
                                                    'OMM_chamgagyeok_raw', 'OMM_nutrition_foods_raw', 'OMM_youtube_videos')
SEASON_GROUP = re.compile(r'양념|소스|드레싱|장\]|시즈닝|토핑')
NUTR = {'energy_kcal': 'AMT_NUM1', 'water_g': 'AMT_NUM2', 'protein_g': 'AMT_NUM3', 'fat_g': 'AMT_NUM4', 'ash_g': 'AMT_NUM5',
        'carb_g': 'AMT_NUM6', 'sugar_g': 'AMT_NUM7', 'fiber_g': 'AMT_NUM8', 'calcium_mg': 'AMT_NUM9', 'iron_mg': 'AMT_NUM10',
        'phosphorus_mg': 'AMT_NUM11', 'potassium_mg': 'AMT_NUM12', 'sodium_mg': 'AMT_NUM13'}


# ─────────── 공통 ───────────
def num(x):
    """'1,234' · '1234원' · 1234 · '-' → 숫자 / None"""
    if x is None or isinstance(x, bool): return None
    if isinstance(x, (int, float)): return float(x)
    if isinstance(x, dict): x = next(iter(x.values()), None); return num(x)     # {'$numberDouble': '..'} 같은 형태
    m = re.search(r'-?\d+(?:\.\d+)?', str(x).replace(',', ''))
    return float(m.group()) if m else None


def day(x):
    """datetime · '2026-11-20T11:29:36+09:00' · '2026/11/20' · '20261120' → '2026-11-20'"""
    if x is None: return ''
    if isinstance(x, dict): x = x.get('$date', '')
    if isinstance(x, (datetime.date, datetime.datetime)): return x.strftime('%Y-%m-%d')
    s = str(x).strip()
    m = re.match(r'(\d{4})[-./]?(\d{1,2})[-./]?(\d{1,2})', s)
    return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}' if m else ''


def text(x):
    if x is None: return ''
    if isinstance(x, (list, tuple)): return ' '.join(text(v) for v in x)
    if isinstance(x, dict): return ' '.join(text(v) for v in x.values())
    return re.sub(r'\s+', ' ', str(x).replace('\xa0', ' ')).strip()


def truthy(x):
    return bool(x) and str(x).strip().upper() not in ('N', 'NO', '0', 'FALSE', 'NONE', '-', 'X', '')


def read(p):
    with open(p, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write(out, rel, fields, rows):
    p = os.path.join(out, *rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    print(f'  {"/".join(rel):45s} {len(rows):>9,}줄')


class Source:
    """몽고 (MONGO_URI) 또는 테스트용 jsonl 폴더"""
    def __init__(self, jsonl_dir=None):
        self.dir = jsonl_dir
        if not jsonl_dir:
            from pymongo import MongoClient
            uri = os.getenv('MONGO_URI') or sys.exit('MONGO_URI 환경변수가 없어요 (omm.env 에 넣기)')
            self.db = MongoClient(uri, serverSelectionTimeoutMS=10000, readPreference='secondaryPreferred')[os.getenv('MONGO_DB', 'OMM')]

    def find(self, coll, fields=None):
        if self.dir:
            p = os.path.join(self.dir, coll + '.jsonl')
            if not os.path.exists(p): return
            with open(p, encoding='utf-8') as f:
                for line in f:
                    if line.strip(): yield json.loads(line)
        else:
            proj = {k: 1 for k in fields} if fields else None
            yield from self.db[coll].find({}, proj, batch_size=5000, no_cursor_timeout=False)

    def peek(self):
        names = [C_RECIPE, C_REVIEW, C_KAMIS, C_CHAM, C_NUTR, C_YT]
        for c in names:
            d = next(iter(self.find(c)), None)
            print(f'\n== {c}')
            if d is None: print('  (비어 있음)'); continue
            for k, v in d.items():
                if c == C_NUTR and re.match(r'AMT_NUM(1[4-9]|[2-9]\d|1\d\d)$', k): continue
                s = json.dumps(v, ensure_ascii=False, default=str)
                print(f'  {k:20s} {type(v).__name__:8s} {s[:160]}{"…" if len(s) > 160 else ""}')


# ─────────── 사전 ───────────
def pg_dict():
    """사전 원본(PostgreSQL) → 메뉴 키워드 · 재료 별칭. 접속 정보는 load_team.py 와 같은 PG* 환경변수"""
    import psycopg2
    conn = psycopg2.connect(host=os.getenv('PGHOST', 'localhost'), port=os.getenv('PGPORT', '5432'), dbname=os.getenv('PGDATABASE', 'omm_insight'),
                            user=os.getenv('PGUSER', 'postgres'), password=os.getenv('PGPASSWORD'))
    try:
        cur = conn.cursor()
        cur.execute('SELECT name, match_keywords FROM omm_menus ORDER BY name')
        menus = cur.fetchall()
        cur.execute("SELECT count(*) FROM information_schema.columns WHERE table_name = 'omm_ingredient_aliases' AND column_name = 'is_active'")
        if cur.fetchone()[0] == 0:
            sys.exit('omm_ingredient_aliases.is_active 칸이 없어요. dict_source_pg.sql 을 먼저 실행해 주세요.')
        cur.execute('SELECT a.alias, i.name, a.is_active FROM omm_ingredient_aliases a JOIN omm_ingredients i USING (ingredient_id)')
        aliases = cur.fetchall()
    finally:
        conn.close()
    return menus, aliases


class Dicts:
    def __init__(self, d, source='pg'):
        P = lambda f: os.path.join(d, f)
        self.dir = d
        self.norm = {r['from']: r['to'] for r in read(P('spelling_norm.csv')) if r.get('from')}
        self.seed = read(P('menu_seed.csv'))
        self.alias_on, self.alias_off = {}, set()           # DB 별칭: 사용 중 (별칭 → 표준 재료) · 관리자가 지운 것
        if source == 'pg':
            # 사전 원본 = PostgreSQL. 기존 메뉴의 키워드는 DB 값만 쓰고, CSV 는 DB에 없는 새 메뉴를 넣을 때만 씀
            pg_menus, pg_aliases = pg_dict()
            have = {n for n, _ in pg_menus}
            new = [r for r in self.seed if (r.get('menu') or '').strip() and (r.get('menu') or '').strip()[:50] not in have]
            self.seed = [{'menu': n, 'aliases': '|'.join(k for k in (kws or []) if k and k != n)} for n, kws in pg_menus] + \
                        [{'menu': (r.get('menu') or '').strip(), 'aliases': r.get('aliases') or ''} for r in new]
            for a, name, on in pg_aliases:
                if on: self.alias_on[a] = name
                else: self.alias_off.add(a)
            print(f'  사전 원본 PostgreSQL: 메뉴 {len(pg_menus):,} (+CSV 새 메뉴 {len(new)}) · 별칭 {len(self.alias_on):,} (지운 것 {len(self.alias_off)})')
        self.menu_kw = []                                   # (키워드(띄어쓰기 없앰), 메뉴)
        for r in self.seed:
            m = (r.get('menu') or '').strip()
            if not m: continue
            for k in [m] + [x.strip() for x in (r.get('aliases') or '').split('|') if x.strip()]:
                self.menu_kw.append((self.fix(k).replace(' ', ''), m))
        self.menu_kw.sort(key=lambda x: -len(x[0]))
        self.raw_std = {r['raw_name']: r['std_name'] for r in read(P('raw_std.csv'))}
        self.unit_g = {(r['std_name'], r['unit']): float(r['g_per_unit']) for r in read(P('unit_grams.csv'))}
        self.season = {r['std_name']: num(r['seasoning_share']) or 0 for r in read(P('seasoning.csv'))}
        self.kamis_map = collections.defaultdict(list)          # (품목, 품종) → [(재료, 등급)]  (한 품목이 재료 여러 개: 쌀 · 백미 · 현미)
        self.kamis_rank = {}
        for r in read(P('kamis_item_map.csv')):
            rank = r['rank_code'].strip().zfill(2) if r['rank_code'].strip() else None
            self.kamis_map[(r['item_code'].strip(), r['kind_code'].strip().zfill(2))].append((r['ingredient'], rank))
            self.kamis_rank[r['ingredient']] = rank
        self.kamis_g = {(r['key'], r['unit']): float(r['grams']) for r in read(P('kamis_unit_g.csv'))}
        self.food_menu = {r['food_cd']: (r['menu'], r['kind']) for r in read(P('food_menu.csv'))}
        self.cham = sorted(((r['ingredient'], (r.get('keyword') or r['ingredient']).replace(' ', '')) for r in read(P('cham_targets.csv'))), key=lambda x: len(x[1]), reverse=True)   # 4단계: keyword 칸이 있으면 상품 이름에서 그 말로 찾음

    def std_of(self, raw):
        """원래 표기 → 표준명. DB 별칭(공백 뺀 값) 먼저, 관리자가 지운 별칭이면 CSV 사전도 건너뜀 → 규칙 정제"""
        k = re.sub(r'\s+', '', raw)[:100]
        if k in self.alias_on: return self.alias_on[k]
        if k in self.alias_off: return None
        s = self.raw_std.get(raw)
        if s is None:                       # 2단계: 사전에 없는 지저분한 표기(감자 손질 후 등) → 메모 · 양 지우고 별칭 다시 찾기
            c = clean(raw)
            if c and c != k and c in self.alias_on: return self.alias_on[c]
        return s

    def fix(self, s):
        s = text(s)
        for a, b in self.norm.items(): s = s.replace(a, b)
        return s

    def menu_of(self, title, intro=''):
        t = self.fix(title).replace(' ', '')
        for k, m in self.menu_kw:
            if k and k in t: return m, '제목'
        t = self.fix(intro).replace(' ', '')[:200]
        for k, m in self.menu_kw:
            if len(k) >= 3 and k in t: return m, '소개'
        return '', ''


# ─────────── ① 레시피 · 재료 · 후기 ───────────
def items_of(d):
    """레시피 문서 → [(그룹, 재료명, 양, material_no)] (ingredient_groups 우선, 없으면 ingredients_flat)"""
    out = []

    def one(it, grp):
        if isinstance(it, dict):
            nm = next((it[k] for k in ('name', 'ingredient', 'item', 'ingredient_name', 'title') if it.get(k)), '')
            amt = next((it[k] for k in ('qty', 'amount', 'quantity', 'ingredient_qty', 'unit', 'volume') if it.get(k) not in (None, '')), '')
            no = next((it[k] for k in ('no', 'material_no', 'material_id', 'id') if it.get(k) not in (None, '')), '')
            g = next((it[k] for k in ('group', 'group_name') if it.get(k)), grp)
            out.append((text(g), text(nm), text(amt), str(no)))
        elif isinstance(it, (list, tuple)) and it:
            out.append((grp, text(it[0]), text(it[1]) if len(it) > 1 else '', ''))
        elif isinstance(it, str) and it.strip():
            s = it.strip()
            m = re.match(r'^(.*?)\s+((?:약간|적당량|조금|한줌|少)?\s*[\d½⅓⅔¼¾].*|약간|적당량|조금|넉넉히|취향껏)$', s)
            out.append((grp, m.group(1).strip() if m else s, m.group(2).strip() if m else '', ''))

    groups = d.get('ingredient_groups')
    if isinstance(groups, dict): groups = [{'group': k, 'items': v} for k, v in groups.items()]
    if isinstance(groups, list) and groups:
        for g in groups:
            if isinstance(g, dict):
                name = next((g[k] for k in ('group', 'group_name', 'name', 'title') if isinstance(g.get(k), str)), '')
                lst = next((v for k, v in g.items() if isinstance(v, list)), [])
                for it in lst: one(it, name)
            else: one(g, '')
    if not out:
        flat = d.get('ingredients_flat')
        if isinstance(flat, str): flat = [x for x in re.split(r'\s*[|\n,]\s*', flat) if x]
        for it in flat or []: one(it, '')
    return out


def situation_of(cats):
    if isinstance(cats, dict):
        return next((text(v) for k, v in cats.items() if '상황' in str(k) or 'situation' in str(k).lower()), '')
    if isinstance(cats, list):
        for c in cats:
            if isinstance(c, dict) and ('상황' in text(c.get('type') or c.get('cat_type') or c.get('key'))):
                return text(c.get('value') or c.get('name'))
    return ''


def categories_map(src):
    """2026-11-25: 레시피 → 만개 상황별 분류 (몽고 OMM_recipe_categories_raw). 원본에 categories 가 없을 때 씀"""
    out = {}
    for d in src.find('OMM_recipe_categories_raw', ['recipe_id', '상황별']):
        v = d.get('상황별') or []
        rid = int(num(d.get('recipe_id')) or 0)
        if rid and v:
            out[rid] = text(v[0] if isinstance(v, list) else v)
    return out


def recipes(src, D):
    rec, lines, menus = [], [], []
    cats = categories_map(src)
    stat = collections.Counter(); dic = collections.defaultdict(lambda: [0, 0, collections.Counter()])
    for d in src.find(C_RECIPE):
        rid = int(num(d.get('recipe_id')) or 0)
        if not rid: continue
        title = text(d.get('title'))
        sv = servings_of(text(d.get('servings')))
        rec.append({'recipe_id': rid, 'title': title, 'description': text(d.get('description')), 'image': text(d.get('image')),
                    'published_date': day(d.get('published_at')), 'servings': sv or '', 'time_min': cook_min_of(text(d.get('time'))) or '',
                    'difficulty_raw': text(d.get('difficulty')), 'views': int(num(d.get('views')) or 0), 'rating': num(d.get('rating')) if num(d.get('rating')) is not None else '',
                    'review_count': int(num(d.get('review_count')) or 0), 'crawled_at': text(d.get('crawled_at'))[:19], 'situation': situation_of(d.get('categories')) or cats.get(rid, '')})
        m, by = D.menu_of(title, text(d.get('description')))
        menus.append({'recipe_id': rid, 'title': title, 'menu': m, 'match_by': by})
        seen = set()
        for i, (grp, raw, amt, no) in enumerate(items_of(d), 1):
            raw = re.sub(r'\s*구매$', '', INVIS.sub('', raw)).strip()   # 보이지 않는 문자 제거
            if not raw: continue
            std = D.std_of(raw)
            if std == "안심" and re.search(r"닭|치킨", title): std = "닭안심"   # 4단계: 찜닭 등 닭 요리의 안심
            if std is None:
                std = normalize(D.fix(raw)) or ''; stat['사전에 없는 표기'] += 1
                if std: std = D.alias_on.get(re.sub(r'\s+', '', std)) or D.alias_on.get(clean(std)) or std   # 규칙 정제 결과도 별칭으로 한 번 더 (파프리카 빨강 → 파프리카)
            qty, unit, grams, cls = parse_amount(amt, std)
            if qty and unit and (std, unit) in D.unit_g: grams = round(qty * D.unit_g[(std, unit)], 1)   # 4단계: 재료별 단위 무게 먼저 (배추 1장 ≠ 배추 1통)
            if grams and sv and grams / sv > 1500: grams = None   # 4단계: 1인분 1.5kg 넘는 무게는 표기 오류로 보고 비움 (800~1kg → 400kg 등)
            seas = (D.season.get(std, 0) >= 0.5) if std in D.season else bool(SEASON_GROUP.search(grp) or std in SEASONING)
            lines.append({'recipe_id': rid, 'line_no': i, 'servings': sv or '', 'group': grp, 'is_seasoning': seas, 'raw_name': raw, 'std_name': std,
                          'material_id': no, 'raw_amount': amt, 'qty': qty if qty is not None else '', 'unit': unit or '',
                          'grams': grams if grams is not None else '', 'grams_per_serving': round(grams / sv, 1) if grams and sv else ''})
            if std:
                x = dic[std]; x[1] += seas; x[2][raw] += 1
                if std not in seen: x[0] += 1; seen.add(std)
    dict_rows = [{'std_name': s, 'recipes': v[0], 'seasoning_share': round(v[1] / max(1, sum(v[2].values())), 2),
                  'raw_examples': ' | '.join(k for k, _ in v[2].most_common(5))} for s, v in dic.items()]
    if stat: print(f'  (재료 표기 중 사전에 없어 규칙으로 정제: {stat["사전에 없는 표기"]:,}줄)')
    return rec, lines, menus, dict_rows


def reviews(src):
    out = []
    for d in src.find(C_REVIEW):
        vid, rid = int(num(d.get('review_id')) or 0), int(num(d.get('recipe_id')) or 0)
        if vid and rid:
            out.append({'review_id': vid, 'recipe_id': rid, 'written_at': day(d.get('written_at')), 'stars': int(num(d.get('stars')) or 0) or '',
                        'text': text(d.get('text'))})
    return out


# ─────────── ② 가격 (KAMIS · 참가격) ───────────
def unit_grams(unit):
    m = re.match(r'^\s*([\d.]+)\s*(kg|g|l|ml)\s*$', (unit or '').lower())
    if not m: return None
    return float(m.group(1)) * {'kg': 1000, 'g': 1, 'l': 1000, 'ml': 1}[m.group(2)]


def kamis(src, D, start):
    daily = collections.defaultdict(lambda: [0.0, 0]); unit_of = {}   # 2026-11-25: 가격 리스트 대신 [합계, 개수] (559만 건에서 메모리 절약, 결과 같음)
    for d in src.find(C_KAMIS, ['item_code', 'kind_code', 'rank_code', 'ingredients', 'date', 'cls', 'price', 'unit']):
        dt = day(d.get('date'))
        if not dt or dt[:7] < start: continue
        p = num(d.get('price'))
        if not p or p <= 0: continue
        ings = d.get('ingredients')                     # 몽고 원문: 이 시세를 쓰는 재료 목록 (['백미', '쌀', '현미'])
        ings = [text(x) for x in ings] if isinstance(ings, list) else ([text(ings)] if ings else [])
        key = (str(d.get('item_code') or '').strip(), str(d.get('kind_code') or '').strip().zfill(2))
        pairs = [(i, D.kamis_rank.get(i)) for i in ings if i] or D.kamis_map.get(key, [])
        rk = str(d.get('rank_code') or '').strip().zfill(2)
        cls = '도매' if '도매' in text(d.get('cls')) or text(d.get('cls')) in ('01', '1') else '소매'
        for ing, rank in pairs:
            if rank and rk != '00' and rk != rank: continue
            a = daily[(ing, dt, cls)]; a[0] += p; a[1] += 1; unit_of[(ing, cls)] = text(d.get('unit'))
    mon = collections.defaultdict(list)
    for (ing, dt, cls), (t, n) in daily.items(): mon[(ing, dt[:7], cls)].append(t / n)
    out = {}
    for (ing, ym, cls), ps in mon.items():
        r = out.setdefault((ing, ym), {'ingredient': ing, 'key': ing, 'month': ym, 'wholesale_avg': '', 'retail_avg': '',
                                       'wholesale_normal': '', 'retail_normal': '', 'vs_normal_pct': '',
                                       'retail_unit': unit_of.get((ing, '소매'), ''), 'wholesale_unit': unit_of.get((ing, '도매'), '')})
        r['retail_avg' if cls == '소매' else 'wholesale_avg'] = round(sum(ps) / len(ps))
    print(f'  KAMIS 일별 {len(daily):,} → 월별 {len(out):,}')
    return sorted(out.values(), key=lambda r: (r['key'], r['month']))


def cham(src, D, start):
    by = collections.defaultdict(list); stores = collections.defaultdict(set); miss = collections.Counter()
    for d in src.find(C_CHAM, ['product', 'survey_date', 'price', 'store', 'sale', 'one_plus_one']):
        if truthy(d.get('sale')) or truthy(d.get('one_plus_one')): continue          # 정상가만
        dt = day(d.get('survey_date'))
        if not dt or dt[:7] < start: continue
        prod = text(d.get('product')); p = num(d.get('price'))
        ing = next((i for i, k in D.cham if k in prod.replace(' ', '')), None)
        if not ing or not p: continue
        m = re.findall(r'([\d.]+)\s*(kg|KG|Kg|g|G|ml|mL|ML|l|L)\b(?:\s*[x×*X]\s*(\d+))?', prod)
        if not m: miss['용량 없음'] += 1; continue
        q, u, n = m[-1]
        g = float(q) * {'kg': 1000, 'g': 1, 'l': 1000, 'ml': 1}[u.lower()] * (int(n) if n else 1)
        if g <= 0: continue
        by[(ing, dt, prod)].append(p / g); stores[(ing, dt)].add(text(d.get('store')))
    agg = collections.defaultdict(list)
    for (ing, dt, prod), v in by.items(): agg[(ing, dt)].append(statistics.median(v))
    out = []
    for (ing, dt), v in sorted(agg.items()):
        out.append({'ingredient': ing, 'date': dt, 'products': len(v), 'stores': len(stores[(ing, dt)]), 'won_per_g': round(statistics.median(v), 3)})
    if miss: print(f'  참가격 상품명에 용량이 없어 뺀 줄 {miss["용량 없음"]:,}')
    return out


def price_monthly(km, ch, D):
    """재료 × 월 g당 가격: KAMIS 소매 → 참가격 → KAMIS 도매 순서"""
    out = {}
    cm = collections.defaultdict(list)
    for r in ch: cm[(r['ingredient'], r['date'][:7])].append(r['won_per_g'])
    for (ing, ym), v in cm.items():
        w = round(sum(v) / len(v), 3); out[(ing, ym)] = {'key': ing, 'month': ym, 'source': '참가격', 'unit': 'g', 'price': w, 'won_per_g': w}
    for r in km:
        for cls, col, ucol in (('KAMIS 소매', 'retail_avg', 'retail_unit'), ('KAMIS 도매', 'wholesale_avg', 'wholesale_unit')):
            p, u = r[col], r[ucol]
            if p == '': continue
            g = D.kamis_g.get((r['key'], u)) or unit_grams(u)
            if not g: continue
            have = out.get((r['key'], r['month']))
            if have and not (cls == 'KAMIS 소매' and have['source'] != 'KAMIS 소매'): continue
            out[(r['key'], r['month'])] = {'key': r['key'], 'month': r['month'], 'source': cls, 'unit': u, 'price': p, 'won_per_g': p / g}
    return sorted(out.values(), key=lambda r: (r['key'], r['month']))


# ─────────── ③ 영양 ───────────
def nutrition(src, D, rec_menu):
    foods = collections.defaultdict(list); kw = D.menu_kw
    for d in src.find(C_NUTR, ['FOOD_CD', 'FOOD_NM_KR', 'DB_CLASS_NM', 'CRT_MTH_NM', 'SERVING_SIZE', 'Z10500', 'RESEARCH_YMD', *NUTR.values()]):
        cd = text(d.get('FOOD_CD')); nm = text(d.get('FOOD_NM_KR'))
        if cd in D.food_menu: menu, kind = D.food_menu[cd]
        else:
            base = D.fix(nm.split('_')[0]).replace(' ', '')
            menu = next((m for k, m in kw if k == base), '')
            kind = ('시판 ' if '상용' in text(d.get('DB_CLASS_NM')) else '') + text(d.get('CRT_MTH_NM'))
        if not menu: continue
        foods[menu].append((kind, nm, d))
    counts = collections.Counter(m for m in rec_menu.values() if m)
    out = []
    for menu, fs in foods.items():
        for want, label in (('분석', '분석 · g'), ('산출', 'mL (산출)'), ('수집', 'g (수집 · 산출) · 시판 제품')):
            pick = [f for f in fs if f[0].endswith(want) and (want != '분석' or not f[0].startswith('시판'))]
            if pick: break
        else: continue
        r = {'menu': menu, 'recipes': counts.get(menu, 0), 'value_kind': label, 'foods': len({f[1] for f in pick}),
             'food_names': ' | '.join(dict.fromkeys(f[1] for f in pick)), 'rows': len(pick)}
        sv = [num(f[2].get('Z10500')) for f in pick if num(f[2].get('Z10500'))]
        r['serving_g'] = round(statistics.median(sv), 1) if sv else ''
        r['research_ymd'] = max((day(f[2].get('RESEARCH_YMD')) for f in pick), default='')
        for k, col in NUTR.items():
            v = [num(f[2].get(col)) for f in pick if num(f[2].get(col)) is not None]
            r[k + '_100g'] = round(sum(v) / len(v), 2) if v else ''
            r[k + '_serving'] = round(r[k + '_100g'] * r['serving_g'] / 100, 2) if v and r['serving_g'] else ''
        out.append(r)
    return out


# ─────────── ④ 유튜브 ───────────
YT = ['run_date', 'query', 'period', 'video_id', 'title', 'channel', 'published_at', 'views', 'likes', 'comments', 'title_menu', 'foods']


def youtube(src):
    out = []
    for d in src.find(C_YT):
        r = {k: d.get(k) for k in YT}
        r['run_date'] = day(r['run_date']); r['published_at'] = r['published_at'].isoformat() if hasattr(r['published_at'], 'isoformat') else text(r['published_at'])
        r['foods'] = ' | '.join(map(text, r['foods'])) if isinstance(r['foods'], list) else text(r['foods'])
        for k in ('views', 'likes', 'comments'): r[k] = int(num(r[k])) if num(r[k]) is not None else ''
        out.append(r)
    return out


# ─────────── 비교 (팀 zip 결과와) ───────────
def verify(out, team):
    T = lambda *p: read(os.path.join(team, 'data', *p)); O = lambda *p: read(os.path.join(out, 'data', *p))
    print('\n[팀 zip 결과와 비교]')
    for rel, key in ((('clean', 'recipes_clean.csv'), 'recipe_id'), (('clean', 'reviews_clean.csv'), 'review_id'),
                     (('youtube', 'trend_videos.csv'), None), (('clean', 'recipe_ingredients_clean.csv'), None)):
        a, b = T(*rel), O(*rel); print(f'  {rel[1]:32s} 팀 {len(a):>8,} · 몽고 {len(b):>8,}')
    tm = {r['recipe_id']: r['menu'] for r in T('clean', 'recipe_menu.csv')}; om = {r['recipe_id']: r['menu'] for r in O('clean', 'recipe_menu.csv')}
    same = sum(1 for k, v in tm.items() if om.get(k) == v); print(f'  레시피 → 메뉴 같은 비율          {same / max(1, len(tm)):.1%}')
    ts = {(r['recipe_id'], r['raw_name']): r['std_name'] for r in T('clean', 'recipe_ingredients_clean.csv')}
    os_ = {(r['recipe_id'], r['raw_name']): r['std_name'] for r in O('clean', 'recipe_ingredients_clean.csv')}
    hit = sum(1 for k, v in ts.items() if os_.get(k) == v); print(f'  재료 표준명 같은 비율            {hit / max(1, len(ts)):.1%}')
    tp = {(r['key'], r['month']): float(r['won_per_g']) for r in T('price', 'ingredient_price_monthly.csv')}
    op = {(r['key'], r['month']): float(r['won_per_g']) for r in O('price', 'ingredient_price_monthly.csv')}
    both = [k for k in tp if k in op]; close = sum(1 for k in both if abs(op[k] - tp[k]) <= 0.05 * tp[k])
    print(f'  월별 가격  팀 {len(tp):,} · 몽고 {len(op):,} · 겹침 {len(both):,} · ±5% 이내 {close / max(1, len(both)):.1%}')
    tn = {r['menu']: num(r['energy_kcal_serving']) for r in T('nutrition', 'menu_nutrition.csv')}
    on = {r['menu']: num(r['energy_kcal_serving']) for r in O('nutrition', 'menu_nutrition.csv')}
    bn = [k for k in tn if k in on and tn[k] and on[k]]; cn = sum(1 for k in bn if abs(on[k] - tn[k]) <= 0.1 * tn[k])
    print(f'  메뉴 영양  팀 {len(tn):,} · 몽고 {len(on):,} · 겹침 {len(bn):,} · 1인분 kcal ±10% 이내 {cn / max(1, len(bn)):.1%}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='mongo_stage'); ap.add_argument('--dict', default=os.path.join(HERE, 'omm_dict'))
    ap.add_argument('--jsonl-dir'); ap.add_argument('--peek', action='store_true'); ap.add_argument('--verify')
    ap.add_argument('--dict-source', choices=['pg', 'csv'], default=os.getenv('DICT_SOURCE', 'pg'),
                    help='메뉴 키워드 · 재료 별칭 원본 (pg = PostgreSQL, csv = omm_dict 만 · 비상용)')
    ap.add_argument('--price-start', default=os.getenv('PRICE_START', '2025-08'), help='이 달부터 가격 집계 (YYYY-MM)')
    a = ap.parse_args()
    src = Source(a.jsonl_dir)
    if a.peek: src.peek(); return
    D = Dicts(a.dict, a.dict_source); t0 = datetime.datetime.now()
    print('[1/4] 레시피 · 재료 · 후기')
    rec, lines, menus, dic = recipes(src, D); rv = reviews(src)
    write(a.out, ('data', 'clean', 'recipes_clean.csv'), list(rec[0].keys()) if rec else ['recipe_id'], rec)
    write(a.out, ('data', 'clean', 'recipe_ingredients_clean.csv'), list(lines[0].keys()) if lines else ['recipe_id'], lines)
    write(a.out, ('data', 'clean', 'recipe_menu.csv'), ['recipe_id', 'title', 'menu', 'match_by'], menus)
    write(a.out, ('data', 'clean', 'ingredient_dictionary.csv'), ['std_name', 'recipes', 'seasoning_share', 'raw_examples'], dic)
    write(a.out, ('data', 'clean', 'reviews_clean.csv'), ['review_id', 'recipe_id', 'written_at', 'stars', 'text'], rv)
    print('[2/4] 가격 (KAMIS · 참가격 · 몇 분 걸릴 수 있음)')
    km = kamis(src, D, a.price_start); ch = cham(src, D, a.price_start); pm = price_monthly(km, ch, D)
    write(a.out, ('data', 'price', 'kamis_monthly.csv'), list(km[0].keys()) if km else ['key'], km)
    write(a.out, ('data', 'price', 'chamgagyeok_price.csv'), ['ingredient', 'date', 'products', 'stores', 'won_per_g'], ch)
    write(a.out, ('data', 'price', 'ingredient_price_monthly.csv'), ['key', 'month', 'source', 'unit', 'price', 'won_per_g'], pm)
    print('[3/4] 영양성분')
    nu = nutrition(src, D, {r['recipe_id']: r['menu'] for r in menus})
    write(a.out, ('data', 'nutrition', 'menu_nutrition.csv'), list(nu[0].keys()) if nu else ['menu'], nu)
    print('[4/4] 유튜브')
    write(a.out, ('data', 'youtube', 'trend_videos.csv'), YT, youtube(src))
    write(a.out, ('dict', 'menu_seed.csv'), ['menu', 'aliases'], D.seed)          # DB 원본을 반영한 메뉴 사전
    write(a.out, ('dict', 'kamis_item_map.csv'), list(read(os.path.join(a.dict, 'kamis_item_map.csv'))[0].keys()),
          read(os.path.join(a.dict, 'kamis_item_map.csv')))
    write(a.out, ('dict', 'tables', 'spelling_norm.csv'), ['from', 'to', 'memo'], read(os.path.join(a.dict, 'spelling_norm.csv')))
    with open(os.path.join(a.out, 'DATA_GUIDE.md'), 'w', encoding='utf-8') as f:
        f.write(f'# MongoDB({os.getenv("MONGO_DB", "OMM")}) 원문을 mongo_extract.py 로 정제한 결과 · {t0:%Y-%m-%d %H:%M}\n')
    print(f'끝 ({(datetime.datetime.now() - t0).seconds}초) → {a.out}')
    if a.verify: verify(a.out, a.verify)


if __name__ == '__main__':
    main()
