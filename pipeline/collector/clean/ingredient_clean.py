"""만개의레시피 재료 정제 — 이름 통일 · 수량 분리 · 단위 통일 · g 환산 · 1인분 g

  python clean/ingredient_clean.py                          # data/recipes.jsonl (수집 중이어도 됨, 받은 데까지)
  python clean/ingredient_clean.py D:\\omm_10000recipe\\omm_10000recipe\\data\\recipes.jsonl

표 (tables 폴더, 엑셀로 고쳐 쓰면 됨)
  ingredient_alias.csv     원문 이름 → 표준 이름 (달걀 → 계란, 쇠고기 → 소고기 …)
  unit_table.csv           단위 → g / ml / 개(ea) 와 배수 (큰술 = 15ml, 종이컵 = 180ml …)
  ingredient_weight.csv    재료별 1개 무게 (양파 1개 = 200g, 두부 1모 = 300g …)
  ingredient_density.csv   재료별 1ml 무게 (기름 0.9, 고춧가루 0.45 …), 없으면 1.0

결과 (recipes.jsonl 과 같은 폴더)
  recipe_ingredients_clean.csv   재료 1개 = 1줄
      recipe_id, servings, group, is_seasoning, raw_name, std_name, material_id,
      raw_amount, qty, unit, unit_std(g/ml/ea), grams, grams_per_serving, status
      status: 정상 / 약간(양 없음) / 단위 모름 / 무게표 없음 / 수량 없음
  ingredient_dictionary.csv      표준 재료 1개 = 1줄 (레시피 수 · 양념 비율 · 원문 이름 예시 · 만개 재료 번호 · 평균 1인분 g)
                                 → KAMIS 매핑 · 영양성분 매핑의 기준 목록
  fix_units.csv                  단위를 몰라 g 을 못 구한 것 (단위 · 횟수 · 예시) → unit_table.csv 에 추가
  fix_weights.csv                개수 단위인데 무게표가 없는 것 (재료 · 단위 · 횟수) → ingredient_weight.csv 에 추가
위 두 fix 파일을 위에서부터 채우고 다시 돌리면 g 환산 비율이 올라감.
"""
import os, re, sys, json, collections
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths as P

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = P.TABLES
SEASONING_WORDS = ('소금', '설탕', '간장', '된장', '고추장', '쌈장', '식초', '액젓', '젓갈', '후추', '맛술', '물엿', '올리고당', '꿀',
                   '기름', '식용유', '참기름', '들기름', '올리브유', '고춧가루', '깨', '다시다', '조미료', '케첩', '마요네즈',
                   '굴소스', '소스', '드레싱', '시럽', '전분', '부침가루', '튀김가루', '밀가루', '버터')
SEASONING_EXACT = {'물', '생수', '찬물', '뜨거운물', '육수', '다시마물', '쌀뜨물'}
SEASONING_GROUP = re.compile(r'양념|소스|드레싱|조미|시즈닝|소금물|육수')
PINCH = re.compile(r'약간|야간|조금|소량|살짝|톡|솔솔|꼬집')
VAGUE = re.compile(r'약간|야간|적당|조금|기호|취향|소량|넉넉|살짝|입맛|선택|생략|약$|톡톡|솔솔|듬뿍|많이|가득|양껏|원하는|먹을만큼|먹고싶은|마음껏|충분히|적량|톡|번$|젓가락|가지$')
UNIT_SYNONYM = {'알': '개', '톨': '쪽', '미': '마리', '잎': '장', '덩어리': '덩이', '움큼': '줌', '주먹': '줌', '손': '줌',
                '봉지': '봉', '팩': '봉', '송이': '개', '뿌리': '대', '줄': '대', '토막': '조각', '쪽': '조각', '통': '개'}
FRACTION = {'½': '1/2', '⅓': '1/3', '⅔': '2/3', '¼': '1/4', '¾': '3/4', '⅕': '1/5', '⅛': '1/8'}
KOR_NUM = {'반': 0.5, '한': 1, '하나': 1, '두': 2, '둘': 2, '세': 3, '셋': 3, '네': 4, '넷': 4, '다섯': 5}
NAME_NOISE = re.compile(r'\(.*?\)|\[.*?\]|국산|수입산|수입|유기농|무농약|친환경|시판용|시판|손질된|손질한|깨끗이|씻은|데친|삶은|냉동|생$|약간')


def load_tables():
    t = lambda f: pd.read_csv(os.path.join(TABLES, f), dtype=str, keep_default_na=False)
    alias = {re.sub(r'\s+', '', r['raw']): re.sub(r'\s+', '', r['std']) for _, r in t('ingredient_alias.csv').iterrows()}
    units = {r['unit'].strip(): (r['to'], float(r['factor'])) for _, r in t('unit_table.csv').iterrows()}
    weight = {(r['ingredient'].strip(), r['unit'].strip()): float(r['grams']) for _, r in t('ingredient_weight.csv').iterrows()}
    density = {r['ingredient'].strip(): float(r['g_per_ml']) for _, r in t('ingredient_density.csv').iterrows()}
    return alias, units, weight, density


def norm_name(raw, alias):
    n = re.sub(r'\s+', '', NAME_NOISE.sub('', str(raw or '')))
    n = re.sub(r'[^\w가-힣]', '', n)
    return alias.get(n, n)


def parse_number(s):
    """'1/2' '1과1/2' '1 1/2' '1.5' '1~2' '반' '두' → 숫자"""
    s = s.strip()
    NUM = r'(\d+(?:\.\d+)?(?:\s*/\s*\d+)?)'
    val = lambda x: (lambda p: float(p[0]) / float(p[1]) if len(p) == 2 else float(p[0]))(re.split(r'\s*/\s*', x))
    m = re.match(NUM + r'\s*\+\s*' + NUM, s)                         # 1+1/2, 600+300 → 더하기
    if m:
        return val(m.group(1)) + val(m.group(2)), s[m.end():]
    m = re.match(NUM + r'\s*[~\-]\s*' + NUM, s)                      # 2~3, 1/2~1, 1/3~1/2 → 평균
    if m:
        a, b = val(m.group(1)), val(m.group(2))
        if a > b * 10:                                                # '900~1L' → 1L
            return b, s[m.end():]
        return (a + b) / 2, s[m.end():]
    m = re.match(r'(\d+)\s*(?:과|와|\s)\s*(\d+)\s*/\s*(\d+)', s)                       # 대분수
    if m:
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3)), s[m.end():]
    m = re.match(r'(\d+)\s*/\s*(\d+)', s)                                               # 분수
    if m:
        return int(m.group(1)) / int(m.group(2)), s[m.end():]
    m = re.match(r'(\d+(?:\.\d+)?)', s)
    if m:
        rest = s[m.end():]
        if re.match(r'\s*개?\s*반', rest):                                              # 1개반
            return float(m.group(1)) + 0.5, re.sub(r'반', '', rest, count=1)
        return float(m.group(1)), rest
    for k in sorted(KOR_NUM, key=len, reverse=True):
        if s.startswith(k):
            return KOR_NUM[k], s[len(k):]
    return None, s


def match_unit(rest, units):
    r = re.sub(r'\s+', '', rest)
    r = re.sub(r'\(.*', '', r)
    for u in sorted(units, key=len, reverse=True):                 # 긴 단위부터 (종이컵 > 컵)
        if u in ('T', 't'):
            if r.startswith(u) and not r[len(u):len(u) + 1].isalpha():
                return u
            continue
        if r.lower().startswith(u.lower()):
            return u
    return None


def parse_amount(amount, std, units, weight, density):
    """→ (qty, unit, unit_std, grams, status)"""
    a = str(amount or '').strip()
    if not a or a.lower() == 'nan':
        return None, None, None, None, '수량 없음'
    inner = re.search(r'\((\s*\d+(?:\.\d+)?\s*(?:g|kg|ml|㎖|cc|그램)\s*)\)', a, re.I)   # 괄호 안 무게가 있으면 그게 더 정확
    if inner:
        a = inner.group(1)
    if VAGUE.search(a) and not re.search(r'\d', a):
        if PINCH.search(a):                                           # 약간 · 조금 · 톡톡 → 1g 로 추정
            return None, None, 'g', 1.0, '약간(1g 추정)'
        return None, None, None, None, '적당량(양 없음)'
    for k, v in FRACTION.items():                                      # '½tsp' → '1/2tsp'
        a = a.replace(k, v)
    a = re.sub(r'^(약|대략|한\s?)?\s*(?=\d)', '', a)                # '약 200g' → '200g'
    a = re.sub(r'(?<=\d),(?=\d{3})', '', a)
    a = a.replace('`', '')
    if re.fullmatch(r'\d+\s*(약간|적당히|적당량)', a):                 # '1약간' → 약간
        a = re.sub(r'^\d+\s*', '', a)
        return parse_amount(a, std, units, weight, density)                           # '1,000ml' → '1000ml'
    a = re.sub(r'^두세', '2~3', a); a = re.sub(r'^서너', '3~4', a); a = re.sub(r'^한두', '1~2', a)
    qty, rest = parse_number(a)
    if qty is None and match_unit(a, units):                           # 숫자 없이 단위만 ('꼬집', '줌', '컵') → 1
        qty, rest = 1.0, a
    if qty is not None and re.search(r'\S\s*반\s*$', rest) and not rest.strip().startswith('반'):
        qty += 0.5                                                    # '1큰술 반' → 1.5큰술
        rest = re.sub(r'\s*반\s*$', '', rest)
    if qty is None:
        return None, None, None, None, '수량 없음'
    unit = match_unit(rest, units)
    if unit is None:
        if not re.sub(r'\W', '', rest):                             # 숫자만 있음 → 개
            unit = '개'
        else:
            return qty, re.sub(r'\s+', '', rest)[:8], None, None, '단위 모름'
    to, factor = units[unit]
    if to == 'g':
        return qty, unit, 'g', round(qty * factor, 1), '정상'
    if to == 'ml':
        ml = qty * factor
        return qty, unit, 'ml', round(ml * density.get(std, 1.0), 1), '정상'
    w = lookup_weight(std, unit, weight)
    if w is None:
        return qty, unit, 'ea', None, '무게표 없음'
    return qty, unit, 'ea', round(qty * w, 1), '정상'


def lookup_weight(std, unit, weight):
    """재료 + 단위 → 1단위 g. 같은 뜻 단위(알=개, 봉지=봉 …)도 찾고, 없으면 그 단위의 기본값('*')"""
    for u in (unit, UNIT_SYNONYM.get(unit)):
        if u and (std, u) in weight:
            return weight[(std, u)]
    for u, alt in UNIT_SYNONYM.items():                   # 거꾸로도 (표에 '알'로 적어 둔 경우)
        if alt == unit and (std, u) in weight:
            return weight[(std, u)]
    if unit == '개':                                       # '개'인데 표에 다른 단위만 있으면 그 무게
        hit = [v for (i, u), v in weight.items() if i == std]
        if len(hit) == 1:
            return hit[0]
    return weight.get(('*', unit)) or weight.get(('*', UNIT_SYNONYM.get(unit)))


def parse_servings(s):
    m = re.search(r'(\d+)', str(s or ''))
    return int(m.group(1)) if m else None


def main(path):
    alias, units, weight, density = load_tables()
    folder = P.CLEAN                                               # 결과는 data/clean
    recipes = {}
    for line in open(path, encoding='utf-8'):
        try:
            r = json.loads(line)
            recipes[r['recipe_id']] = r                                # 같은 번호가 또 있으면 마지막 것
        except (ValueError, KeyError):
            continue                                                   # 수집 중 끊긴 줄은 건너뜀
    # 1차: 이름만 정리
    items = []
    for r in recipes.values():
        sv = parse_servings(r.get('servings'))
        no = 0                                                     # 레시피 안 재료 순서 (원문 기준, 1부터)
        for g in r.get('ingredient_groups') or []:
            gname = g.get('group') or ''
            for it in g.get('items') or []:
                no += 1
                std = norm_name(it.get('name'), alias)
                if std:
                    items.append((r['recipe_id'], no, sv, gname, it, std))
    # 2차: 만개 재료 번호가 같으면 가장 많이 쓰인 이름으로 통일 (무게를 찾기 전에)
    cnt = collections.defaultdict(collections.Counter)
    for _, _, _, _, it, std in items:
        if it.get('material_id') is not None:
            cnt[it['material_id']][std] += 1
    by_mid = {m: c.most_common(1)[0][0] for m, c in cnt.items()}
    # 3차: 수량 · 단위 · g
    rows = []
    for rid, no, sv, gname, it, std in items:
        std = by_mid.get(it.get('material_id'), std)
        seasoning = bool(SEASONING_GROUP.search(gname)) or std in SEASONING_EXACT or std.endswith(SEASONING_WORDS)
        qty, unit, ustd, grams, status = parse_amount(it.get('amount'), std, units, weight, density)
        rows.append({'recipe_id': rid, 'line_no': no, 'servings': sv, 'group': gname, 'is_seasoning': seasoning,
                     'raw_name': it.get('name'), 'std_name': std, 'material_id': it.get('material_id'),
                     'raw_amount': it.get('amount'), 'qty': qty, 'unit': unit, 'unit_std': ustd, 'grams': grams,
                     'grams_per_serving': round(grams / sv, 1) if grams is not None and sv else None,
                     'status': status})
    d = pd.DataFrame(rows)
    if d.empty:
        sys.exit('재료가 없어요. recipes.jsonl 경로를 확인해 주세요.')

    d['check'] = (d['grams_per_serving'] > 1000) & (d['std_name'] != '물')   # 1인분 1kg 넘으면 확인
    d.to_csv(os.path.join(folder, 'recipe_ingredients_clean.csv'), index=False, encoding='utf-8-sig')

    dic = d.groupby('std_name').agg(
        recipes=('recipe_id', 'nunique'), seasoning_share=('is_seasoning', 'mean'),
        raw_examples=('raw_name', lambda s: ' | '.join(s.value_counts().index[:5])),
        material_ids=('material_id', lambda s: ' '.join(str(int(x)) for x in sorted(set(s.dropna())))),
        avg_grams_per_serving=('grams_per_serving', 'mean'), grams_ok=('grams', lambda s: s.notna().mean()),
    ).reset_index().sort_values('recipes', ascending=False)
    dic['seasoning_share'] = dic['seasoning_share'].round(2)
    dic['avg_grams_per_serving'] = dic['avg_grams_per_serving'].round(1)
    dic['grams_ok'] = dic['grams_ok'].round(2)
    dic.to_csv(os.path.join(folder, 'ingredient_dictionary.csv'), index=False, encoding='utf-8-sig')

    u = d[d['status'] == '단위 모름'].groupby('unit').agg(count=('recipe_id', 'size'),
                                                         examples=('raw_amount', lambda s: ' | '.join(s.astype(str).unique()[:5])))
    u.sort_values('count', ascending=False).to_csv(os.path.join(folder, 'fix_units.csv'), encoding='utf-8-sig')
    w = d[d['status'] == '무게표 없음'].groupby(['std_name', 'unit']).size().rename('count').reset_index()
    w.sort_values('count', ascending=False).to_csv(os.path.join(folder, 'fix_weights.csv'), index=False, encoding='utf-8-sig')

    st = d['status'].value_counts()
    main_ing = d[~d['is_seasoning']]
    print(f"레시피 {d['recipe_id'].nunique():,}개 · 재료 줄 {len(d):,}개 · 표준 재료 {d['std_name'].nunique():,}종")
    print('처리 결과:', ', '.join(f'{k} {v:,}' for k, v in st.items()))
    print(f"g 환산 비율: 전체 {d['grams'].notna().mean():.0%} · 주재료(양념 제외) {main_ing['grams'].notna().mean():.0%}")
    print(f"1인분 1kg 넘는 줄(check=True): {int(d['check'].sum())}")
    print(f'\n결과 폴더: {folder}')
    print('  recipe_ingredients_clean.csv · ingredient_dictionary.csv · fix_units.csv · fix_weights.csv')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else P.RECIPES_JSONL)
