"""인기 레시피 · 검색어 (Redis 실시간 집계). Redis 가 꺼져 있으면 빈 목록."""
from fastapi import APIRouter, Query

from .. import cache
from ..db import Conn

router = APIRouter(prefix="/api/popular", tags=["Popular"])


@router.get("/recipes", summary="인기 레시피 (최근 N일 상세 조회수)")
def popular_recipes(conn: Conn, days: int = Query(1, ge=1, le=7), limit: int = Query(10, ge=1, le=50)):
    ranked = cache.top("recipe", days, limit)
    if not ranked:
        return []
    ids = [int(m) for m, _ in ranked]
    info = {r["recipeId"]: r for r in conn.execute("""
        SELECT r.recipe_id AS "recipeId", r.title, r.image_url AS "imageUrl", r.cook_time_min AS "cookMin",
               m.cost_per_serving AS "costPerServing"
        FROM omm_recipes r LEFT JOIN omm_recipe_metrics m USING (recipe_id)
        WHERE r.recipe_id = ANY(%s)
    """, (ids,)).fetchall()}
    # 조회수 순서 유지, 그새 지워진 레시피는 빼기
    return [{**info[i], "views": n} for (i, n) in zip(ids, (n for _, n in ranked)) if i in info]


@router.get("/keywords", summary="인기 검색어 (최근 N일 검색 횟수)")
def popular_keywords(days: int = Query(1, ge=1, le=7), limit: int = Query(10, ge=1, le=50)):
    return [{"keyword": k, "count": n} for k, n in cache.top("q", days, limit)]
