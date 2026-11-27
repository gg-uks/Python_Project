"""UI v3 화면용: 메뉴 추천 · 물가·요리 인사이트 · 재료 탐색 · 계절 캘린더.
모두 매일 적재가 만든 마트 테이블(월별 시세 · 관심도 · 군집 · 시차 상관)을 읽기만 합니다."""
import math
from typing import Literal

from fastapi import APIRouter, Query

from ..cache import cache_response
from ..common import TAG_RULE_SQL, code_suffix, not_found, ym_text
from ..db import Conn
from .trends import month_of

router = APIRouter(prefix="/api", tags=["Insight (UI v3)"])

# 레시피 재료 중 양념이 아닌 주재료의 가장 최근 달 소매 시세 (평년 대비)
MAIN_ING_PRICE = """
    SELECT DISTINCT ON (ri.recipe_id, ri.ingredient_id)
           ri.recipe_id, ri.ingredient_id, i.name, pm.vs_normal_pct, pm.avg_price, pm.unit_label
    FROM omm_recipe_ingredients ri
    JOIN omm_ingredients i ON i.ingredient_id = ri.ingredient_id AND NOT i.is_seasoning
    LEFT JOIN omm_price_monthly pm ON pm.ingredient_id = ri.ingredient_id AND pm.market_type = 'MARKET_RETAIL' AND pm.ym = %s
    WHERE ri.recipe_id = ANY(%s)
    ORDER BY ri.recipe_id, ri.ingredient_id
"""


def _words(text: str | None) -> list[str]:
    return [w for w in (" ".join((text or "").replace("·", ",").split()).split(",")) if w.strip()][:10]


@router.get("/recommend", summary="메뉴 추천 (먹고 싶은 · 빼고 싶은 · 상황 · 기준)")
@cache_response("recommend")
def recommend(conn: Conn,
              want: str | None = Query(None, description="먹고 싶은 음식 · 재료 (쉼표 구분). 메뉴 이름 · 요리 종류 · 대표 레시피 재료 · 맛 표현에서 찾음"),
              avoid: str | None = Query(None, description="빼고 싶은 음식 · 재료 (쉼표 구분)"),
              situation: int | None = Query(None, description="메뉴 4유형 군집 번호 (omm_menu_clusters)"),
              mode: Literal["balance", "price", "trend"] = "balance",
              sort: Literal["rec", "cheap", "hot", "rating"] = "rec",
              limit: int = Query(6, ge=1, le=24), page: int = Query(1, ge=1, le=20),
              eaten: str | None = Query(None, description="최근에 먹은 메뉴 번호 (쉼표 구분). 이 메뉴들은 맨 뒤로 미루고 recentlyEaten=true"),
              tags: str | None = Query(None, description="취향 태그 번호 (쉼표 구분, /api/filter-tags). 먹고 싶은 태그는 want 와 OR, 제외할 태그는 빼기")):
    eaten_ids = {int(x) for x in (eaten or "").split(",") if x.strip().isdigit()}
    price_ym = month_of(conn, "omm_price_monthly", None)
    int_ym = month_of(conn, "omm_menu_interest_monthly", None)
    where, params = ["m.rep_recipe_id IS NOT NULL", "m.recipe_count >= 5"], []
    wants = [w.strip() for w in _words(want)]
    ors, or_params = [], []
    # 취향 태그 (레시피 검색과 같은 규칙 · 대표 레시피 기준)
    tag_ids = [int(x) for x in (tags or "").split(",") if x.strip().isdigit()][:20]
    if tag_ids:
        for row in conn.execute("SELECT kind, rule_type, rule_ref_id FROM omm_filter_tags WHERE tag_id = ANY(%s)",
                                (tag_ids,)).fetchall():
            sql = TAG_RULE_SQL.get(row["rule_type"])
            if sql is None:
                continue
            sql = sql.replace("m.cluster_id", "rm.cluster_id")      # 이 쿼리에서 m = omm_menus
            if row["kind"] == "TAGKIND_WANT":
                ors.append(sql)
                or_params.append(row["rule_ref_id"])
            else:
                where.append(f"NOT ({sql})")
                params.append(row["rule_ref_id"])
    if wants:
        for w in wants:
            like = f"%{w.replace(' ', '')}%"
            ors.append("""(replace(m.name, ' ', '') ILIKE %s OR m.dish_type ILIKE %s
                OR EXISTS (SELECT 1 FROM omm_recipe_ingredients x JOIN omm_ingredients i USING (ingredient_id)
                           WHERE x.recipe_id = m.rep_recipe_id AND i.name ILIKE %s)
                OR EXISTS (SELECT 1 FROM omm_recipe_tastes t JOIN omm_taste_words tw USING (taste_id)
                           WHERE t.recipe_id = m.rep_recipe_id AND (tw.word ILIKE %s OR tw.taste_group ILIKE %s)))""")
            or_params += [like, like, like, like, like]
    if ors:
        where.append("(" + " OR ".join(ors) + ")")
        params += or_params
    for w in _words(avoid):
        like = f"%{w.strip().replace(' ', '')}%"
        where.append("""NOT (replace(m.name, ' ', '') ILIKE %s OR EXISTS (
            SELECT 1 FROM omm_recipe_ingredients x LEFT JOIN omm_ingredients i USING (ingredient_id)
            WHERE x.recipe_id = m.rep_recipe_id AND (replace(x.raw_name, ' ', '') ILIKE %s OR i.name ILIKE %s)))""")
        params += [like, like, like]
    if situation:
        where.append("rm.cluster_id = %s")
        params.append(situation)
    rows = conn.execute(f"""
        SELECT m.menu_id, m.name, m.dish_type, m.recipe_count, m.rep_recipe_id,
               r.title, r.image_url, r.cook_time_min, r.avg_rating, r.review_count, r.view_count,
               rm.cluster_id, mi.yoy_pct, mi.interest_index, mi.interest_cnt
        FROM omm_menus m
        JOIN omm_recipes r ON r.recipe_id = m.rep_recipe_id
        LEFT JOIN omm_recipe_metrics rm ON rm.recipe_id = m.rep_recipe_id
        LEFT JOIN omm_menu_interest_monthly mi ON mi.menu_id = m.menu_id AND mi.ym = %s
        WHERE {" AND ".join(where)}
    """, [int_ym, *params]).fetchall()
    if not rows:
        return {"total": 0, "priceMonth": ym_text(price_ym), "items": []}

    ings: dict[int, list] = {}
    for x in conn.execute(MAIN_ING_PRICE, (price_ym, [r["rep_recipe_id"] for r in rows])).fetchall():
        ings.setdefault(x["recipe_id"], []).append(x)

    out = []
    for r in rows:
        main = ings.get(r["rep_recipe_id"], [])
        pcts = [float(x["vs_normal_pct"]) for x in main if x["vs_normal_pct"] is not None]
        price = sum(pcts) / len(pcts) if pcts else None                  # 주재료 평년 대비 평균 (−면 평소보다 쌈)
        # 관심도 건수가 너무 적으면 % 급등이 의미 없어서 빼요
        hot = max(-100.0, min(100.0, float(r["yoy_pct"]))) if r["yoy_pct"] is not None and (r["interest_cnt"] or 0) >= 5 else None
        pop = math.log10((r["view_count"] or 0) + 10)                    # 동점일 때 조회수
        p, h = (-price if price is not None else 0), (hot or 0)
        score = {"balance": 0.5 * p + 0.5 * h, "price": p, "trend": h}[mode] + pop
        badges = sorted([x for x in main if x["vs_normal_pct"] is not None], key=lambda x: -abs(float(x["vs_normal_pct"])))[:2]
        out.append({
            "menuId": r["menu_id"], "name": r["name"], "dishType": r["dish_type"], "recipeCount": r["recipe_count"],
            "repRecipeId": r["rep_recipe_id"], "repTitle": r["title"], "imageUrl": r["image_url"],
            "cookMin": r["cook_time_min"], "rating": r["avg_rating"], "reviewCount": r["review_count"], "views": r["view_count"],
            "clusterId": r["cluster_id"], "interestYoyPct": r["yoy_pct"], "interestIndex": r["interest_index"],
            "priceVsNormalPct": round(price, 1) if price is not None else None, "score": round(score, 3),
            "ingredients": [{"ingredientId": x["ingredient_id"], "name": x["name"], "vsNormalPct": x["vs_normal_pct"]} for x in badges],
            "recentlyEaten": r["menu_id"] in eaten_ids,
        })
    key = {"rec": lambda x: -x["score"],
           "cheap": lambda x: x["priceVsNormalPct"] if x["priceVsNormalPct"] is not None else 999,
           "hot": lambda x: -(x["interestYoyPct"] if x["interestYoyPct"] is not None else -999),
           "rating": lambda x: (-(x["rating"] or 0), -(x["reviewCount"] or 0))}[sort]
    out.sort(key=lambda x: (x["recentlyEaten"], key(x)))          # 최근 먹은 메뉴는 기준과 상관없이 맨 뒤
    s = (page - 1) * limit
    return {"total": len(out), "priceMonth": ym_text(price_ym), "interestMonth": ym_text(int_ym), "items": out[s:s + limit]}


@router.get("/situations", summary="'지금 상황' 버튼 = 메뉴 4유형 군집")
@cache_response("situations")
def situations(conn: Conn):
    return conn.execute("""
        SELECT cluster_id AS "clusterId", name, description, center_cook_min AS "centerCookMin",
               center_cost_won AS "centerCostWon", recipe_count AS "recipeCount"
        FROM omm_menu_clusters ORDER BY center_cook_min, center_cost_won""").fetchall()


@router.get("/insight", summary="물가·요리 인사이트 첫 줄 숫자 (레시피 수 · 가장 오른/내린 재료 · 가격-관심 상관)")
@cache_response("insight")
def insight(conn: Conn):
    ym = month_of(conn, "omm_price_monthly", None)
    total = conn.execute("SELECT count(*) AS n FROM omm_recipes").fetchone()["n"]
    movers = conn.execute("""
        SELECT i.ingredient_id AS "ingredientId", i.name, pm.vs_normal_pct AS "vsNormalPct",
               pm.avg_price AS "avgPrice", pm.unit_label AS "unitLabel"
        FROM omm_price_monthly pm JOIN omm_ingredients i USING (ingredient_id)
        WHERE pm.ym = %s AND pm.market_type = 'MARKET_RETAIL' AND NOT i.is_seasoning AND pm.vs_normal_pct IS NOT NULL
          AND i.recipe_count >= 100
        ORDER BY pm.vs_normal_pct DESC""", (ym,)).fetchall()
    r = conn.execute("""
        SELECT round(corr(pm.vs_normal_pct, ii.yoy_pct)::numeric, 2) AS r, count(*) AS n
        FROM omm_price_monthly pm JOIN omm_ingredient_interest_monthly ii USING (ingredient_id, ym)
        WHERE pm.market_type = 'MARKET_RETAIL' AND pm.ym = %s AND pm.vs_normal_pct IS NOT NULL AND ii.yoy_pct IS NOT NULL""",
                     (ym,)).fetchone()
    return {"ym": ym_text(ym), "recipeTotal": total, "topUp": movers[0] if movers else None,
            "topDown": movers[-1] if movers else None, "r": r["r"], "n": r["n"]}


@router.get("/insight/extra", summary="인사이트 카드 ②③④: 별점×재료비 · 사람 이름 · 맛 표현별 재료")
@cache_response("insight-extra")
def insight_extra(conn: Conn):
    rating_cost = conn.execute("""
        SELECT r.recipe_id AS "recipeId", r.title, rm.cost_per_serving AS "costPerServing", r.avg_rating AS rating,
               r.review_count AS "reviewCount"
        FROM omm_recipes r JOIN omm_recipe_metrics rm USING (recipe_id)
        WHERE r.review_count >= 3 AND rm.cost_per_serving >= 300 AND rm.priced_ratio >= 0.6 AND r.avg_rating IS NOT NULL
        ORDER BY md5(r.recipe_id::text) LIMIT 800""").fetchall()
    rc = conn.execute("""
        SELECT round(corr(rm.cost_per_serving, r.avg_rating)::numeric, 2) AS r, count(*) AS n
        FROM omm_recipes r JOIN omm_recipe_metrics rm USING (recipe_id)
        WHERE r.review_count >= 3 AND rm.cost_per_serving >= 300 AND rm.priced_ratio >= 0.6 AND r.avg_rating IS NOT NULL""").fetchone()
    person = conn.execute("""
        SELECT (rm.person_name IS NOT NULL) AS "hasName", count(*) AS n,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY r.view_count) AS "medianViews",
               round(avg(r.avg_rating)::numeric, 2) AS "avgRating"
        FROM omm_recipes r JOIN omm_recipe_metrics rm USING (recipe_id)
        WHERE r.view_count > 0 GROUP BY 1 ORDER BY 1""").fetchall()
    names = conn.execute("""
        SELECT rm.person_name AS name, count(*) AS n FROM omm_recipe_metrics rm
        WHERE rm.person_name IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 5""").fetchall()
    taste = conn.execute("""
        WITH t AS (
            SELECT tw.taste_group AS grp, i.name, count(DISTINCT rt.recipe_id) AS n,
                   -- 어디에나 들어가는 재료(마늘 · 대파)가 모든 맛 1등이 되지 않게: 그 맛에서 나온 수 ÷ (전체 쓰인 수)^0.65
                   count(DISTINCT rt.recipe_id) / power(max(i.recipe_count) + 1, 0.65) AS score
            FROM omm_recipe_tastes rt JOIN omm_taste_words tw USING (taste_id)
            JOIN omm_recipe_ingredients ri USING (recipe_id)
            JOIN omm_ingredients i ON i.ingredient_id = ri.ingredient_id
            WHERE tw.taste_group IS NOT NULL AND i.name NOT IN ('물', '소금', '설탕', '식용유', '간장', '후추')
            GROUP BY 1, 2)
        SELECT grp, name, n FROM (SELECT *, row_number() OVER (PARTITION BY grp ORDER BY score DESC) AS k FROM t WHERE n >= 15) x
        WHERE k <= 3 ORDER BY grp, k""").fetchall()
    groups: dict[str, list] = {}
    for row in taste:
        groups.setdefault(row["grp"], []).append(row["name"])
    return {"ratingCost": {"r": rc["r"], "n": rc["n"], "points": rating_cost},
            "person": person, "personNames": names,
            "taste": [{"word": k, "items": v} for k, v in groups.items()]}


def _day_change(conn, ingredient_id: int):
    """KAMIS 일별 소매가로 전일 대비 % (일별 가격이 적재돼 있을 때만)"""
    rows = conn.execute("""
        SELECT p.exmn_ymd, avg(p.price) AS price
        FROM omm_kamis_prices p JOIN omm_kamis_items k ON k.item_cd = p.item_cd AND k.vrty_cd = p.vrty_cd
        WHERE k.ingredient_id = %s AND k.is_primary AND p.se_cd IN ('MARKET_RETAIL', '01')
        GROUP BY 1 ORDER BY 1 DESC LIMIT 2""", (ingredient_id,)).fetchall()
    if len(rows) < 2 or not rows[1]["price"]:
        return None
    return round(float((rows[0]["price"] - rows[1]["price"]) / rows[1]["price"]) * 100, 1)


@router.get("/ingredients/{ingredient_id}/insight", summary="재료 탐색: 시세 · 평년 · 레시피 관심도 13개월 · 시차 상관 · 들어가는 메뉴")
@cache_response("ingredient-insight")
def ingredient_insight(ingredient_id: int, conn: Conn):
    ing = conn.execute("SELECT ingredient_id, name FROM omm_ingredients WHERE ingredient_id = %s", (ingredient_id,)).fetchone()
    if ing is None:
        raise not_found("재료")
    latest = {r["market_type"]: r for r in conn.execute("""
        SELECT DISTINCT ON (market_type) market_type, ym, avg_price, unit_label, normal_price,
               COALESCE(vs_normal_pct, round(((avg_price - normal_price) / NULLIF(normal_price, 0) * 100)::numeric, 1)) AS vs_normal_pct
        FROM omm_price_monthly WHERE ingredient_id = %s AND avg_price IS NOT NULL
        ORDER BY market_type, ym DESC""", (ingredient_id,)).fetchall()}
    series = conn.execute("""
        WITH last AS (SELECT max(ym) AS ym FROM omm_ingredient_interest_monthly)
        SELECT to_char(g.ym, 'YYYY-MM') AS ym, pm.avg_price AS "retailPrice", pm.normal_price AS "normalPrice",
               pm.vs_normal_pct AS "vsNormalPct", ii.interest_cnt AS "interestCnt", ii.yoy_pct AS "interestYoyPct",
               ii.yt_video_cnt AS "ytVideoCnt"
        FROM last, generate_series(last.ym - interval '12 month', last.ym, interval '1 month') AS g(ym)
        LEFT JOIN omm_price_monthly pm ON pm.ingredient_id = %s AND pm.market_type = 'MARKET_RETAIL' AND pm.ym = g.ym::date
        LEFT JOIN omm_ingredient_interest_monthly ii ON ii.ingredient_id = %s AND ii.ym = g.ym::date
        ORDER BY g.ym""", (ingredient_id, ingredient_id)).fetchall()
    lags = conn.execute("""
        SELECT lag_month AS "lagMonth", corr, n_months AS "nMonths" FROM omm_price_interest_corr
        WHERE ingredient_id = %s ORDER BY lag_month""", (ingredient_id,)).fetchall()
    ym = month_of(conn, "omm_menu_interest_monthly", None)
    menus = conn.execute("""
        SELECT m.menu_id AS "menuId", m.name, count(DISTINCT r.recipe_id) AS n, mi.yoy_pct AS "interestYoyPct"
        FROM omm_recipe_ingredients ri JOIN omm_recipes r USING (recipe_id) JOIN omm_menus m ON m.menu_id = r.menu_id
        LEFT JOIN omm_menu_interest_monthly mi ON mi.menu_id = m.menu_id AND mi.ym = %s
        WHERE ri.ingredient_id = %s
        GROUP BY m.menu_id, m.name, mi.yoy_pct HAVING count(DISTINCT r.recipe_id) >= 3
        ORDER BY n DESC LIMIT 6""", (ym, ingredient_id)).fetchall()
    cur = series[-1] if series else {}
    pick = lambda m: None if m not in latest else {
        "ym": ym_text(latest[m]["ym"]), "avgPrice": latest[m]["avg_price"], "unitLabel": latest[m]["unit_label"],
        "normalPrice": latest[m]["normal_price"], "vsNormalPct": latest[m]["vs_normal_pct"]}
    return {"ingredientId": ing["ingredient_id"], "name": ing["name"],
            "retail": pick("MARKET_RETAIL"), "wholesale": pick("MARKET_WHOLESALE"), "dayChangePct": _day_change(conn, ingredient_id),
            "interestCnt": cur.get("interestCnt"), "interestYoyPct": cur.get("interestYoyPct"), "ytVideoCnt": cur.get("ytVideoCnt"),
            "series": series, "lags": lags, "menus": menus}


@router.get("/ingredients-summary", summary="재료별 요약 표 (소매가 · 평년 대비 · 레시피 관심도 · 시차)")
@cache_response("ingredient-summary")
def ingredient_summary(conn: Conn, ids: str | None = Query(None, description="재료 번호 쉼표 구분. 없으면 평년 대비 등락이 큰 주재료 8개")):
    ym = month_of(conn, "omm_price_monthly", None)
    id_list = [int(x) for x in (ids or "").split(",") if x.strip().isdigit()][:20]
    if not id_list:
        id_list = [r["ingredient_id"] for r in conn.execute("""
            SELECT i.ingredient_id FROM omm_price_monthly pm JOIN omm_ingredients i USING (ingredient_id)
            WHERE pm.ym = %s AND pm.market_type = 'MARKET_RETAIL' AND NOT i.is_seasoning AND pm.vs_normal_pct IS NOT NULL
              AND i.recipe_count >= 100
            ORDER BY abs(pm.vs_normal_pct) DESC LIMIT 8""", (ym,)).fetchall()]
    rows = conn.execute("""
        SELECT i.ingredient_id AS "ingredientId", i.name, pm.avg_price AS "avgPrice", pm.unit_label AS "unitLabel",
               pm.vs_normal_pct AS "vsNormalPct", ii.yoy_pct AS "interestYoyPct",
               (SELECT c.lag_month FROM omm_price_interest_corr c WHERE c.ingredient_id = i.ingredient_id
                ORDER BY abs(c.corr) DESC NULLS LAST LIMIT 1) AS "bestLag"
        FROM omm_ingredients i
        LEFT JOIN omm_price_monthly pm ON pm.ingredient_id = i.ingredient_id AND pm.market_type = 'MARKET_RETAIL' AND pm.ym = %s
        LEFT JOIN omm_ingredient_interest_monthly ii ON ii.ingredient_id = i.ingredient_id AND ii.ym = %s
        WHERE i.ingredient_id = ANY(%s)
        ORDER BY pm.vs_normal_pct DESC NULLS LAST""", (ym, month_of(conn, "omm_ingredient_interest_monthly", None), id_list)).fetchall()
    for r in rows:
        r["dayChangePct"] = _day_change(conn, r["ingredientId"])
    return {"ym": ym_text(ym), "items": rows}


@router.get("/trends/calendar", summary="계절 캘린더: 재료별 월 관심도 지수(최근 12개월 최대 = 100) · 평년가가 가장 싼 달")
@cache_response("trend-calendar")
def trend_calendar(conn: Conn, ids: str | None = Query(None, description="재료 번호 쉼표 구분. 없으면 레시피에 많이 쓰는 주재료 8개")):
    id_list = [int(x) for x in (ids or "").split(",") if x.strip().isdigit()][:12]
    if not id_list:
        id_list = [r["ingredient_id"] for r in conn.execute("""
            SELECT i.ingredient_id FROM omm_ingredients i
            WHERE NOT i.is_seasoning AND EXISTS (SELECT 1 FROM omm_price_monthly pm WHERE pm.ingredient_id = i.ingredient_id
                                                 AND pm.market_type = 'MARKET_RETAIL' AND pm.normal_price IS NOT NULL)
            ORDER BY i.recipe_count DESC LIMIT 8""").fetchall()]
    rows = conn.execute("""
        WITH last AS (SELECT max(ym) AS ym FROM omm_ingredient_interest_monthly),
        ii AS (SELECT ii.ingredient_id, extract(month FROM ii.ym)::int AS mon, ii.interest_cnt
               FROM omm_ingredient_interest_monthly ii, last
               WHERE ii.ingredient_id = ANY(%s) AND ii.ym > last.ym - interval '12 month'),
        np AS (SELECT DISTINCT ON (pm.ingredient_id, extract(month FROM pm.ym))
                      pm.ingredient_id, extract(month FROM pm.ym)::int AS mon, pm.normal_price
               FROM omm_price_monthly pm WHERE pm.ingredient_id = ANY(%s) AND pm.market_type = 'MARKET_RETAIL' AND pm.normal_price IS NOT NULL
               ORDER BY pm.ingredient_id, extract(month FROM pm.ym), pm.ym DESC)
        SELECT i.ingredient_id AS "ingredientId", i.name, m.mon,
               round(100.0 * ii.interest_cnt / NULLIF(max(ii.interest_cnt) OVER (PARTITION BY i.ingredient_id), 0)) AS idx,
               np.normal_price AS "normalPrice"
        FROM omm_ingredients i CROSS JOIN generate_series(1, 12) AS m(mon)
        LEFT JOIN ii ON ii.ingredient_id = i.ingredient_id AND ii.mon = m.mon
        LEFT JOIN np ON np.ingredient_id = i.ingredient_id AND np.mon = m.mon
        WHERE i.ingredient_id = ANY(%s)
        ORDER BY i.recipe_count DESC, m.mon""", (id_list, id_list, id_list)).fetchall()
    by: dict[int, dict] = {}
    for r in rows:
        d = by.setdefault(r["ingredientId"], {"ingredientId": r["ingredientId"], "name": r["name"], "cells": [], "_np": []})
        d["cells"].append(r["idx"])
        d["_np"].append(r["normalPrice"])
    out = []
    for d in by.values():
        np_ = d.pop("_np")
        known = [(v, k) for k, v in enumerate(np_) if v is not None]
        d["cheapMonth"] = (min(known)[1] + 1) if known else None             # 1~12월
        out.append(d)
    return {"items": out}
