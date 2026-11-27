"""비밀번호 해시(bcrypt) · JWT · 로그인 확인.

토큰이 필요한 API:    def handler(user: CurrentUser, conn: Conn): ...
관리자만 쓰는 API:   def handler(admin: AdminUser, conn: Conn): ...
로그인 선택 API:     def handler(user: OptionalUser, conn: Conn): ...   (비회원이면 user = None)
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import cache
from .config import settings
from .db import Conn

ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_access_token(user_id: int, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "email": email, "iat": now, "jti": uuid.uuid4().hex,
               "exp": now + timedelta(minutes=settings.jwt_expire_min)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def _unauthorized(msg: str = "로그인이 필요해요") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, msg, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(conn: Conn,
                     cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> dict:
    if cred is None:
        raise _unauthorized()
    try:
        payload = jwt.decode(cred.credentials, settings.jwt_secret, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _unauthorized("토큰이 만료됐거나 올바르지 않아요")
    if cache.is_revoked(payload.get("jti")):
        raise _unauthorized("로그아웃한 토큰이에요. 다시 로그인해 주세요")
    user = conn.execute(
        "SELECT user_id, email, nickname, household_size, status FROM omm_users WHERE user_id = %s",
        (user_id,)).fetchone()
    if user is None:
        raise _unauthorized("없는 회원이에요")
    if user["status"] != "USER_ACTIVE":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "휴면 또는 탈퇴한 회원이에요")
    user["token_jti"], user["token_exp"] = payload.get("jti"), payload.get("exp")    # 로그아웃 때 씀
    return user


def get_admin_user(user: Annotated[dict, Depends(get_current_user)]) -> dict:
    if user["email"].lower() not in settings.admin_emails:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "관리자만 쓸 수 있어요")
    return user


def get_optional_user(conn: Conn,
                      cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> dict | None:
    """토큰이 있으면 회원, 없거나 잘못됐으면 None (비회원도 쓰는 화면에서 취향 반영용)"""
    if cred is None:
        return None
    try:
        return get_current_user(conn, cred)
    except HTTPException:
        return None


CurrentUser = Annotated[dict, Depends(get_current_user)]
OptionalUser = Annotated[dict | None, Depends(get_optional_user)]
AdminUser = Annotated[dict, Depends(get_admin_user)]
