"""레시피: 검색 · 상세 · 조리 순서 · 냉장고 재료로 찾기."""
import html as _html
import re
import urllib.request
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ..common import code_suffix, item_exclude_conditions, not_found, tag_conditions, user_items, ym_text
from ..db import Conn
from ..security import OptionalUser
from .. import cache
from ..cache import cache_response

router = APIRouter(prefix="/api/recipes", tags=["Recipe"])

SORTS = {
    "views": "r.view_count DESC NULLS LAST",
    "rating": "r.avg_rating DESC NULLS LAST, r.review_count DESC",
    "cost": "m.cost_per_serving ASC NULLS LAST",
    "value": "m.protein_per_1000won DESC NULLS LAST",
    "time": "r.cook_time_min ASC NULLS LAST",
}


@router.get("", summary="레시피 검색 · 목록")
def search_recipes(
    conn: Conn,
    user: OptionalUser,
    q: str | None = Query(None, description="제목 또는 재료 이름"),
    tags: str | None = Query(None, description="필터 태그 번호, 쉼표 구분 (1,3)"),
    max_min: int | None = Query(None, alias="maxMin", ge=1, description="최대 조리시간(분)"),
    max_cost: int | None = Query(None, alias="maxCost", ge=1, description="최대 1인분 비용(원)"),
    dish_type: str | None = Query(None, alias="dishType", description="요리 종류 (국·찌개 …)"),
    sort: Literal["views", "rating", "cost", "value", "time"] = "views",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=50),
    prefs: Literal["on", "off"] = Query("on", description="로그인 시 직접 입력한 '빼고 싶은 재료' 제외 (off = 끄기)"),
):
    if q and q.strip() and page == 1:          # 인기 검색어 (첫 페이지만 세서 페이지 넘김은 중복으로 안 셈)
        cache.hit("q", " ".join(q.split()).lower()[:30])
    # 직접 입력한 빼고 싶은 재료 (캐시 키에 넣어서 같은 재료 조합끼리만 공유)
    items = [i for i in user_items(conn, user["user_id"]) if i["kind"] == "TAGKIND_EXCLUDE"] if user and prefs == "on" else []
    key_items = sorted(f"{i['ingredientId'] or ''}:{i['name']}" for i in items)
    data = cache.cached(conn, "recipes", {"q": q, "tags": tags, "maxMin": max_min, "maxCost": max_cost, "dishType": dish_type,
                                          "sort": sort, "page": page, "size": size, "ex": key_items},
                        lambda: _search(conn, q, tags, max_min, max_cost, dish_type, sort, page, size, items))
    return {**data, "excluded": [i["name"] for i in items]}


def _search(conn, q, tags, max_min, max_cost, dish_type, sort, page, size, ex_items=()):
    where, params = [], []
    if q and q.strip():
        like = f"%{q.strip()}%"
        where.append("""(r.title ILIKE %s OR EXISTS (
            SELECT 1 FROM omm_recipe_ingredients x JOIN omm_ingredients i USING (ingredient_id)
            WHERE x.recipe_id = r.recipe_id AND i.name ILIKE %s))""")
        params += [like, like]
    if tags:
        ids = [int(t) for t in tags.split(",") if t.strip().isdigit()]
        w, p = tag_conditions(conn, ids)
        where += w
        params += p
    if max_min:
        where.append("r.cook_time_min <= %s")
        params.append(max_min)
    if max_cost:
        where.append("m.cost_per_serving <= %s")
        params.append(max_cost)
    # 재료비가 들어가는 조건 · 정렬은 재료비를 믿을 수 있는 레시피만 (가격 붙은 재료 60% 이상, 1인분 500원 이상).
    # 그 아래는 단위 환산 · 시세 누락으로 3원 · 48원처럼 나와서 맨 위를 차지함. 가성비는 메인과 같게 1,000원 이상
    if max_cost or sort in ("cost", "value"):
        where.append("m.priced_ratio >= 0.6 AND m.cost_per_serving >= %s")
        params.append(1000 if sort == "value" else 500)
    if dish_type:
        where.append("mn.dish_type = %s")
        params.append(dish_type)
    w, p = item_exclude_conditions(list(ex_items))
    where += w
    params += p
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    base = f"""FROM omm_recipes r
               LEFT JOIN omm_recipe_metrics m USING (recipe_id)
               LEFT JOIN omm_menus mn ON mn.menu_id = r.menu_id
               {where_sql}"""

    total = conn.execute(f"SELECT count(*) AS n {base}", params).fetchone()["n"]
    items = conn.execute(f"""
        SELECT r.recipe_id AS "recipeId", r.title, mn.name AS menu, r.image_url AS "imageUrl",
               r.cook_time_min AS "cookMin", r.servings,
               m.cost_per_serving AS "costPerServing", m.kcal_per_serving AS "kcalPerServing",
               r.avg_rating AS rating, r.view_count AS views,
               mn.dish_type AS "dishType", r.review_count AS "reviewCount",
               m.priced_ratio AS "pricedRatio", m.reliability_grade AS reliability,
               m.protein_per_1000won AS "proteinPer1000won"
        {base}
        ORDER BY {SORTS[sort]}, r.recipe_id DESC
        LIMIT %s OFFSET %s
    """, params + [size, (page - 1) * size]).fetchall()
    for it in items:
        it["reliability"] = code_suffix(it["reliability"])
    return {"total": total, "page": page, "size": size, "items": items}


@router.get("/{recipe_id}", summary="레시피 상세")
def recipe_detail(recipe_id: int, conn: Conn):
    data = cache.cached(conn, "recipe", {"id": recipe_id}, lambda: _detail(recipe_id, conn))
    cache.hit("recipe", recipe_id)             # 인기 레시피 (없는 레시피면 위에서 404 라 안 셈)
    return data


def _detail(recipe_id: int, conn):
    r = conn.execute("""
        SELECT r.recipe_id, r.title, r.intro, r.image_url, r.servings, r.cook_time_min,
               d.code_nm AS difficulty, r.view_count, r.avg_rating, r.review_count,
               r.menu_id, mn.name AS menu, mn.dish_type,
               m.base_ym, m.cost_per_serving, m.est_cost_won, m.priced_ratio, m.reliability_grade,
               m.kcal_per_serving, m.protein_per_serving, m.sodium_per_serving,
               nu.kcal_serving, nu.protein_g_serving, nu.sodium_mg_serving
        FROM omm_recipes r
        LEFT JOIN omm_recipe_metrics m USING (recipe_id)
        LEFT JOIN omm_menus mn ON mn.menu_id = r.menu_id
        LEFT JOIN omm_menu_nutrition nu ON nu.menu_id = r.menu_id
        LEFT JOIN omm_common_codes d ON d.code_id = r.difficulty
        WHERE r.recipe_id = %s
    """, (recipe_id,)).fetchone()
    if r is None:
        raise not_found("레시피")

    # 재료: 시세 월(base_ym) 이전의 가장 최근 100g당 가격, 같은 달이면 소매 우선
    ingredients = conn.execute("""
        SELECT ri.ingredient_id AS "ingredientId", COALESCE(i.is_seasoning, false) AS "isSeasoning",
               COALESCE(i.name, ri.raw_name) AS name, ri.raw_name AS "rawName", ri.raw_amount AS raw,
               ri.group_name AS "group", ri.grams, p.price_per_100g AS "wonPer100g",
               round(ri.grams * p.price_per_100g / 100) AS cost
        FROM omm_recipe_ingredients ri
        LEFT JOIN omm_ingredients i USING (ingredient_id)
        LEFT JOIN LATERAL (
            SELECT pm.price_per_100g FROM omm_price_monthly pm
            WHERE pm.ingredient_id = ri.ingredient_id AND pm.price_per_100g IS NOT NULL
              AND pm.ym <= COALESCE(%s::date, date_trunc('month', now())::date)
            ORDER BY pm.ym DESC, (pm.market_type = 'MARKET_RETAIL') DESC
            LIMIT 1) p ON true
        WHERE ri.recipe_id = %s
        ORDER BY ri.seq
    """, (r["base_ym"], recipe_id)).fetchall()

    tastes = [row["word"] for row in conn.execute("""
        SELECT w.word FROM omm_recipe_tastes t JOIN omm_taste_words w USING (taste_id)
        WHERE t.recipe_id = %s GROUP BY w.word ORDER BY sum(t.mention_count) DESC LIMIT 5
    """, (recipe_id,)).fetchall()]

    reviews = conn.execute("""
        SELECT rating AS stars, body AS text, written_at AS "writtenAt"
        FROM omm_reviews WHERE recipe_id = %s ORDER BY written_at DESC LIMIT 10
    """, (recipe_id,)).fetchall()

    # 영양: 레시피 재료로 계산한 값이 없으면 메뉴 영양성분으로 대신
    from_recipe = r["kcal_per_serving"] is not None
    return {
        "recipeId": r["recipe_id"], "title": r["title"], "intro": r["intro"], "imageUrl": r["image_url"],
        "sourceUrl": f"https://www.10000recipe.com/recipe/{r['recipe_id']}",
        "menuId": r["menu_id"], "menu": r["menu"], "dishType": r["dish_type"], "servings": r["servings"], "cookMin": r["cook_time_min"],
        "difficulty": r["difficulty"], "views": r["view_count"], "rating": r["avg_rating"],
        "reviewCount": r["review_count"],
        "ingredients": ingredients,
        "metrics": {"costPerServing": r["cost_per_serving"], "estCostWon": r["est_cost_won"],
                    "pricedRatio": r["priced_ratio"], "reliability": code_suffix(r["reliability_grade"]),
                    "priceMonth": ym_text(r["base_ym"])},
        "nutrition": {
            "kcal": r["kcal_per_serving"] if from_recipe else r["kcal_serving"],
            "proteinG": r["protein_per_serving"] if from_recipe else r["protein_g_serving"],
            "sodiumMg": r["sodium_per_serving"] if from_recipe else r["sodium_mg_serving"],
            "basis": "recipe" if from_recipe else ("menu" if r["kcal_serving"] is not None else None),
        },
        "tastes": tastes,
        "reviews": reviews,
    }


# ── 조리 순서: 볼 때마다 만개의레시피 원문에서 읽어 옴 (DB 에 저장하지 않음 · 캐시 7일) ─────────────
_STEP_DIV = re.compile(r'<div[^>]+id="stepDiv(\d+)"[^>]*>(.*?)(?=<div[^>]+id="stepDiv\d+"|<div[^>]+class="[^"]*view_step_tip|<div[^>]+class="[^"]*view_tag|<div[^>]+class="[^"]*view_btn|$)', re.S)
_DESCR = re.compile(r'<div[^>]+(?:id="stepdescr\d+"|class="[^"]*media-body[^"]*")[^>]*>(.*?)</div>', re.S)
_IMG = re.compile(r'<img[^>]+src="([^"]+)"')
_TIP = re.compile(r'<div[^>]+class="[^"]*view_step_tip[^"]*"[^>]*>(.*?)</div>', re.S)


def _text(fragment: str) -> str:
    t = re.sub(r"<br\s*/?>", "\n", fragment)
    t = re.sub(r"<[^>]+>", "", t)
    return "\n".join(l.strip() for l in _html.unescape(t).splitlines() if l.strip())


def _fetch_steps(recipe_id: int) -> dict:
    url = f"https://www.10000recipe.com/recipe/{recipe_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (OMM class project; recipe steps viewer)"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            page = r.read().decode("utf-8", errors="replace")
    except Exception as e:                                   # 원문 사이트가 막히거나 느리면 빈 목록 (화면은 원문 링크로 안내)
        return {"steps": [], "tips": [], "sourceUrl": url, "error": f"원문을 불러오지 못했어요 ({type(e).__name__})"}
    steps = []
    for no, block in _STEP_DIV.findall(page):
        block = block[:6000]                                  # 마지막 단계 뒤의 다른 내용까지 잡지 않게
        d = _DESCR.search(block)
        img = _IMG.search(block)
        txt = _text(d.group(1) if d else block)
        if txt or img:
            steps.append({"no": int(no), "text": txt, "imageUrl": img.group(1) if img else None})
    tips = [t for t in (_text(x) for x in _TIP.findall(page)) if t]
    return {"steps": steps, "tips": tips, "sourceUrl": url, "error": None if steps else "조리 순서를 찾지 못했어요"}


@router.get("/{recipe_id}/steps", summary="조리 순서 (만개의레시피 원문에서 읽어 옴 · 저장 안 함 · 캐시 7일)")
def recipe_steps(recipe_id: int, conn: Conn):
    if conn.execute("SELECT 1 FROM omm_recipes WHERE recipe_id = %s", (recipe_id,)).fetchone() is None:
        raise not_found("레시피")
    class _NoSteps(Exception):
        pass

    def load():
        d = _fetch_steps(recipe_id)
        if not d["steps"]:                                    # 실패 · 빈 결과는 캐시에 남기지 않음 (다음에 다시 시도)
            raise _NoSteps(d)
        return d
    try:
        return cache.cached(conn, "recipe-steps", {"id": recipe_id}, load, ttl=7 * 86400)
    except _NoSteps as e:
        return e.args[0]


class ByIngredientsReq(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    ingredient_ids: list[int] = Field(min_length=1, max_length=30)
    limit: int = Field(20, ge=1, le=50)


@router.post("/by-ingredients", summary="냉장고 재료로 찾기")
@cache_response("by-ingredients")
def by_ingredients(body: ByIngredientsReq, conn: Conn):
    have = sorted(set(body.ingredient_ids))
    # 양념 제외한 재료 기준. haveRatio = 가진 재료 수 / 레시피 재료 수. 같은 재료가 두 줄이면 한 번만
    recipes = conn.execute("""
        WITH cand AS (
            SELECT DISTINCT recipe_id FROM omm_recipe_ingredients WHERE ingredient_id = ANY(%s)
        ), lines AS (
            SELECT DISTINCT ri.recipe_id, ri.ingredient_id
            FROM omm_recipe_ingredients ri JOIN cand USING (recipe_id)
            JOIN omm_ingredients i ON i.ingredient_id = ri.ingredient_id AND NOT i.is_seasoning
        ), score AS (
            SELECT recipe_id, count(*) AS total, count(*) FILTER (WHERE ingredient_id = ANY(%s)) AS have_cnt
            FROM lines GROUP BY recipe_id
        )
        SELECT s.recipe_id AS "recipeId", r.title, r.image_url AS "imageUrl", r.cook_time_min AS "cookMin",
               m.cost_per_serving AS "costPerServing",
               round(s.have_cnt::numeric / s.total, 2) AS "haveRatio", s.have_cnt AS "haveCnt", s.total AS "totalCnt",
               r.servings, r.view_count AS views, r.avg_rating AS rating, r.review_count AS "reviewCount",
               mn.dish_type AS "dishType", m.priced_ratio AS "pricedRatio"
        FROM score s JOIN omm_recipes r USING (recipe_id)
        LEFT JOIN omm_recipe_metrics m USING (recipe_id)
        LEFT JOIN omm_menus mn ON mn.menu_id = r.menu_id
        -- 양념 빼고 재료가 1개뿐인 레시피(감자 삶기 등)는 '전부 있음'으로 맨 위에 와서 2개 이상만
        WHERE s.have_cnt > 0 AND s.total >= 2
        ORDER BY s.have_cnt::numeric / s.total DESC, s.total - s.have_cnt, r.view_count DESC NULLS LAST
        LIMIT %s
    """, (have, have, body.limit)).fetchall()
    if not recipes:
        return []

    # 부족한 재료와 재료비 (레시피 g × 가장 최근 100g당 가격, 소매 우선)
    missing = conn.execute("""
        SELECT l.recipe_id, i.ingredient_id AS "ingredientId", i.name,
               round(l.grams * p.price_per_100g / 100) AS cost
        FROM (SELECT recipe_id, ingredient_id, max(grams) AS grams FROM omm_recipe_ingredients
              WHERE recipe_id = ANY(%s) AND ingredient_id IS NOT NULL AND NOT (ingredient_id = ANY(%s))
              GROUP BY recipe_id, ingredient_id) l
        JOIN omm_ingredients i ON i.ingredient_id = l.ingredient_id AND NOT i.is_seasoning
        LEFT JOIN LATERAL (
            SELECT pm.price_per_100g FROM omm_price_monthly pm
            WHERE pm.ingredient_id = l.ingredient_id AND pm.price_per_100g IS NOT NULL
            ORDER BY pm.ym DESC, (pm.market_type = 'MARKET_RETAIL') DESC LIMIT 1) p ON true
        ORDER BY l.recipe_id, cost DESC NULLS LAST
    """, ([r["recipeId"] for r in recipes], have)).fetchall()
    by_recipe: dict[int, list] = {}
    for row in missing:
        by_recipe.setdefault(row.pop("recipe_id"), []).append(row)
    for r in recipes:
        r["missing"] = by_recipe.get(r["recipeId"], [])
        costs = [x["cost"] for x in r["missing"] if x["cost"] is not None]
        r["missingCost"] = sum(costs) if costs else None
    return recipes
