"""재료 이름 정규화 · 수량 파싱 · 메뉴 이름 (load_v4.py에서 씀)"""
import re

# 앞에 붙는 조리 · 손질 표현 (긴 것부터 지움)
# 띄어쓰기 뒤에 재료 이름이 올 때만 뗌 ("간 돼지고기" → 돼지고기, "간장"은 그대로)
MODIFIERS = ['곱게 다진', '굵게 다진', '잘게 다진', '다진', '데친', '불린', '삶은', '볶은', '구운', '찐', '익힌',
             '손질한', '손질된', '씻은', '채 썬', '어슷 썬', '송송 썬', '깍둑 썬', '얇게 썬', '썬', '깐', '간',
             '국산', '생', '냉동', '말린', '으깬', '갈은']
# 붙여 써도 떼는 접두어 ("저염간장" → 간장, "무염버터" → 버터)
PREFIXES = ['저염', '무염', '저당']
# 같은 재료를 한 이름으로 (쇼핑몰 검색어 기준)
SYNONYMS = {'브로컬리': '브로콜리', '컬리플라워': '콜리플라워', '레디쉬': '래디쉬', '셀러리': '샐러리', '노랑파프리카': '파프리카', '노란파프리카': '파프리카', '홍파프리카': '파프리카', '황파프리카': '파프리카', '주황파프리카': '파프리카', '빨강파프리카': '파프리카', '빨간파프리카': '파프리카', '적파프리카': '파프리카', '삼색파프리카': '파프리카', '쇠고기등심': '소고기', '등심': '소고기', '양지': '소고기', '차돌박이': '소고기', '돼지등심': '돼지고기', '통삼겹': '삼겹살', '닭고기살': '닭고기', '닭봉': '닭고기', '닭뼈': '닭고기', '닭': '닭고기', '닭다리살': '닭고기', '배춧잎': '배추', '배추잎': '배추', '알배추': '배추', '적채': '적양배추', '달걀흰자': '계란', '달걀노른자': '계란', '국멸치': '멸치', '잔멸치': '멸치', '건다시마': '다시마', '건미역': '미역', '새송이': '새송이버섯', '애느타리버섯': '느타리버섯', '양송이': '양송이버섯', '주키니호박': '돼지호박', '알마늘': '마늘', '슬라이스햄': '햄', '캔참치': '참치', '모차렐라치즈': '모짜렐라치즈', '레드어니언': '적양파', '중력분': '밀가루', '어린잎채소': '어린잎', '베이비채소': '어린잎', '새싹채소': '새싹', '플레인 요거트': '플레인요거트', '호상요구르트': '플레인요거트', '사과즙': '사과주스', '식용 꽃': '식용꽃', '스파게티면': '스파게티', '멥쌀': '쌀', '백미': '쌀', '대하': '새우', '새우살': '새우', '바지락살': '바지락', '레몬주스': '레몬즙', '달걀': '계란', '달걀물': '계란', '붉은 고추': '홍고추', '빨간 고추': '홍고추', '마른 고추': '건고추',
            '조선부추': '부추', '저염간장': '간장', '진간장': '간장', '국간장': '간장', '양조간장': '간장',
            '다진 마늘': '다진마늘', '마늘 다진것': '다진마늘', '통마늘': '마늘', '다진 생강': '다진생강', '쪽파': '파', '실파': '파', '청고추': '고추', '풋고추': '고추', '생표고버섯': '표고버섯', '표고': '표고버섯', '표고버섯 기둥': '표고버섯', '건표고': '건표고버섯', '마른표고': '건표고버섯', '마른표고버섯': '건표고버섯', '칵테일새우': '새우', '깐새우': '새우', '닭가슴살': '닭가슴살',
            '돼지고기 등심': '돼지고기', '쇠고기': '소고기', '참깨': '깨', '통깨': '깨', '요리당': '올리고당',
            '후춧가루': '후추', '흰 후추': '후추', '통후추': '후추', '올리브오일': '올리브유', '엑스트라버진 올리브유': '올리브유',
            '돈육': '돼지고기', '우육': '소고기', '노랑 파프리카': '노란파프리카', '노란 파프리카': '노란파프리카', '빨강 파프리카': '빨간파프리카',
            '빨간 파프리카': '빨간파프리카', '청피망': '피망', '홍피망': '피망', '게맛살': '크래미', '물엿': '올리고당', '흑설탕': '설탕'}
# 사지 않는 것 · 검색어가 안 되는 것
SKIP = {'물', '육수', '얼음', '소금물', '찬물', '끓는 물', '약간', '고명', '양념', '소스'}

def normalize(name):
    n = re.sub(r'\([^)]*\)', '', name)                    # 남은 괄호
    n = re.sub(r'[0-9./½⅓⅔¼¾]+.*$', '', n).strip()        # 뒤에 붙은 숫자 · 단위
    n = n.replace('·', ' ').strip()
    if re.match(r'^(마늘|생강)\s*다진\s*것$', n):              # 마늘다진것 → 다진마늘
        return '다진' + n[:2]
    if re.match(r'^(마른|말린|건조)\s*표고', n) or re.match(r'^표고(버섯)?\s*(마른|말린)\s*것$', n):
        return '건표고버섯'                                # 표고버섯마른것 · 말린 표고버섯 → 건표고버섯
    n = re.sub(r'\s*(다진\s*것|마른\s*것|채\s*썬\s*것|간\s*것|갠\s*것|슬라이스|가루낸\s*것)$', '', n).strip()   # 홍피망다진것 → 홍피망
    # 다진마늘 · 다진생강은 따로 파는 상품이 많아서 별도 재료로 둠 (다른 '다진 ○○'은 원재료로 합침)
    m = re.match(r'^(?:곱게 |굵게 |잘게 )?다진\s*(마늘|생강)$', n) or re.match(r'^(마늘|생강)\s*다진\s*것$', name.strip())
    if m:
        return '다진' + m.group(1)
    if re.match(r'^(마늘|생강)\s*다진\s*것', n):
        return '다진' + n[:2]
    m = re.match(r'^다진(\S{1,6})$', n)                   # 다진대파 → 대파, 다진양파 → 양파 (붙여 쓴 경우)
    if m and m.group(1) not in ('마늘', '생강'):
        n = m.group(1)
    changed = True
    while changed:                                        # 수식어가 여러 개 붙은 경우
        changed = False
        for m in sorted(MODIFIERS, key=len, reverse=True):
            if n.startswith(m + ' ') and len(n) > len(m) + 1:
                n = n[len(m):].strip()
                changed = True
    for p in PREFIXES:
        if n.startswith(p) and len(n) > len(p) + 1:
            n = n[len(p):].strip()
    m = re.match(r'^(돼지고기|소고기|쇠고기|닭고기|돼지|소)\s*(앞다리|뒷다리|목살|등심|안심|사태|양지|우둔|홍두깨|채끝|부채살|다짐육|간 ?것|불고기용|국거리용|찌개용|구이용|수육용|장조림용|잡채용|카레용)(살)?$', n)
    if m:                                                  # 돼지고기 앞다리 → 돼지고기 (부위는 KAMIS 품종으로)
        n = {'돼지': '돼지고기', '소': '소고기', '쇠고기': '소고기'}.get(m.group(1), m.group(1))
    if n == '파':                                          # 그냥 '파' 는 대파 (쪽파 · 실파는 '파' 로 합침)
        return '대파'
    n = SYNONYMS.get(n, n)
    n = SYNONYMS.get(n, n)
    return n if n and n not in SKIP and len(n) <= 12 else None


SEASONING = set('''
소금 천일염 볶은소금 함초소금 함초가루 버섯마늘소금 깨소금 설탕 황설탕 알룰로스 올리고당 물엿 꿀
후추 흰후추 흰후춧가루 흰 후춧가루 간장 맛간장 어간장 식초 사과식초 양조식초 발사믹식초 발사믹소스 홍초
참기름 들기름 식용유 올리브유 현미유 콩기름 대두유 식물성기름 튀김기름 고추기름 마늘기름 마늘오일
깨 검은깨 검정깨 흑임자 들깻가루 들깨가루 고춧가루
된장 일본된장 미소된장 고추장 쌈장 두반장 청국장가루
새우젓 멸치액젓 까나리액젓 액젓 젓갈
맛술 청주 정종 미림 미향 소주 와인 화이트와인 레드와인
마요네즈 케첩 토마토케첩 머스터드 머스타드 연겨자 겨자 겨자가루 와사비 굴소스 칠리소스 토마토소스 토마토페이스트 토마토콩카세 피클링스파이스
매실액 매실청 유자청 생강청 레몬즙 생강즙 양파즙
녹말가루 녹말 물녹말 전분 전분가루 감자전분 물전분
카레가루 강황가루 계피가루 생강가루 마늘가루 파프리카가루 바질가루 치자가루 백년초가루 표고버섯가루 파슬리가루 치즈가루
월계수잎 바질 로즈마리 로즈메리 오레가노 타임 정향 민트 차이브 가다랑어포 가쓰오부시
'''.split()) | {'흰 후춧가루'}

# 살 수 없는 것 (육수 · 물 · 이미 만든 것)
NOT_BUY = re.compile(r'육수|국물|다시마물|쌀뜨물|탄산수|^밥$|^쌀밥$|^현미밥$|^귀리밥$|지단|페이스트$|^플레인$|^국$')


# ─────────── 수량 파싱 · 정량 분류 (분석 8) ───────────
# 단위 → (분류, 1단위 g).  MEASURED 정량 · COUNTED 개수 · VAGUE 모호
UNITS = {
    'kg': ('MEASURED', 1000), 'g': ('MEASURED', 1), 'mg': ('MEASURED', 0.001), 'l': ('MEASURED', 1000), 'L': ('MEASURED', 1000),
    'ml': ('MEASURED', 1), 'mL': ('MEASURED', 1), 'cc': ('MEASURED', 1),
    'T': ('MEASURED', 15), 'Ts': ('MEASURED', 15), 'tbsp': ('MEASURED', 15), '큰술': ('MEASURED', 15), '큰스푼': ('MEASURED', 15),
    '밥숟가락': ('MEASURED', 15), '숟가락': ('MEASURED', 15), '숟갈': ('MEASURED', 15), '스푼': ('MEASURED', 15),
    't': ('MEASURED', 5), 'ts': ('MEASURED', 5), 'tsp': ('MEASURED', 5), '작은술': ('MEASURED', 5), '티스푼': ('MEASURED', 5), '찻숟가락': ('MEASURED', 5),
    '컵': ('MEASURED', 200), 'C': ('MEASURED', 200), 'cup': ('MEASURED', 200), '종이컵': ('MEASURED', 180), '공기': ('MEASURED', 210),
    '개': ('COUNTED', None), '알': ('COUNTED', None), '모': ('COUNTED', None), '대': ('COUNTED', None), '뿌리': ('COUNTED', None),
    '쪽': ('COUNTED', None), '톨': ('COUNTED', None), '장': ('COUNTED', None), '줄기': ('COUNTED', None), '송이': ('COUNTED', None),
    '마리': ('COUNTED', None), '포기': ('COUNTED', None), '통': ('COUNTED', None), '봉': ('COUNTED', None), '봉지': ('COUNTED', None),
    '팩': ('COUNTED', None), '캔': ('COUNTED', None), '조각': ('COUNTED', None), '토막': ('COUNTED', None), '줄': ('COUNTED', None),
    '단': ('COUNTED', None), '덩이': ('COUNTED', None), '공': ('COUNTED', None), '인분': ('COUNTED', None), '판': ('COUNTED', None),
    '줌': ('VAGUE', 30), '꼬집': ('VAGUE', 0.5), '약간': ('VAGUE', None), '적당량': ('VAGUE', None), '적당히': ('VAGUE', None),
    '조금': ('VAGUE', None), '넉넉히': ('VAGUE', None), '많이': ('VAGUE', None), '취향껏': ('VAGUE', None), '기호에따라': ('VAGUE', None),
    '톡톡': ('VAGUE', None), '살짝': ('VAGUE', None), '듬뿍': ('VAGUE', None), '소량': ('VAGUE', None), '약간씩': ('VAGUE', None),
}
VAGUE_WORDS = [u for u, (c, _) in UNITS.items() if c == 'VAGUE' and not re.match(r'^(줌|꼬집)$', u)]

# 셈 단위 1개 무게 (g) · 흔한 재료만. 없으면 COUNTED는 g을 비워 둠
PIECE_G = {'감자': 150, '양파': 200, '당근': 150, '애호박': 300, '오이': 200, '가지': 150, '무': 1500, '배추': 2500, '양배추': 1500,
           '대파': 100, '파': 10, '쪽파': 10, '마늘': 5, '다진마늘': 15, '생강': 15, '고추': 10, '청양고추': 10, '홍고추': 10,
           '계란': 50, '메추리알': 10, '두부': 300, '토마토': 200, '방울토마토': 15, '사과': 250, '레몬': 120, '단호박': 800,
           '파프리카': 200, '피망': 120, '브로콜리': 300, '새송이버섯': 80, '표고버섯': 20, '팽이버섯': 150, '느타리버섯': 150,
           '깻잎': 2, '상추': 10, '고등어': 400, '오징어': 300, '새우': 20, '닭고기': 1000, '소시지': 50, '햄': 200, '어묵': 30,
           '김': 2, '떡': 30, '라면': 120, '스팸': 200, '참치': 150, '치즈': 20, '슬라이스치즈': 20, '식빵': 35, '밥': 210, '쌀': 160}

NUM = r'(\d+\s*과\s*\d+\s*/\s*\d+|\d+\s+\d+\s*/\s*\d+|\d+\s*/\s*\d+|\d+(?:\.\d+)?|[½⅓⅔¼¾])'
FRAC = {'½': 0.5, '⅓': 1 / 3, '⅔': 2 / 3, '¼': 0.25, '¾': 0.75}

def _num(s):
    s = s.replace(' ', '')
    if s in FRAC: return FRAC[s]
    m = re.match(r'^(\d+)과?(\d+)/(\d+)$', s)
    if m and '/' in s and len(m.group(1)) and ('과' in s or len(s) > len(m.group(2)) + len(m.group(3)) + 1):
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    if '/' in s:
        a, b = s.split('/'); return int(a) / int(b) if int(b) else None
    return float(s)

def parse_amount(raw, ing_name=None):
    """'1/2개' → (0.5, '개', 75.0, 'COUNTED') · '약간' → (None, '약간', None, 'VAGUE') · '' → (None, None, None, 'MISSING')"""
    t = (raw or '').strip()
    if not t:
        return None, None, None, 'MISSING'
    t2 = re.sub(r'\(.*?\)', '', t).strip() or t        # "2큰술(30g)" → 앞 표기 우선
    m = re.search(NUM + r'\s*(?:~|-)\s*' + NUM, t2)   # 범위 1~2 → 평균
    if m:
        qty = (_num(m.group(1)) + _num(m.group(2))) / 2; rest = t2[m.end():]
    else:
        m = re.search(NUM, t2)
        qty = _num(m.group(1)) if m else None
        rest = t2[m.end():] if m else t2
    rest = rest.strip().replace(' ', '')
    unit = None
    for u in sorted(UNITS, key=len, reverse=True):
        if rest.startswith(u) or (qty is None and u in rest):
            unit = u; break
    if unit is None:
        if qty is None:
            return None, rest[:20] or None, None, ('VAGUE' if rest else 'MISSING')
        unit = rest[:20] or None
        return qty, unit, None, 'COUNTED' if unit is None or not re.search(r'[a-zA-Z]', unit) else 'MEASURED'
    cls, g = UNITS[unit]
    grams = None
    if cls == 'MEASURED' and qty is not None:
        grams = qty * g
    elif cls == 'COUNTED' and qty is not None and ing_name in PIECE_G:
        grams = qty * PIECE_G[ing_name]
    elif cls == 'VAGUE':
        if qty is not None and g: grams = qty * g          # 1줌 · 1꼬집만 대표값
    return qty, unit, round(grams, 1) if grams is not None else None, cls

# ─────────── 메뉴 이름 뽑기 (제목 → 메뉴) ───────────
DISH_SUFFIX = ('볶음밥', '비빔밥', '덮밥', '김밥', '주먹밥', '볶음면', '비빔면', '비빔국수', '칼국수', '국수', '라면', '우동', '파스타',
               '찌개', '전골', '국', '탕', '찜', '조림', '볶음', '무침', '구이', '튀김', '전', '부침개', '나물', '김치', '겉절이', '장아찌',
               '말이', '롤', '샐러드', '샌드위치', '토스트', '죽', '스튜', '카레', '떡볶이', '그라탕', '피자', '쿠키', '케이크', '빵', '머핀', '스테이크')
NOT_MENU_PREFIX = re.compile(r'^(초간단|간단|황금레시피|황금비율|백종원|만능|초스피드|맛있는|매콤한|매콤|얼큰한|얼큰|고소한|달콤한|새콤달콤|집에서|'
                             r'자취생|다이어트|밥도둑|최고의|폭풍|엄마표|아빠표|캠핑|도시락|건강한|든든한|영양만점|10분|5분|15분|30분)')

# 요리 이름처럼 끝나지만 요리가 아닌 단어 (도전 → '전'으로 끝남, 한국 → '국', 설탕 → '탕' …)
NOT_MENU = {'도전', '완전', '안전', '충전', '반전', '이전', '대전', '발전', '출전', '회전', '사전', '전전', '재도전', '첫도전', '요리도전',
            '한국', '중국', '미국', '천국', '외국', '전국', '본국', '애국', '사탕', '설탕', '흑설탕', '목욕탕', '캔디사탕',
            '구구', '찜찜', '우동국', '컨트롤', '스크롤', '빵빵', '말이말이', '전부', '죽죽'}

def menu_of(title):
    """'초간단 돼지고기 고추장찌개 황금비율' → '고추장찌개' · 끝이 요리 이름인 마지막 단어"""
    words = re.sub(r'\([^)]*\)', ' ', title or '')                 # 괄호 안 (찜) · (간단) 은 빼고
    words = re.sub(r'[^\w\s가-힣]', ' ', words).split()
    for i in range(len(words) - 1, -1, -1):
        w = NOT_MENU_PREFIX.sub('', words[i])
        if w in DISH_SUFFIX and i > 0:                  # '양배추 덮밥' → 양배추덮밥 (요리 이름만 따로 쓴 경우)
            w = NOT_MENU_PREFIX.sub('', words[i - 1]) + w
        if len(w) >= 2 and w.endswith(DISH_SUFFIX) and w not in DISH_SUFFIX and w not in NOT_MENU and not w.endswith(('도전', '완전')):
            return w
    return None

# ─────────── 숫자 정리 ───────────
def servings_of(s):
    m = re.search(r'(\d+)', s or ''); return int(m.group(1)) if m else None

def cook_min_of(s):
    s = s or ''
    m = re.search(r'(\d+)\s*시간', s)
    if m: return int(m.group(1)) * 60
    m = re.search(r'(\d+)\s*분', s); return int(m.group(1)) if m else None
