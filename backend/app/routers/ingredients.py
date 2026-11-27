"""재료: 검색 · 가격 추이 · 대체 재료 · 함께 쓰는 재료."""
from typing import Literal

from fastapi import APIRouter, Query

from ..common import not_found, ym_text
from ..db import Conn
from ..cache import cache_response

router = APIRouter(prefix="/api/ingredients", tags=["Ingredient"])

# 재료의 가장 최근 100g당 가격 (소매 우선). 쿼리 안에서 x.ingredient_id 로 붙여 씀
LATEST_PRICE = """LEFT JOIN LATERAL (
    SELECT pm.ym, pm.price_per_100g, pm.vs_normal_pct FROM omm_price_monthly pm
    WHERE pm.ingredient_id = {col} AND pm.price_per_100g IS NOT NULL
    ORDER BY pm.ym DESC, (pm.market_type = 'MARKET_RETAIL') DESC LIMIT 1) p ON true"""


@router.get("", summary="재료 검색 (별칭 포함 · 냉장고 재료 선택용)")
@cache_response("ingredients")
def search_ingredients(conn: Conn, q: str | None = Query(None, max_length=50,
                                                         description="없으면 많이 쓰는 재료 24개 (양념 제외 · 냉장고 첫 화면용)")):
    q = (q or "").strip()
    if not q:
        return conn.execute("""
            SELECT i.ingredient_id AS "ingredientId", i.name, c.name AS category, i.is_seasoning AS "isSeasoning"
            FROM omm_ingredients i JOIN omm_ingredient_categories c USING (category_id)
            WHERE NOT i.is_seasoning
            ORDER BY i.recipe_count DESC LIMIT 24
        """).fetchall()
    return conn.execute("""
        SELECT i.ingredient_id AS "ingredientId", i.name, c.name AS category, i.is_seasoning AS "isSeasoning"
        FROM omm_ingredients i
        JOIN omm_ingredient_categories c USING (category_id)
        WHERE i.name ILIKE %s
           OR EXISTS (SELECT 1 FROM omm_ingredient_aliases a
                      WHERE a.ingredient_id = i.ingredient_id AND a.is_active AND a.alias ILIKE %s)
        ORDER BY (i.name = %s) DESC, i.recipe_count DESC
        LIMIT 20
    """, (f"%{q}%", f"%{q.replace(' ', '')}%", q)).fetchall()


@router.get("/{ingredient_id}", summary="재료 상세 (이름 · 분류 · 쓰인 레시피 수 · 최근 시세)")
@cache_response("ingredient")
def ingredient_detail(ingredient_id: int, conn: Conn):
    row = conn.execute(f"""
        SELECT i.ingredient_id AS "ingredientId", i.name, c.name AS category, i.is_seasoning AS "isSeasoning",
               i.recipe_count AS "recipeCount", i.default_unit AS "defaultUnit",
               p.price_per_100g AS "pricePer100g", p.vs_normal_pct AS "vsNormalPct", p.ym AS "priceYm"
        FROM omm_ingredients i
        JOIN omm_ingredient_categories c USING (category_id)
        {LATEST_PRICE.format(col="i.ingredient_id")}
        WHERE i.ingredient_id = %s
    """, (ingredient_id,)).fetchone()
    if row is None:
        raise not_found("재료")
    row["priceYm"] = ym_text(row["priceYm"])
    return row


@router.get("/{ingredient_id}/prices", summary="재료 월별 가격 추이")
@cache_response("ingredient-prices")
def ingredient_prices(ingredient_id: int, conn: Conn,
                      market: Literal["retail", "wholesale"] = "retail",
                      months: int = Query(15, ge=1, le=60)):
    if conn.execute("SELECT 1 FROM omm_ingredients WHERE ingredient_id = %s", (ingredient_id,)).fetchone() is None:
        raise not_found("재료")
    rows = conn.execute("""
        SELECT ym, price_per_100g AS "pricePer100g", unit_label AS "unitLabel",
               vs_normal_pct AS "vsNormalPct", yoy_pct AS "yoyPct", price_source AS source
        FROM omm_price_monthly
        WHERE ingredient_id = %s AND market_type = %s
        ORDER BY ym DESC LIMIT %s
    """, (ingredient_id, f"MARKET_{market.upper()}", months)).fetchall()
    for row in rows:
        row["ym"] = ym_text(row["ym"])
    return list(reversed(rows))          # 오래된 달 → 최근 달 (그래프 순서)


def _check_ingredient(conn, ingredient_id: int) -> None:
    if conn.execute("SELECT 1 FROM omm_ingredients WHERE ingredient_id = %s", (ingredient_id,)).fetchone() is None:
        raise not_found("재료")





@router.get("/{ingredient_id}/substitutes", summary="대체 재료")
@cache_response("ingredient-substitutes")
def ingredient_substitutes(ingredient_id: int, conn: Conn,
                           dish_type: str | None = Query(None, alias="dishType", description="요리 종류 (국·찌개 …). 없으면 전체 기준"),
                           limit: int = Query(10, ge=1, le=30)):
    _check_ingredient(conn, ingredient_id)
    # 같은 대체 재료가 근거(basis) · 요리 종류별로 여러 줄 → 요청한 요리 종류(없으면 전체=NULL) 줄을 우선해서 1줄
    rows = conn.execute(f"""
        SELECT x.substitute_id AS "ingredientId", i.name, x.score, x.evidence_cnt AS "evidenceCnt",
               x.basis, b.code_nm AS "basisName", x.dish_type AS "dishType",
               p.price_per_100g AS "pricePer100g", p.vs_normal_pct AS "vsNormalPct"
        FROM (
            SELECT DISTINCT ON (s.substitute_id) s.*
            FROM omm_ingredient_substitutes s
            WHERE s.ingredient_id = %s AND (s.dish_type IS NULL OR s.dish_type = %s)
            ORDER BY s.substitute_id, (s.dish_type IS NOT DISTINCT FROM %s) DESC, s.score DESC
        ) x
        JOIN omm_ingredients i ON i.ingredient_id = x.substitute_id
        LEFT JOIN omm_common_codes b ON b.code_id = x.basis
        {LATEST_PRICE.format(col="x.substitute_id")}
        ORDER BY x.score DESC LIMIT %s
    """, (ingredient_id, dish_type, dish_type, limit)).fetchall()
    return rows


@router.get("/{ingredient_id}/pairings", summary="함께 쓰는 재료")
@cache_response("ingredient-pairings")
def ingredient_pairings(ingredient_id: int, conn: Conn, limit: int = Query(10, ge=1, le=50),
                        sort: Literal["count", "lift"] = Query("count", description="count = 같이 나온 레시피 수, lift = 우연보다 얼마나 자주"),
                        min_count: int = Query(5, alias="minCount", ge=1, description="lift 정렬 때 드문 쌍 빼기")):
    _check_ingredient(conn, ingredient_id)
    order = "e.co_count DESC, e.lift DESC" if sort == "count" else "e.lift DESC, e.co_count DESC"
    return conn.execute(f"""
        SELECT o.ingredient_id AS "ingredientId", o.name, e.co_count AS "coCount", e.lift,
               n.community_name AS "communityName"
        FROM omm_ingredient_network_edges e
        JOIN omm_ingredients o ON o.ingredient_id = CASE WHEN e.ingredient_a = %s THEN e.ingredient_b ELSE e.ingredient_a END
        LEFT JOIN omm_ingredient_network_nodes n ON n.ingredient_id = o.ingredient_id
        WHERE (e.ingredient_a = %s OR e.ingredient_b = %s) AND e.co_count >= %s
        ORDER BY {order} LIMIT %s
    """, (ingredient_id, ingredient_id, ingredient_id, min_count if sort == "lift" else 1, limit)).fetchall()
