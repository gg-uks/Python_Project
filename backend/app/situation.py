"""상황 문장 분석 (Elasticsearch 없이).

"오늘 뭐 먹지" 워크북의 절 규칙을 OMM 데이터에 맞춰 옮겼습니다.
  1. 절 나누기: ~는데 · ~어서 · ~지만 · 먹고 · 싫고 … 와 "싫어 · 말고 · 빼고" 바로 뒤, 문장부호에서 나눔
  2. 절마다 판단: 피하는 절(싫어 · 못 먹 · 빼고 …) / 이미 먹은 절(어제 … 먹어서) / 찾는 절
  3. 찾는 절: 상황 키워드 → 태그 (해장, 매운맛 …), "먹고 싶은" 재료 · 메뉴
     피하는 절: 재료 · 재료 분류 · 메뉴 이름 · 태그 키워드 → 뺄 것
     "안 매운", "덜 맵게" 처럼 키워드 앞에 안 · 못 · 덜 → 그 태그를 피함

재료 · 메뉴 이름은 형태소 분석 대신 "띄어쓰기 단위 + 조사 떼기"로 찾습니다.
  "오이랑" → 오이, "고수를" → 고수, "김치찌개는" → 김치찌개 (붙은 말은 원문 그대로라 김치만 빠지지 않음)
워크북의 알려진 한계 "망고 싫어 · 표고 빼고" (고에서 절이 잘림) 는 동사형 어미 목록으로만 나눠서 해결.
"""
import re
import time
from dataclasses import dataclass, field

# ── 절 나누기 ────────────────────────────────────────────────────────────
_CONNECT = ("는데", "은데", "니까", "으니", "어서", "아서", "해서", "여서", "워서", "와서", "었더니", "았더니", "했더니",
            "더니", "지만", "면서", "는데도", "건데", "던데", "인데", "한데", "운데", "할건데", "을건데")
_GO_VERBS = ("먹고", "싶고", "싫고", "좋고", "없고", "있고", "빼고", "말고", "않고", "땡기고", "당기고", "마시고",
             "했고", "였고", "같고", "오고", "질리고", "질렸고", "별로고", "아니고")
_NEG_END = ("싫어", "싫어요", "싫음", "싫다", "말고", "빼고", "빼줘", "빼주세요", "별로야", "별로", "질렸어", "질려",
            "물렸어", "물려", "제외", "제외하고", "싫은데", "안땡겨", "안당겨", "못먹어", "안먹어",
            "안먹어요", "못먹어요", "안먹음", "못먹음", "안땡겨요", "안당겨요")

NEG_RE = re.compile(r"못\s?먹|안\s?먹|안\s?땡|안\s?당기|안\s?당겨|안\s?끌|싫|별로(?!\s?없)|질리|질렸|질려|물리|물렸|물려|"
                    r"빼고|빼\s?줘|빼\s?주|제외|말고|피하|피해|알레르기|알러지|먹으면\s?안|끊었|안\s?들어|안\s?넣|(?<!맛)없이|(?<!맛)없는")
ATE_RE = re.compile(r"(어제|그제|아까|방금|점심|저녁|아침|지난번|최근|요즘|매일|계속).*먹(어서|었더니|었으니|었는데|었어|었음|었고)")
WANT_RE = re.compile(r"먹고\s?싶|땡겨|땡기|당겨|당기|들어간|넣은|로\s?만든|으로\s?만든|요리")
NOT_BEFORE_RE = re.compile(r"(안|못|덜)\s?$")

# 조사 (긴 것부터 떼 봄)
_PARTICLES = sorted(("이랑", "하고", "에서", "으로", "처럼", "같은", "이나", "까지", "부터", "이라", "이랑은", "랑은",
                     "들어간", "넣은", "은", "는", "이", "가", "을", "를", "도", "만", "랑", "와", "과", "로", "의",
                     "나", "요", "류", "들", "같이"), key=len, reverse=True)

# 한 글자 키워드가 다른 말 안에 들어 있는 경우 (탕 → 설탕 ✕)
KEYWORD_STOP = {"탕": ("설탕", "사탕", "탕수육", "맛탕", "탕후루"), "맵": (), "안주": ()}

# 재료 분류를 가리키는 말 → omm_ingredient_categories.category_id
CATEGORY_WORDS = {"고기": 4, "육류": 4, "생선": 5, "해산물": 5, "해물": 5, "수산물": 5, "채소": 1, "야채": 1,
                  "과일": 2, "유제품": 7, "가공식품": 8, "콩류": 6}
# 하위 재료로 넓힐 때 잘못 묶이는 것 (워크북 group_exclude 와 같은 생각)
SUFFIX_EXCLUDE = {"배추": {"양배추", "적양배추"}, "고추": {"고추냉이"}, "크림": {"아이스크림"}, "밀가루": {"메밀가루", "오트밀가루", "또는밀가루"},
                  "버터": {"땅콩버터"}, "기름": {"참기름", "들기름", "식용유"}}
ONE_CHAR_CHILDREN = {"파": ("대파", "쪽파", "실파", "파채"), "무": ("열무", "무청", "단무지"), "김": ("김가루", "조미김"),
                     "굴": ("생굴",), "게": ("꽃게", "대게", "홍게", "게살"), "콩": ("검은콩", "서리태", "완두콩", "강낭콩"),
                     "닭": ("닭고기", "닭가슴살", "닭다리", "닭날개", "닭봉", "닭안심"),
                     "빵": ("식빵", "모닝빵", "바게트", "베이글", "치아바타", "모닝롤", "햄버거빵", "핫도그빵", "크루아상")}
PREFIX_PARTS = ("살", "가루", "채", "즙", "포", "젓")
# 이름만으로는 안 묶이는 부위 · 종류 (닭고기 ⊃ 닭가슴살, 새우 ⊃ 대하)
PARENT_CHILDREN = {"닭고기": ("닭가슴살", "닭다리", "닭다리살", "닭날개", "닭봉", "닭안심", "닭발", "닭껍질", "닭갈비"),
                   "돼지고기": ("삼겹살", "목살", "앞다리살", "뒷다리살", "항정살", "돼지갈비", "돼지등뼈", "족발", "대패삼겹살"),
                   "소고기": ("차돌박이", "양지", "사태", "등심", "안심", "우둔", "홍두깨", "소갈비", "우삼겹", "채끝"),
                   "새우": ("대하", "중하", "칵테일새우", "건새우"), "명태": ("황태", "북어", "코다리", "동태", "노가리"),
                   "조개": ("바지락", "모시조개", "홍합", "꼬막", "가리비", "백합"), "버섯": ("표고버섯", "느타리버섯", "팽이버섯", "새송이버섯"),
                   # 밀가루를 피하면 밀가루로 만든 면 · 빵 · 가루도 (당면 · 메밀면 · 쌀국수면 · 두부면은 밀가루 아님)
                   "밀가루": ("중력분", "박력분", "강력분", "부침가루", "튀김가루", "빵가루", "소면", "중면", "칼국수면", "우동면",
                            "중화면", "파스타면", "스파게티면", "파스타", "통밀파스타면", "페투치네면", "카펠리니면", "라면", "짜장라면",
                            "비빔면", "칼국수라면", "멸치칼국수라면", "사리곰탕라면", "불닭볶음면", "생면", "도삭면", "만두피",
                            "식빵", "빵", "또띠아")}
# 피하는 절에 상황(때 · 장소 · 누구와)이 같이 있으면 그건 배경 → 피하는 건 이름 댄 메뉴 · 재료뿐 ("비 오는 날 파전 말고")
CONTEXT_TAGS = {"해장", "야식", "술안주", "손님상", "명절", "도시락", "보양", "비오는날", "따뜻하게", "시원하게",
                "캠핑", "아이", "아침", "간단하게", "가볍게", "고단백", "가성비", "속편한"}


def _nospace(s: str) -> str:
    return re.sub(r"\s+", "", s)


def split_clauses(text: str) -> list[str]:
    clauses, cur = [], []
    toks = [t for t in re.split(r"\s+", text.strip()) if t]
    for k, tok in enumerate(toks):
        end_punct = bool(re.search(r"[,.!?~;…]$", tok))
        word = re.sub(r"[,.!?~;…]+$", "", tok)
        cur.append(word)
        nxt = toks[k + 1] if k + 1 < len(toks) else ""
        go = (word in _GO_VERBS or word.endswith(_GO_VERBS)) and not nxt.startswith(("싶", "있", "말", "나서"))
        # "안 먹어" · "못 먹어" 처럼 띄어 쓴 부정은 앞 낱말과 붙여서 확인 (안+먹어 → 안먹어)
        pair = (cur[-2] if len(cur) > 1 else "") + word
        if end_punct or word.endswith(_CONNECT) or go or word.endswith(_NEG_END) or pair.endswith(_NEG_END):
            clauses.append(" ".join(cur))
            cur = []
    if cur:
        clauses.append(" ".join(cur))
    # "안 먹어" 처럼 부정어 혼자 떨어진 절은 앞 절에 붙임 ("오이 / 안 먹어" → "오이 안 먹어")
    merged: list[str] = []
    for c in clauses:
        # 부정어로 시작하는 짧은 조각만 붙임 ("매운 건 싫어" 처럼 대상이 있는 절은 따로 둠)
        if merged and NEG_RE.search(c) and len(_nospace(c)) <= 5 and re.match(r"(안|못|싫|별로|말고|빼|제외|질|물)", _nospace(c)):
            merged[-1] = merged[-1] + " " + c
        else:
            merged.append(c)
    return [c for c in merged if c]


def _stems(word: str) -> list[str]:
    """조사를 0~2번 떼서 나올 수 있는 후보 전부, 긴 것부터.
    '오이랑' → ['오이랑', '오이', '오'] ('이랑'·'랑' 둘 다 떼 봄) → 사전에 있는 가장 긴 것을 씀"""
    out, frontier = {word}, {word}
    for _ in range(2):
        nxt = set()
        for w in frontier:
            for p in _PARTICLES:
                if len(w) > len(p) and w.endswith(p):
                    nxt.add(w[: -len(p)])
        out |= nxt
        frontier = nxt
    return sorted(out, key=len, reverse=True)


# ── 사전 (DB 에서 읽어 프로세스에 잠시 보관) ──────────────────────────────────────
@dataclass
class Dictionary:
    tags: dict[int, dict]                       # sit_tag_id → {name, title, avoid_share}
    keywords: list[tuple[str, int]]             # (공백 뺀 키워드, sit_tag_id) 긴 것부터
    ingredients: dict[str, int]                 # 이름 · 별칭 → ingredient_id
    ingredient_names: dict[int, str]            # ingredient_id → 이름
    menus: dict[str, int]                       # 메뉴 이름 → menu_id
    loaded_at: float = field(default_factory=time.monotonic)


_DICT: Dictionary | None = None
DICT_TTL = 30                                   # 관리자가 키워드를 바꾸면 30초 안에 반영


def load_dictionary(conn, force: bool = False) -> Dictionary:
    global _DICT
    if _DICT and not force and time.monotonic() - _DICT.loaded_at < DICT_TTL:
        return _DICT
    tags = {r["sit_tag_id"]: r for r in conn.execute(
        "SELECT sit_tag_id, name, title, avoid_share::float AS avoid_share FROM omm_situation_tags WHERE use_yn = 'Y'").fetchall()}
    kws = [(_nospace(r["keyword"]), r["sit_tag_id"]) for r in conn.execute(
        "SELECT keyword, sit_tag_id FROM omm_situation_keywords").fetchall() if r["sit_tag_id"] in tags]
    kws.sort(key=lambda x: -len(x[0]))
    ing_rows = conn.execute(
        "SELECT ingredient_id, name FROM omm_ingredients WHERE recipe_count >= 3 OR name = ANY(%s)",
        ([c for cs in ONE_CHAR_CHILDREN.values() for c in cs],)).fetchall()
    ingredients = {r["name"]: r["ingredient_id"] for r in ing_rows}
    for r in conn.execute("""
            SELECT a.alias, a.ingredient_id FROM omm_ingredient_aliases a
            JOIN omm_ingredients i USING (ingredient_id) WHERE a.is_active""").fetchall():
        ingredients.setdefault(r["alias"], r["ingredient_id"])
    menus = {r["name"]: r["menu_id"] for r in conn.execute(
        "SELECT menu_id, name FROM omm_menus WHERE recipe_count >= 3").fetchall()}
    _DICT = Dictionary(tags, kws, ingredients, {r["ingredient_id"]: r["name"] for r in ing_rows}, menus)
    return _DICT


def expand_ingredient(d: Dictionary, word: str, ingredient_id: int | None) -> set[int]:
    """싫어하는 재료 → 그 재료 + 하위 재료 (호박 → 애호박 · 단호박, 파 → 대파 · 쪽파, 새우 → 새우살)"""
    ids = {ingredient_id} if ingredient_id else set()
    ids |= {d.ingredients[c] for c in PARENT_CHILDREN.get(word, ()) if c in d.ingredients}
    if len(word) == 1:
        ids |= {d.ingredients[c] for c in ONE_CHAR_CHILDREN.get(word, ()) if c in d.ingredients}
        return ids
    bad = SUFFIX_EXCLUDE.get(word, set())
    for name, iid in d.ingredients.items():
        if name == word or name in bad or any(name.endswith(b) for b in bad):
            continue
        if name.endswith(word) or (name.startswith(word) and name[len(word):] in PREFIX_PARTS):
            ids.add(iid)
    return ids


_PARENT_MEMO: dict[tuple[int, str], bool] = {}


def _parent_like(d: Dictionary, word: str) -> bool:
    """재료 사전에 그 이름은 없지만 하위 재료가 있는 말 (호박 → 단호박, 파 → 대파)"""
    if not word or word in d.menus:
        return False
    key = (id(d), word)
    if key not in _PARENT_MEMO:
        _PARENT_MEMO[key] = bool(expand_ingredient(d, word, None))
    return _PARENT_MEMO[key]


# ── 분석 결과 ──────────────────────────────────────────────────────────────
@dataclass
class Analysis:
    clauses: list[dict] = field(default_factory=list)          # [{text, kind: want|avoid|ate}]
    tags: dict[int, str] = field(default_factory=dict)         # 찾은 태그 → 근거 키워드
    avoid_tags: dict[int, str] = field(default_factory=dict)
    avoid_ingredients: dict[str, set[int]] = field(default_factory=dict)   # 말 → 재료 번호들
    avoid_categories: dict[str, int] = field(default_factory=dict)
    avoid_menu_words: list[str] = field(default_factory=list)  # 이름에 이 말이 든 메뉴는 뺌
    want_ingredients: dict[str, set[int]] = field(default_factory=dict)
    want_menus: dict[str, int] = field(default_factory=dict)


def _find_keywords(clause: str, d: Dictionary) -> list[tuple[int, str, bool]]:
    """절에서 상황 키워드 → [(태그, 키워드, 앞에 안·못·덜)]  (공백 무시, 긴 키워드 먼저, 겹치면 하나만)"""
    ns = _nospace(clause)
    used = [False] * len(ns)
    found = []
    for kw, tag_id in d.keywords:
        start = 0
        while (i := ns.find(kw, start)) >= 0:
            start = i + 1
            if any(used[i:i + len(kw)]):
                continue
            stop = KEYWORD_STOP.get(kw, ())
            if any(s in ns[max(0, i - 3):i + len(kw) + 3] for s in stop):
                continue
            for j in range(i, i + len(kw)):
                used[j] = True
            negated = bool(NOT_BEFORE_RE.search(ns[:i]))
            found.append((tag_id, kw, negated))
            break
    return found


def analyze(text: str, d: Dictionary) -> Analysis:
    a = Analysis()
    text = (text or "").strip()[:300]
    if not text:
        return a
    for clause in split_clauses(text):
        kind = "avoid" if NEG_RE.search(clause) else ("ate" if ATE_RE.search(clause) else "want")
        a.clauses.append({"text": clause, "kind": kind})

        kw_set = {kw for kw, _ in d.keywords}
        name_words = []                            # 재료 · 메뉴로 찾은 단어 (피하는 절에서는 키워드 검색에서 뺌)

        # 재료 · 메뉴 이름 (띄어쓰기 단위)
        for word in clause.split():
            hit = next((s for s in _stems(word) if s in kw_set or s in CATEGORY_WORDS or s in d.menus
                        or s in d.ingredients or _parent_like(d, s)), None)
            if hit and hit not in kw_set:
                name_words.append(word)
            for stem in ([hit] if hit else []):
                if stem in kw_set:
                    break                          # 상황 키워드 (맥주, 국물 …) 는 재료로 보지 않음
                if kind in ("avoid", "ate"):
                    if stem in CATEGORY_WORDS and kind == "avoid":
                        a.avoid_categories[stem] = CATEGORY_WORDS[stem]
                        break
                    if stem in d.menus:
                        a.avoid_menu_words.append(stem)
                        break
                    if (stem in d.ingredients or _parent_like(d, stem)) and kind == "avoid":
                        a.avoid_ingredients[stem] = expand_ingredient(d, stem, d.ingredients.get(stem))
                        a.avoid_menu_words.append(stem)
                        break
                elif WANT_RE.search(clause) or _nospace(clause) == stem:   # "떡볶이" 처럼 메뉴 이름만 말한 절도 먹고 싶은 것
                    if stem in d.menus:
                        a.want_menus[stem] = d.menus[stem]
                        break
                    if (stem in d.ingredients or _parent_like(d, stem)) and len(stem) >= 2:
                        a.want_ingredients[stem] = expand_ingredient(d, stem, d.ingredients.get(stem))
                        break

        # 상황 키워드 (피하는 · 먹은 절에서는 메뉴 · 재료 이름 안의 말을 빼고: "김치찌개 말고" ≠ 국물 전체를 피함)
        kw_text = clause
        if kind != "want":
            kw_text = " ".join(w for w in clause.split() if w not in name_words)
        for tag_id, kw, negated in _find_keywords(kw_text, d):
            if kind == "avoid" and name_words and not negated and d.tags[tag_id]["name"] in CONTEXT_TAGS:
                a.tags.setdefault(tag_id, kw)      # "비 오는 날 파전 말고" → 비오는날은 원함, 파전만 피함
            elif kind == "avoid" or negated:
                a.avoid_tags.setdefault(tag_id, kw)
            elif kind == "want":
                a.tags.setdefault(tag_id, kw)
    return _finish(a)


def _finish(a: Analysis) -> Analysis:
    # 찾으면서 동시에 피한 태그 ("매운 거 먹고 싶은데 너무 맵진 않게") → 피하기가 이김
    for t in a.avoid_tags:
        a.tags.pop(t, None)
    return a
