"""비교용: 하고 싶은 말 → 메뉴 (MongoDB 전문검색). /api/recommend/es 와 같은 구조에서 글 검색만 MongoDB 로 바꿈.

POST /api/recommend/mongo   상황 문장 추천(/text)에 MongoDB 검색 점수를 더함 (ES 버전과 점수 · 가중치 같음)

MongoDB(커뮤니티)는 한국어 분석기가 없어서 띄어쓰기로 자르고 흔한 조사 · 어미만 떼어 $regex 로 찾음.
레시피 원문 OMM.OMM_mangae_recipes_raw 를 복제본(secondary)에서 읽기만 함. text 인덱스가 있으면 $text 를 씀 (?mode=text).
MONGO_URI (omm-api.env) 가 없거나 pymongo 가 없거나 MongoDB 가 멈추면 /text 와 같은 결과 (engine = "rule").
비교가 끝나면 이 파일과 main.py 의 두 줄을 지우면 됨.
"""
import logging
import os
import re
import time
from collections import Counter, defaultdict

from fastapi import APIRouter, Query

from .. import cache
from ..db import Conn
from ..security import OptionalUser
from . import recommend_text
from .search_es import ES_MIN, ES_WEIGHT, _norm

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recommend", tags=["Recommend · 상황 문장 · 비슷한 메뉴"])

MONGO_URI = os.getenv("MONGO_URI", "")
COLL = "OMM_mangae_recipes_raw"
FIELDS = {"title": 2, "tags": 2, "description": 1, "ingredients_flat": 0.5}      # ES 와 같은 가중치
DOWN_SECONDS = 30
_col = None
_down_until = 0.0

_ENDINGS = ("해서", "하게", "하는", "스러운", "으로", "에서", "이랑", "하고", "에게", "까지", "부터", "처럼", "보다",
            "만", "도", "을", "를", "이", "가", "은", "는", "로", "랑", "과", "와", "에", "의", "한")
_STOP = {"거", "것", "먹을", "먹고", "싶어", "싶다", "좋은", "추천", "추천해줘", "해줘", "뭐", "좀", "있는", "할", "건데",
         "가서", "중이라", "먹을거", "메뉴", "음식", "요리"}


class MongoDown(Exception):
    pass


def mongo_words(text: str) -> list[str]:
    """띄어쓰기로 자르고 끝의 조사 · 어미 하나만 뗌. 한 글자 · 흔한 말은 버림"""
    out = []
    for w in re.split(r"\s+", text):
        w = re.sub(r"[^\w가-힣]", "", w)
        for e in _ENDINGS:
            if len(w) > len(e) + 1 and w.endswith(e):
                w = w[: -len(e)]
                break
        if len(w) >= 2 and w not in _STOP:
            out.append(w)
    return list(dict.fromkeys(out))


def _collection():
    global _col, _down_until
    if time.monotonic() < _down_until:
        raise MongoDown("최근 실패로 잠시 쉬는 중")
    if _col is None:
        if not MONGO_URI:
            raise MongoDown("MONGO_URI 설정 없음")
        try:
            from pymongo import MongoClient
        except ImportError as e:
            raise MongoDown("pymongo 없음") from e
        _col = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000, socketTimeoutMS=20000)["OMM"][COLL]
    return _col


def _search(text: str, mode: str) -> dict[int, tuple[float, list[str]]]:
    """레시피 → (점수, 맞은 단어). regex: 단어 30% 이상 맞은 레시피만 · text: $text 점수 상위 400"""
    global _down_until
    col = _collection()
    try:
        if mode == "text":
            cur = col.find({"$text": {"$search": text}}, {"recipe_id": 1, "s": {"$meta": "textScore"}}) \
                     .sort([("s", {"$meta": "textScore"})]).limit(400)
            return {int(d["recipe_id"]): (d["s"], []) for d in cur if d.get("recipe_id") is not None}
        words = mongo_words(text)
        if not words:
            return {}
        cond = {"$or": [{f: {"$regex": re.escape(w)}} for w in words for f in FIELDS]}
        need = max(1, round(len(words) * 0.3))
        out = {}
        for d in col.find(cond, {"recipe_id": 1, **{f: 1 for f in FIELDS}}):
            vals = {f: (" ".join(v) if isinstance(v, list) else (v or "")) for f, v in ((f, d.get(f)) for f in FIELDS)}
            s, hit = 0.0, []
            for w in words:
                got = [f for f, v in vals.items() if w in v]
                if got:
                    hit.append(w)
                    s += sum(FIELDS[f] for f in got)
            if len(hit) >= need and d.get("recipe_id") is not None:
                out[int(d["recipe_id"])] = (s, hit)
        return dict(sorted(out.items(), key=lambda x: -x[1][0])[:400])
    except MongoDown:
        raise
    except Exception as e:                                  # 연결 · 인증 · 시간 초과 · text 인덱스 없음
        _down_until = time.monotonic() + DOWN_SECONDS
        log.warning("MongoDB 검색 실패 → 규칙만: %s", e)
        raise MongoDown(str(e)) from e


def _menu_scores(conn, text: str, mode: str) -> dict:
    """ES 버전(_es_menu_scores)과 같은 모으기: 메뉴마다 상위 3개 레시피 점수 합 · 맞은 수 · 자주 맞은 단어. 10분 캐시"""
    def fetch():
        hits = _search(text, mode)
        if not hits:
            return {}
        menu_of = {r["recipe_id"]: r["menu_id"] for r in conn.execute(
            "SELECT recipe_id, menu_id FROM omm_recipes WHERE recipe_id = ANY(%s) AND menu_id IS NOT NULL",
            (list(hits),)).fetchall()}
        scores, words = defaultdict(list), defaultdict(Counter)
        for rid, (s, hit) in hits.items():
            mid = menu_of.get(rid)
            if mid is None:
                continue
            scores[mid].append(s)
            words[mid].update(hit)
        return {str(m): {"s": sum(sorted(v, reverse=True)[:3]), "n": len(v), "w": [w for w, _ in words[m].most_common(2)]}
                for m, v in scores.items()}
    return cache.cached(conn, f"mongo-rec-{mode}", {"t": text}, fetch, ttl=600)


@router.post("/mongo", summary="(비교용) 하고 싶은 말로 메뉴 추천 — MongoDB 전문검색 + 상황 문장 분석")
def recommend_mongo(body: recommend_text.RecommendReq, conn: Conn, user: OptionalUser,
                    mode: str = Query("regex", pattern="^(regex|text)$", description="regex = 부분 일치, text = $text (인덱스 필요)")):
    state = {"error": None}

    def extra_fn(a, base):
        want = " ".join(c["text"] for c in a.clauses if c["kind"] == "want").strip()
        if not want:
            return {}
        try:
            per_menu = _menu_scores(conn, _norm(want), mode)
        except MongoDown as e:
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

    res = recommend_text.run_recommend(body, conn, user, extra_fn=extra_fn, engine=f"mongo-{mode}")
    if state["error"]:
        res["engine"] = "rule"
        res["mongoError"] = state["error"]
    return res
