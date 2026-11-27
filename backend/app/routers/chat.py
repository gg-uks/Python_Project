"""OMM 도우미 챗봇 (Gemini + 도구 호출).

흐름: 질문 → Gemini 가 아래 도구 중 필요한 걸 고름 → 우리가 만든 함수(우리 SQL)로 실행 → 결과를 보고 Gemini 가 답을 씀.
AI 가 SQL 을 직접 만들지 않음. 회원 이메일 같은 개인정보는 Gemini 로 보내지 않음.

env (omm-api.env):
  GEMINI_API_KEY=...            # 없으면 503 → 화면이 규칙 챗봇으로 자동 전환
  CHAT_MODEL=gemini-3.1-flash-lite   # AI Studio 에서 쓰는 모델 이름 그대로 (바꿔도 코드 수정 없음)
  CHAT_LIMIT_PER_HOUR=30        # 회원(비회원은 IP)당 시간당 질문 수
"""
import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import cache
from ..common import user_items
from ..db import Conn
from ..security import OptionalUser
from . import insight, meals, menus, recipes, recommend_text, trends

router = APIRouter(prefix="/api", tags=["Chat · 챗봇"])
log = logging.getLogger("omm-api.chat")

API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL = os.getenv("CHAT_MODEL", "gemini-3.1-flash-lite")
LIMIT = int(os.getenv("CHAT_LIMIT_PER_HOUR", "30"))
URL = os.getenv("CHAT_API_URL", "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent")   # 시험용으로만 바꿈
MAX_ROUNDS = 4

SYSTEM = """너는 'OMM 도우미'야. OMM 은 만개의레시피 레시피, KAMIS 농산물 시세, 식약처 영양성분, 유튜브 쇼츠 관심도로
'오늘 뭐 먹을지'를 골라 주는 서비스야.
규칙:
- 한국어 해요체로 짧게 답해 (3~5문장). 목록은 '·' 로 3~5개까지.
- 메뉴 · 레시피 · 가격 · 영양 · 먹은 기록은 꼭 도구로 확인한 값만 말해. 도구 결과에 없는 숫자나 메뉴 이름을 지어내지 마.
- 시세를 말할 때는 기준 달(예: 2026-11)과 'KAMIS 소매가 기준'을 함께 말해.
- 상황 · 기분 · 몸 상태 문장(속이 안 좋아, 비 와, 야식, 손님, 가볍게 …)은 situation_recommend 를 먼저 써.
  싼 재료 · 요즘 시세 · 유행 기준이거나 재료 조건이 분명하면 recommend_menus 를 써.
- 사용자가 싫다/빼 달라고 한 재료나 음식은 avoid 에 넣어.
- '싸게', '가성비'면 mode=price, '요즘 유행'이면 mode=trend.
- 도구 결과가 비면 조건을 줄여 한 번 더 찾아보고, 그래도 없으면 솔직히 없다고 해.
- 음식 · 요리 · 장보기와 관계없는 질문은 OMM 에서 도와줄 수 있는 일을 짧게 안내해.
- 의학적 진단이나 치료 조언은 하지 말고, 영양 수치는 참고용이라고 말해.
- 카드(메뉴 · 레시피 목록)는 화면이 따로 보여 주니 답에서 링크 주소는 쓰지 마."""

# ── 도구 정의 (Gemini functionDeclarations) ──
STR_LIST = {"type": "array", "items": {"type": "string"}}
TOOLS = [{"functionDeclarations": [
    {"name": "situation_recommend", "description": "사용자의 상황 · 기분 · 몸 상태 문장으로 메뉴 추천 (예: 어제 회식해서 속이 안 좋아, 비 오는 날, 야식, 손님 초대, 가볍게). 해장 · 야식 · 술안주 · 보양 · 매운맛 · 국물 같은 상황 태그로 찾고 추천 이유를 줌. 최근 먹은 메뉴와 비슷한 건 뺌.",
     "parameters": {"type": "object", "properties": {
         "text": {"type": "string", "description": "사용자 상황 문장. 원하는 것과 싫은 것은 마침표로 나눠서 (예: '속이 안 좋아서 해장하고 싶어. 매운 건 싫어.')"}},
         "required": ["text"]}},
    {"name": "recommend_menus", "description": "조건에 맞는 메뉴 추천. 주재료 시세(평년 대비)와 요즘 관심도를 반영해 점수순.",
     "parameters": {"type": "object", "properties": {
         "want": {**STR_LIST, "description": "먹고 싶은 것을 짧은 낱말로 (메뉴 이름 · 요리 종류 · 재료 · 맛 표현에서 글자로 찾음). 예: 고기, 국·찌개, 면·분식, 얼큰, 매콤, 김치. '얼큰한 국물' 같은 문장은 '얼큰', '국·찌개' 로 나눠"},
         "avoid": {**STR_LIST, "description": "빼고 싶은 음식 · 재료 (예: 오이, 해산물)"},
         "mode": {"type": "string", "enum": ["balance", "price", "trend"], "description": "balance=균형, price=싼 재료 위주, trend=요즘 유행"},
         "situation": {"type": "string", "enum": ["any", "자취형", "간편 고급형", "주말 요리형", "대접형"],
                       "description": "자취형=빠르고 싸요, 간편 고급형=빠르지만 재료비가 들어요, 주말 요리형=오래 걸리지만 싸요, 대접형=오래 걸리고 재료비도 들어요"}}}},
    {"name": "ingredient_prices", "description": "재료 시세 (KAMIS 소매가 · 평년 대비 %). names 가 비면 요즘 시세가 많이 움직인 재료.",
     "parameters": {"type": "object", "properties": {"names": {**STR_LIST, "description": "재료 이름 (예: 대파, 계란)"}}}},
    {"name": "search_recipes", "description": "레시피 검색 (제목 · 재료 이름). 1인분 재료비 · 조리시간 조건 가능.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string", "description": "요리 이름이나 재료 (예: 김치찌개, 두부)"},
         "max_cost_won": {"type": "integer", "description": "1인분 재료비 상한 (원)"},
         "max_minutes": {"type": "integer", "description": "조리시간 상한 (분)"},
         "sort": {"type": "string", "enum": ["views", "cost", "value", "time", "rating"], "description": "views=인기, cost=싼 순, value=천원당 단백질, time=빠른 순"}},
         "required": ["query"]}},
    {"name": "recipes_from_fridge", "description": "가진 재료로 만들 수 있는 레시피 (가진 재료 비율 · 더 필요한 재료).",
     "parameters": {"type": "object", "properties": {"ingredients": {**STR_LIST, "description": "가진 재료 이름"}}, "required": ["ingredients"]}},
    {"name": "trending_menus", "description": "작년 같은 달보다 관심도(레시피 등록 · 후기 · 유튜브)가 오른/내린 메뉴",
     "parameters": {"type": "object", "properties": {"order": {"type": "string", "enum": ["rise", "fall"]}}}},
    {"name": "menu_info", "description": "메뉴의 1인분 영양(열량 · 단백질 · 나트륨) · 재료비 · 조리시간 · 대표 레시피. 비교할 때 여러 개.",
     "parameters": {"type": "object", "properties": {"names": {**STR_LIST, "description": "메뉴 이름 (예: 김치찌개, 된장찌개)"}}, "required": ["names"]}},
    {"name": "my_meals", "description": "로그인한 사용자의 이번 주(또는 지난주) 먹은 기록 요약 · 최근 3일 먹은 메뉴",
     "parameters": {"type": "object", "properties": {"week": {"type": "string", "enum": ["this", "last"]}}}},
]}]


def _clean(o):
    """DB 값(Decimal · date) → JSON"""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return o


def _find_ingredients(conn, names: list[str]) -> list[dict]:
    out = []
    for n in [x.strip() for x in names if x and x.strip()][:6]:
        r = conn.execute("""
            SELECT i.ingredient_id, i.name FROM omm_ingredients i
            WHERE i.name = %s OR i.name ILIKE %s
               OR EXISTS (SELECT 1 FROM omm_ingredient_aliases a WHERE a.ingredient_id = i.ingredient_id AND a.is_active AND a.alias = %s)
            ORDER BY (i.name = %s) DESC, i.is_seasoning, i.recipe_count DESC LIMIT 1
        """, (n, f"%{n}%", n.replace(" ", ""), n)).fetchone()
        if r and all(x["ingredient_id"] != r["ingredient_id"] for x in out):
            out.append(r)
    return out


# ── 도구 실행: (Gemini 에 돌려줄 결과, 화면 카드) ──
def run_tool(name: str, args: dict, conn, user) -> tuple[dict, list]:
    if name == "situation_recommend":       # 팀 상황 문장 추천 (POST /api/recommend/text 와 같은 함수)
        res = recommend_text.run_recommend(recommend_text.RecommendReq(text=(args.get("text") or "")[:300], recentDays=3 if user else 0, limit=5), conn, user)
        items = res["items"]
        data = {"title": res["title"], "analysis": res["analysis"], "menus": [
            {"name": m["name"], "dishType": m["dishType"], "cookMin": m["cookMin"], "costPerServing": m["costPerServing"],
             "reasons": m["reasons"]} for m in items]}
        cards = [{"to": f'/menus/{m["menuId"]}', "img": m["imageUrl"], "title": m["name"],
                  "sub": " · ".join(str(x) for x in [m["dishType"], m["cookMin"] and f'{m["cookMin"]}분', (m["reasons"] or [None])[0]] if x)} for m in items]
        return data, cards

    if name == "recommend_menus":
        sit = None
        if args.get("situation") and args["situation"] != "any":
            row = conn.execute("SELECT cluster_id FROM omm_menu_clusters WHERE name = %s", (args["situation"],)).fetchone()
            sit = row["cluster_id"] if row else None
        eaten = ",".join(str(i) for i in meals.recent_menus(user=user, conn=conn, days=3)["menuIds"]) if user else None
        res = insight.recommend(conn=conn, want=",".join(args.get("want") or []) or None, avoid=",".join(args.get("avoid") or []) or None,
                                situation=sit, mode=args.get("mode") or "balance", sort="rec", limit=5, page=1, eaten=eaten or None)
        items = res["items"]
        data = {"priceMonth": res.get("priceMonth"), "total": res["total"], "menus": [
            {"name": m["name"], "dishType": m["dishType"], "cookMin": m["cookMin"], "rating": m["rating"],
             "mainIngredientVsNormalPct": m["priceVsNormalPct"], "interestYoyPct": m["interestYoyPct"],
             "recentlyEaten": m["recentlyEaten"], "cheapOrExpensiveIngredients": [f'{i["name"]} {i["vsNormalPct"]}%' for i in m["ingredients"]]} for m in items]}
        cards = [{"to": f'/menus/{m["menuId"]}', "img": m["imageUrl"], "title": m["name"],
                  "sub": " · ".join(x for x in [m["dishType"], m["cookMin"] and f'{m["cookMin"]}분',
                                                m["priceVsNormalPct"] is not None and f'주재료 평년 대비 {m["priceVsNormalPct"]:+.0f}%'] if x)} for m in items]
        return data, cards

    if name == "ingredient_prices":
        found = _find_ingredients(conn, args.get("names") or [])
        if args.get("names") and not found:
            return {"error": "재료 사전에서 못 찾았어요", "names": args["names"]}, []
        res = insight.ingredient_summary(conn=conn, ids=",".join(str(f["ingredient_id"]) for f in found) or None)
        return {"basis": "KAMIS 소매가 · 전국 평균", "month": res["ym"], "items": [
            {"name": i["name"], "avgPrice": i["avgPrice"], "unit": i["unitLabel"], "vsNormalPct": i["vsNormalPct"]} for i in res["items"]]}, []

    if name == "search_recipes":
        res = recipes._search(conn, args.get("query"), None, args.get("max_minutes"), args.get("max_cost_won"), None,
                              args.get("sort") or "views", 1, 5)
        items = res["items"]
        return {"total": res["total"], "recipes": [
            {"title": r["title"], "cookMin": r["cookMin"], "costPerServing": r.get("costPerServing"), "rating": r.get("rating"),
             "views": r.get("views")} for r in items]}, [_recipe_card(r) for r in items]

    if name == "recipes_from_fridge":
        found = _find_ingredients(conn, args.get("ingredients") or [])
        if not found:
            return {"error": "재료를 못 찾았어요"}, []
        res = recipes.by_ingredients(body=recipes.ByIngredientsReq(ingredient_ids=[f["ingredient_id"] for f in found], limit=5), conn=conn)
        return {"have": [f["name"] for f in found], "recipes": [
            {"title": r["title"], "haveRatio": r["haveRatio"], "missing": [m.get("name") for m in r.get("missing", [])][:5],
             "cookMin": r["cookMin"]} for r in res]}, [_recipe_card(r) for r in res]

    if name == "trending_menus":
        res = trends.trending_menus(conn=conn, ym=None, limit=5, min_cnt=5, order=args.get("order") or "rise")
        items = res["items"]
        return {"month": res["ym"], "menus": [{"name": m["name"], "dishType": m["dishType"], "interestYoyPct": m["yoyPct"]} for m in items]}, \
            [{"to": f'/menus/{m["menuId"]}', "img": m["imageUrl"], "title": m["name"],
              "sub": " · ".join(x for x in [m["dishType"], m["yoyPct"] is not None and f'관심도 {m["yoyPct"]:+.0f}%'] if x)} for m in items]

    if name == "menu_info":
        out, cards = [], []
        for n in (args.get("names") or [])[:4]:
            row = conn.execute("""SELECT menu_id FROM omm_menus WHERE name = %s OR replace(name, ' ', '') ILIKE %s
                                  ORDER BY (name = %s) DESC, recipe_count DESC LIMIT 1""", (n, f"%{n.replace(' ', '')}%", n)).fetchone()
            if not row:
                out.append({"name": n, "error": "메뉴를 못 찾았어요"})
                continue
            d = menus.menu_detail(menu_id=row["menu_id"], conn=conn)
            nu = d.get("nutrition") or {}
            out.append({"name": d["name"], "dishType": d["dishType"], "cookMin": d["cookMin"], "costPerServingWon": d["costPerServing"],
                        "kcal": nu.get("kcal"), "proteinG": nu.get("proteinG"), "sodiumMg": nu.get("sodiumMg"),
                        "type": (d.get("cluster") or {}).get("name"), "repRecipe": d["repTitle"]})
            cards.append({"to": f'/menus/{d["menuId"]}', "img": d["imageUrl"], "title": d["name"],
                          "sub": " · ".join(x for x in [d["dishType"], nu.get("kcal") and f'{float(nu["kcal"]):.0f} kcal'] if x)})
        return {"menus": out, "note": "영양은 식약처 메뉴 단위 1인분 값"}, cards

    if name == "my_meals":
        if not user:
            return {"error": "로그인해야 볼 수 있어요"}, []
        wk = None
        if args.get("week") == "last":
            wk = meals.today() - timedelta(days=7)
        s = meals.week_summary(user=user, conn=conn, week=wk)
        recent = meals.recent_menus(user=user, conn=conn, days=3)
        names = [r["name"] for r in conn.execute("SELECT name FROM omm_menus WHERE menu_id = ANY(%s)", (recent["menuIds"],)).fetchall()] if recent["menuIds"] else []
        return {"week": f'{s["weekStart"]}~{s["weekEnd"]}', "meals": s["count"], "total": s["total"], "dailyAvg": s["dailyAvg"],
                "dishMix": s["dishMix"], "topMenus": s["topMenus"], "recent3days": names}, []

    return {"error": f"모르는 도구: {name}"}, []


def _recipe_card(r):
    cost = r.get("costPerServing")
    ok = cost is not None and (r.get("pricedRatio") or 0) >= 0.6 and cost >= 500
    return {"to": f'/recipes/{r["recipeId"]}', "img": r.get("imageUrl"), "title": r["title"],
            "sub": " · ".join(x for x in [r.get("cookMin") is not None and f'{r["cookMin"]}분', ok and f'1인분 {int(cost):,}원',
                                          r.get("haveRatio") is not None and f'가진 재료 {float(r["haveRatio"]) * 100:.0f}%'] if x)}


# ── Gemini 호출 ──
def _gemini(contents: list, system: str) -> dict:
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents, "tools": TOOLS,
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 800}}
    req = urllib.request.Request(URL.format(model=MODEL), data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": API_KEY}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")[:300]
        log.warning("gemini %s: %s", e.code, msg)
        raise HTTPException(429 if e.code == 429 else 502, "AI 사용량을 넘었어요. 잠시 뒤 다시 물어봐 주세요" if e.code == 429 else "AI 응답을 받지 못했어요")
    except (urllib.error.URLError, TimeoutError) as e:
        log.warning("gemini 연결 실패: %s", e)
        raise HTTPException(502, "AI 서버에 연결하지 못했어요")


def _limit(who: str) -> None:
    r = cache._r()
    if r is None:
        return
    key = f"{cache.P}chat:{who}:{int(time.time() // 3600)}"
    try:
        n = r.incr(key)
        if n == 1:
            r.expire(key, 3700)
    except Exception:
        return
    if n > LIMIT:
        raise HTTPException(429, f"질문은 한 시간에 {LIMIT}번까지 할 수 있어요")


class Turn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=2000)


class ChatReq(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    history: list[Turn] = Field(default_factory=list, max_length=20)


@router.get("/chat/status", summary="챗봇 AI 가 켜져 있는지 (화면이 처음 열 때 확인)")
def chat_status():
    return {"enabled": bool(API_KEY), "provider": "gemini", "model": MODEL if API_KEY else None, "limitPerHour": LIMIT}


@router.post("/chat", summary="OMM 도우미 챗봇 (Gemini · 도구 호출). 키가 없으면 503")
def chat(body: ChatReq, conn: Conn, user: OptionalUser, request: Request):
    if not API_KEY:
        raise HTTPException(503, "챗봇 AI 가 아직 설정되지 않았어요")
    _limit(f'u{user["user_id"]}' if user else f'ip{request.client.host if request.client else "-"}')

    system = SYSTEM
    if user:        # 저장한 취향만 알려 줌 (이메일 · 이름 같은 개인정보는 안 보냄)
        items = user_items(conn, user["user_id"])
        want = [i["name"] for i in items if i["kind"] == "TAGKIND_WANT"]
        avoid = [i["name"] for i in items if i["kind"] == "TAGKIND_EXCLUDE"]
        system += f"\n이 사용자는 로그인했어. 저장한 취향 - 먹고 싶은: {', '.join(want) or '없음'} / 빼고 싶은: {', '.join(avoid) or '없음'}. 추천할 때 빼고 싶은 재료는 avoid 에 넣어."
    else:
        system += "\n이 사용자는 로그인하지 않았어. 먹은 기록을 물으면 로그인이 필요하다고 해."
    system += f"\n오늘 날짜: {meals.today().isoformat()}"

    contents = [{"role": "user" if t.role == "user" else "model", "parts": [{"text": t.content}]} for t in body.history[-10:] if t.content.strip()]
    # Gemini 는 user 로 시작해야 해서 앞쪽 인사(assistant)는 뺌
    while contents and contents[0]["role"] != "user":
        contents.pop(0)
    contents.append({"role": "user", "parts": [{"text": body.message}]})

    cards, used = [], []
    for _ in range(MAX_ROUNDS):
        res = _gemini(contents, system)
        cand = (res.get("candidates") or [{}])[0]
        content = cand.get("content") or {"role": "model", "parts": []}
        parts = content.get("parts") or []
        calls = [p["functionCall"] for p in parts if "functionCall" in p]
        if not calls:
            text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
            if not text:
                text = "답을 만들지 못했어요. 조금 다르게 물어봐 주세요."
            return {"reply": text, "cards": cards[:5], "actions": _actions(used), "model": MODEL}
        contents.append(content)        # thoughtSignature 포함 그대로 돌려줘야 함
        responses = []
        for fc in calls:
            try:
                data, c = run_tool(fc.get("name", ""), fc.get("args") or {}, conn, user)
            except HTTPException as e:
                data, c = {"error": e.detail}, []
            except Exception as e:      # 도구 하나가 실패해도 대화는 계속
                log.exception("chat tool %s", fc.get("name"))
                data, c = {"error": "조회 중 오류"}, []
            if c:
                cards = c
            used.append((fc.get("name"), fc.get("args") or {}))
            fr = {"name": fc.get("name"), "response": _clean(data)}
            if fc.get("id"):
                fr["id"] = fc["id"]
            responses.append({"functionResponse": fr})
        contents.append({"role": "user", "parts": responses})
    return {"reply": "조건이 복잡해서 한 번에 찾지 못했어요. 조금 나눠서 물어봐 주세요.", "cards": cards[:5], "actions": _actions(used), "model": MODEL}


def _actions(used: list) -> list:
    """마지막으로 쓴 도구에 맞는 화면 바로가기"""
    from urllib.parse import urlencode
    for name, a in reversed(used):
        if name == "situation_recommend":
            return [["메뉴 추천 화면", "/"]]
        if name == "recommend_menus":
            q = {k: v for k, v in {"want": ",".join(a.get("want") or []), "avoid": ",".join(a.get("avoid") or []), "mode": a.get("mode") or "balance"}.items() if v}
            return [["추천 결과 전체 보기", f"/recommend?{urlencode(q)}"]]
        if name == "search_recipes":
            return [["레시피 검색 결과 보기", f"/recipes?{urlencode({'q': a.get('query', '')})}"]]
        if name == "recipes_from_fridge":
            return [["냉장고 털기 화면", "/fridge"]]
        if name == "trending_menus":
            return [["트렌드 더 보기", "/trends"]]
        if name == "ingredient_prices":
            return [["재료 시세 보기", "/explore"]]
        if name == "my_meals":
            return [["먹은 기록 자세히", "/mypage?tab=meals"]]
        if name == "menu_info":
            return [["메뉴 추천 보기", "/"]]
    return []
