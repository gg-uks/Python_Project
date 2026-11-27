"""추가 그림 (⑨ 비슷한 메뉴 · ⑩ 대체 재료 · ⑪ 가격 ↔ 관심) — 보고서 차트 탭에만 나와요"""
from common import *

# ───────────── 9. 비슷한 메뉴 (분석 ④) ─────────────
def chart9():
    d = q("""SELECT a.name AS a, b.name AS b, s.score FROM omm_menu_similarities s
             JOIN omm_menus a ON a.menu_id = s.menu_id JOIN omm_menus b ON b.menu_id = s.similar_menu_id
             WHERE s.menu_id < s.similar_menu_id AND a.recipe_count >= 20 AND b.recipe_count >= 20
             ORDER BY s.score DESC LIMIT 15""")
    if d.empty: return empty('9_비슷한메뉴.png', 9, '재료가 비슷한 메뉴', 'mart_python_v4.py를 먼저 실행')
    d = d.iloc[::-1]; lab = d.a + '  ↔  ' + d.b
    fig, ax = plt.subplots(figsize=(11, 0.9 + len(d) * 0.45))
    ax.barh(lab, d.score, color=S[0], height=0.6)
    for y, v in enumerate(d.score): ax.text(v, y, f'  {v:.2f}', va='center', fontsize=11, color=INK2)
    ax.set_xlim(0, 1.08); ax.grid(axis='y', visible=False)
    ax.set_title('④ 재료 구성이 비슷한 메뉴 쌍 TOP 15 (코사인 유사도)')
    note(ax, '두 메뉴 레시피들에 들어간 재료 비율을 벡터로 보고 비교 · 레시피 20개 이상인 메뉴만')
    save(fig, '9_비슷한메뉴.png', 9, '재료가 비슷한 메뉴', '같은 재료를 비슷한 비율로 쓰는 메뉴끼리')

# ───────────── 10. 대체 재료 (분석 ⑤) ─────────────
def chart10():
    d = q("""SELECT a.name AS a, b.name AS b, x.score, x.evidence_cnt AS n
             FROM (SELECT DISTINCT ON (ingredient_id, substitute_id) * FROM omm_ingredient_substitutes
                   ORDER BY ingredient_id, substitute_id, (dish_type IS NULL) DESC, score DESC) x
             JOIN omm_ingredients a ON a.ingredient_id = x.ingredient_id JOIN omm_ingredients b ON b.ingredient_id = x.substitute_id
             WHERE x.evidence_cnt >= 20 AND x.ingredient_id < x.substitute_id
             ORDER BY x.score DESC, x.evidence_cnt DESC LIMIT 15""")
    if d.empty: return empty('10_대체재료.png', 10, '대신 쓸 수 있는 재료', 'mart_python_v4.py를 먼저 실행')
    d = d.iloc[::-1]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14, 0.9 + len(d) * 0.45), gridspec_kw={'width_ratios': [1.6, 1]}, sharey=True)
    ax.barh(d.a + '  →  ' + d.b, d.score, color=S[2], height=0.6)
    for y, v in enumerate(d.score): ax.text(v, y, f'  {v:.2f}', va='center', fontsize=11, color=INK2)
    ax.grid(axis='y', visible=False); ax.set_title('⑤ 같은 요리에서 바꿔 쓰인 재료 TOP 15')
    ax2.barh(range(len(d)), d.n, color=S[3], height=0.6)
    for y, v in enumerate(d.n): ax2.text(v, y, f'  {v:,}', va='center', fontsize=11, color=INK2)
    ax2.grid(axis='y', visible=False); ax2.set_title('근거 레시피 수')
    note(ax, '점수 = 같은 메뉴 레시피에서 한쪽만 쓰인 비율 · 근거 20개 이상인 쌍만')
    save(fig, '10_대체재료.png', 10, '대신 쓸 수 있는 재료', '같은 메뉴에서 A 대신 B 를 쓴 레시피가 많은 쌍')

# ───────────── 11. 가격 ↔ 관심 (분석 ⑥) ─────────────
def chart11():
    m = q("""SELECT max(pm.ym) AS ym FROM omm_price_monthly pm JOIN omm_ingredient_interest_monthly ii USING (ingredient_id, ym)
             WHERE pm.market_type = 'MARKET_RETAIL'""").ym.iloc[0]
    d = q(f"""SELECT i.name, pm.vs_normal_pct AS p, ii.yoy_pct AS y, ii.interest_cnt AS n
              FROM omm_price_monthly pm JOIN omm_ingredients i USING (ingredient_id)
              JOIN omm_ingredient_interest_monthly ii ON ii.ingredient_id = pm.ingredient_id AND ii.ym = pm.ym
              WHERE pm.market_type = 'MARKET_RETAIL' AND pm.ym = '{m}' AND pm.vs_normal_pct IS NOT NULL AND ii.yoy_pct IS NOT NULL""")
    lags = q("SELECT lag_month AS l, corr AS c FROM omm_price_interest_corr WHERE ingredient_id IS NULL ORDER BY lag_month")
    if d.empty: return empty('11_가격관심.png', 11, '가격 ↔ 관심', '시세 · 관심도 데이터가 함께 있는 달이 없음')
    d = d[(d.y.abs() <= 300) & (d.p.abs() <= 100)]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14, 6), gridspec_kw={'width_ratios': [1.7, 1]})
    ax.scatter(d.p, d.y, s=18 + np.sqrt(d.n.clip(lower=1)) * 6, color=S[0], alpha=0.55, edgecolor='white', linewidth=0.6, rasterized=True)
    if len(d) > 2:
        k, b = np.polyfit(d.p, d.y, 1); xs = np.linspace(d.p.min(), d.p.max(), 50); ax.plot(xs, k * xs + b, color=S[1], lw=2, ls='--')
    ax.axhline(0, color=INK2, lw=0.8); ax.axvline(0, color=INK2, lw=0.8)
    for _, r in d.reindex(d.p.abs().sort_values(ascending=False).index).head(8).iterrows():
        ax.annotate(r['name'], (r.p, r.y), xytext=(5, 4), textcoords='offset points', fontsize=11, color=INK)
    rr = d.p.corr(d.y) if len(d) > 2 else float('nan')
    ax.set_xlabel('평년 대비 가격 %'); ax.set_ylabel('작년 대비 관심 %'); ax.set_title(f'⑥ 재료 가격 vs 관심 ({str(m)[:7]} · r = {rr:.2f})')
    if not lags.empty:
        ax2.bar(lags.l.astype(str) + '개월', lags.c, color=[S[1] if c < 0 else S[0] for c in lags.c], width=0.6)
        for x, c in enumerate(lags.c): ax2.text(x, c, f'{c:.2f}', ha='center', va='bottom' if c >= 0 else 'top', fontsize=11, color=INK)
        ax2.axhline(0, color=INK2, lw=0.8); ax2.grid(axis='x', visible=False)
    ax2.set_title('가격이 움직인 뒤 몇 달 뒤 관심이 따라오나 (시차 상관)')
    note(ax, '점 크기 = 그 달 관심도 건수 · 점선 = 추세선 · 관심 ±300% 넘는 점은 뺌')
    save(fig, '11_가격관심.png', 11, '가격 ↔ 관심', '재료 값이 오를 때 관심도도 움직이는지')
