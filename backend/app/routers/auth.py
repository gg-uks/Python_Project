"""회원가입 · 로그인 · 내 정보."""
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from psycopg import errors
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from .. import cache
from ..common import user_items
from ..config import settings
from ..db import Conn
from ..security import CurrentUser, create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api", tags=["Auth · User"])

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ItemReq(CamelModel):
    """직접 입력한 재료 한 개. 재료 사전에 있으면 ingredientId, 없으면 null 로 글자만"""
    ingredient_id: int | None = None
    name: str = Field(min_length=1, max_length=50)


class SignupReq(CamelModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=100)
    password: str = Field(min_length=8, max_length=64)
    nickname: str = Field(min_length=1, max_length=30)
    household_size: int | None = Field(None, ge=1, le=6)
    want_tag_ids: list[int] = []
    exclude_tag_ids: list[int] = []
    want_items: list[ItemReq] = Field(default_factory=list, max_length=30)
    exclude_items: list[ItemReq] = Field(default_factory=list, max_length=30)

    @field_validator("password")
    @classmethod
    def bcrypt_limit(cls, v: str) -> str:
        if len(v.encode()) > 72:                       # bcrypt 는 72바이트까지만 씀
            raise ValueError("비밀번호가 너무 길어요")
        return v


class LoginReq(CamelModel):
    email: str
    password: str


def _save_preferences(conn, user_id: int, want: list[int], exclude: list[int]) -> None:
    """취향 태그를 통째로 교체. 태그 종류(먹고 싶은 / 제외할)가 맞는지도 확인."""
    tag_ids = set(want) | set(exclude)
    if tag_ids:
        kinds = {r["tag_id"]: r["kind"] for r in conn.execute(
            "SELECT tag_id, kind FROM omm_filter_tags WHERE tag_id = ANY(%s)", (list(tag_ids),)).fetchall()}
        bad = [t for t in want if kinds.get(t) != "TAGKIND_WANT"] + \
              [t for t in exclude if kinds.get(t) != "TAGKIND_EXCLUDE"]
        if bad:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"태그 번호가 올바르지 않아요: {bad}")
    conn.execute("DELETE FROM omm_user_preferences WHERE user_id = %s", (user_id,))
    for t in tag_ids:
        conn.execute("INSERT INTO omm_user_preferences (user_id, tag_id) VALUES (%s, %s)", (user_id, t))


def _save_items(conn, user_id: int, kind: str, items: list[ItemReq]) -> None:
    """직접 입력 재료를 종류(TAGKIND_WANT / TAGKIND_EXCLUDE)별로 통째로 교체.
    ingredientId 가 없으면 이름 · 별칭이 정확히 같은 재료를 찾아 붙이고, 그래도 없으면 글자(raw_text)만 저장."""
    conn.execute("DELETE FROM omm_user_ingredient_prefs WHERE user_id = %s AND pref_kind = %s", (user_id, kind))
    seen = set()
    for it in items:
        text = " ".join(it.name.split())[:50]
        if not text or text in seen:
            continue
        seen.add(text)
        iid = it.ingredient_id
        if iid is not None:
            ok = conn.execute("SELECT 1 FROM omm_ingredients WHERE ingredient_id = %s", (iid,)).fetchone()
            if ok is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"재료 번호가 올바르지 않아요: {iid}")
        else:
            row = conn.execute("""
                SELECT ingredient_id FROM omm_ingredients WHERE name = %s
                UNION ALL
                SELECT ingredient_id FROM omm_ingredient_aliases WHERE alias = %s AND is_active
                LIMIT 1
            """, (text, text.replace(" ", ""))).fetchone()
            iid = row["ingredient_id"] if row else None
        conn.execute("""
            INSERT INTO omm_user_ingredient_prefs (user_id, pref_kind, ingredient_id, raw_text)
            VALUES (%s, %s, %s, %s)
        """, (user_id, kind, iid, text))


@router.get("/auth/check-email", summary="이메일 중복 확인")
def check_email(conn: Conn, email: str = Query(pattern=EMAIL_PATTERN)):
    taken = conn.execute("SELECT 1 FROM omm_users WHERE lower(email) = lower(%s)", (email,)).fetchone()
    return {"available": taken is None}


@router.post("/auth/signup", status_code=status.HTTP_201_CREATED, summary="회원가입")
def signup(body: SignupReq, conn: Conn):
    try:
        row = conn.execute("""
            INSERT INTO omm_users (email, password_hash, nickname, household_size)
            VALUES (lower(%s), %s, %s, %s) RETURNING user_id
        """, (body.email, hash_password(body.password), body.nickname, body.household_size)).fetchone()
    except errors.UniqueViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 가입된 이메일이에요")
    _save_preferences(conn, row["user_id"], body.want_tag_ids, body.exclude_tag_ids)
    _save_items(conn, row["user_id"], "TAGKIND_WANT", body.want_items)
    _save_items(conn, row["user_id"], "TAGKIND_EXCLUDE", body.exclude_items)
    return {"userId": row["user_id"]}


@router.post("/auth/login", summary="로그인 (JWT 발급)")
def login(body: LoginReq, conn: Conn, request: Request):
    # 같은 이메일 + IP 로 10분에 5번 틀리면 잠시 막음 (Redis). IP 는 HAProxy 가 넘긴 실제 접속자 IP
    ip = request.client.host if request.client else "-"
    wait = cache.login_blocked_for(body.email, ip)
    if wait:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"로그인 실패가 많아요. {(wait + 59) // 60}분 뒤에 다시 시도해 주세요",
                            headers={"Retry-After": str(wait)})
    user = conn.execute(
        "SELECT user_id, email, password_hash, nickname, status FROM omm_users WHERE lower(email) = lower(%s)",
        (body.email,)).fetchone()
    if user is None or not verify_password(body.password, user["password_hash"]):
        cache.login_failed(body.email, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "이메일 또는 비밀번호가 맞지 않아요")
    if user["status"] != "USER_ACTIVE":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "휴면 또는 탈퇴한 회원은 로그인할 수 없어요")
    cache.login_succeeded(body.email, ip)
    return {"accessToken": create_access_token(user["user_id"], user["email"]), "nickname": user["nickname"],
            "admin": user["email"].lower() in settings.admin_emails}


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, summary="로그아웃")
def logout(user: CurrentUser):
    # 이 토큰을 만료 시각까지 Redis 에 "로그아웃함"으로 기록 → 다시 쓰면 401
    cache.revoke_token(user.get("token_jti"), user.get("token_exp"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users/me", summary="내 정보 조회")
def me(user: CurrentUser, conn: Conn):
    tags = conn.execute("""
        SELECT p.tag_id, t.kind FROM omm_user_preferences p JOIN omm_filter_tags t USING (tag_id)
        WHERE p.user_id = %s ORDER BY t.sort_order
    """, (user["user_id"],)).fetchall()
    items = user_items(conn, user["user_id"])
    pick = lambda kind: [{"ingredientId": i["ingredientId"], "name": i["name"]} for i in items if i["kind"] == kind]
    return {
        "userId": user["user_id"], "email": user["email"], "nickname": user["nickname"],
        "householdSize": user["household_size"],
        "wantTagIds": [t["tag_id"] for t in tags if t["kind"] == "TAGKIND_WANT"],
        "excludeTagIds": [t["tag_id"] for t in tags if t["kind"] == "TAGKIND_EXCLUDE"],
        "wantItems": pick("TAGKIND_WANT"),
        "excludeItems": pick("TAGKIND_EXCLUDE"),
    }


class UpdateMeReq(CamelModel):
    """보낸 칸만 바뀜. 취향 태그는 보내면 통째로 교체"""
    nickname: str | None = Field(None, min_length=1, max_length=30)
    household_size: int | None = Field(None, ge=1, le=6)
    want_tag_ids: list[int] | None = None
    exclude_tag_ids: list[int] | None = None
    want_items: list[ItemReq] | None = Field(None, max_length=30)
    exclude_items: list[ItemReq] | None = Field(None, max_length=30)


@router.put("/users/me", summary="내 정보 · 취향 수정 (취향 태그 · 직접 입력 재료는 보내면 통째로 교체)")
def update_me(body: UpdateMeReq, user: CurrentUser, conn: Conn):
    conn.execute("""
        UPDATE omm_users SET nickname = COALESCE(%s, nickname), household_size = COALESCE(%s, household_size)
        WHERE user_id = %s
    """, (body.nickname, body.household_size, user["user_id"]))
    if body.want_tag_ids is not None or body.exclude_tag_ids is not None:
        cur = me(user, conn)
        _save_preferences(conn, user["user_id"],
                          cur["wantTagIds"] if body.want_tag_ids is None else body.want_tag_ids,
                          cur["excludeTagIds"] if body.exclude_tag_ids is None else body.exclude_tag_ids)
    if body.want_items is not None:          # 직접 입력 재료도 보내면 통째로 교체
        _save_items(conn, user["user_id"], "TAGKIND_WANT", body.want_items)
    if body.exclude_items is not None:
        _save_items(conn, user["user_id"], "TAGKIND_EXCLUDE", body.exclude_items)
    fresh = conn.execute("SELECT user_id, email, nickname, household_size FROM omm_users WHERE user_id = %s",
                         (user["user_id"],)).fetchone()
    return me(fresh, conn)


@router.delete("/users/me", status_code=status.HTTP_204_NO_CONTENT, summary="회원 탈퇴 (상태만 USER_WITHDRAWN)")
def withdraw(user: CurrentUser, conn: Conn):
    # 행은 남기고 상태만 바꿈 → 이 토큰도 바로 못 씀 (get_current_user 가 USER_ACTIVE 만 통과)
    conn.execute("UPDATE omm_users SET status = 'USER_WITHDRAWN' WHERE user_id = %s", (user["user_id"],))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
