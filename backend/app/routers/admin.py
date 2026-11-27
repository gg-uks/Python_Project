"""관리자: 적재 현황 · 공통코드 · 사전 · 회원 관리. 모두 ADMIN_EMAILS 에 있는 계정만."""
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from .. import cache
from ..common import not_found
from ..db import Conn
from ..security import AdminUser

router = APIRouter(prefix="/api/admin", tags=["Admin"])


PAGE_SIZE = 20


@router.get("/etl-runs", summary="적재 현황 (실패 먼저 · 20개씩)")
def etl_runs(admin: AdminUser, conn: Conn, status_: str | None = Query(None, alias="status", description="ETL_OK · ETL_FAILED · ETL_RUNNING"),
             page: int = Query(1, ge=1)):
    where, params = ("WHERE status = %s", [status_]) if status_ else ("", [])
    total = conn.execute(f"SELECT count(*) AS n FROM omm_etl_runs {where}", params).fetchone()["n"]
    items = conn.execute(f"""
        SELECT run_id AS "runId", source, job, started_at AS "startedAt", finished_at AS "finishedAt",
               status, row_count AS "rowCount", message
        FROM omm_etl_runs {where}
        ORDER BY (status = 'ETL_FAILED') DESC, run_id DESC
        LIMIT %s OFFSET %s
    """, params + [PAGE_SIZE, (page - 1) * PAGE_SIZE]).fetchall()
    return {"total": total, "page": page, "size": PAGE_SIZE, "items": items}


@router.get("/codes", summary="공통코드 조회")
def list_codes(admin: AdminUser, conn: Conn, group: str | None = Query(None, description="그룹 코드 (PRICE_SOURCE …)")):
    return conn.execute("""
        SELECT code_id AS "codeId", group_code AS "group", group_nm AS "groupName", code, code_nm AS "codeNm",
               sort, use_yn AS "useYn", description
        FROM omm_common_codes WHERE (%s::text IS NULL OR group_code = %s)
        ORDER BY group_sort, group_code, sort, code_id
    """, (group, group)).fetchall()


class CodeReq(BaseModel):
    codeNm: str | None = Field(None, min_length=1, max_length=50)
    sort: int | None = Field(None, ge=0, le=999)
    useYn: Literal["Y", "N"] | None = None


@router.put("/codes/{code_id}", summary="공통코드 수정 (이름 · 순서 · 사용 여부)")
def update_code(code_id: str, body: CodeReq, admin: AdminUser, conn: Conn):
    if body.codeNm is None and body.sort is None and body.useYn is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "codeNm · sort · useYn 중 하나는 보내 주세요")
    row = conn.execute("""
        UPDATE omm_common_codes
           SET code_nm = COALESCE(%s, code_nm), sort = COALESCE(%s, sort), use_yn = COALESCE(%s, use_yn)
         WHERE code_id = %s
        RETURNING code_id AS "codeId", group_code AS "group", code_nm AS "codeNm", sort, use_yn AS "useYn"
    """, (body.codeNm, body.sort, body.useYn, code_id)).fetchone()
    if not row:
        raise not_found("공통코드")
    cache.clear_cache()                  # 분석 · 대체 재료 응답에 코드 이름이 들어가서
    return row


# ── 메뉴 · 재료 사전 ────────────────────────────────────────────────────────
# 사전 원본 = PostgreSQL (omm_menus.match_keywords · omm_ingredient_aliases).
# 매칭은 normalizer(mongo_extract.py) 배치가 하므로 "다음 적재 때 반영" 됩니다.
# 별칭 삭제는 행을 지우지 않고 is_active = false 로 남깁니다 (다음 적재 때 CSV 에서 다시 살아나지 않도록).

def _nospace(s: str) -> str:
    return re.sub(r"\s+", "", s)


class KeywordsReq(BaseModel):
    keywords: list[str] = Field(max_length=50)


class AliasReq(BaseModel):
    alias: str = Field(min_length=1, max_length=100)


def _menu_keywords(conn, menu_id: int) -> dict:
    row = conn.execute("""
        SELECT menu_id AS "menuId", name, COALESCE(match_keywords, ARRAY[name]) AS keywords
        FROM omm_menus WHERE menu_id = %s
    """, (menu_id,)).fetchone()
    if not row:
        raise not_found("메뉴")
    return row


@router.get("/menus/{menu_id}/keywords", summary="메뉴 키워드 조회")
def get_menu_keywords(menu_id: int, admin: AdminUser, conn: Conn):
    return _menu_keywords(conn, menu_id)


@router.put("/menus/{menu_id}/keywords", summary="메뉴 키워드 수정 (목록 전체를 바꿈 · 다음 적재 때 반영)")
def update_menu_keywords(menu_id: int, body: KeywordsReq, admin: AdminUser, conn: Conn):
    menu = _menu_keywords(conn, menu_id)
    # 메뉴 이름은 항상 첫 키워드로 유지. 공백만 다른 키워드는 하나로 (매칭은 공백을 빼고 비교)
    kws, seen = [], set()
    for k in [menu["name"], *body.keywords]:
        k = " ".join(k.split())
        if not k:
            continue
        if len(k) > 50:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"키워드는 50자 이하로: {k[:20]}…")
        if _nospace(k) in seen:
            continue
        seen.add(_nospace(k))
        kws.append(k)
    conn.execute("UPDATE omm_menus SET match_keywords = %s WHERE menu_id = %s", (kws, menu_id))
    # 다른 메뉴와 겹치는 키워드 (긴 키워드가 먼저 매칭되므로 오매칭 확인용 경고)
    shared = conn.execute("""
        SELECT k AS keyword, m.name AS menu
        FROM omm_menus m, unnest(m.match_keywords) k
        WHERE m.menu_id <> %s AND replace(k, ' ', '') = ANY(%s)
        ORDER BY 1, 2
    """, (menu_id, list(seen))).fetchall()
    cache.clear_cache()
    return {"menuId": menu_id, "name": menu["name"], "keywords": kws, "sharedWith": shared}


def _ingredient_name(conn, ingredient_id: int) -> str:
    row = conn.execute("SELECT name FROM omm_ingredients WHERE ingredient_id = %s", (ingredient_id,)).fetchone()
    if not row:
        raise not_found("재료")
    return row["name"]


@router.get("/ingredients/{ingredient_id}/aliases", summary="재료 별칭 조회")
def list_aliases(ingredient_id: int, admin: AdminUser, conn: Conn, include_deleted: bool = Query(False, alias="includeDeleted")):
    name = _ingredient_name(conn, ingredient_id)
    rows = conn.execute("""
        SELECT alias, source, is_active AS "isActive", updated_at AS "updatedAt"
        FROM omm_ingredient_aliases
        WHERE ingredient_id = %s AND (is_active OR %s)
        ORDER BY is_active DESC, alias
    """, (ingredient_id, include_deleted)).fetchall()
    return {"ingredientId": ingredient_id, "name": name, "aliases": rows}


@router.post("/ingredients/{ingredient_id}/aliases", status_code=status.HTTP_201_CREATED,
             summary="재료 별칭 추가 (지운 별칭은 다시 살림 · 다음 적재 때 반영)")
def add_alias(ingredient_id: int, body: AliasReq, admin: AdminUser, conn: Conn):
    name = _ingredient_name(conn, ingredient_id)
    alias = _nospace(body.alias)[:100]
    if not alias:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "별칭이 비어 있어요")
    # 새 별칭 · 지운 별칭 · 같은 재료의 별칭이면 저장. 다른 재료가 쓰는 중이면 RETURNING 이 비어서 409
    row = conn.execute("""
        INSERT INTO omm_ingredient_aliases AS a (alias, ingredient_id, source, is_active, updated_at)
        VALUES (%s, %s, 'SRC_MANUAL', true, now())
        ON CONFLICT (alias) DO UPDATE
           SET ingredient_id = EXCLUDED.ingredient_id, source = 'SRC_MANUAL', is_active = true, updated_at = now()
         WHERE NOT a.is_active OR a.ingredient_id = EXCLUDED.ingredient_id
        RETURNING alias
    """, (alias, ingredient_id)).fetchone()
    if not row:
        other = conn.execute("""
            SELECT i.name FROM omm_ingredient_aliases a JOIN omm_ingredients i USING (ingredient_id) WHERE a.alias = %s
        """, (alias,)).fetchone()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"'{alias}' 은(는) 이미 '{other['name'] if other else '다른 재료'}' 의 별칭이에요. 그쪽에서 먼저 지워 주세요")
    cache.clear_cache()                  # 재료 검색이 별칭을 바로 씀
    return {"ingredientId": ingredient_id, "name": name, "alias": alias, "source": "SRC_MANUAL"}


@router.delete("/ingredients/{ingredient_id}/aliases/{alias:path}", status_code=status.HTTP_204_NO_CONTENT,
               summary="재료 별칭 지우기 (다음 적재 때 반영)")
def delete_alias(ingredient_id: int, alias: str, admin: AdminUser, conn: Conn):
    row = conn.execute("""
        UPDATE omm_ingredient_aliases
           SET is_active = false, source = 'SRC_MANUAL', updated_at = now()
         WHERE alias = %s AND ingredient_id = %s AND is_active
        RETURNING alias
    """, (_nospace(alias), ingredient_id)).fetchone()
    if not row:
        raise not_found("별칭")
    cache.clear_cache()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/cache", summary="API 응답 캐시 비우기 (Redis)")
def clear_cache(admin: AdminUser):
    return {"deleted": cache.clear_cache(), "redis": cache.status()}


UserStatus = Literal["USER_ACTIVE", "USER_DORMANT", "USER_WITHDRAWN"]


@router.get("/users", summary="회원 목록 (이메일 · 닉네임 검색, 20개씩)")
def list_users(admin: AdminUser, conn: Conn, q: str | None = None, status_: UserStatus | None = Query(None, alias="status"),
               page: int = Query(1, ge=1)):
    where, params = [], []
    if q and q.strip():
        where.append("(email ILIKE %s OR nickname ILIKE %s)")
        params += [f"%{q.strip()}%"] * 2
    if status_:
        where.append("status = %s")
        params.append(status_)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT count(*) AS n FROM omm_users {where_sql}", params).fetchone()["n"]
    items = conn.execute(f"""
        SELECT user_id AS "userId", email, nickname, household_size AS "householdSize", status, created_at AS "createdAt"
        FROM omm_users {where_sql} ORDER BY user_id DESC LIMIT %s OFFSET %s
    """, params + [PAGE_SIZE, (page - 1) * PAGE_SIZE]).fetchall()
    return {"total": total, "page": page, "size": PAGE_SIZE, "items": items}


class UserStatusReq(BaseModel):
    status: UserStatus


@router.patch("/users/{user_id}", summary="회원 상태 변경 (사용 중 · 휴면 · 탈퇴)")
def update_user_status(user_id: int, body: UserStatusReq, admin: AdminUser, conn: Conn):
    if user_id == admin["user_id"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "내 계정 상태는 여기서 바꿀 수 없어요")
    row = conn.execute("""
        UPDATE omm_users SET status = %s WHERE user_id = %s
        RETURNING user_id AS "userId", email, nickname, status
    """, (body.status, user_id)).fetchone()
    if not row:
        raise not_found("회원")
    return row
