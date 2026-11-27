"""엘라스틱서치 검색 (팀 ES 10.0.10.102 의 omm_recipes · omm_menus 를 읽기만 함).

GET /api/search/recipes?q=    레시피 검색: ES 가 순위(레시피 번호)를 정하고, 사진 · 재료비 · 조리시간은 PostgreSQL 에서 채움
                              응답 모양은 팀 GET /api/recipes 와 같음 (+ engine, highlights)
GET /api/search/suggest?q=    메뉴 이름 자동완성 (메뉴 이름 · 별칭 앞부분)
GET /api/search/status        ES 연결 상태 · 인덱스 문서 수
POST /api/recommend/es        하고 싶은 말(문장) → 메뉴 6개. 상황 문장 추천(/text)에 ES 점수를 더함:
                              문장의 '먹고 싶은' 부분으로 레시피 제목 · 설명 · 태그 · 재료를 검색 → 메뉴별로 모아 점수.
                              사전에 없는 말(막걸리, 비 오는 날, 집들이 …)도 레시피 글에 있으면 잡힘.
                              말고 · 빼고 · 먹었다 · 취향 · 6개 고르기는 /text 와 같음

ES 가 응답하지 않으면 자동으로 PostgreSQL 검색으로 돌아감 (engine = "pg"). 30초 동안은 ES 를 다시 부르지 않음.
ES 에는 아무것도 쓰지 않음. 인덱스 적재는 ES 담당 팀원.
"""
import json
import logging
import re
from collections import Counter, defaultdict
import os
import time
import urllib.error
import urllib.request

from fastapi import APIRouter, Query

from .. import cache
from ..common import code_suffix, item_exclude_conditions, user_items
from ..db import Conn
from ..security import OptionalUser
from . import recipes as team_recipes          # ES 가 멈췄을 때 팀 PostgreSQL 검색을 그대로 씀 (읽기만)
from . import recommend_text                   # 문장 분석 · 제외 조건 · 6개 고르기 (내 문장 추천)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["Search · 엘라스틱서치"])
rec_router = APIRouter(prefix="/api/recommend", tags=["Recommend · 상황 문장 · 비슷한 메뉴"])

ES_URL = os.getenv("ES_URL", "http://10.0.10.102:9200").rstrip("/")
ES_TIMEOUT = float(os.getenv("ES_TIMEOUT", "2"))
DOWN_SECONDS = 30            # ES 실패 뒤 이 시간 동안은 바로 PostgreSQL 로
CANDIDATES = 300             # ES 에서 받는 후보 수 (조건 거르기 · 페이지 나누기는 PostgreSQL 쪽)
_down_until = 0.0


class EsDown(Exception):
    pass


def _es(path: str, body: dict | None = None) -> dict:
    """ES 요청 하나. 실패하면 EsDown (30초 동안 다시 안 부름)"""
    global _down_until
    if time.monotonic() < _down_until:
        raise EsDown("최근 실패로 잠시 쉬는 중")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(ES_URL + path, data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=ES_TIMEOUT) as res:
            return json.loads(res.read())
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        _down_until = time.monotonic() + DOWN_SECONDS
        log.warning("엘라스틱서치 실패 → PostgreSQL 로 대체: %s", e)
        raise EsDown(str(e)) from e


def _norm(q: str) -> str:
    return " ".join(q.split())[:50]


# ── 레시피 검색 ────────────────────────────────────────────────────────────────
def _recipe_query(q: str) -> dict:
    """제목에 붙은 그대로 > 제목에 단어 모두 > 재료 · 태그 · 설명. 조회수는 조금만 반영 (log)"""
    return {
        "size": CANDIDATES,
        "_source": False,
        "track_total_hits": True,
        "query": {"function_score": {
            "query": {"bool": {"should": [
                {"match_phrase": {"title": {"query": q, "boost": 4}}},
                {"match": {"title": {"query": q, "operator": "and", "boost": 2}}},
                {"match": {"ingredients_flat": {"query": q, "operator": "and"}}},
                {"match": {"tags": {"query": q, "operator": "and"}}},
                {"match": {"description": {"query": q, "operator": "and", "boost": 0.5}}},
            ], "minimum_should_match": 1}},
            "field_value_factor": {"field": "views", "modifier": "log2p", "factor": 0.5, "missing": 0},
            "boost_mode": "multiply",
        }},
        "highlight": {"fields": {"title": {}}, "pre_tags": ["<b>"], "post_tags": ["</b>"]},
    }


def _es_candidates(conn, q: str) -> dict:
    """ES 순위 → {ids: [...], highlights: {id: 제목}, esTotal}. 같은 검색어는 10분 캐시"""
    def fetch():
        res = _es("/omm_recipes/_search", _recipe_query(q))
        hits = res["hits"]["hits"]
        return {"ids": [int(h["_id"]) for h in hits],
                "highlights": {h["_id"]: h["highlight"]["title"][0] for h in hits if h.get("highlight", {}).get("title")},
                "esTotal": res["hits"]["total"]["value"]}
    return cache.cached(conn, "es-recipes", {"q": q}, fetch, ttl=600)


def _rows_by_ids(conn, ids: list[int], max_min, max_cost, dish_type, ex_items) -> list[dict]:
    """ES 후보를 PostgreSQL 에서 채우고 조건으로 거름 (ES 순서 유지). 열 이름은 팀 /api/recipes 와 같음"""
    where, params = ["r.recipe_id = ANY(%s)"], [ids]
    if max_min:
        where.append("r.cook_time_min <= %s")
        params.append(max_min)
    if max_cost:
        where.append("m.priced_ratio >= 0.6 AND m.cost_per_serving >= 500 AND m.cost_per_serving <= %s")
        params.append(max_cost)
    if dish_type:
        where.append("mn.dish_type = %s")
        params.append(dish_type)
    w, p = item_exclude_conditions(list(ex_items))
    where += w
    params += p
    rows = conn.execute(f"""
        SELECT r.recipe_id AS "recipeId", r.title, mn.name AS menu, r.image_url AS "imageUrl",
               r.cook_time_min AS "cookMin", r.servings,
               m.cost_per_serving AS "costPerServing", m.kcal_per_serving AS "kcalPerServing",
               r.avg_rating AS rating, r.view_count AS views,
               mn.dish_type AS "dishType", r.review_count AS "reviewCount",
               m.priced_ratio AS "pricedRatio", m.reliability_grade AS reliability,
               m.protein_per_1000won AS "proteinPer1000won"
        FROM omm_recipes r
        LEFT JOIN omm_recipe_metrics m USING (recipe_id)
        LEFT JOIN omm_menus mn ON mn.menu_id = r.menu_id
        WHERE {" AND ".join(where)}
    """, params).fetchall()
    order = {rid: k for k, rid in enumerate(ids)}
    rows.sort(key=lambda x: order[x["recipeId"]])
    for it in rows:
        it["reliability"] = code_suffix(it["reliability"])
    return rows


@router.get("/recipes", summary="레시피 검색 (엘라스틱서치 · 한국어 형태소, ES 가 멈추면 PostgreSQL)")
def search_recipes(
    conn: Conn,
    user: OptionalUser,
    q: str = Query(..., min_length=1, max_length=50, description="검색어 (예: 김치찌개, 돼지고기 김치)"),
    max_min: int | None = Query(None, alias="maxMin", ge=1, description="최대 조리시간(분)"),
    max_cost: int | None = Query(None, alias="maxCost", ge=1, description="최대 1인분 비용(원)"),
    dish_type: str | None = Query(None, alias="dishType", description="요리 종류 (국·찌개 …)"),
    page: int = Query(1, ge=1, le=15),
    size: int = Query(20, ge=1, le=50),
    prefs: str = Query("on", pattern="^(on|off)$", description="로그인 시 '빼고 싶은 재료' 제외 (off = 끄기)"),
):
    q = _norm(q)
    if page == 1:
        cache.hit("q", q.lower()[:30])          # 인기 검색어 (팀 레시피 검색과 같은 집계)
    items = [i for i in user_items(conn, user["user_id"]) if i["kind"] == "TAGKIND_EXCLUDE"] if user and prefs == "on" else []
    try:
        cand = _es_candidates(conn, q)
    except EsDown as e:
        data = team_recipes._search(conn, q, None, max_min, max_cost, dish_type, "views", page, size, items)
        return {**data, "engine": "pg", "esError": str(e)[:100], "excluded": [i["name"] for i in items]}

    rows = _rows_by_ids(conn, cand["ids"], max_min, max_cost, dish_type, items) if cand["ids"] else []
    start = (page - 1) * size
    out = rows[start:start + size]
    for it in out:
        hl = cand["highlights"].get(str(it["recipeId"]))
        if hl:
            it["titleHighlight"] = hl                 # 검색어 부분이 <b> … </b>
    return {"total": len(rows), "page": page, "size": size, "items": out, "engine": "es",
            "esTotal": cand["esTotal"], "excluded": [i["name"] for i in items]}


# ── 메뉴 자동완성 ──────────────────────────────────────────────────────────────
@router.get("/suggest", summary="메뉴 이름 자동완성 (메뉴 이름 · 별칭 앞부분, ES 가 멈추면 PostgreSQL)")
def suggest(conn: Conn, q: str = Query(..., min_length=1, max_length=30), limit: int = Query(8, ge=1, le=20)):
    q = _norm(q)

    def from_es():
        res = _es("/omm_menus/_search", {
            "size": limit * 2, "_source": ["menu", "aliases"],
            "query": {"bool": {"should": [
                {"prefix": {"menu.raw": {"value": q, "boost": 5}}},
                {"match_phrase_prefix": {"menu": {"query": q, "boost": 3}}},
                {"prefix": {"aliases.raw": {"value": q, "boost": 2}}},
                {"match_phrase_prefix": {"aliases": {"query": q}}},
            ], "minimum_should_match": 1}},
        })
        names, alias_of = [], {}
        for h in res["hits"]["hits"]:
            name = h["_source"]["menu"]
            names.append(name)
            hit_alias = next((a for a in h["_source"].get("aliases") or [] if a.startswith(q)), None)
            if hit_alias and not name.startswith(q):
                alias_of[name] = hit_alias
        return {"names": names, "aliasOf": alias_of}

    try:
        found = cache.cached(conn, "es-suggest", {"q": q, "limit": limit}, from_es, ttl=600)   # ES 결과만 캐시
        names, alias_of, engine = found["names"], found["aliasOf"], "es"
    except EsDown:
        names = [r["name"] for r in conn.execute(
            "SELECT name FROM omm_menus WHERE name ILIKE %s ORDER BY recipe_count DESC NULLS LAST LIMIT %s",
            (q + "%", limit * 2)).fetchall()]
        alias_of, engine = {}, "pg"
    if not names:
        return {"engine": engine, "items": []}
    rows = conn.execute("""
        SELECT menu_id AS "menuId", name, dish_type AS "dishType", recipe_count AS "recipeCount",
               rep_recipe_id AS "repRecipeId"
        FROM omm_menus WHERE name = ANY(%s)""", (names,)).fetchall()
    by = {r["name"]: r for r in rows}
    items = [by[n] | ({"matchedAlias": alias_of[n]} if n in alias_of else {}) for n in names if n in by][:limit]
    return {"engine": engine, "items": items}


# ── 상태 ──────────────────────────────────────────────────────────────────────
@router.get("/status", summary="엘라스틱서치 연결 상태 · 인덱스 문서 수")
def status_():
    global _down_until
    _down_until = 0.0                                   # 상태 확인은 쉬는 중이어도 다시 시도
    try:
        info = _es("/")
        idx = _es("/_cat/indices/omm_*?format=json&h=index,docs.count,health")
        return {"es": "ok", "url": ES_URL, "version": info["version"]["number"],
                "indices": {i["index"]: {"docs": int(i["docs.count"]), "health": i["health"]} for i in idx}}
    except EsDown as e:
        return {"es": "down", "url": ES_URL, "error": str(e)[:200]}


# ── 하고 싶은 말 → 메뉴 (ES) ──────────────────────────────────────────────────
ES_WEIGHT = 1.5              # ES 점수 최대치 (상황 태그 하나 ≈ 1, 말한 메뉴 = 3)
ES_MIN = 0.15                # 이보다 약하게 맞은 메뉴는 ES 점수 안 줌
_MARK = re.compile(r"<<(.+?)>>")


def _sentence_query(text: str) -> dict:
    """문장 단어 중 30% 이상이 맞는 레시피 (한국어 형태소 · 조사 · 어미는 분석기가 버림)"""
    def m(field, boost):
        return {"match": {field: {"query": text, "minimum_should_match": "30%", "boost": boost}}}
    return {
        "size": 400, "_source": False,
        "query": {"bool": {"should": [m("title", 2), m("tags", 2), m("description", 1),
                                      m("ingredients_flat", 0.5)], "minimum_should_match": 1}},
        "highlight": {"pre_tags": ["<<"], "post_tags": [">>"], "fields": {
            "title": {"number_of_fragments": 0}, "tags": {"number_of_fragments": 0},
            "description": {"fragment_size": 80, "number_of_fragments": 2}}},
    }


def _es_menu_scores(conn, text: str) -> dict:
    """ES 레시피 점수 → 메뉴별 (상위 3개 레시피 점수 합, 맞은 레시피 수, 자주 맞은 단어). 10분 캐시"""
    def fetch():
        hits = _es("/omm_recipes/_search", _sentence_query(text))["hits"]["hits"]
        if not hits:
            return {}
        menu_of = {r["recipe_id"]: r["menu_id"] for r in conn.execute(
            "SELECT recipe_id, menu_id FROM omm_recipes WHERE recipe_id = ANY(%s) AND menu_id IS NOT NULL",
            ([int(h["_id"]) for h in hits],)).fetchall()}
        scores, words = defaultdict(list), defaultdict(Counter)
        for h in hits:
            mid = menu_of.get(int(h["_id"]))
            if mid is None:
                continue
            scores[mid].append(h["_score"])
            for frags in (h.get("highlight") or {}).values():
                for f in frags:
                    words[mid].update(w for w in _MARK.findall(f) if len(w) >= 2)
        return {str(m): {"s": sum(sorted(v, reverse=True)[:3]), "n": len(v), "w": [w for w, _ in words[m].most_common(2)]}
                for m, v in scores.items()}
    return cache.cached(conn, "es-rec", {"t": text}, fetch, ttl=600)


@rec_router.post("/es", summary="하고 싶은 말로 메뉴 추천 (엘라스틱서치 + 상황 문장 분석, ES 가 멈추면 /text 와 같음)")
def recommend_es(body: recommend_text.RecommendReq, conn: Conn, user: OptionalUser):
    state = {"error": None}

    def extra_fn(a, base):
        want = " ".join(c["text"] for c in a.clauses if c["kind"] == "want").strip()
        if not want:                                    # "매운 거 말고" 처럼 피하는 말만 있으면 ES 안 씀
            return {}
        try:
            per_menu = _es_menu_scores(conn, _norm(want))
        except EsDown as e:
            state["error"] = str(e)[:100]
            return {}
        top = max((v["s"] for k, v in per_menu.items() if int(k) in base), default=0)
        out = {}
        for k, v in per_menu.items():
            mid = int(k)
            norm = v["s"] / top if top else 0
            if mid not in base or norm < ES_MIN:
                continue
            words = " · ".join(f"'{w}'" for w in v["w"])
            out[mid] = (ES_WEIGHT * norm, f"{words} 나오는 레시피 {v['n']}개" if words else f"비슷한 레시피 {v['n']}개")
        return out

    res = recommend_text.run_recommend(body, conn, user, extra_fn=extra_fn, engine="es")
    if state["error"]:
        res["engine"] = "rule"
        res["esError"] = state["error"]
    return res
