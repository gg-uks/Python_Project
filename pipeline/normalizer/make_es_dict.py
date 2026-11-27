"""PG 사전 → ES 사전 파일 2개 (매일 daily.sh 에서 es_reload 앞에 돌려도 됨)
  python make_es_dict.py            # 만들기만 (logs/es/ 에 저장, 줄 수 · 예시 출력)
  python make_es_dict.py --push     # 만든 뒤 es 서버 /etc/elasticsearch/analysis/ 로 복사 (scp, adminb)

omm_userdict.txt   Nori 사용자 사전: 붙여 쓴 메뉴 · 재료 이름을 한 단어로 (만두피 · 오이탕탕이 · 닭가슴살)
                   → 바꾸면 인덱스를 닫았다 열고(es_search_setup.py --apply) es_reload.py --apply 로 다시 색인해야 반영
omm_synonyms.txt   동의어 (검색할 때만, 한쪽으로): 별칭 → 표준명 (대하 · 주키니 → 새우 · 애호박), 키워드 → 메뉴 (김찌 → 김치찌개)
                   → 바꾸면 _reload_search_analyzers 로 바로 반영 (다시 색인 필요 없음)
"""
import os, re, sys, subprocess, collections
import psycopg2

OUT = 'logs/es'
HANGUL = re.compile(r'[가-힣]{2,10}')
# 양 · 상태 · 메모가 붙은 별칭은 동의어로 쓰지 않음 (새우먹고싶은만큼, 애호박손질후 …)
JUNK = re.compile(r'(손질|약간|조금|적당|선택|생략|또는|먹고|만큼|정도|분량|사이즈|크기|작은|큰것|큰거|중간|냉동|시판|불린|삶은|다진|채썬|썬것|인분|개입|팩|봉지|컵|숟|스푼|큰술|작은술'
                  r'|그릇|가득|기준|듬뿍|크게|취향|실온|상태|몇알|다지기|삶기|삶는|찌기|튀김용|찜용|구이용|국물|건더기|건데기|약$|등$|한$|껏$)')

conn = psycopg2.connect(''); cur = conn.cursor()
cur.execute('SELECT ingredient_id, name, recipe_count FROM omm_ingredients')
ing = {i: (n, c or 0) for i, n, c in cur.fetchall()}
cur.execute('SELECT alias, ingredient_id FROM omm_ingredient_aliases WHERE is_active')
aliases = cur.fetchall()
cur.execute('SELECT name, coalesce(match_keywords, ARRAY[]::text[]) FROM omm_menus')
menus = cur.fetchall()

# 1) 사용자 사전: 3글자 이상 한글만 (2글자는 Nori 기본 사전이 대부분 앎) · 레시피 3개 이상 재료 + 메뉴 전부
words = {n for n, c in ing.values() if c >= 3 and HANGUL.fullmatch(n) and len(n) >= 3}
words |= {m for m, _ in menus if HANGUL.fullmatch(m) and len(m) >= 3}
# 아는 이름으로 나뉘면 나눔도 적어 둠 → decompound_mode=mixed 에서 통째 + 조각이 같이 색인
#   칵테일새우 → '칵테일새우 칵테일 새우' : '새우'로 찾아도 걸리고, '칵테일새우'로 찾으면 더 위로
known = {n for n, _ in ing.values() if HANGUL.fullmatch(n)} | {m for m, _ in menus if HANGUL.fullmatch(m)}


DISH_END = set('찜국탕전밥죽면')                   # 한 글자 조각은 요리 끝말일 때만 (차돌박이찜 → 차돌박이 + 찜)


def ok(part):
    return len(part) >= 2 or part in DISH_END      # 애호박 → '애' + 호박 ✕ (호박 ≠ 애호박), 만두피 → 만두 + '피' ✕


def seg(w):
    for i in range(1, len(w)):                     # 오른쪽이 아는 이름인 가장 긴 것
        if w[i:] in known and ok(w[:i]) and ok(w[i:]):
            return f'{w} {w[:i]} {w[i:]}'
    for i in range(len(w) - 1, 0, -1):              # 아니면 왼쪽이 아는 이름인 가장 긴 것
        if w[:i] in known and ok(w[:i]) and ok(w[i:]):
            return f'{w} {w[:i]} {w[i:]}'
    return w


userdict = [seg(w) for w in sorted(words)]

# 2) 동의어: 재료 표준명 + 깨끗한 별칭, 메뉴 + 키워드
groups = collections.defaultdict(set)
for a, iid in aliases:
    if iid not in ing:
        continue
    std = ing[iid][0]
    a = a.replace(' ', '')
    if a != std and HANGUL.fullmatch(a) and HANGUL.fullmatch(std) and not JUNK.search(a):
        groups[std].add(a)
for m, kws in menus:
    for k in kws:
        k = (k or '').replace(' ', '')
        if k != m and HANGUL.fullmatch(k) and HANGUL.fullmatch(m) and not JUNK.search(k):
            groups[m].add(k)
# 별칭이 다른 표준명과 같은 이름이면 빼기 (예: 별칭 '마늘' 이 '다진마늘' 쪽에 있으면 마늘 검색이 다진마늘로 섞임)
names = {n for n, _ in ing.values()} | {m for m, _ in menus}
syn = []
for k in sorted(groups):
    vals = sorted(v for v in groups[k] if v not in names)
    if vals:
        syn.append(f"{', '.join(vals)} => {k}")      # 한쪽으로만: 별칭으로 찾으면 표준명도 찾음 (표준명 검색은 넓히지 않음)

os.makedirs(OUT, exist_ok=True)
open(f'{OUT}/omm_userdict.txt', 'w', encoding='utf-8').write('\n'.join(userdict) + '\n')
open(f'{OUT}/omm_synonyms.txt', 'w', encoding='utf-8').write('\n'.join(syn) + '\n')
print(f'사용자 사전 {len(userdict):,}개 → {OUT}/omm_userdict.txt  예: {userdict[:8]}')
print(f'동의어 {len(syn):,}줄 → {OUT}/omm_synonyms.txt')
for s in [x for x in syn if x.endswith(('=> 새우', '=> 김치찌개', '=> 마늘', '=> 호박', '=> 만두', '=> 애호박'))]:
    print('  ', s[:120])
sys.stdout.flush()

if '--push' in sys.argv:
    dst = os.environ.get('ES_SSH', 'adminb@es')
    subprocess.run(['scp', f'{OUT}/omm_userdict.txt', f'{OUT}/omm_synonyms.txt', f'{dst}:/tmp/'], check=True)
    subprocess.run(['ssh', '-t', dst, 'sudo mkdir -p /etc/elasticsearch/analysis && sudo install -m 644 -o root -g elasticsearch /tmp/omm_userdict.txt /tmp/omm_synonyms.txt '
                    '/etc/elasticsearch/analysis/ && ls -l /etc/elasticsearch/analysis/'], check=True)