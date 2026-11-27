"""먹은 기록 (v4.7 omm_user_meals) · 기록 추가 / 목록 / 삭제 / 주간 요약 / 최근 먹은 메뉴.

영양 · 재료비는 고른 레시피, 없으면 메뉴 대표 레시피의 분석값(omm_recipe_metrics 1인분 기준) × 먹은 인분.
회원마다 달라서 캐시는 안 씀.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ..db import Conn
from ..security import CurrentUser

router = APIRouter(prefix="/api/users/me", tags=["Meals · 먹은 기록"])
KST = ZoneInfo("Asia/Seoul")
MEAL_TYPES = {"MEAL_BREAKFAST", "MEAL_LUNCH", "MEAL_DINNER", "MEAL_SNACK"}


def today() -> date:
    return datetime.now(KST).date()        # 서버 시간대와 상관없이 한국 날짜


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class MealReq(CamelModel):
    """메뉴 · 레시피 중 하나는 꼭. 레시피만 보내면 메뉴는 그 레시피의 메뉴로 채움"""
    menu_id: int | None = None
    recipe_id: int | None = None
    eaten_on: date | None = Field(None, description="먹은 날 (없으면 오늘)")
    meal_type: str | None = Field(None, description="MEAL_BREAKFAST / MEAL_LUNCH / MEAL_DINNER / MEAL_SNACK")
    servings: float = Field(1, gt=0, le=20)
    memo: str | None = Field(None, max_length=200)


# 기록 한 줄 + 메뉴 · 레시피 이름 + 1인분 분석값 (레시피 없으면 메뉴 대표 레시피)
MEAL_SELECT = """
    SELECT ml.meal_id, ml.eaten_on, ml.meal_type, cc.code_nm AS meal_type_nm, ml.servings, ml.memo, ml.created_at,
           ml.menu_id, mn.name AS menu_name, mn.dish_type,
           ml.recipe_id, r.title AS recipe_title,
           COALESCE(r.image_url, rr.image_url) AS image_url,
           rm.kcal_per_serving, rm.protein_per_serving, rm.sodium_per_serving,
           CASE WHEN rm.priced_ratio >= 0.6 AND rm.cost_per_serving >= 500 THEN rm.cost_per_serving END AS cost_per_serving
    FROM omm_user_meals ml
    LEFT JOIN omm_menus mn ON mn.menu_id = ml.menu_id
    LEFT JOIN omm_recipes r ON r.recipe_id = ml.recipe_id
    LEFT JOIN omm_recipes rr ON rr.recipe_id = mn.rep_recipe_id
    LEFT JOIN omm_recipe_metrics rm ON rm.recipe_id = COALESCE(ml.recipe_id, mn.rep_recipe_id)
    LEFT JOIN omm_common_codes cc ON cc.code_id = ml.meal_type
"""


def _f(v):
    return float(v) if v is not None else None


def _row(x) -> dict:
    sv = float(x["servings"])
    mul = lambda v: round(float(v) * sv, 1) if v is not None else None
    return {
        "mealId": x["meal_id"], "eatenOn": x["eaten_on"].isoformat(),
        "mealType": x["meal_type"], "mealTypeName": x["meal_type_nm"],
        "servings": sv, "memo": x["memo"],
        "menuId": x["menu_id"], "menuName": x["menu_name"], "dishType": x["dish_type"],
        "recipeId": x["recipe_id"], "recipeTitle": x["recipe_title"], "imageUrl": x["image_url"],
        "kcal": mul(x["kcal_per_serving"]), "proteinG": mul(x["protein_per_serving"]),
        "sodiumMg": mul(x["sodium_per_serving"]),
        "costWon": round(float(x["cost_per_serving"]) * sv) if x["cost_per_serving"] is not None else None,
    }


@router.post("/meals", status_code=status.HTTP_201_CREATED, summary="먹었어요 기록 추가")
def add_meal(body: MealReq, user: CurrentUser, conn: Conn):
    if body.menu_id is None and body.recipe_id is None:
        raise HTTPException(422, "메뉴나 레시피 중 하나는 골라 주세요")
    menu_id = body.menu_id
    if body.recipe_id is not None:
        r = conn.execute("SELECT menu_id FROM omm_recipes WHERE recipe_id = %s", (body.recipe_id,)).fetchone()
        if not r:
            raise HTTPException(404, "레시피를 찾을 수 없어요")
        menu_id = menu_id or r["menu_id"]
    if menu_id is not None and not conn.execute("SELECT 1 FROM omm_menus WHERE menu_id = %s", (menu_id,)).fetchone():
        raise HTTPException(404, "메뉴를 찾을 수 없어요")
    if body.meal_type is not None and body.meal_type not in MEAL_TYPES:
        raise HTTPException(422, "끼니는 MEAL_BREAKFAST / MEAL_LUNCH / MEAL_DINNER / MEAL_SNACK 중 하나예요")
    d = body.eaten_on or today()
    if d > today() + timedelta(days=1) or d < today() - timedelta(days=366):
        raise HTTPException(422, "먹은 날은 지난 1년 안의 날짜로 골라 주세요")
    memo = (body.memo or "").strip() or None
    new = conn.execute("""
        INSERT INTO omm_user_meals (user_id, menu_id, recipe_id, eaten_on, meal_type, servings, memo)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING meal_id
    """, (user["user_id"], menu_id, body.recipe_id, d, body.meal_type, body.servings, memo)).fetchone()
    return _row(conn.execute(MEAL_SELECT + " WHERE ml.meal_id = %s", (new["meal_id"],)).fetchone())


@router.get("/meals", summary="먹은 기록 목록 (기간 · 최근순)")
def list_meals(user: CurrentUser, conn: Conn,
               date_from: date | None = Query(None, alias="from", description="시작일 (없으면 30일 전)"),
               date_to: date | None = Query(None, alias="to", description="끝일 (없으면 오늘)"),
               limit: int = Query(100, ge=1, le=300)):
    t = date_to or today()
    f = date_from or (t - timedelta(days=29))
    if f > t:
        raise HTTPException(422, "시작일이 끝일보다 늦어요")
    rows = conn.execute(MEAL_SELECT + """
        WHERE ml.user_id = %s AND ml.eaten_on BETWEEN %s AND %s
        ORDER BY ml.eaten_on DESC, cc.sort NULLS LAST, ml.created_at DESC LIMIT %s
    """, (user["user_id"], f, t, limit)).fetchall()
    return {"from": f.isoformat(), "to": t.isoformat(), "total": len(rows), "items": [_row(x) for x in rows]}


@router.delete("/meals/{meal_id}", status_code=status.HTTP_204_NO_CONTENT, summary="먹은 기록 삭제 (내 기록만)")
def delete_meal(meal_id: int, user: CurrentUser, conn: Conn):
    cur = conn.execute("DELETE FROM omm_user_meals WHERE meal_id = %s AND user_id = %s", (meal_id, user["user_id"]))
    if cur.rowcount == 0:
        raise HTTPException(404, "기록을 찾을 수 없어요")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/meals/summary", summary="주간 요약 (열량 · 단백질 · 나트륨 · 재료비 · 요리 종류 비율)")
def week_summary(user: CurrentUser, conn: Conn,
                 week: date | None = Query(None, description="그 주에 들어 있는 아무 날 (없으면 이번 주). 월요일 시작")):
    d = week or today()
    start = d - timedelta(days=d.weekday())
    end = start + timedelta(days=6)
    rows = [_row(x) for x in conn.execute(MEAL_SELECT + " WHERE ml.user_id = %s AND ml.eaten_on BETWEEN %s AND %s",
                                          (user["user_id"], start, end)).fetchall()]
    keys = ("kcal", "proteinG", "sodiumMg", "costWon")

    def total(items):
        out = {}
        for k in keys:
            vals = [i[k] for i in items if i[k] is not None]
            out[k] = (round(sum(vals)) if k in ("costWon", "sodiumMg", "kcal") else round(sum(vals), 1)) if vals else None
        out["known"] = {k: sum(1 for i in items if i[k] is not None) for k in keys}   # 값이 있는 기록 수
        return out

    days = []
    for i in range(7):
        day = start + timedelta(days=i)
        items = [r for r in rows if r["eatenOn"] == day.isoformat()]
        days.append({"date": day.isoformat(), "count": len(items), **{k: v for k, v in total(items).items() if k != "known"}})
    mix: dict[str, int] = {}
    for r in rows:
        mix[r["dishType"] or "기타"] = mix.get(r["dishType"] or "기타", 0) + 1
    menus: dict[tuple, int] = {}
    for r in rows:
        if r["menuId"]:
            menus[(r["menuId"], r["menuName"])] = menus.get((r["menuId"], r["menuName"]), 0) + 1
    eaten_days = sum(1 for x in days if x["count"])
    tot = total(rows)
    return {
        "weekStart": start.isoformat(), "weekEnd": end.isoformat(), "count": len(rows), "eatenDays": eaten_days,
        "total": {k: tot[k] for k in keys}, "known": tot["known"],
        "dailyAvg": {k: (round(tot[k] / eaten_days, 1) if tot[k] is not None and eaten_days else None) for k in keys},
        "days": days,
        "dishMix": [{"dishType": k, "count": v, "pct": round(100 * v / len(rows), 1)}
                    for k, v in sorted(mix.items(), key=lambda kv: -kv[1])],
        "topMenus": [{"menuId": k[0], "name": k[1], "count": v} for k, v in sorted(menus.items(), key=lambda kv: -kv[1])[:5]],
    }


@router.get("/meals/recent-menus", summary="최근 N일 안에 먹은 메뉴 번호 (추천에서 뒤로 미룰 때)")
def recent_menus(user: CurrentUser, conn: Conn, days: int = Query(3, ge=1, le=14)):
    rows = conn.execute("""
        SELECT menu_id, max(eaten_on) AS last_on FROM omm_user_meals
        WHERE user_id = %s AND menu_id IS NOT NULL AND eaten_on > %s
        GROUP BY menu_id ORDER BY last_on DESC
    """, (user["user_id"], today() - timedelta(days=days))).fetchall()
    return {"days": days, "menuIds": [r["menu_id"] for r in rows],
            "items": [{"menuId": r["menu_id"], "lastEatenOn": r["last_on"].isoformat()} for r in rows]}
