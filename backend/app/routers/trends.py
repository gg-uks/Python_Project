"""트렌드 · 분석."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Query

from ..common import code_suffix, ym_text
from ..db import Conn
from ..cache import cache_response

router = APIRouter(prefix="/api", tags=["Trend · Analysis"])

YM_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


def month_of(conn, table: str, ym: str | None) -> date | None:
    """'2026-11' → date(2026-11-01). 안 주면 그 테이블의 가장 최근 달 (table 은 코드에 적힌 이름만)"""
    if ym:
        return date(int(ym[:4]), int(ym[5:7]), 1)
    return conn.execute(f"SELECT max(ym) AS ym FROM {table}").fetchone()["ym"]


def trending_menu_rows(conn, ym: date | None, limit: int, min_cnt: int,
                       where: list[str] | None = None, params: list | None = None, fall: bool = False) -> list[dict]:
    """작년 같은 달 대비 관심도가 많이 오른 메뉴. where 는 대표 레시피(r · m) 기준 조건 (메인 취향 반영용)"""
    if ym is None:
        return []
    extra = "".join(f" AND {w}" for w in (where or []))
    return conn.execute(f"""
        SELECT mn.menu_id AS "menuId", mn.name, mn.dish_type AS "dishType", mn.rep_recipe_id AS "repRecipeId",
               mi.interest_index AS "interestIndex", mi.interest_cnt AS "interestCnt", mi.yoy_pct AS "yoyPct",
               mi.yt_video_cnt AS "ytVideoCnt", mi.yt_yoy_pct AS "ytYoyPct",
               mn.recipe_count AS "recipeCount", r.image_url AS "imageUrl", nu.kcal_serving AS kcal
        FROM omm_menu_interest_monthly mi
        JOIN omm_menus mn USING (menu_id)
        LEFT JOIN omm_recipes r ON r.recipe_id = mn.rep_recipe_id
        LEFT JOIN omm_recipe_metrics m ON m.recipe_id = mn.rep_recipe_id
        LEFT JOIN omm_menu_nutrition nu ON nu.menu_id = mn.menu_id
        WHERE mi.ym = %s AND mi.yoy_pct IS NOT NULL AND mi.interest_cnt >= %s {extra}
        ORDER BY mi.yoy_pct {"ASC" if fall else "DESC"}, mi.interest_cnt DESC
        LIMIT %s
    """, [ym, min_cnt, *(params or []), limit]).fetchall()


@router.get("/trends/menus", summary="뜨는 메뉴")
@cache_response("trend-menus")
def trending_menus(conn: Conn, ym: str | None = Query(None, pattern=YM_PATTERN), limit: int = Query(10, ge=1, le=50),
                   min_cnt: int = Query(5, alias="minCnt", ge=0, description="그 달 관심도(신규 레시피 + 후기) 최소. 작은 수의 % 급등 빼기"),
                   order: Literal["rise", "fall"] = Query("rise", description="rise = 뜨는 메뉴, fall = 지는 메뉴 (작년 같은 달 대비)")):
    month = month_of(conn, "omm_menu_interest_monthly", ym)
    return {"ym": ym_text(month), "items": trending_menu_rows(conn, month, limit, min_cnt, fall=order == "fall")}


@router.get("/trends/keywords", summary="뜨는 키워드")
@cache_response("trend-keywords")
def trending_keywords(conn: Conn, ym: str | None = Query(None, pattern=YM_PATTERN), limit: int = Query(10, ge=1, le=50)):
    month = month_of(conn, "omm_keyword_trend_monthly", ym)
    items = conn.execute("""
        SELECT k.keyword_id AS "keywordId", k.keyword, k.kind, k.menu_id AS "menuId", k.ingredient_id AS "ingredientId",
               t.yt_video_cnt AS "ytVideoCnt", t.yt_view_sum AS "ytViewSum", t.recipe_cnt AS "recipeCnt", t.yoy_pct AS "yoyPct"
        FROM omm_keyword_trend_monthly t JOIN omm_trend_keywords k USING (keyword_id)
        WHERE t.ym = %s AND t.yt_video_cnt > 0
        ORDER BY t.yoy_pct DESC NULLS LAST, t.yt_view_sum DESC
        LIMIT %s
    """, (month, limit)).fetchall()
    for row in items:
        row["kind"] = code_suffix(row["kind"])
    # 그 달에 올라온 영상 중 조회수 많은 10개 (없으면 최근 영상 기준)
    videos = conn.execute("""
        SELECT video_id AS id, title, published_at AS "publishedAt", view_count AS views, like_count AS likes
        FROM omm_youtube_videos
        WHERE %s::date IS NULL OR (published_at >= %s::date AND published_at < %s::date + interval '1 month')
        ORDER BY view_count DESC NULLS LAST LIMIT 10
    """, (month, month, month)).fetchall()
    if not videos:
        videos = conn.execute("""
            SELECT video_id AS id, title, published_at AS "publishedAt", view_count AS views, like_count AS likes
            FROM omm_youtube_videos ORDER BY published_at DESC NULLS LAST, view_count DESC NULLS LAST LIMIT 10
        """).fetchall()
    return {"ym": ym_text(month), "items": items, "videos": videos}


# ── 분석 차트 (queries_v4.sql 의 분석 쿼리를 API 용으로) ───────────────────────────

def _clusters(conn):   # 분석 1: 조리시간 × 1인분 재료비 군집
    items = conn.execute("""
        SELECT cluster_id AS "clusterId", name, description, center_cook_min AS "centerCookMin",
               center_cost_won AS "centerCostWon", recipe_count AS "recipeCount"
        FROM omm_menu_clusters ORDER BY cluster_id""").fetchall()
    # 산점도용 표본 1,500개 (가격을 60% 이상 찾은 레시피, md5 순서라 매번 같은 표본)
    points = conn.execute("""
        SELECT r.recipe_id AS "recipeId", r.cook_time_min AS "cookMin", rm.cost_per_serving AS "costPerServing",
               rm.cluster_id AS "clusterId"
        FROM omm_recipes r JOIN omm_recipe_metrics rm USING (recipe_id)
        WHERE rm.priced_ratio >= 0.6 AND rm.cluster_id IS NOT NULL AND r.cook_time_min IS NOT NULL
        ORDER BY md5(r.recipe_id::text) LIMIT 1500""").fetchall()
    return {"items": items, "points": points}


def _value(conn):   # 분석 6: 재료 1,000원당 단백질 · 열량 (최근 달 소매가)
    month = month_of(conn, "omm_price_monthly", None)
    items = conn.execute("""
        SELECT i.ingredient_id AS "ingredientId", i.name, pm.price_per_100g AS "pricePer100g",
               nf.protein_g AS "proteinPer100g", nf.energy_kcal AS "kcalPer100g",
               round(nf.protein_g / pm.price_per_100g * 1000, 1) AS "proteinPer1000won",
               round(nf.energy_kcal / pm.price_per_100g * 1000) AS "kcalPer1000won"
        FROM omm_ingredients i
        JOIN omm_nutrition_foods nf ON nf.food_cd = i.nutr_food_cd
        JOIN omm_price_monthly pm ON pm.ingredient_id = i.ingredient_id AND pm.market_type = 'MARKET_RETAIL' AND pm.ym = %s
        WHERE pm.price_per_100g > 0 AND nf.protein_g IS NOT NULL
        ORDER BY 6 DESC NULLS LAST LIMIT 30""", (month,)).fetchall()
    # 레시피 기준 가성비 (천 원당 단백질). 재료 영양 코드(nutr_food_cd)가 비어 있어도 화면이 비지 않게 같이 보냄
    recipes = conn.execute("""
        SELECT r.recipe_id AS "recipeId", r.title, m.cost_per_serving AS "costPerServing",
               m.protein_per_1000won AS "proteinPer1000won", m.priced_ratio AS "pricedRatio"
        FROM omm_recipe_metrics m JOIN omm_recipes r USING (recipe_id)
        WHERE m.priced_ratio >= 0.6 AND m.cost_per_serving >= 1000 AND m.protein_per_1000won IS NOT NULL
        ORDER BY m.protein_per_1000won DESC LIMIT 15""").fetchall()
    return {"ym": ym_text(month), "items": items, "recipes": recipes}


def _network(conn):   # 분석 7: 재료 네트워크 (많이 쓰는 재료 150개와 그 사이 엣지)
    nodes = conn.execute("""
        SELECT n.ingredient_id AS id, i.name AS label, n.recipe_count AS "recipeCount", n.degree,
               n.betweenness, n.community_id AS "communityId", n.community_name AS "communityName"
        FROM omm_ingredient_network_nodes n JOIN omm_ingredients i USING (ingredient_id)
        ORDER BY n.recipe_count DESC LIMIT 150""").fetchall()
    ids = [n["id"] for n in nodes]
    edges = conn.execute("""
        SELECT ingredient_a AS source, ingredient_b AS target, co_count AS "coCount", lift
        FROM omm_ingredient_network_edges
        WHERE ingredient_a = ANY(%s) AND ingredient_b = ANY(%s) AND lift > 1
        ORDER BY co_count DESC LIMIT 600""", (ids, ids)).fetchall()
    return {"items": nodes, "edges": edges}


def _similar(conn):   # 비슷한 메뉴 쌍 (점수 높은 50쌍, A-B · B-A 중복 제거)
    items = conn.execute("""
        SELECT s.menu_id AS "menuId", a.name, s.similar_menu_id AS "similarMenuId", b.name AS "similarName", s.score
        FROM omm_menu_similarities s
        JOIN omm_menus a ON a.menu_id = s.menu_id JOIN omm_menus b ON b.menu_id = s.similar_menu_id
        WHERE s.menu_id < s.similar_menu_id
          -- 레시피가 적은 메뉴끼리는 재료 몇 개만 겹쳐도 1.0 이 나와서 (계란밥 → 쿠키) 20개 이상인 메뉴만
          AND a.recipe_count >= 20 AND b.recipe_count >= 20
        ORDER BY s.score DESC LIMIT 50""").fetchall()
    return {"items": items}


def _substitutes(conn):   # 대체 재료 쌍 (전체 기준 우선, 점수 높은 50쌍)
    items = conn.execute("""
        SELECT x.ingredient_id AS "ingredientId", a.name, x.substitute_id AS "substituteId", b.name AS "substituteName",
               x.score, x.evidence_cnt AS "evidenceCnt", c.code_nm AS "basisName"
        FROM (SELECT DISTINCT ON (ingredient_id, substitute_id) * FROM omm_ingredient_substitutes
              ORDER BY ingredient_id, substitute_id, (dish_type IS NULL) DESC, score DESC) x
        JOIN omm_ingredients a ON a.ingredient_id = x.ingredient_id
        JOIN omm_ingredients b ON b.ingredient_id = x.substitute_id
        LEFT JOIN omm_common_codes c ON c.code_id = x.basis
        -- 근거가 적은 쌍(돼지껍데기 → 동그랑땡 · 근거 4개)은 빼고, A→B · B→A 는 한 번만
        WHERE x.evidence_cnt >= 20 AND x.ingredient_id < x.substitute_id
        ORDER BY x.score DESC, x.evidence_cnt DESC LIMIT 50""").fetchall()
    return {"items": items}


def _price_interest(conn):   # 화면 4: 평년 대비 가격 vs 작년 대비 관심도 + 시차 상관
    month = conn.execute("""
        SELECT max(pm.ym) AS ym FROM omm_price_monthly pm
        JOIN omm_ingredient_interest_monthly ii USING (ingredient_id, ym)
        WHERE pm.market_type = 'MARKET_RETAIL'""").fetchone()["ym"]
    items = conn.execute("""
        SELECT i.ingredient_id AS "ingredientId", i.name, pm.vs_normal_pct AS "priceVsNormalPct",
               ii.yoy_pct AS "interestYoyPct", ii.interest_cnt AS "interestCnt"
        FROM omm_price_monthly pm JOIN omm_ingredients i USING (ingredient_id)
        JOIN omm_ingredient_interest_monthly ii ON ii.ingredient_id = pm.ingredient_id AND ii.ym = pm.ym
        WHERE pm.market_type = 'MARKET_RETAIL' AND pm.ym = %s
          AND pm.vs_normal_pct IS NOT NULL AND ii.yoy_pct IS NOT NULL
        ORDER BY pm.vs_normal_pct DESC""", (month,)).fetchall()
    r = conn.execute("""
        SELECT round(corr(pm.vs_normal_pct, ii.yoy_pct)::numeric, 2) AS r, count(*) AS n
        FROM omm_price_monthly pm JOIN omm_ingredient_interest_monthly ii USING (ingredient_id, ym)
        WHERE pm.market_type = 'MARKET_RETAIL' AND pm.ym = %s""", (month,)).fetchone()
    lags = conn.execute("""
        SELECT lag_month AS "lagMonth", corr, n_months AS "nMonths" FROM omm_price_interest_corr
        WHERE ingredient_id IS NULL ORDER BY lag_month""").fetchall()
    return {"ym": ym_text(month), "r": r["r"], "n": r["n"], "items": items, "lags": lags}


def _interest(conn):   # 분석 5: 키워드별 월별 YouTube 영상 수 vs 만개 레시피 수 (최근 12개월 영상 많은 10개)
    rows = conn.execute("""
        WITH last AS (SELECT max(ym) AS ym FROM omm_keyword_trend_monthly),
        top AS (
            SELECT keyword_id FROM omm_keyword_trend_monthly, last
            WHERE omm_keyword_trend_monthly.ym > last.ym - interval '12 month'
            GROUP BY keyword_id ORDER BY sum(yt_video_cnt) DESC LIMIT 10)
        SELECT k.keyword, t.ym, t.yt_video_cnt AS "ytVideoCnt", t.recipe_cnt AS "recipeCnt", t.yoy_pct AS "yoyPct"
        FROM omm_keyword_trend_monthly t JOIN top USING (keyword_id) JOIN omm_trend_keywords k USING (keyword_id), last
        WHERE t.ym > last.ym - interval '12 month'
        ORDER BY k.keyword, t.ym""").fetchall()
    series: dict[str, list] = {}
    for row in rows:
        kw = row.pop("keyword")
        row["ym"] = ym_text(row["ym"])
        series.setdefault(kw, []).append(row)
    return {"items": [{"keyword": k, "series": v} for k, v in series.items()]}


def _measure(conn):   # 분석 8: 수량 표기 신뢰도
    classes = conn.execute("""
        SELECT ri.amount_class AS "amountClass", c.code_nm AS name, count(*) AS cnt,
               round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
        FROM omm_recipe_ingredients ri LEFT JOIN omm_common_codes c ON c.code_id = ri.amount_class
        GROUP BY 1, 2 ORDER BY 3 DESC""").fetchall()
    grades = conn.execute("""
        SELECT rm.reliability_grade AS grade, count(*) AS cnt, round(avg(r.avg_rating), 2) AS "avgRating",
               round(avg(r.view_count)) AS "avgViews"
        FROM omm_recipe_metrics rm JOIN omm_recipes r USING (recipe_id)
        WHERE rm.reliability_grade IS NOT NULL GROUP BY 1 ORDER BY 1""").fetchall()
    for g in grades:
        g["grade"] = code_suffix(g["grade"])
    vague = conn.execute("""
        SELECT unit AS expression, count(*) AS cnt FROM omm_recipe_ingredients
        WHERE amount_class = 'AMOUNT_VAGUE' AND unit IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 15""").fetchall()
    return {"items": classes, "grades": grades, "vague": vague}


ANALYSES = {"value": _value, "clusters": _clusters, "network": _network, "similar": _similar,
            "substitutes": _substitutes, "price-interest": _price_interest, "interest": _interest, "measure": _measure}
AnalysisType = Literal["value", "clusters", "network", "similar", "substitutes", "price-interest", "interest", "measure"]


@router.get("/analysis/{type}", summary="분석 차트 데이터 (8가지)")
@cache_response("analysis")
def analysis(type: AnalysisType, conn: Conn):
    return {"type": type, **ANALYSES[type](conn)}
