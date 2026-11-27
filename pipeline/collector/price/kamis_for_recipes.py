"""만개의레시피 정제 재료에 KAMIS 시세 붙이기 (공공데이터포털 'KAMIS 일별 도·소매 가격정보')

준비
  config.ini 의 [data_go] service_key
  python clean/ingredient_clean.py   → data/clean 에 recipe_ingredients_clean.csv · ingredient_dictionary.csv

실행 (프로젝트 폴더에서. 읽고 쓰는 위치는 paths.py)
  python price/kamis_for_recipes.py test                 # 0. 키 · 연결 확인
  python price/kamis_for_recipes.py codes          # 1. 코드표 엑셀(dict/kamis_code_table.xlsx) → kamis_codes.csv
  python price/kamis_for_recipes.py map          # 2. 표준 재료명 ↔ KAMIS 품목 자동 매핑 → kamis_item_map.csv
  python price/kamis_for_recipes.py fetch          # 3. 시세 받기 (최근 13개월 + 평년용 작년 같은 달)
  python price/kamis_for_recipes.py fetch --months auto   #    레시피 가장 옛날 달부터 (매일 주기 작업은 이걸로)
  python price/kamis_for_recipes.py join          # 4. 레시피 재료비 계산

1. codes  공공데이터포털 참고문서 '(참고)일별 도,소매 가격정보_코드.xlsx' 를 dict/kamis_code_table.xlsx 로 저장해 두면 읽음 (API 요청 없음)
2. map    ingredient_dictionary.csv 의 재료 이름을 KAMIS 품종 · 품목 이름과 맞추고,
          품목마다 최근 30일 소매 값을 한 번 불러 실제 조사되는 품종 · 등급 · 단위를 고름
          이미 kamis_item_map.csv 에 있는 줄(직접 적은 것)은 그대로 두고, 새로 찾은 것만 추가 (memo = 자동: …)
          결과: kamis_item_map.csv · kamis_map_review.csv (자동 매핑 확인용) · ingredients_to_map.csv (못 찾은 재료)
3. fetch  kamis_raw.csv · kamis_daily.csv · kamis_monthly.csv (소매/도매 평균 · 평년 · 평년 대비 %)
4. join   recipe_ingredient_price.csv  재료 줄마다 g · g당 가격 · 재료비 (등록 월 시세 / 최근 월 시세)
          recipe_price.csv             레시피마다 재료비 합계 · 1인분 재료비 · 시세 붙은 비율 · 물가 지수
"""
import os, re, sys, json, time, argparse, datetime, configparser, collections
import requests
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths as P
import ingredient_clean as ic                     # 무게표 · 단위 동의어를 같이 씀

URL = 'https://apis.data.go.kr/B552845/perDay/price'
HERE = os.path.dirname(os.path.abspath(__file__))
MAP = P.KAMIS_MAP
CONFIG = P.CONFIG
CLS = {'01': '소매', '02': '도매'}
TIMEOUT = 30
# [재료] 묶음에 섞여 나와도 시세를 붙이지 않는 것
SKIP = {'물', '생수', '찬물', '뜨거운물', '얼음', '얼음물', '육수', '쌀뜨물'}
_KEY = None
# 계절마다 품종이 바뀌거나(봄배추 · 가을배추 …) 코드가 바뀐 품목은 품종 구분 없이 받아 1년 내내 이어지게
# 이름으로 보는 소스 · 양념 (오일 · 육수 · ~액 · ~청 · 술 · 향신료 …) → 재료비에서 뺌
SAUCE = re.compile(r'오일|기름|육수|스톡|다시다|미원|소스|드레싱|시즈닝|쯔유|맛술|미림|청주|소주|와인|식초|케첩|마요네즈|머스타드|'
                   r'액$|청$|즙$|분말$|전분|녹말|파슬리|바질가루|월계수|페페론치노|시나몬|카레가루|후추|깨$|소금|설탕|알룰로스|올리고당|물엿|조청|꿀$')
ALL_KINDS = {'111', '121', '211', '212', '231', '232', '251', '254', '411', '412', '415', '416', '421'}


def key():
    global _KEY
    if _KEY:
        return _KEY
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG, encoding='utf-8')
    k = cfg.get('data_go', 'service_key', fallback='').strip()
    if not k or k.startswith('여기에'):
        sys.exit(f'{CONFIG} 의 [data_go] service_key 를 채워 주세요. (공공데이터포털 일반 인증키 Decoding)')
    _KEY = k
    return k


def norm(s):
    return re.sub(r'\s+', '', str(s or ''))


def code(v):
    return str(v or '').strip().zfill(2)


def get_page(cond, page, verbose=False):
    p = {'serviceKey': key(), 'pageNo': str(page), 'numOfRows': '1000', 'returnType': 'JSON', **cond}
    for attempt in range(3):
        try:
            t0 = time.time()
            r = requests.get(URL, params=p, timeout=TIMEOUT)
            if verbose:
                print(f'    응답 {time.time() - t0:.1f}초 · HTTP {r.status_code}')
            d = r.json()
            body = d.get('body') or (d.get('response') or {}).get('body') or {}
            head = d.get('header') or (d.get('response') or {}).get('header') or {}
            if str(head.get('resultCode', '0')) not in ('0', '00'):
                print(f"    API 응답: {head.get('resultCode')} {head.get('resultMsg')}")
            items = (body.get('items') or {}).get('item') or []
            return (items if isinstance(items, list) else [items]), int(body.get('totalCount') or 0)
        except (requests.RequestException, ValueError) as e:
            print(f'    재시도 {attempt + 1}/3: {str(e)[:150]}')
            time.sleep(3)
    return [], 0


def fetch_range(cat, item, d_from, d_to, verbose=False, kind=None, rank=None):
    """d_from, d_to = 'YYYYMMDD'. 품종 · 등급을 주면 서버에서 먼저 걸러 받음 (행 수가 크게 줄어듦)"""
    cond = {'cond[exmn_ymd::GTE]': d_from, 'cond[exmn_ymd::LTE]': d_to,
            'cond[ctgry_cd::EQ]': cat, 'cond[item_cd::EQ]': item}
    if kind:
        cond['cond[vrty_cd::EQ]'] = kind
    if rank:
        cond['cond[grd_cd::EQ]'] = rank
    items, total = get_page(cond, 1, verbose)
    page = 1
    while len(items) < total and page < 50:
        page += 1
        more, _ = get_page(cond, page)
        if not more:
            break
        items += more
    return items


def to_rows(items, kind, rank):
    out = []
    for i in items:
        if code(i.get('se_cd')) not in CLS or code(i.get('grd_cd')) != code(rank):
            continue
        if kind and code(i.get('vrty_cd')) != code(kind):
            continue
        try:
            price = float(str(i.get('exmn_dd_prc')).replace(',', ''))
        except ValueError:
            continue
        if price <= 0:
            continue
        ymd = re.sub(r'\D', '', str(i.get('exmn_ymd')))
        out.append({'date': f'{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}', 'cls': CLS[code(i.get('se_cd'))], 'price': price,
                    'market': i.get('mrkt_nm'), 'unit': f"{i.get('unit_sz') or ''}{i.get('unit') or ''}"})
    return out


def read_csv_any(path, **kw):
    """엑셀에서 저장해 cp949 가 된 CSV 도 읽기"""
    for enc in ('utf-8-sig', 'cp949'):
        try:
            return pd.read_csv(path, encoding=enc, **kw)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, encoding='utf-8', encoding_errors='replace', **kw)


def load_map():
    m = read_csv_any(MAP, dtype=str, keep_default_na=False)
    for c in ('category_code', 'item_code', 'kind_code', 'rank_code'):
        m[c] = m[c].str.strip()
    m['rank_code'] = m['rank_code'].replace('', '04')
    m['key'] = m['ingredient'].map(norm)
    return m


def ingredient_rows(folder):
    ing = pd.read_csv(os.path.join(P.CLEAN, 'recipe_ingredients_clean.csv'))
    ing['key'] = ing['std_name'].map(norm)
    return ing[~ing['key'].isin(SKIP)]


def ymd(d):
    return d.strftime('%Y%m%d')


# ───────────── 0. test ─────────────
def run_test(a):
    end = datetime.date.today()
    print('양파(200/245) 최근 2주 요청 중…')
    items = fetch_range('200', '245', ymd(end - datetime.timedelta(days=14)), ymd(end), verbose=True)
    print(f'받은 행 {len(items)}개')
    if items:
        print('첫 행:', json.dumps(items[0], ensure_ascii=False)[:400])
        rows = to_rows(items, '00', '04')
        print(f"소매 · 상품 · 품종 00: {sum(r['cls'] == '소매' for r in rows)}행 / 도매: {sum(r['cls'] == '도매' for r in rows)}행")


# ───────────── 1. codes ─────────────
CODE_XLSX = P.KAMIS_CODE_XLSX       # 공공데이터포털 참고문서 '(참고)일별 도,소매 가격정보_코드.xlsx'


def run_codes(a):
    """공식 코드표 엑셀 → kamis_codes.csv (API 요청 없음)"""
    path = a.xlsx or CODE_XLSX
    if not os.path.exists(path):
        sys.exit(f'{path} 가 없어요. 코드표 엑셀을 이 이름으로 스크립트 폴더에 두거나 --xlsx 로 경로를 주세요.')
    rd = lambda sh: pd.read_excel(path, sheet_name=sh, dtype=str).apply(lambda c: c.str.strip())
    cat, item, kind, grade = rd('부류코드'), rd('품목코드'), rd('품종코드'), rd('등급코드')
    d = (grade.merge(kind, on=['부류코드', '품목코드', '품종코드'], how='left')
              .merge(item, on=['부류코드', '품목코드'], how='left').merge(cat, on='부류코드', how='left'))
    d = d.rename(columns={'부류코드': 'category_code', '부류명': 'category_name', '품목코드': 'item_code', '품목명': 'item_name',
                          '품종코드': 'kind_code', '품종명': 'kind_name', '등급코드': 'rank_code', '등급명': 'rank_name'})
    d = d[~d['item_code'].between('351', '359')]                # 꽃 제외
    cols = ['category_code', 'category_name', 'item_code', 'item_name', 'kind_code', 'kind_name', 'rank_code', 'rank_name']
    d[cols].sort_values(cols[:7]).to_csv(os.path.join(P.PRICE, 'kamis_codes.csv'), index=False, encoding='utf-8-sig')
    print(f"kamis_codes.csv {len(d):,}줄 · 품목 {d['item_code'].nunique()}개 · 품종 {d.groupby(['item_code', 'kind_code']).ngroups}개")


# ───────────── 2. map ─────────────
# 이름만으로는 안 맞는 것: 표준 재료명 → (KAMIS 품목 이름, 품종 이름에 들어 있는 말)
HINT = {'돼지고기': ('돼지', '앞다리'), '다진돼지고기': ('돼지', '앞다리'), '돼지앞다리살': ('돼지', '앞다리'), '앞다리살': ('돼지', '앞다리'),
        '목살': ('돼지', '목심'), '돼지목살': ('돼지', '목심'), '돼지갈비': ('돼지', '갈비'),
        '소고기': ('소', '설도'), '다진소고기': ('소', '설도'), '소불고기': ('소', '설도'), '불고기': ('소', '설도'),
        '소고기양지': ('소', '양지'), '양지': ('소', '양지'), '소갈비': ('소', '갈비'), '소등심': ('소', '등심'),
        '닭고기': ('닭', '육계'), '닭': ('닭', '육계'), '생닭': ('닭', '육계'), '닭볶음탕용닭': ('닭', '육계'), '토종닭': ('닭', '토종'),
        '계란': ('계란', '특란'), '달걀': ('계란', '특란'),
        '마늘': ('깐마늘', '깐마늘'), '다진마늘': ('깐마늘', '깐마늘'), '통마늘': ('깐마늘', '깐마늘'), '깐마늘': ('깐마늘', '깐마늘'),
        '파': ('파', '대파'), '홍고추': ('붉은고추', ''), '오이고추': ('풋고추', '오이맛'), '아삭이고추': ('풋고추', '오이맛'),
        '알배추': ('알배기배추', ''), '오징어': ('물오징어', ''), '멸치': ('마른멸치', ''), '국물멸치': ('마른멸치', ''),
        '다시마': ('건다시마', ''), '미역': ('마른미역', ''), '건미역': ('마른미역', ''), '북어채': ('북어', ''), '황태채': ('북어', ''),
        '키위': ('참다래', ''), '귤': ('감귤', ''), '우유': ('우유', ''),
        '돼지고기앞다리살': ('돼지', '앞다리'), '다짐돼지고기': ('돼지', '앞다리'), '다진돼지앞다리살': ('돼지', '앞다리'),
        '닭가슴살': ('닭', '육계'), '닭다리살': ('닭', '육계'), '닭안심': ('닭', '육계'), '닭다리': ('닭', '육계'), '닭봉': ('닭', '육계'),
        '닭날개': ('닭', '육계'), '닭볶음탕용': ('닭', '육계'), '백미': ('쌀', ''), '현미': ('쌀', ''), '쌀': ('쌀', ''),
        '김밥김': ('김', ''), '김가루': ('김', ''), '조미김': ('김', ''), '황태': ('북어', ''), '먹태': ('북어', '')}


# 이름이 겹쳐도 다른 재료 (옥수수 → 수수, 쑥갓 → 갓, 밤 → 고구마 '밤' 품종 …)
NO_MATCH = {'옥수수', '찰옥수수', '밤', '깐밤', '쑥갓', '묵은지', '김치', '배추김치', '총각무', '밤고구마', '늙은호박', '밥새우', '마늘참깨', '절임생강',
            '생선', '단호박', '미니단호박', '커피우유', '홀토마토', '딸기우유', '바나나우유'}


def field(i, p):
    v = i.get(f'{p}_nm')
    return str(v).strip() if v not in (None, '') else ''


def nn(s):
    return norm(re.sub(r'\(.*?\)', '', str(s or '')))


def probe(cat, item, kind_codes, cache):
    """실제 조사되는 품종 · 등급 · 단위 고르기. 소매 최근 30일 → 소매 90일 → 도매 30일 순 (상품 · 1등급 우선, 조사 건수 많은 순)"""
    if (cat, item) not in cache:
        end = datetime.date.today()
        got = fetch_range(cat, item, ymd(end - datetime.timedelta(days=30)), ymd(end))
        if not any(code(i.get('se_cd')) == '01' for i in got):
            got += [i for i in fetch_range(cat, item, ymd(end - datetime.timedelta(days=90)), ymd(end - datetime.timedelta(days=31)))
                    if code(i.get('se_cd')) == '01']
        cache[(cat, item)] = got
        time.sleep(0.2)
    allrows = [i for i in cache[(cat, item)] if not kind_codes or code(i.get('vrty_cd')) in kind_codes]
    for se in ('01', '02'):
        rows = [i for i in allrows if code(i.get('se_cd')) == se]
        if rows:
            break
    if not rows:
        return None
    c = collections.Counter((str(i.get('vrty_cd')), field(i, 'vrty'), str(i.get('grd_cd')), field(i, 'grd'),
                             f"{i.get('unit_sz') or ''}{i.get('unit') or ''}") for i in rows)
    (kd, kn, rk, rn, unit), n = sorted(c.items(), key=lambda x: ('상품' in x[0][3], x[0][3] == '1등급', x[1]), reverse=True)[0]
    return {'kind_code': kd, 'rank_code': rk, 'kamis_name': f"{field(rows[0], 'item')} / {kn} / {rn}", 'unit': unit,
            'cls': CLS[se], 'rows': n}


def run_map(a):
    codes = read_csv_any(os.path.join(P.PRICE, 'kamis_codes.csv'), dtype=str, keep_default_na=False)
    codes['item_n'] = codes['item_name'].map(nn)
    codes['kind_n'] = codes['kind_name'].map(nn)
    dic = read_csv_any(os.path.join(P.CLEAN, 'ingredient_dictionary.csv'))
    dic['key'] = dic['std_name'].map(norm)
    dic = dic[~dic['key'].isin(SKIP)]

    def find(k):
        """→ (후보 코드 줄, 방식, 품종을 고정할지)"""
        if k in NO_MATCH:
            return None
        if k in HINT:
            it, kd = HINT[k]
            c = codes[(codes['item_n'] == it) & codes['kind_n'].str.contains(kd)]
            if len(c):
                return c, '힌트', bool(kd)
        c = codes[(codes['kind_n'] == k) | (codes['kind_n'] + codes['item_n'] == k) | (codes['item_n'] + codes['kind_n'] == k)]
        if len(c):
            return c, '품종 이름', True
        c = codes[codes['item_n'] == k]
        if len(c):
            return c, '품목 이름', False
        dried = k.startswith(('건', '마른', '말린'))                # 건새우 ≠ 새우, 건표고버섯 ≠ 표고버섯
        c = codes[codes['item_n'].map(lambda x: k.endswith(x) and 0 < len(k) - len(x) <= 2 and len(x) >= 2
                                      and not (dried and not x.startswith(('건', '마른'))))]
        if len(c):                                          # 적양배추 → 양배추, 다진양파 → 양파 (확인 필요)
            best = c['item_n'].str.len().max()
            return c[c['item_n'].str.len() == best], '부분 일치 (확인)', False
        return None

    m = load_map()
    m = m[~m['memo'].astype(str).str.startswith('자동')].reset_index(drop=True)   # 자동 줄은 매번 새로 찾음
    have = set(m['key'])
    cache, add, review, miss = {}, [], [], []
    todo = dic[~dic['key'].isin(have)]
    print(f'재료 {len(dic):,}종 중 직접 매핑 {len(have & set(dic["key"]))}종 · 나머지 이름으로 찾는 중…')
    for _, r in todo.iterrows():
        f = find(r['key'])
        if not f:
            miss.append({'ingredient': r['std_name'], 'recipes': r['recipes'], 'reason': '이름 없음'})
            continue
        c, how, fix_kind = f
        p = None
        for (cat, item), cc in c.groupby(['category_code', 'item_code'], sort=True):   # 계란 516 · 9903 처럼 코드가 여럿이면 값 있는 쪽
            p = probe(cat, item, set(cc['kind_code'].map(code)) if fix_kind else None, cache)
            if not p and fix_kind:
                p = probe(cat, item, None, cache)
                if p:
                    how += ' · 품종 없음 → 품목 대표'
            if p:
                break
        if not p:
            miss.append({'ingredient': r['std_name'], 'recipes': r['recipes'], 'reason': f"최근 30일 소매 값 없음 ({c.iloc[0]['item_name']})"})
            continue
        add.append({'ingredient': r['std_name'], 'category_code': cat, 'item_code': item, 'kind_code': p['kind_code'],
                    'rank_code': p['rank_code'], 'memo': f"자동: {how} · {p['kamis_name']} · {p['unit']}" + (' · 도매만' if p['cls'] == '도매' else '')})
        review.append({'ingredient': r['std_name'], 'recipes': r['recipes'], 'match': how, 'category_code': cat, 'item_code': item, **p})
    bad = []
    for i, r in m.iterrows():                               # 직접 적은 줄도 실제 조사되는 품종 · 등급 코드로 다시 맞춤
        cat, item, note = r['category_code'], r['item_code'], ''
        p = probe(cat, item, {code(r['kind_code'])} if r['kind_code'] else None, cache)
        if not p and r['kind_code']:                        # 적어 둔 품종 코드가 바뀌었으면 이름이 같은 품종 → 아무 품종 순
            same = codes[(codes['category_code'] == cat) & (codes['item_code'] == item) & (codes['kind_n'] == r['key'])]
            p = probe(cat, item, set(same['kind_code'].map(code)), cache) if len(same) else None
            if not p:
                p, note = probe(cat, item, None, cache), ' (품종 바뀜, 확인)'
        if p:
            m.loc[i, ['kind_code', 'rank_code']] = p['kind_code'], p['rank_code']
            if not str(m.loc[i, 'memo']).startswith('자동'):
                m.loc[i, 'memo'] = f"직접{note} · {p['kamis_name']} · {p['unit']}" + (' · 도매만' if p['cls'] == '도매' else '')
        else:
            bad.append(r['ingredient'])
    if bad:
        print('직접 매핑인데 최근 30일 소매 값이 없는 재료 (코드 확인):', ', '.join(bad))
    out = pd.concat([m.drop(columns='key'), pd.DataFrame(add)], ignore_index=True)
    out.to_csv(MAP, index=False, encoding='utf-8-sig')
    for rows, name in ((review, 'kamis_map_review.csv'), (miss, 'ingredients_to_map.csv')):
        pd.DataFrame(rows, columns=None if rows else ['ingredient', 'recipes']).sort_values('recipes', ascending=False).to_csv(
            os.path.join(P.PRICE, name), index=False, encoding='utf-8-sig')
    rv = pd.DataFrame(review)
    keys = have | {norm(x['ingredient']) for x in add}
    print(f'자동 매핑 {len(add)}종 · 못 찾음 {len(miss)}종 (API 요청 {len(cache)}번)')
    if len(rv):
        print('자동 매핑 방식:', ', '.join(f'{k} {v}' for k, v in rv['match'].value_counts().items()))
    main = dic[dic['seasoning_share'] < 0.5]
    print(f"재료 등장 기준 커버율: 전체 {dic[dic['key'].isin(keys)]['recipes'].sum() / dic['recipes'].sum():.0%}"
          f" · 주재료 {main[main['key'].isin(keys)]['recipes'].sum() / main['recipes'].sum():.0%}")
    print('→ kamis_map_review.csv 의 "부분 일치 (확인)" 줄을 확인하고, 틀린 줄은 kamis_item_map.csv 에서 지우거나 고치세요.')


# ───────────── 2. fetch ─────────────
def months_to_fetch(n_recent, normal_years):
    today = datetime.date.today().replace(day=1)
    recent = [(pd.Timestamp(today) - pd.DateOffset(months=k)).date() for k in range(n_recent)]
    want = set(recent)
    for d in recent:                                     # 평년 계산용: 같은 달 과거 N년
        for y in range(1, normal_years + 1):
            want.add(d.replace(year=d.year - y))
    return sorted(want)


def auto_months():
    """레시피 중 가장 옛날 등록 월부터 이번 달까지 개월 수 (만개를 과거로 더 받으면 자동으로 늘어남)"""
    import json as _json                                 # 2026-11-25: 정제 파일 대신 수집 원본에서 읽음 (collect는 수집만)
    first = None
    with open(P.RECIPES_JSONL, encoding='utf-8') as f:
        for line in f:
            try:
                ym = str(_json.loads(line).get('published_at') or '')[:7]
            except ValueError:
                continue
            if len(ym) == 7 and (first is None or ym < first):
                first = ym
    if first is None:
        return 13
    y, m = map(int, first.split('-'))
    t = datetime.date.today()
    return max(13, (t.year - y) * 12 + (t.month - m) + 1)


def _add_normal(mon, n_years):
    """평년 = 과거 N년 같은 달 평균 (그 해 제외) — 2026-11-25: 행마다 전체를 훑던 것을 merge 한 번으로"""
    k = ['key', 'cls', 'mm']
    past = mon[k + ['yyyy', 'avg_price']].rename(columns={'yyyy': 'p_yyyy', 'avg_price': 'p_price'})
    j = mon[k + ['yyyy']].merge(past, on=k)
    j = j[(j['p_yyyy'] < j['yyyy']) & (j['p_yyyy'] >= j['yyyy'] - n_years)]
    nm = j.groupby(k + ['yyyy'])['p_price'].mean().round(0).rename('normal_price')
    return mon.join(nm, on=k + ['yyyy'])


def run_fetch(a):
    if str(a.months) == 'auto':
        a.months = auto_months()
        print(f'--months auto → 레시피 가장 옛날 달부터 {a.months}개월')
    a.months = int(a.months)
    m = load_map()
    m = m[m['kind_code'] != ''].drop_duplicates('key')   # 2026-11-25: 정제 파일 대신 사전(kamis_item_map) 전체를 받음
    m = m.drop_duplicates(['category_code', 'item_code', 'kind_code', 'rank_code', 'key'])
    m = m.sort_values(['ingredient', 'key'], kind='stable')   # 파일을 재료 순서대로 덧붙여 씀
    months = months_to_fetch(a.months, a.normal_years)
    today = datetime.date.today()
    print(f'재료 {len(m)}종 × {len(months)}개월 (최근 {a.months}개월 + 평년용 과거 {a.normal_years}년)', flush=True)
    cache_dir = P.KAMIS_CACHE      # 받은 달은 저장해 두고 다시 안 받음
    os.makedirs(cache_dir, exist_ok=True)
    this_month = today.replace(day=1)
    # 2026-11-25: 전 재료 원본을 메모리에 모으면 5년치에서 1GB+ → 재료 하나씩 처리해 파일에 바로 덧붙이고 월평균만 남김
    out_raw = os.path.join(P.PRICE, 'kamis_raw.csv')
    out_daily = os.path.join(P.PRICE, 'kamis_daily.csv')
    tmp_raw, tmp_daily = out_raw + '.tmp', out_daily + '.tmp'
    f_raw = open(tmp_raw if getattr(a, 'raw', False) else os.devnull, 'w', encoding='utf-8-sig', newline='')   # 2026-11-25: 아무도 안 읽어(몽고는 캐시 json) 기본은 안 씀, --raw 로 켬
    f_daily = open(tmp_daily, 'w', encoding='utf-8-sig', newline='')
    head_raw = head_daily = True
    n_raw = n_daily = 0
    mons = []
    try:
        for _, r in m.iterrows():
            t0, hit = time.time(), 0
            cols = {c: [] for c in ('date', 'cls', 'price', 'market', 'unit')}
            for d in months:
                kd = 'all' if r['item_code'] in ALL_KINDS else r['kind_code']
                path = os.path.join(cache_dir, f"{r['category_code']}_{r['item_code']}_{kd}_{r['rank_code']}_{d:%Y%m}.json")
                done_at = time.mktime((pd.Timestamp(d) + pd.DateOffset(months=1, days=1)).timetuple())   # 다음 달 2일 0시
                if os.path.exists(path) and d < this_month and os.path.getmtime(path) >= done_at:   # 2026-11-25: 이번 달 · 달이 끝나기 전에 받은 캐시(마지막 날 빠짐)는 다시 받음
                    with open(path, encoding='utf-8') as fh:
                        rows = json.load(fh)
                    hit += 1
                else:
                    last = min((pd.Timestamp(d) + pd.offsets.MonthEnd(0)).date(), today)
                    kind = None if r['item_code'] in ALL_KINDS else r['kind_code']
                    items = fetch_range(r['category_code'], r['item_code'], ymd(d), ymd(last), kind=kind, rank=r['rank_code'])
                    rows = to_rows(items, kind, r['rank_code'])
                    with open(path, 'w', encoding='utf-8') as fh:
                        json.dump(rows, fh, ensure_ascii=False)
                for x in rows:
                    cols['date'].append(x.get('date')); cols['cls'].append(x.get('cls'))
                    cols['price'].append(x.get('price')); cols['market'].append(x.get('market'))
                    cols['unit'].append(x.get('unit'))
                del rows
            n = len(cols['price'])
            print(f"  {r['ingredient']}: {n:,}행 · {time.time() - t0:.0f}초 (저장본 {hit}개월)"
                  + ('  ← 값 없음: map 을 다시 돌려 코드 확인' if n == 0 else ''), flush=True)
            if n == 0:
                continue
            di = pd.DataFrame(cols)
            del cols
            di.insert(0, 'ingredient', r['ingredient'])
            di.insert(1, 'key', r['key'])
            di.drop(columns='key').sort_values(['date', 'cls', 'market']).to_csv(
                f_raw, header=head_raw, index=False)                                   # 시장별 원본
            head_raw = False
            n_raw += n
            # 시장마다 단위가 다를 수 있어 재료 · 도소매별로 가장 많은 단위만 사용
            top_unit = di.groupby('cls')['unit'].agg(lambda s: s.value_counts().index[0])
            di = di[di['unit'] == di['cls'].map(top_unit)]
            daily = di.groupby(['ingredient', 'key', 'date', 'cls', 'unit']).agg(
                avg_price=('price', 'mean'), markets=('market', 'nunique')).reset_index()
            del di
            daily['avg_price'] = daily['avg_price'].round(0)
            daily.to_csv(f_daily, header=head_daily, index=False)
            head_daily = False
            n_daily += len(daily)
            daily['month'] = daily['date'].str[:7]
            mons.append(daily.groupby(['ingredient', 'key', 'cls', 'month'])['avg_price'].mean().round(0).reset_index())
            del daily
    finally:
        f_raw.close(); f_daily.close()
    if not mons:
        os.remove(tmp_daily)
        if getattr(a, 'raw', False): os.remove(tmp_raw)
        sys.exit('받은 값이 없어요. test · check 를 먼저 확인해 주세요.')
    if getattr(a, 'raw', False):
        os.replace(tmp_raw, out_raw)
    os.replace(tmp_daily, out_daily)

    mon = pd.concat(mons, ignore_index=True)
    del mons
    mon['mm'] = mon['month'].str[5:]
    mon['yyyy'] = mon['month'].str[:4].astype(int)
    mon = _add_normal(mon, a.normal_years)
    wide = mon.pivot_table(index=['ingredient', 'key', 'month'], columns='cls', values=['avg_price', 'normal_price'])
    wide.columns = [f'{"retail" if c == "소매" else "wholesale"}_{"avg" if v == "avg_price" else "normal"}' for v, c in wide.columns]
    wide = wide.reset_index()
    recent = {d.strftime('%Y-%m') for d in months[-a.months:]} | {datetime.date.today().strftime('%Y-%m')}
    wide = wide[wide['month'] >= min(recent)]
    if {'retail_avg', 'retail_normal'} <= set(wide.columns):
        wide['vs_normal_pct'] = ((wide['retail_avg'] / wide['retail_normal'] - 1) * 100).round(1)
    wide.to_csv(os.path.join(P.PRICE, 'kamis_monthly.csv'), index=False, encoding='utf-8-sig')
    print(f'\nkamis_raw.csv {n_raw:,}줄 · kamis_daily.csv {n_daily:,}줄 · kamis_monthly.csv {len(wide):,}줄 (최근 {a.months}개월)')


# ───────────── 4. join ─────────────
UNIT_EXTRA = {'구': '개', '속': '개', '입': '개'}


def unit_grams(unit, ing, weight):
    """KAMIS 단위 → g. '1kg' 1000 · '100g' 100 · '10개' 양파면 10 × 200 · '30구' 계란 30 × 50"""
    m = re.match(r'([\d.]+)\s*(.*)', str(unit or '').strip())
    if not m:
        return None
    n, u = float(m.group(1)), m.group(2).strip().lower()
    if u in ('kg', '킬로'):
        return n * 1000
    if u in ('g', '그램'):
        return n
    if u in ('l', '리터'):
        return n * 1000
    if u == 'ml':
        return n
    u = UNIT_EXTRA.get(u, u)
    name = norm(ing)
    w = ic.lookup_weight(name, u, weight)                # 재료 그대로 (기본값 포함)
    for i in range(1, len(name) - 1):                    # 없으면 뒤쪽 이름: 빨간파프리카 → 파프리카, 채썬오이 → 오이
        if w:
            break
        if (name[i:], u) in weight or (name[i:], ic.UNIT_SYNONYM.get(u)) in weight:
            w = ic.lookup_weight(name[i:], u, weight)
    return n * w if w else None


def load_recipes(folder):
    rec = {}
    for line in open(os.path.join(P.RAW, 'recipes.jsonl'), encoding='utf-8'):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        rec[r['recipe_id']] = {k: r.get(k) for k in ('recipe_id', 'title', 'published_at', 'servings', 'time',
                                                      'difficulty', 'views', 'rating', 'review_count')}
    d = pd.DataFrame(rec.values())
    d['month'] = d['published_at'].astype(str).str[:7]
    d['servings_n'] = d['servings'].map(ic.parse_servings)
    return d


def price_table(folder, weight):
    """재료(key) × 월 → g당 가격. 재료마다 출처 하나: KAMIS 소매 → 참가격 → KAMIS 도매"""
    daily = pd.read_csv(os.path.join(P.PRICE, 'kamis_daily.csv'))
    mon = pd.read_csv(os.path.join(P.PRICE, 'kamis_monthly.csv'))
    name = daily.drop_duplicates('key').set_index('key')['ingredient']
    parts, no_unit = [], []
    for cls, col, src in (('소매', 'retail_avg', 'KAMIS 소매'), ('도매', 'wholesale_avg', 'KAMIS 도매')):
        if col not in mon:
            continue
        unit = daily[daily['cls'] == cls].groupby('key')['unit'].agg(lambda s: s.value_counts().index[0])
        ug = {k: unit_grams(u, name[k], weight) for k, u in unit.items()}
        no_unit += [f'{name[k]}({unit[k]})' for k, v in ug.items() if not v and cls == '소매']
        x = mon[['key', 'month', col]].dropna().rename(columns={col: 'price'})
        x['unit'] = x['key'].map(unit)
        x['won_per_g'] = x['price'] / x['key'].map(ug)
        x['source'] = src
        parts.append(x.dropna(subset=['won_per_g']))
    cg = os.path.join(P.PRICE, 'chamgagyeok_price.csv')
    if os.path.exists(cg):
        c = read_csv_any(cg)
        c['key'] = c['ingredient'].map(norm)
        c['month'] = c['date'].astype(str).str[:7]
        c = c.groupby(['key', 'month'], as_index=False)['won_per_g'].mean()
        c['source'], c['unit'], c['price'] = '참가격', 'g', c['won_per_g']
        parts.insert(1, c)                                       # 우선순위: KAMIS 소매 · 참가격 · KAMIS 도매
    p = pd.concat(parts, ignore_index=True)
    order = {'KAMIS 소매': 0, '참가격': 1, 'KAMIS 도매': 2}
    best = p.assign(o=p['source'].map(order)).groupby('key')['o'].min()
    p = p[p['source'].map(order) == p['key'].map(best)]
    return p[['key', 'month', 'source', 'unit', 'price', 'won_per_g']], no_unit


def run_join(a):
    _, _, weight, _ = ic.load_tables()
    rec = load_recipes(a.folder)
    ing = ingredient_rows(a.folder)
    p, no_unit = price_table(a.folder, weight)
    p.to_csv(os.path.join(P.PRICE, 'ingredient_price_monthly.csv'), index=False, encoding='utf-8-sig')
    latest = p.sort_values('month').groupby('key').tail(1).set_index('key')

    x = ing.merge(rec[['recipe_id', 'month']], on='recipe_id', how='left')
    x = x.merge(p[['key', 'month', 'won_per_g']], on=['key', 'month'], how='left')
    x['source'] = x['key'].map(latest['source'])
    x['won_per_g_now'] = x['key'].map(latest['won_per_g'])
    x['cost_at_publish'] = (x['grams'] * x['won_per_g']).round(0)
    x['cost_now'] = (x['grams'] * x['won_per_g_now']).round(0)
    share = {}
    dpath = os.path.join(P.CLEAN, 'ingredient_dictionary.csv')
    if os.path.exists(dpath):                                # [재료] 묶음에 섞여 나온 굴소스 · 맛술도 양념으로
        dic = read_csv_any(dpath)
        share = dict(zip(dic['std_name'].map(norm), dic['seasoning_share']))
    x['seasoning'] = (x['is_seasoning'].astype(str).str.lower().isin(['true', '1']) | (x['key'].map(share).fillna(0) >= 0.5)
                      | x['key'].str.contains(SAUCE))

    x['in_cost'] = ~x['seasoning']                           # 재료비는 주재료만 (소스 · 양념 제외)
    x.drop(columns='key').to_csv(os.path.join(P.PRICE, 'recipe_ingredient_price.csv'), index=False, encoding='utf-8-sig')
    main = x[x['in_cost']]
    g = main.groupby('recipe_id').agg(main_lines=('std_name', 'size'), main_priced=('cost_now', 'count'),
                                      cost_at_publish=('cost_at_publish', 'sum'), cost_now=('cost_now', 'sum')).reset_index()
    out = rec.merge(g, on='recipe_id', how='left')
    out['priced_share'] = (out['main_priced'] / out['main_lines']).round(2)
    out['cost_per_serving_now'] = (out['cost_now'] / out['servings_n']).round(0)
    for c in ('cost_at_publish', 'cost_now', 'cost_per_serving_now'):
        out.loc[out['main_priced'].fillna(0) == 0, c] = None
    out.to_csv(os.path.join(P.PRICE, 'recipe_price.csv'), index=False, encoding='utf-8-sig')

    has = out['main_lines'].fillna(0) > 0
    print(f"레시피 {len(out):,}개 · 재료 줄 {len(x):,}개 = 주재료 {len(main):,} + 양념 · 소스 {len(x) - len(main):,} (재료비에서 뺌)")
    print(f"주재료 줄 중 재료비 붙은 줄 {main['cost_now'].notna().sum():,}개 ({main['cost_now'].notna().mean():.0%}) · "
          + '출처: ' + ', '.join(f'{k} {v:,}' for k, v in main.dropna(subset=['cost_now'])['source'].value_counts().items()))
    print(f"레시피별 주재료 가격 붙은 비율: 평균 {out.loc[has, 'priced_share'].mean():.0%} · "
          f"절반 이상 {(out.loc[has, 'priced_share'] >= 0.5).mean():.0%} · 80% 이상 {(out.loc[has, 'priced_share'] >= 0.8).mean():.0%}")
    print(f"1인분 재료비(최근 시세) 중앙값 {out['cost_per_serving_now'].median():,.0f}원")
    if no_unit:
        print('KAMIS 단위를 g 으로 못 바꾼 재료 (tables/ingredient_weight.csv 에 추가):', ', '.join(no_unit))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['test', 'codes', 'map', 'fetch', 'join'])
    ap.add_argument('folder', nargs='?', default=P.PRICE, help=argparse.SUPPRESS)   # 예전 'data' 인자도 받기만 함 (폴더는 paths.py)
    ap.add_argument('--months', default='13', help='fetch: 최근 몇 개월 (기본 13). auto = 레시피 가장 옛날 달부터 (만개 과거 수집과 맞춤)')
    ap.add_argument('--xlsx', help='codes: 코드표 엑셀 경로 (기본: dict/kamis_code_table.xlsx)')
    ap.add_argument('--normal-years', type=int, default=1, help='fetch: 비교에 쓸 과거 연수 (기본 1 = 작년 같은 달)')
    ap.add_argument('--raw', action='store_true', help='시장별 원본 kamis_raw.csv 도 씀 (기본: 안 씀, 아무도 안 읽음)')
    a = ap.parse_args()
    {'test': run_test, 'codes': run_codes, 'map': run_map, 'fetch': run_fetch, 'join': run_join}[a.cmd](a)
