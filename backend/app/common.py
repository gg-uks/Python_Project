"""여러 라우터가 같이 쓰는 도구."""
from fastapi import HTTPException, status


def not_implemented(owner: str = "") -> HTTPException:
    """아직 만들지 않은 API. 담당자가 구현하면서 이 줄을 지웁니다."""
    who = f" (담당: {owner})" if owner else ""
    return HTTPException(status.HTTP_501_NOT_IMPLEMENTED, f"아직 구현 전이에요{who}")


def not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what}을(를) 찾을 수 없어요")


def ym_text(d) -> str | None:
    """DATE(2026-11-01) → '2026-11'"""
    return d.strftime("%Y-%m") if d else None


def code_suffix(code_id: str | None) -> str | None:
    """공통코드 'REL_A' → 'A'"""
    return code_id.split("_", 1)[1] if code_id and "_" in code_id else code_id


# ── 취향 · 필터 태그 → SQL 조건 ─────────────────────────────────────────────
# omm_filter_tags 의 rule_type 별로 "이 레시피가 태그에 맞는가" 를 판단하는 조건.
# r = omm_recipes, m = omm_recipe_metrics 별칭이 쿼리에 있어야 합니다.
TAG_RULE_SQL = {
    "RULE_TASTE": "EXISTS (SELECT 1 FROM omm_recipe_tastes t WHERE t.recipe_id = r.recipe_id AND t.taste_id = %s)",
    "RULE_RECIPE_CATEGORY": "EXISTS (SELECT 1 FROM omm_recipe_categories c WHERE c.recipe_id = r.recipe_id AND c.category_id = %s)",
    "RULE_INGREDIENT": "EXISTS (SELECT 1 FROM omm_recipe_ingredients x WHERE x.recipe_id = r.recipe_id AND x.ingredient_id = %s)",
    "RULE_INGREDIENT_CATEGORY": ("EXISTS (SELECT 1 FROM omm_recipe_ingredients x JOIN omm_ingredients i USING (ingredient_id) "
                                 "WHERE x.recipe_id = r.recipe_id AND i.category_id = %s)"),
    "RULE_MENU": "r.menu_id = %s",
    "RULE_CLUSTER": "m.cluster_id = %s",
}


def tag_conditions(conn, tag_ids: list[int]) -> tuple[list[str], list]:
    """태그 번호 목록 → (WHERE 조건 목록, 값 목록).
    먹고 싶은(TAGKIND_WANT) 태그는 '맞아야', 제외할(TAGKIND_EXCLUDE) 태그는 '맞지 않아야' 합니다."""
    if not tag_ids:
        return [], []
    rows = conn.execute("SELECT kind, rule_type, rule_ref_id FROM omm_filter_tags WHERE tag_id = ANY(%s)",
                        (tag_ids,)).fetchall()
    where, params = [], []
    for row in rows:
        sql = TAG_RULE_SQL.get(row["rule_type"])
        if sql is None:
            continue
        where.append(sql if row["kind"] == "TAGKIND_WANT" else f"NOT ({sql})")
        params.append(row["rule_ref_id"])
    return where, params


# ── 회원이 직접 입력한 재료 (omm_user_ingredient_prefs) ──────────────────────────
def user_items(conn, user_id: int) -> list[dict]:
    """회원의 직접 입력 재료. [{kind, ingredientId, name}]"""
    return conn.execute("""
        SELECT pref_kind AS kind, ingredient_id AS "ingredientId", raw_text AS name
        FROM omm_user_ingredient_prefs WHERE user_id = %s ORDER BY pref_id
    """, (user_id,)).fetchall()


def item_exclude_conditions(items: list[dict]) -> tuple[list[str], list]:
    """빼고 싶은 재료 → (WHERE 조건 목록, 값 목록). r = omm_recipes 별칭이 쿼리에 있어야 합니다.
    사전에 있는 재료(ingredientId)는 그 재료가 들어간 레시피를,
    사전에 없는 글자는 레시피 재료 원문 · 표준 이름에 그 글자가 들어간 레시피를 뺍니다."""
    where, params = [], []
    for it in items:
        if it["kind"] != "TAGKIND_EXCLUDE":
            continue
        if it["ingredientId"]:
            where.append("NOT EXISTS (SELECT 1 FROM omm_recipe_ingredients x "
                         "WHERE x.recipe_id = r.recipe_id AND x.ingredient_id = %s)")
            params.append(it["ingredientId"])
        else:
            word = "%" + "".join(it["name"].split()) + "%"
            where.append("NOT EXISTS (SELECT 1 FROM omm_recipe_ingredients x "
                         "LEFT JOIN omm_ingredients i ON i.ingredient_id = x.ingredient_id "
                         "WHERE x.recipe_id = r.recipe_id AND (replace(x.raw_name, ' ', '') ILIKE %s OR i.name ILIKE %s))")
            params += [word, word]
    return where, params
