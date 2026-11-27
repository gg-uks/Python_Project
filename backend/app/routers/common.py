"""공통: 메인 화면 · 필터 태그 · 상태 확인."""
from fastapi import APIRouter

from .. import cache
from ..common import item_exclude_conditions, tag_conditions, user_items, ym_text
from ..db import Conn
from ..security import OptionalUser
from .trends import month_of, trending_menu_rows

router = APIRouter(prefix="/api", tags=["Common"])


@router.get("/health", summary="서버 · DB · Redis 상태 (HAProxy 헬스체크용)")
def health(conn: Conn):
    conn.execute("SELECT 1")
    last = conn.execute(
        "SELECT job, status, finished_at FROM omm_etl_runs ORDER BY run_id DESC LIMIT 1").fetchone()
    # Redis 가 down 이어도 status 는 ok (Redis 없이도 API 는 동작) → HAProxy 가 서버를 빼지 않음
    return {"status": "ok", "redis": cache.status(), "lastEtl": last}


@router.get("/filter-tags", summary="필터 태그 목록 (검색 필터 · 취향 선택)")
def filter_tags(conn: Conn):
    return cache.cached(conn, "filter-tags", None, lambda: conn.execute("""
        SELECT tag_id AS "tagId", label, kind
        FROM omm_filter_tags
        ORDER BY kind, sort_order, tag_id
    """).fetchall())


@router.get("/main", summary="메인 화면 (가성비 TOP · 뜨는 메뉴 · 가격 변동 재료 · 로그인 시 취향 반영)")
def main_page(conn: Conn, user: OptionalUser):
    tag_ids, excl_ids, items = [], [], []
    if user:   # 취향 태그: 가성비 레시피는 먹고 싶은 · 제외 모두, 뜨는 메뉴는 제외만 반영
        tags = conn.execute("""
            SELECT p.tag_id, t.kind FROM omm_user_preferences p JOIN omm_filter_tags t USING (tag_id) WHERE p.user_id = %s
        """, (user["user_id"],)).fetchall()
        tag_ids = sorted(t["tag_id"] for t in tags)
        excl_ids = sorted(t["tag_id"] for t in tags if t["kind"] == "TAGKIND_EXCLUDE")
        items = [i for i in user_items(conn, user["user_id"]) if i["kind"] == "TAGKIND_EXCLUDE"]
    # 캐시는 회원별이 아니라 "취향 태그 조합"별 → 같은 취향인 회원끼리 공유
    key_items = sorted(f"{i['ingredientId'] or ''}:{i['name']}" for i in items)
    return cache.cached(conn, "main", {"user": user is not None, "tags": tag_ids, "ex": key_items},
                        lambda: _main_body(conn, user is not None, tag_ids, excl_ids, items))


def _main_body(conn, personalized: bool, tag_ids: list[int], excl_ids: list[int], items=()) -> dict:
    want_where, want_params = tag_conditions(conn, tag_ids)
    excl_where, excl_params = tag_conditions(conn, excl_ids)
    # 직접 입력한 빼고 싶은 재료: 가성비 레시피 · 뜨는 메뉴(대표 레시피 기준) 둘 다 제외
    item_where, item_params = item_exclude_conditions(list(items))
    want_where, want_params = want_where + item_where, want_params + item_params
    excl_where, excl_params = excl_where + item_where, excl_params + item_params

    extra = "".join(f" AND {w}" for w in want_where)
    value = conn.execute(f"""
        SELECT r.recipe_id AS "recipeId", r.title, r.image_url AS "imageUrl", r.cook_time_min AS "cookMin",
               m.cost_per_serving AS "costPerServing", m.protein_per_1000won AS "proteinPer1000won",
               r.servings, r.view_count AS views, r.avg_rating AS rating, r.review_count AS "reviewCount",
               mn.dish_type AS "dishType", m.priced_ratio AS "pricedRatio"
        FROM omm_recipe_metrics m JOIN omm_recipes r USING (recipe_id)
        LEFT JOIN omm_menus mn ON mn.menu_id = r.menu_id
        -- 재료비가 너무 낮게 잡힌 레시피(소스 · 양념 등)가 1등이 되지 않게 1인분 1,000원 이상만
        WHERE m.priced_ratio >= 0.6 AND m.cost_per_serving >= 1000 AND m.protein_per_1000won IS NOT NULL {extra}
        ORDER BY m.protein_per_1000won DESC LIMIT 10
    """, want_params).fetchall()

    trend_month = month_of(conn, "omm_menu_interest_monthly", None)
    trending = trending_menu_rows(conn, trend_month, 10, 5, excl_where, excl_params)

    # 가격 변동 재료: 최근 달 소매가, 양념 제외, 평년 대비 오른 · 내린 5개씩
    price_month = month_of(conn, "omm_price_monthly", None)
    movers = conn.execute("""
        SELECT i.ingredient_id AS "ingredientId", i.name, pm.vs_normal_pct AS "vsNormalPct",
               pm.avg_price AS "avgPrice", pm.unit_label AS "unitLabel", pm.price_per_100g AS "pricePer100g"
        FROM omm_price_monthly pm JOIN omm_ingredients i USING (ingredient_id)
        WHERE pm.ym = %s AND pm.market_type = 'MARKET_RETAIL' AND NOT i.is_seasoning AND pm.vs_normal_pct IS NOT NULL
    """, (price_month,)).fetchall()
    up = sorted((x for x in movers if x["vsNormalPct"] > 0), key=lambda x: -x["vsNormalPct"])[:5]
    down = sorted((x for x in movers if x["vsNormalPct"] < 0), key=lambda x: x["vsNormalPct"])[:5]

    return {
        "personalized": personalized,
        "valueRecipes": value,
        "trendingMenus": trending, "trendMonth": ym_text(trend_month),
        "priceMovers": {"up": up, "down": down}, "priceMonth": ym_text(price_month),
    }
