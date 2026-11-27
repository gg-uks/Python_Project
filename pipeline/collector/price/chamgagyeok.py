"""한국소비자원 참가격(생필품 가격 정보) — KAMIS 에 없는 가공식품 가격 보완용 모듈

쓸지 아직 몰라서 kamis_for_recipes.py 와 따로 둠. 결과 파일만 만들고 다른 스크립트를 건드리지 않음.

데이터 받는 방법 2가지
  A. 파일 (권장)  공공데이터포털 '한국소비자원_생필품 가격 정보' CSV (월간 갱신, 로그인 없이 다운로드)
                  → 받은 CSV 들을 data/raw/chamgagyeok_raw/ 에 넣기
  B. API          '한국소비자원_생필품 가격 정보_GW' (업체 ID 또는 상품 ID 중 하나 필수)
                  → config.ini [chamgagyeok] 에 operation 등을 적고 test 로 응답 모양부터 확인

실행 (프로젝트 폴더에서)
  python price/chamgagyeok.py peek      # 0. 받은 CSV 의 컬럼 · 앞 5줄 보기 (컬럼 이름 확인)
  python price/chamgagyeok.py test             # 0. API 한 번 불러 원본 응답 보기 (B 방식일 때)
  python price/chamgagyeok.py load      # 1. CSV 합치기 · 정리 → chamgagyeok_items.csv
  python price/chamgagyeok.py map      # 2. KAMIS 에 없는 재료 ↔ 참가격 상품명 매칭 → chamgagyeok_map.csv
  python price/chamgagyeok.py price      # 3. 재료별 조사일 g당 가격 · 직전 조사 대비 · 전월 대비

결과
  chamgagyeok_items.csv    조사일 · 상품명 · 판매업소 · 업태 · 가격 · 세일 · 1+1 · 용량(g) · 개입 수 · g당 가격 · 정상가 여부
  chamgagyeok_map.csv      재료 · 매칭 상품 수 · 예시 상품 (틀린 줄은 지우고 다시 price)
  chamgagyeok_price.csv    재료 · 조사일 · g당 가격 중앙값 · 상품 수
  chamgagyeok_change.csv   재료 · 최근 조사일 · g당 가격 · 직전 조사 대비 % · 전월 대비 %
"""
import os, re, sys, glob, argparse, configparser
import requests
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths as P

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = P.CONFIG

# CSV 컬럼 이름 후보 (파일마다 이름이 조금씩 다를 수 있어 앞에서부터 찾음). peek 로 보고 다르면 여기에 추가
COLS = {
    'date': ['조사일', '조사일자', '가격조사일', 'inspectDay', 'goodInspectDay'],
    'name': ['상품명', '품목명', 'goodName'],
    'maker': ['제조사명', 'goodMakerNm'],
    'store': ['판매업소', '업체명', '판매점명', 'entpName'],
    'store_type': ['업태', '업소형태', '판매업소형태', 'entpTypeName', '제조사'],   # 실제 파일은 '제조사' 칸에 업태(대형마트 …)가 들어 있음
    'price': ['판매가격', '가격', 'goodPrice'],
    'sale': ['세일여부', '할인여부', 'goodDcYn'],
    'one_plus_one': ['원플러스원', '1+1', 'plusoneYn'],
    'volume': ['용량', '규격', '상품용량', 'goodTotalCnt', 'goodBaseCnt'],
    'unit': ['단위', '용량단위', 'goodUnitDivCode'],
    'category': ['품목', '상품분류', '분류', '품목명분류'],
}
# KAMIS 에서 이미 다루는 신선 재료는 빼고, 여기 적힌 가공식품 위주로 매칭 (map 이 ingredients_to_map.csv 도 같이 봄)
DEFAULT_TARGETS = ['참치캔', '묵은지', '크래미', '콩나물', '스팸', '두부', '순두부', '연두부', '치즈', '모짜렐라치즈', '체다치즈', '버터', '햄', '스팸', '소시지', '베이컨',
                   '참치캔', '참치', '어묵', '크래미', '맛살', '식빵', '당면', '소면', '파스타면', '스파게티면', '라면', '떡볶이떡',
                   '떡국떡', '만두', '우유', '생크림', '요거트', '간장', '국간장', '고추장', '된장', '쌈장', '식초', '올리고당', '물엿',
                   '설탕', '밀가루', '부침가루', '튀김가루', '전분', '식용유', '올리브오일', '참기름', '들기름', '마요네즈', '케첩',
                   '굴소스', '맛술', '소금', '김치', '코인육수', '카레', '짜장']
# 이 말이 상품명에 있으면 다른 상품 (두부과자, 참치김밥 …)
EXCLUDE = re.compile(r'과자|스낵|김밥|도시락|샌드위치|아이스|음료|주스|젤리|사탕|초코|빵가루|라면스프|볶음밥|초밥|진밥|국밥|컵반|죽\(|이유식|DOG|CAT|반려')
# 이름으로는 못 찾는 것: 재료 → 상품명 정규식
PRODUCT_HINT = {'밥': r'^(햇반|오뚜기밥)\s*\(', '즉석밥': r'^(햇반|오뚜기밥)\s*\('}
# 레시피 재료명 → 상품명에서 찾을 말 (참치캔 → '참치', 묵은지 → '김치')
SEARCH_AS = {'참치캔': '참치', '묵은지': '김치', '배추김치': '김치', '포기김치': '김치', '크래미': '맛살', '게맛살': '맛살',
             '스팸': '햄', '슬라이스햄': '햄', '체다치즈': '치즈', '슬라이스치즈': '치즈', '굵은콩나물': '콩나물', '라면사리': '라면',
             '사각어묵': '어묵', '납작당면': '당면', '소면사리': '소면', '두부면': '두부'}


def is_match(ing, name):
    """상품명 단어 중 하나가 재료명으로 끝나면 매칭 ('부침두부' ✔, '소고기와두부진밥' ✘, '허니버터아몬드' ✘)"""
    name = str(name or '')
    if ing in PRODUCT_HINT:
        return bool(re.search(PRODUCT_HINT[ing], name))
    ing = SEARCH_AS.get(ing, ing)
    if EXCLUDE.search(name):
        return False
    core = re.sub(r'\(.*?\)', ' ', name)
    return any(t.endswith(ing) for t in core.split())


def cfg():
    c = configparser.ConfigParser()
    c.read(CONFIG, encoding='utf-8')
    return c


def read_csv_any(path, **kw):
    for enc in ('utf-8-sig', 'cp949'):
        try:
            return pd.read_csv(path, encoding=enc, **kw)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, encoding='utf-8', encoding_errors='replace', **kw)


def pick(df, field):
    for c in COLS[field]:
        if c in df.columns:
            return c
    return None


def grams_from(text):
    """'풀무원 두부 300g' → 300, '스팸 200g×3' → 600, '우유 1L' → 1000, '두부 2입(600g)' → 600"""
    s = str(text or '').replace(',', '')
    m = re.findall(r'(\d+(?:\.\d+)?)\s*(kg|g|ml|l|L|리터)\b(?:\s*[x×*X]\s*(\d+))?', s)
    if not m:
        return None
    n, u, k = m[-1]
    g = float(n) * (1000 if u.lower() in ('kg', 'l', '리터') else 1)
    return g * (int(k) if k else 1)


def count_from(text):
    """'햇반(3개입)' → 3, '유정란(10개)' → 10, '냉면(4인)' → 4 (g 이 없는 상품용)"""
    m = re.search(r'(\d+)\s*(?:개입|개|입|인|봉|매)\s*\)', str(text or ''))
    return int(m.group(1)) if m else None


def raw_files(folder):
    files = sorted({f for f in glob.glob(os.path.join(P.CHAMGAGYEOK_RAW, '*'))
                    if f.lower().endswith('.csv')})                       # .CSV 대문자 확장자도
    if not files:
        sys.exit(f"{P.CHAMGAGYEOK_RAW} 에 CSV 가 없어요. 공공데이터포털 '한국소비자원_생필품 가격 정보' CSV 를 넣어 주세요.")
    return files


# ───────────── 0. peek / test ─────────────
def run_peek(a):
    for f in raw_files(a.folder):
        d = read_csv_any(f, nrows=5, dtype=str)
        print(f'\n== {os.path.basename(f)}\n컬럼: {", ".join(d.columns)}')
        print(d.to_string(index=False)[:1500])
        print('찾은 컬럼:', {k: pick(d, k) for k in COLS})


def run_test(a):
    c = cfg()
    key = c.get('chamgagyeok', 'service_key', fallback='') or c.get('data_go', 'service_key', fallback='')
    url = c.get('chamgagyeok', 'url', fallback='https://apis.data.go.kr/B551919/ProductPriceInfoService')
    op = c.get('chamgagyeok', 'operation', fallback='')
    extra = dict(x.split('=', 1) for x in c.get('chamgagyeok', 'params', fallback='').split('&') if '=' in x)
    if not op:
        print('config.ini [chamgagyeok] operation 이 비어 있어요. 활용신청 후 명세서(Swagger)에 있는 오퍼레이션 이름을 적어 주세요.')
    r = requests.get(f"{url.rstrip('/')}/{op}" if op else url,
                     params={'serviceKey': key, 'pageNo': 1, 'numOfRows': 10, **extra}, timeout=30)
    print('HTTP', r.status_code, r.url.replace(key, '***') if key else r.url)
    print(r.text[:2000])


# ───────────── 1. load ─────────────
def run_load(a):
    parts = []
    for f in raw_files(a.folder):
        d = read_csv_any(f, dtype=str)
        col = {k: pick(d, k) for k in COLS}
        miss = [k for k in ('date', 'name', 'price') if not col[k]]
        if miss:
            print(f'  ✘ {os.path.basename(f)}: {miss} 컬럼을 못 찾음 → peek 로 보고 COLS 에 이름 추가')
            continue
        x = pd.DataFrame({k: d[c] if c else None for k, c in col.items()})
        x['file'] = re.sub(r'\D', '', os.path.basename(f))[-8:] or os.path.basename(f).encode('utf-8', 'replace').decode()   # 파일 날짜만
        parts.append(x)
        print(f'  ✔ {x["file"].iloc[0]}: {len(x):,}줄')
    if not parts:
        sys.exit('읽은 파일이 없어요.')
    d = pd.concat(parts, ignore_index=True)
    d['date'] = pd.to_datetime(d['date'].astype(str).str.replace(r'\D', '', regex=True).str[:8], format='%Y%m%d', errors='coerce')
    d['price'] = pd.to_numeric(d['price'].astype(str).str.replace(r'[^\d.]', '', regex=True), errors='coerce')
    d = d.dropna(subset=['date', 'price'])
    d = d[d['price'] > 0]
    # 용량: 상품명 안의 '300g' 우선, 없으면 용량 · 단위 컬럼
    g = d['name'].map(grams_from)
    if d['volume'].notna().any():
        alt = pd.to_numeric(d['volume'], errors='coerce') * d['unit'].astype(str).str.lower().map(
            lambda u: 1000 if u in ('kg', 'l') else (1 if u in ('g', 'ml') else None))
        g = g.fillna(alt)
    d['grams'] = g
    d['count'] = d['name'].map(count_from)
    d['won_per_g'] = (d['price'] / d['grams']).round(3)
    d['regular'] = ~(d['sale'].astype(str).eq('Y') | d['one_plus_one'].astype(str).eq('Y'))   # 세일 · 1+1 아님
    d = d.drop_duplicates(['date', 'name', 'store', 'price'])
    d.sort_values(['name', 'date']).to_csv(os.path.join(P.PRICE, 'chamgagyeok_items.csv'), index=False, encoding='utf-8-sig')
    days = d['date'].drop_duplicates().sort_values()
    gap = days.diff().dt.days.median()
    print(f"\nchamgagyeok_items.csv {len(d):,}줄 · 상품 {d['name'].nunique():,}개 · 조사일 {len(days)}개 "
          f"({days.min():%Y-%m-%d} ~ {days.max():%Y-%m-%d}, 조사 간격 중앙값 {gap:.0f}일) · 용량(g) 찾은 비율 {d['grams'].notna().mean():.0%}")


# ───────────── 2. map ─────────────
def run_map(a):
    items = read_csv_any(os.path.join(P.PRICE, 'chamgagyeok_items.csv'), usecols=['name'])     # 상품명만 (파일이 커서)
    names = items['name'].dropna().drop_duplicates()
    targets = list(DEFAULT_TARGETS)
    todo = os.path.join(P.PRICE, 'ingredients_to_map.csv')            # kamis map 이 못 찾은 재료
    if os.path.exists(todo):
        t = read_csv_any(todo)
        targets += [x for x in t.head(a.top)['ingredient'] if x not in targets]
    rows = []
    for ing in dict.fromkeys(targets):                           # 중복 제거 (순서 유지)
        hit = names[names.map(lambda n: is_match(ing, n))]
        if len(hit):
            rows.append({'ingredient': ing, 'products': len(hit), 'examples': ' | '.join(hit.head(5))})
    m = pd.DataFrame(rows).sort_values('products', ascending=False)
    m.to_csv(os.path.join(P.PRICE, 'chamgagyeok_map.csv'), index=False, encoding='utf-8-sig')
    print(f'재료 {len(targets)}종 중 참가격 상품이 있는 재료 {len(m)}종 → chamgagyeok_map.csv (예시 상품 보고 틀린 줄은 지우기)')
    print(m.head(30).to_string(index=False))


# ───────────── 3. price ─────────────
def run_price(a):
    items = read_csv_any(os.path.join(P.PRICE, 'chamgagyeok_items.csv'), parse_dates=['date'],
                         usecols=['date', 'name', 'store', 'price', 'grams', 'count', 'won_per_g', 'regular'])
    items = items[items['regular'].astype(str).str.lower().isin(['true', '1'])]            # 세일 · 1+1 은 빼고 정상가로
    try:                                                                                      # g 없는 '3개입' 상품 → 재료 1개 무게로
        import ingredient_clean as ic
        weight = ic.load_tables()[2]
    except Exception:
        weight = {}
    m = read_csv_any(os.path.join(P.PRICE, 'chamgagyeok_map.csv'))
    out = []
    for ing in m['ingredient'].drop_duplicates():
        ok = {n for n in items['name'].unique() if is_match(ing, n)}
        x = items[items['name'].isin(ok)].copy()
        w1 = weight.get((ing, '개')) or weight.get((ing, '봉'))
        if w1:
            miss = x['grams'].isna() & x['count'].notna()
            x.loc[miss, 'won_per_g'] = x.loc[miss, 'price'] / (x.loc[miss, 'count'] * w1)
        x = x.dropna(subset=['won_per_g'])
        if len(x):
            g = x.groupby('date').agg(products=('name', 'nunique'), stores=('store', 'nunique')).reset_index()
            # 상품마다 그날 평균 g당 가격 → 상품들의 중앙값 (매장 수가 많은 상품 쪽으로 쏠리지 않게)
            pv = x.groupby(['name', 'date'])['won_per_g'].mean().unstack('name').sort_index()
            g['won_per_g'] = g['date'].map(pv.median(axis=1))
            # 직전 조사 대비: 같은 상품끼리 비교한 변화율의 중앙값 (조사 상품이 바뀌어도 흔들리지 않게)
            g['prev_pct'] = g['date'].map((pv.pct_change(fill_method=None).median(axis=1) * 100).round(1))
            g.insert(0, 'ingredient', ing)
            out.append(g)
    if not out:
        sys.exit('g당 가격을 낼 수 있는 재료가 없어요. load 의 용량(g) 비율을 확인해 주세요.')
    p = pd.concat(out).sort_values(['ingredient', 'date'])
    p['won_per_g'] = p['won_per_g'].round(3)
    p.to_csv(os.path.join(P.PRICE, 'chamgagyeok_price.csv'), index=False, encoding='utf-8-sig')

    last = p.groupby('ingredient').tail(1).set_index('ingredient')
    p['month'] = p['date'].dt.to_period('M')
    mon = p.groupby(['ingredient', 'month'])['won_per_g'].mean()
    mom = []
    for ing, r in last.iterrows():
        cur, prev = r['date'].to_period('M'), r['date'].to_period('M') - 1
        mom.append(round((mon.get((ing, cur)) / mon.get((ing, prev)) - 1) * 100, 1) if (ing, prev) in mon else None)
    last['mom_pct'] = mom                                                                  # 전월 대비
    last.reset_index()[['ingredient', 'date', 'won_per_g', 'products', 'stores', 'prev_pct', 'mom_pct']].to_csv(
        os.path.join(P.PRICE, 'chamgagyeok_change.csv'), index=False, encoding='utf-8-sig')
    print(f"chamgagyeok_price.csv {len(p):,}줄 · 재료 {p['ingredient'].nunique()}종")
    print(last[['date', 'won_per_g', 'prev_pct', 'mom_pct']].head(20).to_string())


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['peek', 'test', 'load', 'map', 'price'])
    ap.add_argument('folder', nargs='?', default=P.PRICE, help=argparse.SUPPRESS)   # 예전 'data' 인자도 받기만 함
    ap.add_argument('--top', type=int, default=100, help='map: ingredients_to_map.csv 에서 볼 상위 재료 수')
    a = ap.parse_args()
    {'peek': run_peek, 'test': run_test, 'load': run_load, 'map': run_map, 'price': run_price}[a.cmd](a)
