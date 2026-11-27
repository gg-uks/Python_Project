"""만개의레시피 레시피 → 메뉴로 묶기

  python clean/menu_group.py                    # 기본: data/raw/recipes.jsonl · dict/menu_seed.csv → 결과 data/clean

입력
  recipes.jsonl   팀원 수집 결과 (recipe_id, title, ingredients_flat, views, review_count …)
  menu_seed.csv   메뉴 사전: menu(표준 메뉴명), aliases(오타 · 줄임말, | 로 구분)
                  예) 김치찌개,김치찌게      소세지야채볶음,쏘야|소야|소시지야채볶음
결과
  recipe_menu.csv        레시피 → 메뉴 · 상위 메뉴 (김치찌개 ← 참치김치찌개)
  menu_summary.csv       메뉴별 레시피 수 · 후기 수 · 대표 레시피 · 기본 재료
  menu_unmatched.csv     못 묶은 제목 끝부분 (참고용)
  menu_unmatched_titles.csv  못 묶은 제목 (조회수 순)
  menu_changes.csv           지난 실행과 비교해 메뉴가 바뀐 레시피 (사전 · 규칙을 고친 뒤 확인: 다른 메뉴 · 묶임 풀림 먼저)
  menu_seed_candidates.csv   사전에 넣을 후보 '주재료 + 조리법' · 레시피 수 · 비슷한 사전 메뉴 · 제목 예시
                             → 맞는 것만 menu_seed.csv 에 추가 (메뉴 또는 별칭)하고 다시 실행
"""
import os, re, sys, json, collections
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths as P

# 제목에서 지울 말 (메뉴 이름이 아닌 꾸밈말)
NOISE = re.compile(
    r'[^\w\s]|\d+'
    r'|만드는\s*법|만들기|끓이는\s*법|레시피|황금|초간단|간단|쉬운|쉽게|맛있게|맛있는|초보|실패\s*없는'
    r'|백종원|이연복|편스토랑|자취|요리|맛집|강추|꿀팁|버전|스타일|[가-힣]+표(?=\s|$)|st')
# 메뉴 이름 끝에 잘 오는 말 (못 묶은 제목에서 후보를 뽑을 때)
DISH_END = ('찌개', '국', '탕', '전골', '볶음', '조림', '무침', '나물', '전', '찜', '구이', '튀김', '밥', '덮밥', '볶음밥',
            '죽', '국수', '면', '파스타', '김치', '장아찌', '샐러드', '샌드위치', '떡볶이', '스테이크', '카레', '수프', '스프')


def load_spelling():
    """dict/tables/spelling_norm.csv: 같은 말 다른 표기 (달걀 → 계란). 레시피 제목 · 식약처 이름 · 메뉴 사전에 똑같이 씀
    재료 별칭표(ingredient_alias.csv)는 재료 이름용이라 제목에 그대로 쓰면 안 됨 (게살 → 크래미, 참깨 → 깨)"""
    path = os.path.join(P.TABLES, 'spelling_norm.csv')
    if not os.path.exists(path):
        return []
    d = pd.read_csv(path, keep_default_na=False, encoding='utf-8-sig')
    return sorted(((r['from'].strip(), r['to'].strip()) for _, r in d.iterrows() if r['from'].strip()),
                  key=lambda x: len(x[0]), reverse=True)


SPELLING = load_spelling()


def spell(t):
    for a, b in SPELLING:
        t = t.replace(a, b)
    return t


# '맛집보다 · 식당 부럽지 않은' 은 요리가 아니라 가게와 비교 → 먼저 지움 ('청국장 맛집보다 맛있는' → 청국장 ✔)
SHOP_COMPARE = re.compile(r'(맛집|식당|가게|전문점|카페|편의점|시판)\s*(보다|부럽지\s*않은|안\s*부러운|못지않은)')


def clean(title):
    t = NOISE.sub(' ', SHOP_COMPARE.sub(' ', str(title)))
    return spell(re.sub(r'\s+', '', t))


def load_dictionary(path):
    """메뉴 사전 → (표준 메뉴 목록, 이름 → 표준 메뉴). 별칭도 같은 표준 메뉴로"""
    seed = pd.read_csv(path, keep_default_na=False)
    to_std = {}
    for _, r in seed.iterrows():
        std = spell(re.sub(r'\s+', '', str(r['menu'])))
        if len(std) < 2:
            continue
        to_std[std] = std
        for a in str(r.get('aliases', '')).split('|'):
            a = spell(re.sub(r'\s+', '', a))
            if len(a) >= 2 and a != std:
                to_std.setdefault(a, std)
    menus = sorted(set(to_std.values()), key=lambda m: (-len(m), m))   # 같은 길이는 가나다순 (실행마다 같은 결과)
    return menus, to_std


# 다른 낱말의 일부라서 그 안에서 메뉴 이름을 찾으면 안 되는 말
#   양배추 → 배추김치 ✘ · 열무나물 → 무나물 ✘ · 율무밥 → 무밥 ✘ · 치커리 → 커리(카레) ✘ · 양파전 → 파전 ✘
#   마늘무침 → 마무침 ✘ · 고구마전 → 마전 ✘ · 두가지 → 가지 ✘ · 무설탕 → 무 ✘
INSIDE = re.compile(r'양배추|열무|(?<!비)율무|메밀|모밀|치커리|단무지|총각무|알타리무|양파|양상추|양송이|새송이|마늘|고구마|'
                    r'[0-9두세네다섯몇]가지|여러가지|무설탕|무반죽|무가당|무염|무첨가|'
                    r'.탕(?=후루룩)')                     # '백합탕 후루룩' → 탕후루 ✘


# 메뉴 이름 바로 뒤에 이 말이 오면 '만드는 요리'가 아님 (비교 · 대신 · 재료로 씀)
#   '계란 후라이보다 간단한 계란찜' → 계란찜 · '찹쌀떡 부럽지 않은 고구마 경단' → 찹쌀떡 ✘
#   '냉동 핫도그로 만든 사라다빵' → 사라다빵 · '들기름 막국수 말고 이게 대세! 들기름 수제비' → 수제비
NOT_DISH_AFTER = re.compile(r'(보다|대신|말고|부럽지|안부럽|빼고|아닌|없이|로만든|으로만든|로만드는|으로만드는|를활용|을활용|활용|넣은|넣고|소스로|양념으로)')


def not_dish(t, end):
    """t[end:] 가 비교 · 대신 · 재료 표현으로 시작하면 True"""
    return bool(NOT_DISH_AFTER.match(t, end))


def blocked(t):
    """제목 안에서 '다른 낱말 안쪽' 위치들 (그 위치에서 시작하는 메뉴 이름은 안 씀)"""
    return {k for m in INSIDE.finditer(t) for k in range(m.start() + 1, m.end())}


def build_matcher(names):
    names = sorted(names, key=len, reverse=True)
    return re.compile('|'.join(map(re.escape, names)))


def match(title, pat, to_std):
    """제목 안의 메뉴 이름(별칭 포함) 중 가장 긴 것, 길이가 같으면 뒤쪽 → 표준 메뉴명"""
    t = clean(title)
    inside = blocked(t)
    hits = [(m.end() - m.start(), m.start(), m.group()) for m in pat.finditer(t)]
    # finditer 는 겹치는 후보를 놓치므로, 모든 시작 위치에서 다시 찾음
    for i in range(len(t)):
        m = pat.match(t, i)
        if m:
            hits.append((len(m.group()), i, m.group()))
    hits = [h for h in hits if h[1] not in inside and not not_dish(t, h[1] + h[0])]
    return to_std[max(hits)[2]] if hits else None


def gap_rules(menus, to_std=None):
    """사전 메뉴 → (메뉴, 재료 부분, 조리법 부분). '애호박볶음' → ('애호박볶음', '애호박', '볶음')
    to_std 를 주면 별칭도 규칙으로 ('시금치 된장 무침' → 별칭 시금치무침 → 시금치나물)"""
    names = sorted(to_std, key=lambda n: (-len(n), n)) if to_std else menus
    rules = []
    for n in names:
        std = to_std[n] if to_std else n
        for meth in sorted(METHOD, key=len, reverse=True):
            if n.endswith(meth) and len(n) - len(meth) >= 2:
                rules.append((std, n[:-len(meth)], meth))
                break
    return sorted(rules, key=lambda r: len(r[0]), reverse=True)


GAP_MAX = 8


def match_gap(title, rules):
    """재료 부분 … 조리법 부분이 순서대로 나오면 그 메뉴 ('애호박새우젓볶음' → 애호박볶음).
    사이는 8글자까지, 사이에 다른 조리법 말이 있으면 안 됨 ('애호박전과두부볶음' ✘)"""
    t = clean(title)
    inside = blocked(t)
    best = None
    for menu, head, meth in rules:
        i = t.find(head)
        while i >= 0:
            if i in inside:
                i = t.find(head, i + 1)
                continue
            if t[i + len(head):i + len(head) + 1] == '장' and head.endswith(('고추', '된', '간')):   # '고추장쥐포볶음' ≠ 고추볶음
                i = t.find(head, i + 1)
                continue
            j = t.find(meth, i + len(head))
            if j >= 0 and not not_dish(t, j + len(meth)):
                gap = t[i + len(head):j]
                if len(gap) <= GAP_MAX and not any(x in gap for x in METHOD if len(x) >= 2):
                    key = (len(menu), j, -len(gap))            # 긴 메뉴 → 뒤쪽 → 사이가 짧은 것
                    if best is None or key > best[0]:
                        best = (key, menu)
                    break
            i = t.find(head, i + 1)
    return best[1] if best else None


def match_best(title, pat, to_std, rules):
    """제목 → (메뉴, 방법). 기본은 이름 그대로(match).
    단, 사이 말 건너뛴 메뉴가 더 길고 그 메뉴가 그대로 찾은 메뉴로 끝나면 그쪽
    ('딸기 생크림 케이크' → 케이크 ✘ 딸기케이크 ✔, '바나나 우유 라떼' → 바나나라떼)"""
    e = match(title, pat, to_std)
    g = match_gap(title, rules)
    if e and g and len(g) > len(e) and g.endswith(e):
        return g, '제목 (사이 말 건너뜀)'
    if e:
        return e, '제목'
    if g:
        return g, '제목 (사이 말 건너뜀)'
    return None, None


def match_desc(desc, title, pat, to_std, heads):
    """소개 글에서 사전 메뉴 이름(별칭 포함). 단, 그 메뉴의 재료 부분이 제목에도 있어야 함
    ('말린 고사리 삶는법' + 소개 '고사리나물' ✔ / '애호박나물 …' + 소개 '라면' ✘). 여러 개면 자주 나온 것 → 긴 것 → 먼저 나온 것"""
    t = re.sub(r'\s+', '', str(desc or ''))
    tt = clean(title)
    if not t or t == 'None':
        return None
    cnt, first = collections.Counter(), {}
    for i in range(len(t)):
        m = pat.match(t, i)
        if m:
            std = to_std[m.group()]
            if not heads.get(std) or heads[std] not in tt:
                continue
            cnt[std] += 1
            first.setdefault(std, i)
    if not cnt:
        return None
    return min(cnt, key=lambda k: (-cnt[k], -len(k), first[k]))


def parent_of(menu, menus):
    """'참치김치찌개' → '김치찌개' 처럼 끝이 같은 더 짧은 메뉴"""
    cands = [m for m in menus if m != menu and menu.endswith(m) and len(m) >= 2]
    return max(cands, key=len) if cands else menu


def candidate(title):
    t = clean(title)
    for end in sorted(DISH_END, key=len, reverse=True):
        i = t.rfind(end)
        if i >= 0:
            return t[max(0, i - 6): i + len(end)]
    return None


# 조리법 (제목 끝 쪽) — 못 묶은 제목에서 '주재료 + 조리법' 사전 후보를 뽑을 때 씀 (묶기는 사전으로만)
METHOD = ['탕탕이', '탕탕', '볶음밥', '비빔밥', '덮밥', '김밥', '주먹밥', '초밥', '솥밥', '국밥', '비빔국수', '칼국수', '국수', '파스타', '리조또',
          '찌개', '전골', '국', '탕', '찜', '조림', '볶음', '무침', '나물', '전', '구이', '튀김', '맛탕', '김치', '장아찌', '피클',
          '절임', '샐러드', '스테이크', '카레', '죽', '밥', '말이', '꼬치', '샌드위치', '토스트', '케이크', '쿠키', '빵', '머핀',
          '스콘', '떡', '라떼', '에이드', '스무디', '청', '잼', '수프', '스프']
METHOD_SAME = {'나물볶음': '나물', '나물무침': '나물', '초무침': '무침', '들깨무침': '무침', '된장무침': '무침', '고추장무침': '무침', '스프': '수프', '뭇국': '국',
               '버터구이': '구이', '소금구이': '구이', '양념구이': '구이'}


def load_ingredients(folder, min_recipes=5):
    """재료 사전에서 주재료 이름 (양념 제외, 레시피 10개 이상) + 별칭(달걀 → 계란)"""
    path = P.clean('ingredient_dictionary.csv')
    if not os.path.exists(path):
        return {}
    d = pd.read_csv(path)
    d = d[(d['recipes'] >= min_recipes) & (d['seasoning_share'] < 0.5)]
    names = {re.sub(r'\s+', '', n): re.sub(r'\s+', '', n) for n in d['std_name']}
    alias = os.path.join(P.TABLES, 'ingredient_alias.csv')
    if os.path.exists(alias):
        for r in pd.read_csv(alias).itertuples():
            a, b = str(r[1]).strip(), str(r[2]).strip()
            if b in names and len(a) >= 2:
                names.setdefault(a, b)
    return names


def auto_menu(title, ing_names):
    """'고소한 송이버섯 들깨무침' → '송이버섯무침', '애호박새우젓볶음' → '애호박볶음' (주재료 = 조리법 앞에서 가장 앞에 나온 재료)"""
    t = clean(title)
    best = None
    for m in sorted(METHOD, key=len, reverse=True):
        i = t.rfind(m)
        if i > 0 and (best is None or i + len(m) > best[0] + len(best[1])):
            best = (i, m)
    if not best:
        return None
    i, m = best
    head = re.sub(r'김장|무지개|밥도둑|배달|파티|무조건|무한|밤새', '', t[:i])   # 한 글자 재료(김 · 무 · 밤)로 잘못 읽히는 말
    for long_m, base in METHOD_SAME.items():                        # '오징어초무침' → 무침
        if t[:i + len(m)].endswith(long_m):
            head, m = re.sub(r'김장|무지개|밥도둑|배달|파티|무조건|무한|밤새', '', t[:i + len(m) - len(long_m)]), base
    hits = []
    for name, std in ing_names.items():
        j = head.find(name)
        if j >= 0 and (len(name) >= 2 or j == 0):                    # 한 글자 재료(무 · 굴 · 김)는 맨 앞일 때만
            hits.append((j, -len(name), std))
    if not hits:
        return None
    return min(hits)[2] + m


def core_ingredients(lists, share=0.5):
    names = collections.Counter()
    for ing in lists:
        names.update({re.split(r'\s+\d|\s+약간|\s+적당', x)[0].strip() for x in ing})
    n = len(lists)
    return [k for k, v in names.most_common() if v / n >= share]


HERE = os.path.dirname(os.path.abspath(__file__))


def load_dish_types(map_path=os.path.join(P.DICT, 'dish_type_map.csv')):
    """레시피 → 요리 종류 (만개 종류별 분류 → dict/dish_type_map.csv 로 묶음). 한 레시피에 종류가 여럿이면 나눠서 셈"""
    if not (os.path.exists(P.CATEGORIES_RAW) and os.path.exists(map_path)):
        return {}
    c = pd.read_csv(P.CATEGORIES_RAW, encoding='utf-8-sig', dtype=str)
    c = c[c['group'] == '종류별']
    m = pd.read_csv(map_path, encoding='utf-8-sig', dtype=str).set_index('cat4_name')['dish_type']
    c = c.assign(dish=c['name'].map(m).fillna('기타'), recipe_id=pd.to_numeric(c['recipe_id'], errors='coerce'))
    out = collections.defaultdict(collections.Counter)
    for rid, g in c.dropna(subset=['recipe_id']).groupby('recipe_id'):
        for d in g['dish']:
            out[int(rid)][d] += 1 / len(g)
    return out


def menu_dish_type(recipe_ids, dish_by_recipe):
    """메뉴 레시피들의 요리 종류 다수결 → (요리 종류, 그 비율). 분류가 하나도 없으면 ('기타', None)"""
    cnt = collections.Counter()
    for rid in recipe_ids:
        cnt.update(dish_by_recipe.get(int(rid), {}))
    if not cnt:
        return '기타', None
    dish, n = cnt.most_common(1)[0]
    return dish, round(n / sum(cnt.values()), 2)


def main(recipes_path=P.RECIPES_JSONL, seed_path=P.MENU_SEED):
    out_dir = P.CLEAN                                                  # 결과는 data/clean
    rows_ = []
    for line in open(recipes_path, encoding='utf-8'):                 # 수집이 끊겨 깨진 줄은 건너뜀
        try:
            rows_.append(json.loads(line))
        except ValueError:
            pass
    df = pd.DataFrame(rows_)
    df = df.drop_duplicates('recipe_id', keep='last')
    menus, to_std = load_dictionary(seed_path)
    pat = build_matcher(to_std.keys())
    rules = gap_rules(menus, to_std)
    got = [match_best(t, pat, to_std, rules) for t in df['title']]
    df['menu'] = [m for m, _ in got]
    df['match_by'] = [b for _, b in got]
    if 'description' in df:
        heads = {m: h for m, h, _ in gap_rules(menus)}
        un = df['menu'].isna()
        m3 = pd.Series([match_desc(d_, t_, pat, to_std, heads) for d_, t_ in zip(df.loc[un, 'description'], df.loc[un, 'title'])],
                       index=df.index[un]).dropna()
        df.loc[m3.index, 'menu'] = m3
        df.loc[m3.index, 'match_by'] = '소개'
    ing_names = load_ingredients(out_dir)
    df['parent_menu'] = df['menu'].map(lambda m: parent_of(m, menus) if isinstance(m, str) else None)
    rm_path = os.path.join(out_dir, 'recipe_menu.csv')
    import changes                                                     # 지난 결과와 비교 → menu_changes.csv
    changes.compare(rm_path, df, 'recipe_id', 'menu', os.path.join(out_dir, 'menu_changes.csv'),
                    show=('title',), spell=lambda x: spell(re.sub(r'\s+', '', x)), label='메뉴가 바뀐 레시피')
    df[['recipe_id', 'title', 'menu', 'match_by', 'parent_menu']].to_csv(rm_path, index=False, encoding='utf-8-sig')

    for c in ('review_count', 'views'):
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0) if c in df else 0
    ok = df[df['menu'].notna()].copy()
    ok['score'] = ok['review_count'] * 100 + ok['views']   # 후기 1개 = 조회 100번으로 쳐서 대표 레시피 고름
    rows = []
    dish_by_recipe = load_dish_types()
    for menu, g in ok.groupby('menu'):
        best = g.sort_values('score', ascending=False).iloc[0]
        dish, dish_share = menu_dish_type(g['recipe_id'], dish_by_recipe)
        rows.append({'menu': menu, 'parent_menu': g['parent_menu'].iloc[0], 'dish_type': dish, 'dish_type_share': dish_share,
                     'recipes': len(g),
                     'reviews': int(g['review_count'].sum()),
                     'rep_recipe_id': best['recipe_id'], 'rep_title': best['title'],
                     'core_ingredients': ', '.join(core_ingredients(g['ingredients_flat']))})
    if not dish_by_recipe:
        print('  종류별 분류가 없어 dish_type 은 모두 기타 (collect_10000.py list --groups 종류별 로 받은 뒤 다시 실행)')
    pd.DataFrame(rows, columns=['menu', 'parent_menu', 'dish_type', 'dish_type_share', 'recipes', 'reviews', 'rep_recipe_id', 'rep_title', 'core_ingredients']).sort_values('recipes', ascending=False).to_csv(os.path.join(out_dir, 'menu_summary.csv'), index=False, encoding='utf-8-sig')

    miss = df[df['menu'].isna()]
    cnt = collections.Counter(c for c in miss['title'].map(candidate) if c)
    pd.DataFrame(cnt.most_common(), columns=['candidate', 'count']).to_csv(os.path.join(out_dir, 'menu_unmatched.csv'), index=False, encoding='utf-8-sig')
    miss[['recipe_id', 'title', 'views']].sort_values('views', ascending=False).to_csv(
        os.path.join(out_dir, 'menu_unmatched_titles.csv'), index=False, encoding='utf-8-sig')      # 못 묶은 제목 (조회수 순)
    # 사전에 넣을 후보: 못 묶은 제목 → '주재료 + 조리법' (사전 메뉴와 같은 이름이면 '별칭 후보')
    auto = miss.assign(cand=miss['title'].map(lambda t: auto_menu(t, ing_names))).dropna(subset=['cand'])
    cands = []
    for cand, g in auto.groupby('cand'):
        near = [m for m in menus if m != cand and (cand.endswith(m) or m.endswith(cand))]
        similar = f'{cand} (이미 사전에 있음 → 제목 표기를 별칭으로)' if cand in menus else (max(near, key=len) if near else '')
        cands.append({'candidate': cand, 'recipes': len(g), 'views': int(g['views'].sum()),
                      'similar_menu_in_seed': similar,
                      'example_titles': ' | '.join(g.sort_values('views', ascending=False)['title'].head(5))})
    cdf = pd.DataFrame(cands, columns=['candidate', 'recipes', 'views', 'similar_menu_in_seed', 'example_titles'])
    cdf.sort_values(['recipes', 'views'], ascending=False).to_csv(
        os.path.join(out_dir, 'menu_seed_candidates.csv'), index=False, encoding='utf-8-sig')
    print(f'레시피 {len(df):,}개 중 메뉴로 묶음 {len(ok):,}개 ({len(ok) / len(df):.0%}) · 메뉴 {len(rows):,}개 · 못 묶음 {len(miss):,}개')
    print('  묶은 방법:', ', '.join(f'{k} {v:,}' for k, v in ok['match_by'].value_counts().items()))
    if ing_names:
        print(f"사전 후보 {len(cdf):,}개 (레시피 3개 이상 {(cdf['recipes'] >= 3).sum():,}개 · 이 후보들로 묶일 레시피 {cdf['recipes'].sum():,}개)"
              f" → menu_seed_candidates.csv 에서 맞는 것만 menu_seed.csv 에 추가")
    else:
        print('  data/ingredient_dictionary.csv 가 없어 사전 후보는 건너뜀 (ingredient_clean.py 를 먼저 돌려 주세요)')

if __name__ == '__main__':
    main(*sys.argv[1:3])
