"""메뉴: 상세 · 관심도 추이 · 비슷한 메뉴."""
from fastapi import APIRouter, Query

from ..common import not_found, ym_text
from ..db import Conn
from ..cache import cache_response

router = APIRouter(prefix="/api/menus", tags=["Menu"])


def _check_menu(conn, menu_id: int) -> None:
    if conn.execute("SELECT 1 FROM omm_menus WHERE menu_id = %s", (menu_id,)).fetchone() is None:
        raise not_found("메뉴")


@router.get("/{menu_id}", summary="메뉴 상세 (대표 레시피 · 영양 · 군집)")
@cache_response("menu")
def menu_detail(menu_id: int, conn: Conn):
    m = conn.execute("""
        SELECT m.menu_id, m.name, m.dish_type, m.rep_recipe_id, m.recipe_count,
               r.title AS rep_title, r.image_url, r.cook_time_min,
               rm.cost_per_serving,
               nu.value_kind, nu.serving_g, nu.kcal_serving, nu.protein_g_serving, nu.fat_g_serving,
               nu.carb_g_serving, nu.sugar_g_serving, nu.sodium_mg_serving,
               c.cluster_id, c.name AS cluster_name, c.description AS cluster_desc,
               c.center_cook_min, c.center_cost_won,
               mi.ym AS interest_ym, mi.interest_index, mi.yoy_pct
        FROM omm_menus m
        LEFT JOIN omm_recipes r ON r.recipe_id = m.rep_recipe_id
        LEFT JOIN omm_recipe_metrics rm ON rm.recipe_id = m.rep_recipe_id
        LEFT JOIN omm_menu_clusters c ON c.cluster_id = rm.cluster_id
        LEFT JOIN omm_menu_nutrition nu ON nu.menu_id = m.menu_id
        LEFT JOIN LATERAL (
            SELECT ym, interest_index, yoy_pct FROM omm_menu_interest_monthly
            WHERE menu_id = m.menu_id ORDER BY ym DESC LIMIT 1) mi ON true
        WHERE m.menu_id = %s
    """, (menu_id,)).fetchone()
    if m is None:
        raise not_found("메뉴")
    recipes = conn.execute("""
        SELECT r.recipe_id AS "recipeId", r.title, r.image_url AS "imageUrl", r.cook_time_min AS "cookMin",
               r.servings, rm.cost_per_serving AS "costPerServing", rm.priced_ratio AS "pricedRatio",
               r.avg_rating AS rating, r.view_count AS views, r.review_count AS "reviewCount"
        FROM omm_recipes r LEFT JOIN omm_recipe_metrics rm USING (recipe_id)
        WHERE r.menu_id = %s ORDER BY r.view_count DESC NULLS LAST LIMIT 8
    """, (menu_id,)).fetchall()
    return {
        "menuId": m["menu_id"], "name": m["name"], "dishType": m["dish_type"],
        "repRecipeId": m["rep_recipe_id"], "repTitle": m["rep_title"], "imageUrl": m["image_url"],
        "cookMin": m["cook_time_min"], "costPerServing": m["cost_per_serving"], "recipeCount": m["recipe_count"],
        "nutrition": None if m["value_kind"] is None else {
            "valueKind": m["value_kind"], "servingG": m["serving_g"], "kcal": m["kcal_serving"],
            "proteinG": m["protein_g_serving"], "fatG": m["fat_g_serving"], "carbG": m["carb_g_serving"],
            "sugarG": m["sugar_g_serving"], "sodiumMg": m["sodium_mg_serving"]},
        # 군집 = 대표 레시피의 군집 (분석 1 K-means)
        "cluster": None if m["cluster_id"] is None else {
            "clusterId": m["cluster_id"], "name": m["cluster_name"], "description": m["cluster_desc"],
            "centerCookMin": m["center_cook_min"], "centerCostWon": m["center_cost_won"]},
        "interest": None if m["interest_ym"] is None else {
            "ym": ym_text(m["interest_ym"]), "interestIndex": m["interest_index"], "yoyPct": m["yoy_pct"]},
        "recipes": [{**r, "dishType": m["dish_type"]} for r in recipes],
    }


@router.get("/{menu_id}/interest", summary="메뉴 관심도 추이")
@cache_response("menu-interest")
def menu_interest(menu_id: int, conn: Conn, months: int = Query(12, ge=1, le=36)):
    _check_menu(conn, menu_id)
    rows = conn.execute("""
        SELECT ym, interest_index AS "interestIndex", interest_cnt AS "interestCnt",
               new_recipe_cnt AS "newRecipeCnt", review_cnt AS "reviewCnt",
               yt_video_cnt AS "ytVideoCnt", yt_index AS "ytIndex", yoy_pct AS "yoyPct", yt_yoy_pct AS "ytYoyPct"
        FROM omm_menu_interest_monthly WHERE menu_id = %s
        ORDER BY ym DESC LIMIT %s
    """, (menu_id, months)).fetchall()
    for row in rows:
        row["ym"] = ym_text(row["ym"])
    return list(reversed(rows))          # 오래된 달 → 최근 달 (그래프 순서)


@router.get("/{menu_id}/similar", summary="비슷한 메뉴")
@cache_response("menu-similar")
def menu_similar(menu_id: int, conn: Conn, limit: int = Query(5, ge=1, le=20)):
    _check_menu(conn, menu_id)
    return conn.execute("""
        SELECT s.similar_menu_id AS "menuId", m.name, m.dish_type AS "dishType", s.score, m.rep_recipe_id AS "repRecipeId",
               m.recipe_count AS "recipeCount", r.image_url AS "imageUrl", nu.kcal_serving AS kcal
        FROM omm_menu_similarities s JOIN omm_menus m ON m.menu_id = s.similar_menu_id
        LEFT JOIN omm_recipes r ON r.recipe_id = m.rep_recipe_id
        LEFT JOIN omm_menu_nutrition nu ON nu.menu_id = m.menu_id
        WHERE s.menu_id = %s ORDER BY s.rank LIMIT %s
    """, (menu_id, limit)).fetchall()
