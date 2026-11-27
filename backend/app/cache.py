"""Redis: API 응답 캐시 · 로그아웃 토큰 차단 · 로그인 시도 제한 · 인기 레시피 / 검색어 집계.

구성: db2 마스터 · db3 복제본 · db1~3 Sentinel. API 는 Sentinel 에게 "지금 마스터"를 물어서 접속하므로
db2 가 죽어서 db3 가 승격돼도 설정을 바꿀 필요가 없습니다.

Redis 가 꺼져도 API 는 계속 동작합니다: 캐시 없이 DB 를 바로 읽고, 차단 · 제한 · 집계만 잠시 멈춤.
한 번 실패하면 30초 동안은 Redis 를 건너뜀 (요청마다 접속 대기 시간이 쌓이지 않게). 경고는 api.log 에.

키 (모두 TTL 있음 → maxmemory-policy volatile-lru 로 넘치면 오래 안 쓴 것부터 지움)
  omm:cache:<적재 버전>:<이름>:<파라미터>   API 응답. 매일 적재가 끝나면 버전이 바뀌어 자동으로 새로 계산
  omm:bl:<토큰 jti>                       로그아웃한 토큰 (토큰 만료 시각까지)
  omm:login:<이메일>:<IP>                  로그인 실패 횟수 (10분)
  omm:pop:recipe:<YYYYMMDD>               그날 레시피 상세 조회수 (정렬 집합, 8일)
  omm:pop:q:<YYYYMMDD>                    그날 검색어 횟수 (정렬 집합, 8일)
"""
import functools
import json
import logging
import time
from datetime import date, timedelta

import redis
from fastapi.encoders import jsonable_encoder
from redis.sentinel import Sentinel

from .config import settings

log = logging.getLogger("omm-api.redis")
P = "omm:"
LOGIN_MAX_FAIL = 5
LOGIN_WINDOW_SEC = 600
POP_KEEP_DAYS = 8

_client = None
_down_until = 0.0
_version = (0.0, "0")


def _connect():
    kw = {"password": settings.redis_password or None, "socket_timeout": 0.5,
          "socket_connect_timeout": 0.5, "decode_responses": True}
    if settings.redis_sentinels:
        return Sentinel(settings.redis_sentinels, socket_timeout=0.5).master_for(settings.redis_master, **kw)
    if settings.redis_url:
        return redis.Redis.from_url(settings.redis_url, **kw)
    return None


def _r():
    """사용할 수 있으면 Redis 클라이언트, 꺼져 있거나 설정이 없으면 None"""
    global _client
    if time.monotonic() < _down_until:
        return None
    if _client is None:
        _client = _connect()
    return _client


def _fail(e: Exception) -> None:
    global _down_until
    _down_until = time.monotonic() + 30
    log.warning("Redis 오류 → 30초 동안 Redis 없이 동작: %s", e)


def status() -> str:
    """헬스체크용: ok · down · off(설정 없음)"""
    if not (settings.redis_sentinels or settings.redis_url):
        return "off"
    r = _r()
    try:
        return "ok" if r and r.ping() else "down"
    except redis.RedisError as e:
        _fail(e)
        return "down"


# ── 응답 캐시 ─────────────────────────────────────────────────────────────

def _data_version(conn) -> str:
    """마지막으로 성공한 적재 번호. 적재가 끝나면 바뀌어서 예전 캐시는 안 쓰이고 TTL 로 사라짐 (1분마다 확인)"""
    global _version
    if time.monotonic() - _version[0] > 60:
        row = conn.execute("SELECT max(run_id) AS v FROM omm_etl_runs WHERE status = 'ETL_OK'").fetchone()
        _version = (time.monotonic(), str(row["v"] if row else 0))
    return _version[1]


def cached(conn, name: str, params: dict | None, fn, ttl: int | None = None):
    """캐시에 있으면 그 값, 없으면 fn() 을 계산해 저장 후 반환. fn 에서 난 404 같은 예외는 저장하지 않음."""
    r = _r()
    key = None
    if r is not None:
        key = (f"{P}cache:{_data_version(conn)}:{name}:"
               + json.dumps(params or {}, sort_keys=True, ensure_ascii=False, default=str))
        try:
            hit = r.get(key)
            if hit is not None:
                return json.loads(hit)
        except redis.RedisError as e:
            _fail(e)
            r = None
    value = fn()
    if r is not None:
        try:
            r.set(key, json.dumps(jsonable_encoder(value), ensure_ascii=False), ex=ttl or settings.cache_ttl)
        except redis.RedisError as e:
            _fail(e)
    return value


def cache_response(name: str, ttl: int | None = None):
    """조회 API 에 붙이는 캐시 데코레이터. 요청 파라미터(conn · 로그인 정보 제외)가 캐시 키가 됨.
        @router.get(...)
        @cache_response("menu-detail")
        def menu_detail(menu_id: int, conn: Conn): ...
    """
    def deco(fn):
        @functools.wraps(fn)                       # FastAPI 가 원래 함수의 파라미터를 그대로 보게
        def wrapper(*args, **kwargs):
            params = {k: (v.model_dump() if hasattr(v, "model_dump") else v)
                      for k, v in kwargs.items() if k not in ("conn", "user", "admin")}
            return cached(kwargs["conn"], name, params, lambda: fn(*args, **kwargs), ttl)
        return wrapper
    return deco


def clear_cache() -> int:
    """관리자가 사전 · 공통코드를 바꿨을 때 바로 반영되도록 응답 캐시 전부 지우기. 지운 키 수"""
    r = _r()
    if r is None:
        return 0
    try:
        keys = list(r.scan_iter(match=f"{P}cache:*", count=500))
        for i in range(0, len(keys), 500):
            r.delete(*keys[i:i + 500])
        return len(keys)
    except redis.RedisError as e:
        _fail(e)
        return 0


# ── 로그아웃 토큰 차단 ─────────────────────────────────────────────────────

def revoke_token(jti: str | None, exp: int | None) -> None:
    r = _r()
    if r is None or not jti or not exp:
        return
    ttl = int(exp - time.time())
    if ttl <= 0:
        return
    try:
        r.set(f"{P}bl:{jti}", "1", ex=ttl)
    except redis.RedisError as e:
        _fail(e)


def is_revoked(jti: str | None) -> bool:
    r = _r()
    if r is None or not jti:
        return False                     # Redis 가 꺼지면 차단 확인을 잠시 건너뜀 (서비스 우선)
    try:
        return bool(r.exists(f"{P}bl:{jti}"))
    except redis.RedisError as e:
        _fail(e)
        return False


# ── 로그인 시도 제한 (이메일 + IP 마다 10분에 5번) ───────────────────────────

def _login_key(email: str, ip: str) -> str:
    return f"{P}login:{email.lower()}:{ip}"


def login_blocked_for(email: str, ip: str) -> int:
    """막혀 있으면 남은 초, 아니면 0"""
    r = _r()
    if r is None:
        return 0
    try:
        key = _login_key(email, ip)
        n = r.get(key)
        if n is not None and int(n) >= LOGIN_MAX_FAIL:
            return max(int(r.ttl(key)), 1)
    except redis.RedisError as e:
        _fail(e)
    return 0


def login_failed(email: str, ip: str) -> None:
    r = _r()
    if r is None:
        return
    try:
        key = _login_key(email, ip)
        if r.incr(key) == 1:
            r.expire(key, LOGIN_WINDOW_SEC)
    except redis.RedisError as e:
        _fail(e)


def login_succeeded(email: str, ip: str) -> None:
    r = _r()
    if r is None:
        return
    try:
        r.delete(_login_key(email, ip))
    except redis.RedisError as e:
        _fail(e)


# ── 인기 레시피 · 검색어 ─────────────────────────────────────────────────────

def _day_key(kind: str, d: date) -> str:
    return f"{P}pop:{kind}:{d:%Y%m%d}"


def hit(kind: str, member) -> None:
    """kind = recipe | q"""
    r = _r()
    if r is None:
        return
    try:
        key = _day_key(kind, date.today())
        r.zincrby(key, 1, str(member))
        r.expire(key, POP_KEEP_DAYS * 86400)
    except redis.RedisError as e:
        _fail(e)


def top(kind: str, days: int, limit: int) -> list[tuple[str, int]]:
    """최근 days 일 합계 상위 limit 개 [(항목, 횟수)]"""
    r = _r()
    if r is None:
        return []
    keys = [_day_key(kind, date.today() - timedelta(days=i)) for i in range(days)]
    try:
        rows = r.zunion(keys, withscores=True)
    except redis.RedisError as e:
        _fail(e)
        return []
    rows = sorted(rows, key=lambda x: (-x[1], x[0]))[:limit]
    return [(m, int(s)) for m, s in rows]
