"""상황 문장 추천 · 먹은 기록 기반 비슷한 메뉴 추천 (팀 추천 GET /api/recommend 과는 별도 경로).

POST /api/recommend/text      문장 ("어제 회식해서 속이 안 좋아") → 메뉴 6개 + 추천 이유 + 문장 분석
GET  /api/recommend/similar   (로그인) 최근 먹은 메뉴와 비슷한 메뉴 먼저 → 6개
GET  /api/recommend/status    미리 데우기 상태
관리자: /api/admin/situations · 키워드 추가/삭제 · /api/admin/recommend-stats
식사 기록 자체는 팀 meals.py (/api/users/me/meals) 가 담당.

점수 (높을수록 위)
  상황 태그   태그마다: 메뉴 레시피 중 태그에 맞는 비율을 태그 안에서 정규화 (0~1)
  말한 메뉴   +3   ("김치찌개 먹고 싶어")
  말한 재료   +0.8 × 그 재료가 든 레시피 비율 (0.5 이상이면 만점)
  취향 태그   +0.3 (먹고 싶은 음식 태그에 대표 레시피가 맞으면)
  인기       +0.4 × 조회수(로그) 정규화,  요즘 관심 ↑ +0.1
빼는 것
  최근 N일 먹은 메뉴와 아주 비슷한 메뉴(유사도 0.8 이상), 싫어하는 재료 · 재료 분류가 주재료(레시피 30% 이상)인 메뉴,
  싫다고 한 말이 이름에 든 메뉴, 피하는 태그 비율이 높은 메뉴, 취향 "제외" 태그, 방금 보여 준 메뉴, 김치류
"""
import logging
import math
import re
import threading
import time
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from .. import cache
from ..common import TAG_RULE_SQL, not_found, user_items
from ..db import Conn, pool
from ..security import AdminUser, CurrentUser, OptionalUser
from ..situation import Analysis, analyze, expand_ingredient, load_dictionary

log = logging.getLogger("omm-api.recommend")
router = APIRouter(prefix="/api/recommend", tags=["Recommend · 상황 문장 · 비슷한 메뉴"])
admin_router = APIRouter(prefix="/api/admin", tags=["Admin"])

MAIN_SHARE = 0.3            # 재료가 메뉴 레시피의 30% 이상에 들어가면 주재료
SIMILAR_RECENT = 0.8        # 최근 먹은 메뉴와 이 유사도 이상이면 같이 뺌
DROP_DISH = {"김치"}
SNACK_DISH = "디저트·음료"  # 간식 · 달달 태그나 메뉴를 직접 말했을 때만
MEMO_TTL = 600
# 요리 종류 규칙은 없지만(글자로 고름) 그 종류로 6개를 채워도 되는 태그 → 종류당 개수 제한에서 뺌
DISH_PREF = {"면요리": "면·분식", "반찬": "반찬·메인"}

# ── 태그 규칙 → SQL ─────────────────────────────────────────────────────────
# r = omm_recipes, m = omm_recipe_metrics, mn = omm_menus
RECIPE_RULES = {
    "RULE_RECIPE_CATEGORY": ("EXISTS (SELECT 1 FROM omm_recipe_categories c WHERE c.recipe_id = r.recipe_id AND c.category_id = %s)", 1, "ref_id"),
    "RULE_TASTE_GROUP": ("EXISTS (SELECT 1 FROM omm_recipe_tastes t JOIN omm_taste_words w USING (taste_id) "
                         "WHERE t.recipe_id = r.recipe_id AND w.taste_group = %s)", 1, "ref_text"),
    "RULE_INGREDIENT": ("EXISTS (SELECT 1 FROM omm_recipe_ingredients x WHERE x.recipe_id = r.recipe_id AND x.ingredient_id = %s)", 1, "ref_id"),
    "RULE_TEXT": ("(r.title ~ %s OR coalesce(r.intro, '') ~ %s OR EXISTS (SELECT 1 FROM omm_recipe_tags g "
                  "WHERE g.recipe_id = r.recipe_id AND g.tag ~ %s))", 3, "ref_text"),
    "RULE_COST": ("(m.cost_per_serving <= %s AND m.priced_ratio >= 0.6)", 1, "ref_id"),
}
MENU_RULES = {
    "RULE_DISH_TYPE": ("mn.dish_type = %s", 1, "ref_text"),
    "RULE_PROTEIN": ("EXISTS (SELECT 1 FROM omm_menu_nutrition nu WHERE nu.menu_id = mn.menu_id AND nu.protein_g_serving >= %s)", 1, "ref_id"),
}

_memo: dict[str, tuple[float, object]] = {}
warm = {"state": "idle", "seconds": None, "error": None}


def _memoized(conn, name: str, params: dict | None, fn):
    """프로세스 메모리 (10분) → Valkey (적재 버전별) → 계산"""
    key = f"{name}:{sorted((params or {}).items())}:{cache._data_version(conn)}"
    hit = _memo.get(key)
    if hit and time.monotonic() - hit[0] < MEMO_TTL:
        return hit[1]
    value = cache.cached(conn, name, params, fn)
    _memo[key] = (time.monotonic(), value)
    return value


def _base(conn) -> dict[int, dict]:
    """추천 후보 메뉴 (레시피 3개 이상, 대표 레시피 있음) + 인기 · 관심도"""
    rows = _memoized(conn, "rec-base", None, lambda: conn.execute("""
        SELECT mn.menu_id AS "menuId", mn.name, mn.dish_type AS "dishType", mn.rep_recipe_id AS "repRecipeId",
               rc.n AS "recipeCnt", rc.views, r.title AS "repTitle", r.image_url AS "imageUrl",
               r.cook_time_min AS "cookMin", rm.cost_per_serving AS "costPerServing", mi.yoy_pct AS "yoyPct"
        FROM omm_menus mn
        JOIN (SELECT menu_id, count(*) AS n, sum(coalesce(view_count, 0)) AS views
              FROM omm_recipes WHERE menu_id IS NOT NULL GROUP BY menu_id) rc USING (menu_id)
        JOIN omm_recipes r ON r.recipe_id = mn.rep_recipe_id
        LEFT JOIN omm_recipe_metrics rm ON rm.recipe_id = mn.rep_recipe_id
        LEFT JOIN LATERAL (SELECT yoy_pct FROM omm_menu_interest_monthly
                           WHERE menu_id = mn.menu_id ORDER BY ym DESC LIMIT 1) mi ON true
        WHERE rc.n >= 3
    """).fetchall())
    top = max((float(x["views"] or 0) for x in rows), default=0)
    out = {}
    for x in rows:
        x = dict(x)
        x["pop"] = math.log1p(float(x["views"] or 0)) / math.log1p(top) if top else 0
        out[int(x["menuId"])] = x
    return out


def _rule_sql(rules: dict, targets: list[dict]) -> tuple[str, list]:
    parts, params = [], []
    for t in targets:
        if t["rule_type"] not in rules:
            continue
        sql, n, col = rules[t["rule_type"]]
        parts.append(sql)
        params += [t[col]] * n
    return (" OR ".join(f"({p})" for p in parts) or "false"), params


def _tag_shares(conn, tag_id: int) -> dict[int, tuple[float, float]]:
    """태그 → {menu_id: (비율, 태그 안 정규화 점수)}"""
    def compute():
        targets = conn.execute("SELECT rule_type, ref_id, ref_text FROM omm_situation_targets WHERE sit_tag_id = %s",
                               (tag_id,)).fetchall()
        rsql, rparams = _rule_sql(RECIPE_RULES, targets)
        msql, mparams = _rule_sql(MENU_RULES, targets)
        rows = conn.execute(f"""
            WITH rc AS (
                SELECT r.menu_id, count(*) AS n, count(*) FILTER (WHERE {rsql}) AS hit
                FROM omm_recipes r LEFT JOIN omm_recipe_metrics m USING (recipe_id)
                WHERE r.menu_id IS NOT NULL GROUP BY r.menu_id)
            SELECT mn.menu_id, CASE WHEN {msql} THEN 1.0 ELSE rc.hit::float / rc.n END AS share
            FROM omm_menus mn JOIN rc USING (menu_id)
            WHERE ({msql}) OR rc.hit > 0
        """, rparams + mparams + mparams).fetchall()
        shares = sorted(float(r["share"]) for r in rows)
        p90 = shares[int(len(shares) * 0.9)] if shares else 1.0
        return [[r["menu_id"], round(float(r["share"]), 4), round(min(1.0, float(r["share"]) / (p90 or 1.0)), 4)] for r in rows]
    return {int(m): (s, n) for m, s, n in _memoized(conn, "rec-tag", {"id": tag_id}, compute)}


def _ingredient_shares(conn, ids: set[int], base: dict[int, dict]) -> dict[int, float]:
    """재료들 → {menu_id: 그 재료가 하나라도 든 레시피 비율}"""
    if not ids:
        return {}
    rows = _memoized(conn, "rec-ing", {"ids": sorted(ids)}, lambda: conn.execute("""
        SELECT r.menu_id, count(DISTINCT r.recipe_id) AS hit
        FROM omm_recipe_ingredients ri JOIN omm_recipes r USING (recipe_id)
        WHERE ri.ingredient_id = ANY(%s) AND r.menu_id IS NOT NULL
        GROUP BY r.menu_id
    """, (sorted(ids),)).fetchall())
    return {int(r["menu_id"]): r["hit"] / base[int(r["menu_id"])]["recipeCnt"]
            for r in rows if int(r["menu_id"]) in base}


_TABLES: dict[str, bool] = {}


def _has_table(conn, name: str) -> bool:
    """테이블이 아직 없는 DB 에서도 500 이 나지 않게 (한 번 확인하면 기억)"""
    if name not in _TABLES:
        _TABLES[name] = conn.execute("SELECT to_regclass(%s) IS NOT NULL AS ok", (name,)).fetchone()["ok"]
    return _TABLES[name]


def _category_ingredients(conn, cat_id: int) -> set[int]:
    return {r["ingredient_id"] for r in conn.execute(
        "SELECT ingredient_id FROM omm_ingredients WHERE category_id = %s AND NOT is_seasoning", (cat_id,)).fetchall()}


def _rep_menu_ids(conn, rule_type: str, ref_id: int) -> set[int]:
    """취향 태그 규칙에 대표 레시피가 맞는 메뉴"""
    sql = TAG_RULE_SQL.get(rule_type)
    if not sql:
        return set()
    return {r["menu_id"] for r in conn.execute(f"""
        SELECT mn.menu_id FROM omm_menus mn JOIN omm_recipes r ON r.recipe_id = mn.rep_recipe_id
        LEFT JOIN omm_recipe_metrics m ON m.recipe_id = r.recipe_id WHERE {sql}
    """, (ref_id,)).fetchall()}


def _user_filters(conn, user: dict, d, a: Analysis | None, base: dict, recent_days: int):
    """회원 취향 · 최근 식사 → (뺄 메뉴, 피할 재료, 취향 '먹고 싶은' 메뉴, 최근 먹은 메뉴 이름)
    취향 태그(omm_user_preferences)와 직접 입력 재료(omm_user_ingredient_prefs, 팀 user_items) 둘 다"""
    excluded: set[int] = set()
    avoid_ids: set[int] = set()
    pref_want: set[int] = set()
    for p in conn.execute("""
            SELECT t.kind, t.rule_type, t.rule_ref_id FROM omm_user_preferences up
            JOIN omm_filter_tags t USING (tag_id) WHERE up.user_id = %s""", (user["user_id"],)).fetchall():
        if p["kind"] == "TAGKIND_EXCLUDE":
            if p["rule_type"] == "RULE_INGREDIENT":
                avoid_ids.add(p["rule_ref_id"])
            elif p["rule_type"] == "RULE_INGREDIENT_CATEGORY":
                avoid_ids |= _category_ingredients(conn, p["rule_ref_id"])
            elif p["rule_type"] == "RULE_MENU":
                excluded.add(p["rule_ref_id"])
            else:
                excluded |= _rep_menu_ids(conn, p["rule_type"], p["rule_ref_id"])
        elif p["rule_type"] == "RULE_MENU":
            pref_want.add(p["rule_ref_id"])
        else:
            pref_want |= _rep_menu_ids(conn, p["rule_type"], p["rule_ref_id"])
    for it in user_items(conn, user["user_id"]):
        word = (it["name"] or "").strip()
        ids = expand_ingredient(d, word, it["ingredientId"]) if (word or it["ingredientId"]) else set()
        if it["kind"] == "TAGKIND_EXCLUDE":
            avoid_ids |= ids
            if word and len(word) >= 2:          # 사전에 없는 글자도 이름에 들어 있으면 뺌 (팀 추천과 같은 생각)
                excluded |= {m for m, c in base.items() if word in c["name"]}
        elif it["kind"] == "TAGKIND_WANT" and ids and a is not None:
            a.want_ingredients.setdefault(word or d.ingredient_names.get(it["ingredientId"], "재료"), ids)
    recent_names: list[str] = []
    if recent_days:
        recent = [r["menu_id"] for r in conn.execute("""
            SELECT DISTINCT menu_id FROM omm_user_meals
            WHERE user_id = %s AND eaten_on > current_date - %s AND menu_id IS NOT NULL
        """, (user["user_id"], recent_days)).fetchall()]
        excluded |= set(recent)
        if recent:
            excluded |= {r["similar_menu_id"] for r in conn.execute("""
                SELECT similar_menu_id FROM omm_menu_similarities WHERE menu_id = ANY(%s) AND score >= %s
            """, (recent, SIMILAR_RECENT)).fetchall()}
        recent_names = [base[m]["name"] for m in recent if m in base]
    if avoid_ids:
        excluded |= {m for m, s in _ingredient_shares(conn, avoid_ids, base).items() if s >= MAIN_SHARE}
    return excluded, set(), pref_want, recent_names


class RecommendReq(BaseModel):
    text: str = Field("", max_length=300, description="상황 문장 (비워도 됨)")
    recentDays: int = Field(0, ge=0, le=14, description="로그인 시 최근 N일 먹은 메뉴 빼기 (기본 0 = 안 뺌)")
    excludeMenuIds: list[int] = Field(default_factory=list, max_length=60, description="방금 보여 준 메뉴 (다른 메뉴 보기)")
    limit: int = Field(6, ge=1, le=12)


@router.post("/text", summary="상황 문장으로 메뉴 추천 = 사전 + 엘라스틱서치 (기본). ES 가 멈추면 사전만 (engine: rule)")
def recommend(body: RecommendReq, conn: Conn, user: OptionalUser):
    # 11-26: 기본 추천을 ② 사전+ES 로 (compare5 비교에서 사전에 없는 말까지 가장 잘 맞춤). 프론트는 그대로 /text 를 부름
    from .search_es import recommend_es        # search_es 가 이 파일을 import 하므로 함수 안에서 (순환 import 방지)
    return recommend_es(body, conn, user)


@router.post("/rule", summary="상황 문장 추천 - 사전(규칙)만, ES 안 씀 (비교 · 벤치마크용, compare5 ①)")
def recommend_rule(body: RecommendReq, conn: Conn, user: OptionalUser):
    return run_recommend(body, conn, user)


def run_recommend(body: RecommendReq, conn, user, extra_fn=None, engine: str = "rule"):
    """문장 추천 본체. extra_fn(a, base) → {메뉴: (더할 점수, 이유)} 를 주면 그 점수를 더함 (ES 추천이 씀)"""
    d = load_dictionary(conn)
    a = analyze(body.text, d)
    base = _base(conn)
    excluded: set[int] = set(body.excludeMenuIds)
    reasons_out: dict[str, list] = {"recent": [], "prefExclude": 0}

    # ── 피하는 재료 · 분류 → 주재료인 메뉴 빼기
    avoid_ids: set[int] = set()
    for ids in a.avoid_ingredients.values():
        avoid_ids |= ids
    for cat in a.avoid_categories.values():
        avoid_ids |= _category_ingredients(conn, cat)

    pref_want: set[int] = set()
    if user:
        ex, avoid_more, pref_want, recent_names = _user_filters(conn, user, d, a, base, body.recentDays)
        excluded |= ex
        avoid_ids |= avoid_more
        reasons_out["recent"] = recent_names

    if avoid_ids:
        excluded |= {m for m, s in _ingredient_shares(conn, avoid_ids, base).items() if s >= MAIN_SHARE}
    for tag_id in a.avoid_tags:
        limit_share = d.tags[tag_id]["avoid_share"]
        excluded |= {m for m, (s, _) in _tag_shares(conn, tag_id).items() if s >= limit_share}

    tag_shares = {t: _tag_shares(conn, t) for t in a.tags}
    want_ing = {w: _ingredient_shares(conn, ids, base) for w, ids in a.want_ingredients.items()}
    want_menu_ids = set(a.want_menus.values())
    # 말한 메뉴와 같은 요리 종류 (국수 → 면·분식). 이름에 그 말이 든 메뉴(국수 → 잔치국수 · 비빔국수)는 더 위로
    want_menu_dish = {base[m]["dishType"] for m in want_menu_ids if m in base}
    snack_ok = bool(want_menu_ids) or any(d.tags[t]["name"] in ("간식", "달달") for t in a.tags)
    extra = extra_fn(a, base) if extra_fn else {}

    # ── 점수
    scored = []
    for mid, c in base.items():
        if mid in excluded or c["dishType"] in DROP_DISH:
            continue
        if c["dishType"] == SNACK_DISH and not snack_ok and mid not in want_menu_ids:
            continue
        # 싫다고 한 말이 이름에 든 메뉴 (호박 → 호박죽). 한 글자(파 · 무 · 김)는 파스타 · 무스처럼 잘못 걸려서 같은 이름만
        if any(c["name"] == w or (len(w) >= 2 and w in c["name"]) for w in a.avoid_menu_words):
            continue
        score, why, matched = 0.0, [], False
        if mid in want_menu_ids:
            score += 3
            why.append("말씀하신 메뉴")
            matched = True
        elif want_menu_ids:
            kin = next((w for w, m in a.want_menus.items() if len(w) >= 2 and w in c["name"]
                        and m in base and base[m]["dishType"] == c["dishType"]), None)   # 같은 종류 안에서만 (김치전 ≠ 김치전골)
            if kin:
                score += 1.2
                why.append(f"{kin} 종류")
                matched = True
            elif c["dishType"] in want_menu_dish:
                score += 0.5
                why.append(f"비슷한 {c['dishType']}")
                matched = True
        for t, shares in tag_shares.items():
            if mid in shares:
                share, norm = shares[mid]
                score += norm
                matched = True
                name = d.tags[t]["name"]
                why.append(f"#{name}" if share >= 0.999 else f"#{name} 레시피 {round(share * 100)}%")
        if mid in extra:
            add, reason = extra[mid]
            score += add
            matched = True
            why.append(reason)
        for w, shares in want_ing.items():
            s = shares.get(mid, 0)
            if s > 0:
                score += 0.8 * min(1.0, s / 0.5)
                matched = True
                why.append(f"{w} 들어간 레시피 {round(s * 100)}%")
        if mid in pref_want:
            score += 0.3
            why.append("내 취향 태그")
        score += 0.4 * c["pop"]
        if c["yoyPct"] is not None and float(c["yoyPct"]) >= 20:
            score += 0.1
            why.append("요즘 관심 ↑")
        if not why:
            why.append("많이 찾는 메뉴" if c["pop"] >= 0.7 else "오늘의 추천")
        scored.append((score, matched, mid, why))
    scored.sort(key=lambda x: (-x[0], x[2]))

    # ── 6개 고르기: 요리 종류가 한쪽으로 몰리지 않게 (요청한 종류는 예외)
    wanted_dish = {t["ref_text"] for t in conn.execute(
        "SELECT ref_text FROM omm_situation_targets WHERE rule_type = 'RULE_DISH_TYPE' AND sit_tag_id = ANY(%s)",
        (list(a.tags),)).fetchall()} if a.tags else set()
    wanted_dish |= {DISH_PREF[d.tags[t]["name"]] for t in a.tags if d.tags[t]["name"] in DISH_PREF}
    if want_menu_ids and not a.tags:          # 메뉴 이름만 말했으면 그 종류로 채워도 됨 (상황 태그가 같이 있으면 다양하게)
        wanted_dish |= want_menu_dish
    # 1차: 문장에 맞은 메뉴 (종류마다 3개까지) → 2차: 나머지 (종류마다 2개까지) → 3차: 모자라면 아무거나
    picked, per_dish, taken = [], {}, set()
    for only_matched, cap in ((True, 3), (False, 2), (False, None)):
        for score, matched, mid, why in scored:
            if len(picked) >= body.limit:
                break
            if mid in taken or (only_matched and not matched):
                continue
            dish = base[mid]["dishType"]
            if cap is not None and dish not in wanted_dish and per_dish.get(dish, 0) >= cap:
                continue
            picked.append((score, matched, mid, why))
            taken.add(mid)
            per_dish[dish] = per_dish.get(dish, 0) + 1

    items = []
    for score, matched, mid, why in picked:
        c = base[mid]
        items.append({k: c[k] for k in ("menuId", "name", "dishType", "repRecipeId", "repTitle", "imageUrl",
                                         "cookMin", "costPerServing")} | {"reasons": why, "matched": matched,
                                                                           "score": round(score, 3)})

    tag_names = ([d.tags[t]["name"] for t in a.tags] + [f"재료:{w}" for w in a.want_ingredients]
                 + [f"메뉴:{m}" for m in a.want_menus] + (["ES검색"] if extra else []))   # 통계용 (찾은 것)
    avoid_words = (list(a.avoid_ingredients) + list(a.avoid_categories)
                   + [w for w in a.avoid_menu_words if w not in a.avoid_ingredients]
                   + [d.tags[t]["name"] for t in a.avoid_tags])
    title = d.tags[next(iter(a.tags))]["title"] if a.tags else "말씀하신 내용과 어울리는 메뉴" if extra else (
        f"{next(iter(a.want_ingredients))} 들어간 메뉴" if a.want_ingredients else None) or ("말씀하신 것을 뺀 메뉴" if avoid_words else "오늘의 추천 메뉴")
    log_id = conn.execute("""
        INSERT INTO omm_recommend_logs (user_id, input_text, tags, avoid, result_menu_ids)
        VALUES (%s, %s, %s, %s, %s) RETURNING rec_log_id
    """, (user["user_id"] if user else None, body.text.strip()[:300] or None, tag_names, avoid_words,
          [i["menuId"] for i in items])).fetchone()["rec_log_id"]

    return {
        "recLogId": log_id,
        "engine": engine,
        "title": title,
        "personalized": user is not None,
        "analysis": {
            "clauses": a.clauses,
            "tags": [{"name": d.tags[t]["name"], "keyword": kw} for t, kw in a.tags.items()],
            "avoidTags": [{"name": d.tags[t]["name"], "keyword": kw} for t, kw in a.avoid_tags.items()],
            "avoidIngredients": list(a.avoid_ingredients) + list(a.avoid_categories),
            "avoidMenuWords": a.avoid_menu_words,
            "wantIngredients": list(a.want_ingredients),
            "wantMenus": list(a.want_menus),
            "recentMenus": reasons_out["recent"],
        },
        "items": items,
    }


# ── 먹은 기록 기반: 비슷한 메뉴 먼저 ────────────────────────────────────────────
HALF_LIFE_DAYS = 7          # 7일 지난 기록은 반만 셈 (최근 · 자주 먹은 메뉴일수록 크게)
OTHER_DISH_FACTOR = 0.6     # 먹은 메뉴와 요리 종류가 다르면 유사도를 60%만 반영 (재료만 겹치는 다른 요리는 뒤로)
# 11-26: 사전 + ES (engine=es, 기본). engine=rule 이면 예전 방식 (재료 유사도만, 비교용)
ES_SIM_WEIGHT = 1.0         # ES 비슷한 레시피 (먹은 메뉴의 인기 레시피 3개와 제목 · 태그 · 재료가 비슷한 레시피 → 메뉴)
OLD_SIM_WEIGHT = 0.5        # 재료 유사도(omm_menu_similarities)는 거칠어서 (국수 → 고추무침) ES 를 쓸 때는 반만
TAG_PROFILE_WEIGHT = 0.6    # 사전: 먹은 메뉴들이 자주 걸리는 상황 · 맛 태그 (#매운맛 · #국물 …) 와 같은 태그의 메뉴
SIM_MENUS = 5               # ES 로 비슷한 메뉴를 찾는 먹은 메뉴 수 (가중치 큰 순)
TAG_BROAD = 0.35            # 후보 메뉴의 35% 넘게 걸리는 넓은 태그(#간단하게 · #가성비)는 취향으로 안 봄


def _es_similar_menus(conn, menu_id: int) -> dict[int, float]:
    """먹은 메뉴의 인기 레시피 3개와 비슷한 레시피 (ES more_like_this) → {비슷한 메뉴: 0~1}. 캐시 (적재 버전별)"""
    from .search_es import _es                 # search_es 가 이 파일을 import 하므로 함수 안에서

    def fetch():
        rids = [r["recipe_id"] for r in conn.execute(
            "SELECT recipe_id FROM omm_recipes WHERE menu_id = %s ORDER BY view_count DESC NULLS LAST LIMIT 3",
            (menu_id,)).fetchall()]
        if not rids:
            return {}
        hits = _es("/omm_recipes/_search", {"size": 200, "_source": False, "query": {"more_like_this": {
            "fields": ["title", "tags", "ingredients_flat"],
            "like": [{"_index": "omm_recipes", "_id": str(r)} for r in rids],
            "min_term_freq": 1, "min_doc_freq": 3, "max_query_terms": 30, "minimum_should_match": "20%"}}})["hits"]["hits"]
        menu_of = {r["recipe_id"]: r["menu_id"] for r in conn.execute(
            "SELECT recipe_id, menu_id FROM omm_recipes WHERE recipe_id = ANY(%s) AND menu_id IS NOT NULL",
            ([int(h["_id"]) for h in hits],)).fetchall()}
        scores = defaultdict(list)
        for h in hits:
            m = menu_of.get(int(h["_id"]))
            if m is not None and m != menu_id:
                scores[m].append(h["_score"])
        total = {m: sum(sorted(v, reverse=True)[:3]) for m, v in scores.items()}
        top = max(total.values(), default=0)
        return {str(m): round(v / top, 4) for m, v in total.items()} if top else {}
    return {int(k): v for k, v in cache.cached(conn, "es-sim", {"m": menu_id}, fetch).items()}


def _tag_profile(conn, d, weight: dict[int, float], base: dict) -> dict[int, float]:
    """사전: 먹은 메뉴들이 레시피 50% 이상 걸리는 태그 → {태그: 먹은 비중}. 먹은 것의 절반 이상인 태그, 많아야 2개"""
    total = sum(weight.values()) or 1.0
    prof = {}
    for t in d.tags:
        shares = _tag_shares(conn, t)
        if sum(1 for m in base if shares.get(m, (0, 0))[0] >= 0.3) > TAG_BROAD * len(base):
            continue
        w = sum(wt for m, wt in weight.items() if shares.get(m, (0, 0))[0] >= 0.5)
        if w / total >= 0.5:
            prof[t] = round(w / total, 3)
    return dict(sorted(prof.items(), key=lambda x: -x[1])[:2])



@router.get("/similar", summary="(로그인) 최근 먹은 메뉴와 비슷한 메뉴 먼저 추천")
def similar_to_meals(user: CurrentUser, conn: Conn,
                     days: int = Query(30, ge=1, le=180, description="이 기간의 먹은 기록을 봄"),
                     excludeRecentDays: int = Query(3, ge=0, le=14, description="최근 N일 먹은 메뉴는 결과에서 뺌"),
                     limit: int = Query(6, ge=1, le=24),
                     engine: str = Query("es", pattern="^(es|rule)$", description="es = 사전 + ES (기본), rule = 재료 유사도만 (비교용)")):
    """점수 = Σ (먹은 메뉴 가중치 × 메뉴 유사도 × 요리 종류 다르면 0.6) 정규화 + 0.3 × 자주 먹은 요리 종류 비율 + 0.2 × 인기.
    먹은 메뉴 가중치 = Σ 0.5^(지난 날 / 7) × 인분. 기록이 없으면 인기 메뉴."""
    d = load_dictionary(conn)
    base = _base(conn)
    meals = conn.execute("""
        SELECT menu_id, current_date - eaten_on AS age, servings
        FROM omm_user_meals WHERE user_id = %s AND eaten_on > current_date - %s AND menu_id IS NOT NULL
    """, (user["user_id"], days)).fetchall()
    return _similar(conn, user, d, base, meals, excludeRecentDays, limit, engine)


def _similar(conn, user, d, base, meals, excludeRecentDays: int, limit: int, engine: str):
    """비슷한 메뉴 추천 본체 (meals = [{menu_id, age, servings}]). 시험할 때 기록을 직접 넣을 수 있게 따로 둠"""

    weight: dict[int, float] = {}
    times: dict[int, int] = {}
    for m in meals:
        w = 0.5 ** (int(m["age"]) / HALF_LIFE_DAYS) * float(m["servings"] or 1)
        weight[m["menu_id"]] = weight.get(m["menu_id"], 0) + w
        times[m["menu_id"]] = times.get(m["menu_id"], 0) + 1
    total_w = sum(weight.values()) or 1.0
    dish_share: dict[str, float] = {}
    for mid, w in weight.items():
        if mid in base:
            dish = base[mid]["dishType"]
            dish_share[dish] = dish_share.get(dish, 0) + w / total_w

    # 비슷한 메뉴 점수 + 가장 크게 기여한 먹은 메뉴 (추천 이유)
    sim: dict[int, float] = {}
    src: dict[int, tuple[float, int, float]] = {}
    if weight:
        for r in conn.execute("""
                SELECT menu_id, similar_menu_id, score FROM omm_menu_similarities WHERE menu_id = ANY(%s)
            """, (list(weight),)).fetchall():
            c = r["similar_menu_id"]
            same = c in base and r["menu_id"] in base and base[c]["dishType"] == base[r["menu_id"]]["dishType"]
            part = weight[r["menu_id"]] * float(r["score"]) * (1.0 if same else OTHER_DISH_FACTOR)
            sim[c] = sim.get(c, 0) + part
            if part > src.get(c, (0, 0, 0))[0]:
                src[c] = (part, r["menu_id"], float(r["score"]))
    top_sim = max(sim.values(), default=1.0) or 1.0

    # ES 비슷한 레시피 · 사전 태그 취향 (engine=es)
    es_sim: dict[int, float] = {}
    es_src: dict[int, tuple[float, int]] = {}
    profile: dict[int, float] = {}
    es_error = None
    if engine == "es" and weight:
        from .search_es import EsDown
        try:
            for eaten in sorted(weight, key=lambda m: -weight[m])[:SIM_MENUS]:
                for c, v in _es_similar_menus(conn, eaten).items():
                    part = weight[eaten] * v
                    es_sim[c] = es_sim.get(c, 0) + part
                    if part > es_src.get(c, (0, 0))[0]:
                        es_src[c] = (part, eaten)
        except EsDown as e:
            es_error, es_sim, es_src = str(e)[:100], {}, {}
        profile = _tag_profile(conn, d, weight, base)
    top_es = max(es_sim.values(), default=1.0) or 1.0
    tag_sh = {t: _tag_shares(conn, t) for t in profile}
    old_w = OLD_SIM_WEIGHT if es_sim else 1.0

    excluded, _, pref_want, _ = _user_filters(conn, user, d, None, base, excludeRecentDays)
    snack_ok = SNACK_DISH in dish_share

    scored = []
    for mid, c in base.items():
        if mid in excluded or c["dishType"] in DROP_DISH or (c["dishType"] == SNACK_DISH and not snack_ok):
            continue
        s, why, matched = 0.0, [], False
        if mid in es_sim and es_sim[mid] / top_es >= 0.15:
            s += ES_SIM_WEIGHT * es_sim[mid] / top_es
            matched = True
            from_id = es_src[mid][1]
            if from_id in base:
                why.append(f"{base[from_id]['name']}{_wa(base[from_id]['name'])} 비슷한 레시피")
        if mid in sim:
            s += old_w * sim[mid] / top_sim
            matched = True
            _, from_id, score = src[mid]
            if from_id in base and not any("비슷" in w for w in why):
                why.append(f"{base[from_id]['name']}{_wa(base[from_id]['name'])} 비슷해요 ({round(score * 100)}%)")
        for t, pw in profile.items():
            share, norm = tag_sh[t].get(mid, (0, 0))
            if share >= 0.3:
                s += TAG_PROFILE_WEIGHT * pw * norm
                matched = True
                why.append(f"자주 먹은 #{d.tags[t]['name']}")
        share = dish_share.get(c["dishType"], 0)
        if share:
            s += 0.3 * share
            if share >= 0.3:
                why.append(f"자주 먹은 {c['dishType']}")
        if mid in pref_want:
            s += 0.2
            why.append("내 취향 태그")
        s += 0.2 * c["pop"]
        if not why:
            why.append("많이 찾는 메뉴" if c["pop"] >= 0.7 else "오늘의 추천")
        scored.append((s, matched, mid, why))
    scored.sort(key=lambda x: (-x[0], x[2]))

    # 비슷한 메뉴 먼저 (종류마다 3개, 취향 태그가 #면요리 · #반찬이면 그 종류는 제한 없음) → 모자라면 나머지
    free_dish = {DISH_PREF[d.tags[t]["name"]] for t in profile if d.tags[t]["name"] in DISH_PREF}
    picked, per_dish, taken = [], {}, set()
    for only_matched, cap in ((True, 3), (False, 2), (False, None)):
        for s, matched, mid, why in scored:
            if len(picked) >= limit:
                break
            if mid in taken or (only_matched and not matched):
                continue
            dish = base[mid]["dishType"]
            if cap is not None and dish not in free_dish and per_dish.get(dish, 0) >= cap:
                continue
            picked.append((s, matched, mid, why))
            taken.add(mid)
            per_dish[dish] = per_dish.get(dish, 0) + 1

    based_on = sorted(({"menuId": m, "name": base[m]["name"] if m in base else None, "times": times[m],
                        "weight": round(w, 3)} for m, w in weight.items()), key=lambda x: -x["weight"])[:10]
    return {
        "title": "최근 먹은 메뉴와 비슷한 메뉴" if weight else "먹은 기록이 없어서 많이 찾는 메뉴를 보여 드려요",
        "engine": "es" if es_sim else "rule",
        **({"esError": es_error} if es_error else {}),
        "tasteTags": [d.tags[t]["name"] for t in sorted(profile, key=lambda t: -profile[t])],
        "basedOn": based_on,
        "items": [{k: base[mid][k] for k in ("menuId", "name", "dishType", "repRecipeId", "repTitle", "imageUrl",
                                              "cookMin", "costPerServing")} | {"reasons": why, "similar": matched,
                                                                                "score": round(s, 3)}
                  for s, matched, mid, why in picked],
    }


@router.get("/status", summary="상황 · 비슷한 메뉴 추천 준비 상태 (미리 데우기)")
def status_(conn: Conn):
    return {"warmUp": warm, "tags": conn.execute(
        "SELECT count(*) AS n FROM omm_situation_tags WHERE use_yn = 'Y'").fetchone()["n"]}


# ── 관리자: 상황 사전 · 통계 ───────────────────────────────────────────────────
def _wa(name: str) -> str:
    """받침 있으면 '과', 없으면 '와' (김치찌개와 · 콩나물국과)"""
    ch = name[-1] if name else ""
    return "과" if "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 else "와"


def _nospace(s: str) -> str:
    return re.sub(r"\s+", "", s)


@admin_router.get("/situations", summary="상황 태그 · 규칙 · 키워드 목록")
def list_situations(admin: AdminUser, conn: Conn):
    tags = conn.execute("""
        SELECT sit_tag_id AS "tagId", name, title, avoid_share AS "avoidShare", use_yn AS "useYn", sort_order AS "sort"
        FROM omm_situation_tags ORDER BY sort_order, sit_tag_id
    """).fetchall()
    rules = conn.execute("""SELECT sit_tag_id, rule_type AS "ruleType", ref_id AS "refId", ref_text AS "refText"
                            FROM omm_situation_targets ORDER BY target_id""").fetchall()
    kws = conn.execute("SELECT sit_tag_id, keyword, source FROM omm_situation_keywords ORDER BY source DESC, keyword").fetchall()
    for t in tags:
        t["rules"] = [{k: v for k, v in r.items() if k != "sit_tag_id"} for r in rules if r["sit_tag_id"] == t["tagId"]]
        t["keywords"] = [{"keyword": k["keyword"], "source": k["source"]} for k in kws if k["sit_tag_id"] == t["tagId"]]
    return tags


class SituationKeywordReq(BaseModel):
    keyword: str = Field(min_length=1, max_length=30)


@admin_router.post("/situations/{tag_id}/keywords", status_code=status.HTTP_201_CREATED,
                   summary="상황 키워드 추가 (30초 안에 반영)")
def add_situation_keyword(tag_id: int, body: SituationKeywordReq, admin: AdminUser, conn: Conn):
    kw = _nospace(body.keyword)
    if not kw:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "키워드가 비어 있어요")
    tag = conn.execute("SELECT name FROM omm_situation_tags WHERE sit_tag_id = %s", (tag_id,)).fetchone()
    if not tag:
        raise not_found("상황 태그")
    other = conn.execute("""SELECT t.name FROM omm_situation_keywords k JOIN omm_situation_tags t USING (sit_tag_id)
                            WHERE k.keyword = %s AND k.sit_tag_id <> %s""", (kw, tag_id)).fetchall()
    conn.execute("INSERT INTO omm_situation_keywords (keyword, sit_tag_id, source) VALUES (%s, %s, 'ADMIN') ON CONFLICT DO NOTHING",
                 (kw, tag_id))
    return {"tagId": tag_id, "tag": tag["name"], "keyword": kw, "alsoIn": [o["name"] for o in other]}


@admin_router.delete("/situations/{tag_id}/keywords/{keyword}", status_code=status.HTTP_204_NO_CONTENT,
                     summary="상황 키워드 지우기")
def delete_situation_keyword(tag_id: int, keyword: str, admin: AdminUser, conn: Conn):
    row = conn.execute("DELETE FROM omm_situation_keywords WHERE keyword = %s AND sit_tag_id = %s RETURNING keyword",
                       (_nospace(keyword), tag_id)).fetchone()
    if not row:
        raise not_found("키워드")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.get("/recommend-stats", summary="상황 문장 추천 통계 (많이 들어온 상황 · 피한 것 · 못 알아들은 문장)")
def recommend_stats(admin: AdminUser, conn: Conn, days: int = Query(7, ge=1, le=90)):
    since = "created_at > now() - make_interval(days => %s)"
    total = conn.execute(f"""SELECT count(*) AS n, count(*) FILTER (WHERE input_text IS NOT NULL) AS with_text
                             FROM omm_recommend_logs WHERE {since}""", (days,)).fetchone()
    tags = conn.execute(f"""SELECT t AS name, count(*) AS cnt FROM omm_recommend_logs, unnest(tags) t
                            WHERE {since} GROUP BY t ORDER BY 2 DESC LIMIT 20""", (days,)).fetchall()
    avoid = conn.execute(f"""SELECT t AS name, count(*) AS cnt FROM omm_recommend_logs, unnest(avoid) t
                             WHERE {since} GROUP BY t ORDER BY 2 DESC LIMIT 20""", (days,)).fetchall()
    no_tag = conn.execute(f"""SELECT input_text AS text, count(*) AS cnt FROM omm_recommend_logs
                              WHERE {since} AND input_text IS NOT NULL AND cardinality(tags) = 0 AND cardinality(avoid) = 0
                              GROUP BY 1 ORDER BY 2 DESC LIMIT 20""", (days,)).fetchall()
    return {"days": days, "requests": total["n"], "withText": total["with_text"], "tags": tags, "avoid": avoid,
            "unmatchedTexts": no_tag}


# ── 미리 데우기 (서버 시작 직후 백그라운드) ──────────────────────────────────────
def warm_up() -> None:
    """후보 메뉴와 태그별 점수를 미리 계산 → 첫 추천 요청이 느리지 않게. 실패해도 서비스는 그대로"""
    def run():
        warm["state"], t0 = "running", time.monotonic()
        try:
            with pool.connection() as conn:
                load_dictionary(conn, force=True)
                base = _base(conn)
                for tag_id in conn.execute("SELECT sit_tag_id FROM omm_situation_tags WHERE use_yn = 'Y'").fetchall():
                    _tag_shares(conn, tag_id["sit_tag_id"])
            warm.update(state="done", seconds=round(time.monotonic() - t0, 1), error=None)
            log.info("추천 미리 데우기 완료: 후보 메뉴 %s개, %.1f초", len(base), warm["seconds"])
        except Exception as e:      # 테이블이 아직 없을 때 등
            warm.update(state="failed", seconds=round(time.monotonic() - t0, 1), error=str(e)[:200])
            log.warning("추천 미리 데우기 실패 (서비스는 계속): %s", e)
    threading.Thread(target=run, name="recommend-warm-up", daemon=True).start()
