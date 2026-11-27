"""메뉴 영양성분 (식품의약품안전처 식품영양성분DB · 공공데이터포털) — 만개의레시피와 같은 메뉴 사전으로 정제

API: https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo03   키: config.ini [data_go] service_key (활용신청 필요)

기준은 만개의레시피 메뉴. 식약처 '음식'(조리된 요리) 이름을 레시피 제목과 **같은 규칙(clean/menu_group.py) · 같은 사전(dict/menu_seed.csv)** 으로
메뉴에 붙인 뒤, 메뉴마다 영양값을 냄. 사전에 별칭을 더하면 레시피 묶기와 영양 매칭이 같이 좋아짐.

실행 (프로젝트 폴더에서)
  python nutrition/nutrition_fetch.py test 김치찌개      # 검색 결과가 어느 메뉴로 붙는지 보기
  python nutrition/nutrition_fetch.py fetch            # 1. 수집: 메뉴 사전의 메뉴명 · 별칭으로 검색 → data/raw/nutrition_foods.jsonl
  python nutrition/nutrition_fetch.py build            # 2. 정제: 식품 이름 → 메뉴 (menu_group 규칙) → 메뉴별 영양
  python nutrition/nutrition_fetch.py fetch --retry-empty  # 결과가 없던 검색어 다시 (예전에 연결이 끊긴 것)
  python nutrition/nutrition_fetch.py fetch --missing      # 영양값 없는 메뉴만 다시 검색 (식약처에 새로 들어왔는지, 주기 작업용)
  (fetch 끝에 build 도 자동으로 돌림. 사전만 고쳤으면 build 만 다시. 연결이 끊긴 이름은 완료로 안 적어서 다시 돌리면 이어서 찾음)

정제 규칙
  1. 음식 분류만. 간편조리세트(밀키트)는 양이 한 봉지 전체라 아예 안 씀. 시판 제품(상용제품)은 일반 음식이 없는 메뉴에만
  2. 식품 이름 → 메뉴: 식약처 이름은 '요리_변형' 형식
     '변형 + 요리' 가 사전 메뉴와 정확히 같으면 그 메뉴 (김치찌개_참치 → 참치김치찌개), 아니면 '_' 앞 요리 이름 (햄버거_불고기버거 → 햄버거)
     레시피 제목과 같은 규칙 (사전 메뉴 · 별칭 그대로 → 사이 말 건너뛰기). 못 붙으면 대표 음식명으로 한 번 더
     '_국물' · '_면' · '_김치만' 처럼 요리 일부분만 분석한 줄은 뺌
  3. 메뉴마다 값 종류 순서: ① 직접 분석 · g 기준 → ② g 기준(수집) → ③ mL 기준(산출, 1mL ≈ 1g). 앞 종류가 있으면 그것만 평균
     100g 당 값은 평균, 1인분 g 은 중앙값
결과
  data/raw/nutrition_foods.jsonl        API 원본 (식품 1개 = 1줄, 식품코드로 중복 제거)
  data/nutrition/food_menu.csv          식품 → 메뉴 매칭 결과 (recipe_menu.csv 와 같은 역할, 확인용)
  data/nutrition/menu_nutrition.csv     메뉴 1줄: 쓴 식품 · 값 종류 · 1인분 g · 100g 당 영양 · 1인분 영양
  data/nutrition/menu_nutrition_unmatched.csv   만개 메뉴인데 식약처 음식이 안 붙은 메뉴 (비워 둠) · 찾아본 검색어 · 상태
  data/nutrition/food_menu_changes.csv  ·  menu_nutrition_changes.csv   지난 실행과 비교해 바뀐 것 (사전을 고친 뒤 확인)
  data/nutrition/nutrition_seed_candidates.csv  메뉴 사전에 없는 식약처 요리 이름 (같은 요리면 menu_seed.csv 별칭으로)
"""
import os, re, sys, json, time, argparse, configparser
import requests
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths as P
import menu_group as mg                                 # 레시피 제목과 같은 메뉴 매칭 규칙

BASE = 'https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo03'
# 식품영양성분DB 표준 순서 (100g 당). 양파볶음 값으로 맞춰 봄: 에너지 56kcal · 수분 86.9g · 나트륨 274mg (명세로 한 번 더 확인)
NUTRIENTS = {'AMT_NUM1': 'energy_kcal', 'AMT_NUM2': 'water_g', 'AMT_NUM3': 'protein_g', 'AMT_NUM4': 'fat_g', 'AMT_NUM5': 'ash_g',
             'AMT_NUM6': 'carb_g', 'AMT_NUM7': 'sugar_g', 'AMT_NUM8': 'fiber_g', 'AMT_NUM9': 'calcium_mg', 'AMT_NUM10': 'iron_mg',
             'AMT_NUM11': 'phosphorus_mg', 'AMT_NUM12': 'potassium_mg', 'AMT_NUM13': 'sodium_mg'}
RAW = P.raw('nutrition_foods.jsonl')
DONE = P.raw('nutrition_queries.txt')                   # 이미 검색한 이름 (다시 안 찾음)
OLD_CANDS = P.nutrition('menu_nutrition_candidates.csv')   # 예전 버전이 받은 후보 → 원본으로 옮겨 씀
OUT = P.nutrition('menu_nutrition.csv')
FOOD_MENU = P.nutrition('food_menu.csv')
UNMATCHED = P.nutrition('menu_nutrition_unmatched.csv')
SEED_CANDS = P.nutrition('nutrition_seed_candidates.csv')


# ───────────── API ─────────────
def cfg():
    c = configparser.ConfigParser()
    c.read(P.CONFIG, encoding='utf-8')
    key = c.get('data_go', 'service_key', fallback='').strip()
    if not key or key.startswith('여기에'):
        sys.exit('config.ini 의 [data_go] service_key 를 채워 주세요.')
    return key, c.get('nutrition', 'operation', fallback='getFoodNtrCpntDbInq03').strip(), \
        c.get('nutrition', 'name_param', fallback='FOOD_NM_KR').strip()


def search(name, rows=100, pages=3):
    """이름이 들어간 식품 (최대 rows × pages 건). 연결이 끝내 안 되면 None (→ 검색 완료로 기록하지 않음)"""
    key, op, name_param = cfg()
    out = []
    for page in range(1, pages + 1):
        p = {'serviceKey': key, 'pageNo': str(page), 'numOfRows': str(rows), 'type': 'json', name_param: name}
        d = None
        for attempt, wait in enumerate((10, 30, 60), 1):
            try:
                d = requests.get(f'{BASE}/{op}', params=p, timeout=60).json()
                break
            except (requests.RequestException, ValueError) as e:
                print(f'    재시도 {attempt}/3 ({wait}초 뒤): {str(e)[:80]}')
                time.sleep(wait)
        if d is None:
            return None
        body = d.get('body') or (d.get('response') or {}).get('body') or {}
        head = d.get('header') or (d.get('response') or {}).get('header') or {}
        if str(head.get('resultCode', '00')) not in ('0', '00'):
            print(f"    API 응답: {head.get('resultCode')} {head.get('resultMsg')}")
            return None
        items = body.get('items') or []
        if isinstance(items, dict):
            items = items.get('item') or []
        items = items if isinstance(items, list) else [items]
        out += items
        if len(out) >= int(body.get('totalCount') or 0) or len(items) < rows:
            break
        time.sleep(0.2)
    return out


# ───────────── 공통 ─────────────
def nm(s):
    return re.sub(r'\s+', '', str(s or ''))


def num(v):
    try:
        return float(str(v).replace(',', ''))
    except ValueError:
        return None


def grams(s):
    """'400.000g' → 400, '200.000mL' → 200 (1mL ≈ 1g)"""
    m = re.search(r'([\d.,]+)\s*(g|ml)', str(s or ''), re.I)
    return num(m.group(1)) if m else None


def is_gram(i):
    return all(re.search(r'\dg$', str(i.get(k) or '').strip(), re.I) for k in ('SERVING_SIZE', 'Z10500'))


def is_dish(i):
    return '음식' in str(i.get('DB_GRP_NM') or '')


def is_kit(i):
    """간편조리세트(밀키트): 양(Z10500)이 한 봉지 전체(2~3인분)라 1인분 영양이 부풀려짐 → 아예 안 씀"""
    return '간편조리세트' in str(i.get('FOOD_NM_KR') or '')


def is_commercial(i):
    return '상용제품' in str(i.get('DB_CLASS_NM') or '')


def load_menus():
    """만개 메뉴 (menu_summary.csv) + 메뉴 사전 매처 (menu_group 과 같은 것)"""
    path = P.clean('menu_summary.csv')
    if not os.path.exists(path):
        sys.exit('data/clean/menu_summary.csv 가 없어요. python clean/menu_group.py 를 먼저 돌려 주세요.')
    summary = pd.read_csv(path).sort_values('recipes', ascending=False)
    menus, to_std = mg.load_dictionary(P.MENU_SEED)
    return summary, menus, to_std, mg.build_matcher(to_std.keys()), mg.gap_rules(menus, to_std)


PART = re.compile(r'(만|국물|면|건더기|소스|양념|국|밥)$')          # 라면_국물 · 라면_면 · 김치찌개_김치만 (요리의 일부분)


def food_to_menu(item, pat, to_std, rules):
    """식약처 이름 → 만개 메뉴 (레시피 제목과 같은 사전 · 같은 규칙). 식약처 이름은 '요리_변형' 형식
      1. '_국물' 처럼 요리 일부분이면 뺌
      2. 변형이 요리 이름으로 끝나고 사전 메뉴면 그 메뉴   초밥_유부초밥 → 유부초밥 (돼지갈비찜_배추김치 → 배추김치 ✘)
      3. '변형 + 요리' 가 사전 메뉴면 그 메뉴             김치찌개_참치 → 참치김치찌개
      4. 요리 이름 (없으면 대표 음식명) 을 제목처럼 매칭    햄버거_불고기버거 → 햄버거
      5. 그래도 없으면 괄호 속 다른 이름                  완자전_소고기(동그랑땡/육원전) → 동그랑땡"""
    name = str(item.get('FOOD_NM_KR') or '')
    head, _, variant = name.partition('_')
    if variant and PART.search(nm(variant.split('_')[-1])) and len(nm(variant.split('_')[-1])) <= 3:
        return None, '요리 일부분 (뺌)'
    no_paren = lambda x: re.sub(r'\([^)]*\)', '', x)
    head0 = mg.clean(no_paren(head))
    variants = list(dict.fromkeys(mg.clean(no_paren(x)) for x in variant.split('_') if x))
    for v in variants:
        if v and head0 and v.endswith(head0) and v in to_std:
            return to_std[v], '이름 (변형)'
    for v in variants:
        if v + head0 in to_std:
            return to_std[v + head0], '이름 (변형 + 요리)'
    for text, tag in ((head, ''), (str(item.get('FOOD_REF_NM') or ''), ' (대표 음식명)')):
        if not text or text == 'None':
            continue
        m, by = mg.match_best(text, pat, to_std, rules)
        if m:
            return m, by.replace('제목', '이름') + tag
    for inner in re.findall(r'\(([^)]*)\)', name):
        for x in inner.split('/'):
            if mg.clean(x) in to_std:
                return to_std[mg.clean(x)], '이름 (괄호 속 이름)'
    return None, None


def load_raw():
    items = {}
    if os.path.exists(RAW):
        for line in open(RAW, encoding='utf-8'):
            try:
                i = json.loads(line)
                items[i.get('FOOD_CD')] = i
            except ValueError:
                pass
    return items


def save_raw(new, have):
    with open(RAW, 'a', encoding='utf-8') as f:
        for i in new:
            if i.get('FOOD_CD') and i['FOOD_CD'] not in have:
                f.write(json.dumps(i, ensure_ascii=False) + '\n')
                have[i['FOOD_CD']] = i


# ───────────── 1. 수집 ─────────────
# 사전은 표기를 통일했지만(spelling_norm.csv) 식약처는 다른 표기를 씀 → 검색할 때만 식약처 표기로도 찾음
SEARCH_ALSO = {'계란': '달걀', '파스타': '스파게티'}


def queries_for(menu, alias):
    """메뉴 하나 → 식약처 검색어 (메뉴 이름 + 별칭 + 식약처 표기)"""
    qs = []
    for q in [menu] + [x for x in str(alias.get(menu, '')).split('|') if len(x) >= 2]:
        qs.append(q)
        qs += [q.replace(a, b) for a, b in SEARCH_ALSO.items() if a in q]
    return list(dict.fromkeys(qs))


def load_alias():
    seed = pd.read_csv(P.MENU_SEED, keep_default_na=False)
    return dict(zip(seed['menu'], seed['aliases']))


def run_fetch(a):
    summary, menus, to_std, pat, rules = load_menus()
    have = load_raw()
    if not have and os.path.exists(OLD_CANDS):                      # 예전 버전이 받은 후보를 원본으로 옮김 (다시 안 받게)
        c = pd.read_csv(OLD_CANDS, dtype=str, keep_default_na=False)
        save_raw(c.drop(columns=[x for x in ('menu', 'searched_as') if x in c]).to_dict('records'), have)
        done0 = set(c['searched_as'])
        open(DONE, 'a', encoding='utf-8').write(''.join(q + '\n' for q in done0))
        print(f'예전 후보 {len(have):,}건을 원본으로 옮김')
    done = set(open(DONE, encoding='utf-8').read().split('\n')) if os.path.exists(DONE) else set()
    alias = load_alias()
    if a.retry_empty:                                                 # 예전 버전이 끊긴 검색도 '완료'로 적었음 → 결과 없는 이름 다시
        names = ' '.join(nm(i.get('FOOD_NM_KR')) for i in have.values())
        empty = {q for q in done if q and nm(q) not in names}
        done -= empty
        print(f'원본에 결과가 없는 검색어 {len(empty)}개를 다시 찾음')
    if a.missing:                                                     # 영양값 없는 메뉴만 다시 검색 (식약처에 나중에 추가됐는지)
        miss = pd.read_csv(UNMATCHED)['menu'] if os.path.exists(UNMATCHED) else []
        again = {q for m in miss for q in queries_for(m, alias)}
        done -= again
        print(f'영양값 없는 메뉴 {len(miss)}개의 검색어 {len(again)}개를 다시 찾음')
    queries = []
    for m in summary['menu'].dropna():                                # 만개 메뉴 (레시피 많은 순) + 별칭 + 식약처 표기
        queries += queries_for(m, alias)
    queries = [q for q in dict.fromkeys(queries) if q not in done]
    if a.top:
        queries = queries[:a.top]
    print(f'검색할 이름 {len(queries)}개 (이미 검색 {len(done)}개 · 원본 {len(have):,}건)')
    failed = []
    for k, q in enumerate(queries, 1):
        items = search(q)
        if items is None:                                             # 연결 실패 → 완료로 적지 않음 (다음 fetch 때 다시)
            failed.append(q)
            print(f'[{k}/{len(queries)}] {q}: 연결 실패 → 다음에 다시')
            continue
        before = len(have)
        save_raw([i for i in items if is_dish(i)], have)
        open(DONE, 'a', encoding='utf-8').write(q + '\n')
        print(f'[{k}/{len(queries)}] {q}: 음식 {sum(is_dish(i) for i in items)}건 · 새로 {len(have) - before}건')
        time.sleep(0.2)
    if failed:
        print(f'\n연결 실패 {len(failed)}개: 같은 명령을 다시 돌리면 이것만 다시 찾아요 → ' + ', '.join(failed[:20]))
    run_build(a)


# ───────────── 2. 정제 ─────────────
def average(rows):
    sg = pd.Series([grams(i.get('Z10500')) for i in rows], dtype=float).median()
    sg = None if pd.isna(sg) else round(sg, 1)
    names = list(dict.fromkeys(i.get('FOOD_NM_KR') for i in rows))
    r = {'foods': len(names), 'food_names': ' | '.join(names[:15]), 'rows': len(rows), 'serving_g': sg,
         'research_ymd': max(str(i.get('RESEARCH_YMD') or '') for i in rows)}
    for k, v in NUTRIENTS.items():
        vals = [x for x in (num(i.get(k)) for i in rows) if x is not None]
        x = round(sum(vals) / len(vals), 2) if vals else None
        r[f'{v}_100g'] = x
        r[f'{v}_serving'] = round(x * sg / 100, 2) if x is not None and sg else None
    return r


def choose(rows):
    """메뉴에 붙은 식품 줄 → (평균 낼 줄, 값 종류). 일반 음식 먼저, 없으면 시판 제품"""
    for commercial in (False, True):
        base = [i for i in rows if is_commercial(i) == commercial]
        tag = ' · 시판 제품' if commercial else ''
        for kind, test in (('분석 · g', lambda i: is_gram(i) and '분석' in str(i.get('CRT_MTH_NM') or '')),
                           ('g (수집 · 산출)', is_gram), ('mL (산출)', lambda i: True)):
            hit = [i for i in base if test(i)]
            if hit:
                return hit, kind + tag
    return [], None


def run_build(a=None):
    summary, menus, to_std, pat, rules = load_menus()
    raw = [i for i in load_raw().values() if is_dish(i) and not is_kit(i)]
    if not raw:
        sys.exit(f'{RAW} 가 비어 있어요. fetch 를 먼저 돌려 주세요.')
    fm = []
    for i in raw:
        m, by = food_to_menu(i, pat, to_std, rules)
        fm.append({'food_cd': i.get('FOOD_CD'), 'food_name': i.get('FOOD_NM_KR'), 'food_ref': i.get('FOOD_REF_NM'),
                   'menu': m, 'match_by': by, 'kind': ('시판 ' if is_commercial(i) else '') + str(i.get('CRT_MTH_NM')),
                   'serving_size': i.get('SERVING_SIZE'), 'z10500': i.get('Z10500'), 'energy_kcal_100g': num(i.get('AMT_NUM1'))})
    fmd = pd.DataFrame(fm)
    import changes                                                     # 지난 결과와 비교 → *_changes.csv
    sp = lambda x: mg.spell(re.sub(r'\s+', '', x))
    changes.compare(FOOD_MENU, fmd, 'food_cd', 'menu', P.nutrition('food_menu_changes.csv'),
                    show=('food_name',), spell=sp, label='메뉴가 바뀐 식약처 식품')
    fmd.sort_values(['menu', 'food_name']).to_csv(FOOD_MENU, index=False, encoding='utf-8-sig')
    left = fmd[fmd['menu'].isna() & fmd['match_by'].isna()]
    left.assign(head=left['food_name'].str.split('_').str[0]).groupby('head').size().sort_values(ascending=False).rename(
        'foods').to_csv(SEED_CANDS, encoding='utf-8-sig')            # 사전에 없는 식약처 요리 이름 (메뉴 · 별칭 후보)
    by_menu = {}
    for i, r in zip(raw, fm):
        if r['menu']:
            by_menu.setdefault(r['menu'], []).append(i)

    out, miss = [], []
    for _, s in summary.iterrows():
        rows, kind = choose(by_menu.get(s['menu'], []))
        if not rows:
            miss.append({'menu': s['menu'], 'recipes': s['recipes']})
            continue
        out.append({'menu': s['menu'], 'recipes': s['recipes'], 'value_kind': kind, **average(rows)})
    o_new = pd.DataFrame(out)
    if os.path.exists(OUT) and len(o_new):                             # 메뉴 영양값이 10% 넘게 바뀐 메뉴
        prev = pd.read_csv(OUT, encoding='utf-8-sig')
        if {'menu', 'energy_kcal_serving'} <= set(prev):
            mm = o_new[['menu', 'energy_kcal_serving', 'food_names']].merge(
                prev[['menu', 'energy_kcal_serving']].rename(columns={'energy_kcal_serving': 'kcal_before'}), on='menu', how='outer')
            mm = mm.rename(columns={'energy_kcal_serving': 'kcal_after'})
            pct = (mm['kcal_after'] / mm['kcal_before'] - 1).abs()
            mm['change'] = ['새 메뉴' if pd.isna(b) else '없어짐' if pd.isna(a) else ('10% 넘게 바뀜' if p > 0.1 else None)
                            for a, b, p in zip(mm['kcal_after'], mm['kcal_before'], pct)]
            mm = mm[mm['change'].notna()]
            mm.to_csv(P.nutrition('menu_nutrition_changes.csv'), index=False, encoding='utf-8-sig')
            c = mm['change'].value_counts()
            print('  지난 결과와 비교: 영양값 ' + (' · '.join(f'{k} {v}' for k, v in c.items()) + ' → menu_nutrition_changes.csv' if len(mm) else '바뀐 메뉴 없음'))
    o_new.to_csv(OUT, index=False, encoding='utf-8-sig')
    alias = load_alias()
    done = set(open(DONE, encoding='utf-8').read().split('\n')) if os.path.exists(DONE) else set()
    um = pd.DataFrame(miss, columns=['menu', 'recipes'])
    um['searched_as'] = um['menu'].map(lambda m: '|'.join(queries_for(m, alias)))
    um['status'] = um['searched_as'].map(lambda q: '식약처에 없음 (검색함)' if all(x in done for x in q.split('|'))
                                         else '아직 검색 안 함 → fetch')
    um.to_csv(UNMATCHED, index=False, encoding='utf-8-sig')
    o = pd.DataFrame(out)
    cov = o['recipes'].sum() / summary['recipes'].sum() if len(o) else 0
    print(f"\n식약처 음식 {len(raw):,}건 중 메뉴에 붙음 {fmd['menu'].notna().sum():,}건 · 일부분이라 뺌 {(fmd['match_by'] == '요리 일부분 (뺌)').sum():,}건"
          f" · 사전에 없음 {len(left):,}건 → {FOOD_MENU}")
    print(f"만개 메뉴 {len(summary)}개 중 영양값 있는 메뉴 {len(o)}개 (레시피 기준 {cov:.0%}) → {OUT}")
    if len(o):
        print('값 종류: ' + ', '.join(f'{k} {v}' for k, v in o['value_kind'].value_counts().items()))
    st = um['status'].value_counts()
    print(f'영양값 없는 메뉴 {len(miss)}개 (' + ' · '.join(f'{k} {v}' for k, v in st.items()) + f') → {UNMATCHED}')
    print('  비워 둠. 식약처 표기를 알게 되면 menu_seed.csv 별칭에 넣고 fetch / 식약처에 새로 들어왔는지는 fetch --missing')


def run_test(a):
    summary, menus, to_std, pat, rules = load_menus()
    items = [i for i in (search(a.name) or []) if is_dish(i)]
    print(f'"{a.name}" 음식 {len(items)}건 → 메뉴 매칭')
    for i in sorted(items, key=lambda i: len(nm(i.get('FOOD_NM_KR'))))[:30]:
        m, by = food_to_menu(i, pat, to_std, rules)
        print(f"  {str(i.get('FOOD_NM_KR')):28s} → {str(m):12s} {str(by):22s} "
              f"{'시판 ' if is_commercial(i) else ''}{i.get('CRT_MTH_NM')} {i.get('SERVING_SIZE')} {i.get('Z10500')} {i.get('AMT_NUM1')}kcal")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('test'); p.add_argument('name')
    p = sub.add_parser('fetch'); p.add_argument('folder', nargs='?', help=argparse.SUPPRESS)
    p.add_argument('--top', type=int, default=0, help='검색할 이름 앞에서 N개만 (기본: 전부)')
    p.add_argument('--missing', action='store_true', help='영양값 없는 메뉴의 검색어를 다시 찾기 (식약처에 새로 들어왔는지 확인, 주기 작업용)')
    p.add_argument('--retry-empty', action='store_true', help='원본에 결과가 하나도 없는 검색어를 다시 찾기 (연결이 끊겼던 것)')
    sub.add_parser('build', help='받은 원본으로 메뉴 매칭 · 영양 다시 계산 (API 안 씀)')
    a = ap.parse_args()
    {'test': run_test, 'fetch': run_fetch, 'build': run_build}[a.cmd](a)
