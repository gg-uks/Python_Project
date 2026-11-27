"""⑥ 영양 효율 — 재료비 대비 영양 효율 (공공데이터: KAMIS · 참가격 · 식약처)
담당: 3팀 (⑤⑥) · 이 파일만 고치면 돼요.
  - 노트북 notebooks/3팀_⑤⑥.ipynb 에서 고치고 바로 실행해 볼 수 있어요.
  - 서버는 매일 18:30 charts_v4.py 가 이 파일의 chart6() 을 불러 그림을 다시 그려요.
  - 관리자 화면 › 데이터 분석 탭의 '차트 그리기' 코드 칸에 이 파일 내용이 그대로 보여요.
"""
from common import *

# [1단계] DB에서 데이터 불러오기 (q = SQL → pandas DataFrame)
# [2단계] pandas 로 가공
# [3단계] matplotlib 으로 그리고 save() 로 저장 (PNG + SVG)

def chart6():
    d = q("""SELECT i.name, nf.protein_g / pm.price_per_100g * 1000 AS p, nf.energy_kcal / pm.price_per_100g * 1000 AS k
             FROM omm_ingredients i JOIN omm_nutrition_foods nf ON nf.food_cd = i.nutr_food_cd
             JOIN omm_price_monthly pm ON pm.ingredient_id = i.ingredient_id AND pm.market_type = 'MARKET_RETAIL' AND pm.ym = (SELECT max(ym) FROM omm_price_monthly)
             WHERE pm.price_per_100g > 0 AND nf.protein_g IS NOT NULL""")
    unit = '재료'
    if d.empty:                                   # 재료별 영양성분이 없으면(팀 공유 데이터) 메뉴 영양성분 × 레시피 재료비로
        d = q("""SELECT m.name, percentile_cont(0.5) WITHIN GROUP (ORDER BY rm.protein_per_1000won) AS p,
                        percentile_cont(0.5) WITHIN GROUP (ORDER BY rm.kcal_per_1000won) AS k
                 FROM omm_recipe_metrics rm JOIN omm_recipes r USING (recipe_id) JOIN omm_menus m USING (menu_id)
                 WHERE rm.protein_per_1000won IS NOT NULL AND rm.priced_ratio >= 0.6 AND rm.cost_per_serving >= 500
                 GROUP BY m.name HAVING count(*) >= 5""")
        unit = '메뉴'
    if d.empty: return empty('6_영양효율.png', 6, '재료비 대비 영양 효율', '영양성분과 재료비가 함께 있는 재료 · 메뉴가 없음')
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(15, max(6, min(len(d), 20) * 0.35)))
    t = d.sort_values('p').tail(20)
    ax.barh(t.name, t.p, color=S[0], height=0.6)
    for y, v in enumerate(t.p): ax.text(v, y, f'  {v:.1f}g', va='center', fontsize=11, color=INK2)
    ax.set_title(f'⑥ 1,000원으로 살 수 있는 단백질 (g) · {unit}별'); ax.grid(axis='y', visible=False)
    ax2.scatter(d.k, d.p, s=50, color=S[0], alpha=0.7, edgecolor=SURF, linewidth=1)
    mk, mp = d.k.median(), d.p.median()
    ax2.axvline(mk, color=MUTED, ls=':', lw=1); ax2.axhline(mp, color=MUTED, ls=':', lw=1)
    lab = pd.concat([d.nlargest(6, 'p'), d.nlargest(4, 'k'), d.nsmallest(3, 'p')]).drop_duplicates('name')
    for _, r in lab.iterrows(): ax2.annotate(r['name'], (r.k, r.p), xytext=(5, 4), textcoords='offset points', fontsize=11, color=INK)
    ax2.text(0.98, 0.98, '단백질 · 열량 모두 가성비 ↑', transform=ax2.transAxes, ha='right', va='top', color=INK2, fontsize=11)
    ax2.text(0.02, 0.02, '둘 다 비쌈', transform=ax2.transAxes, color=INK2, fontsize=11)
    ax2.set_xlabel('1,000원당 열량 (kcal)'); ax2.set_ylabel('1,000원당 단백질 (g)'); ax2.set_title('열량 · 단백질 가성비 사분면')
    note(ax, '최근 월 KAMIS 소매가 · 식약처 100g당 영양성분 · 가격과 영양이 모두 연결된 재료만' if unit == '재료' else
             '메뉴별 식약처 1인분 영양성분 ÷ 레시피 1인분 재료비 · 레시피 5개 이상 메뉴의 중앙값 (가격 붙은 재료 60% 이상 · 1인분 500원 이상)')
    save(fig, '6_영양효율.png', 6, '재료비 대비 영양 효율', '1,000원당 단백질 · 열량')

if __name__ == '__main__':
    chart6()
