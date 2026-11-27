"""④ 맛 표현 — 맛 표현별 주요 재료 → "매콤한 거 먹고 싶어" 같은 문장 추천
이 파일만 고치면 돼요.
  - 노트북 notebooks/분석_③④.ipynb 에서 고치고 바로 실행해 볼 수 있어요.
  - 서버는 매일 18:30 charts_v4.py 가 이 파일의 chart4() 을 불러 그림을 다시 그려요.
  - 관리자 화면 › 데이터 분석 탭의 '차트 그리기' 코드 칸에 이 파일 내용이 그대로 보여요.
"""
from common import *

# [1단계] DB에서 데이터 불러오기 (q = SQL → pandas DataFrame)
# [2단계] pandas 로 가공
# [3단계] matplotlib 으로 그리고 save() 로 저장 (PNG + SVG)

def chart4():
    d = q("""SELECT t.taste_group AS g, i.name AS ing, count(DISTINCT rt.recipe_id) AS n,
                    (SELECT count(DISTINCT rt2.recipe_id) FROM omm_recipe_tastes rt2 JOIN omm_taste_words t2 USING (taste_id) WHERE t2.taste_group = t.taste_group) AS tot
             FROM omm_recipe_tastes rt JOIN omm_taste_words t USING (taste_id) JOIN omm_recipe_ingredients ri USING (recipe_id)
             JOIN omm_ingredients i ON i.ingredient_id = ri.ingredient_id AND NOT i.is_seasoning GROUP BY t.taste_group, i.name""")
    if d.empty: return empty('4_맛표현_재료.png', 4, '맛 표현별 주요 재료', '맛 표현이 든 레시피가 없음')
    d['pct'] = d.n / d.tot * 100
    cols = d.groupby('ing').n.sum().sort_values(ascending=False).head(14).index
    m = d.pivot_table(index='g', columns='ing', values='pct', fill_value=0).reindex(columns=cols, fill_value=0)
    m = m.loc[d.groupby('g').tot.first().sort_values(ascending=False).index]
    fig, ax = plt.subplots(figsize=(max(9, len(cols) * 0.85), 1.2 + len(m) * 0.7))
    im = ax.imshow(m.values, cmap='Blues', aspect='auto', vmin=0)
    ax.set_xticks(range(len(cols)), cols, rotation=40, ha='right'); ax.set_yticks(range(len(m)), [f'{g} ({int(d[d.g == g].tot.iloc[0]):,})' for g in m.index])
    ax.grid(False)
    for y in range(m.shape[0]):
        for x in range(m.shape[1]):
            v = m.values[y, x]
            if v >= 5: ax.text(x, y, f'{v:.0f}', ha='center', va='center', fontsize=11, color='white' if v > m.values.max() * 0.6 else INK)
    ax.set_title('④ 맛 표현별 주요 재료 — 그 맛 레시피 중 재료가 들어간 비율(%)')
    fig.colorbar(im, ax=ax, shrink=0.8, label='%')
    note(ax, '맛 표현 = 제목 · 소개 · 후기에서 찾은 단어 (매콤 · 얼큰 → 매운맛 …) · 괄호 = 레시피 수')
    save(fig, '4_맛표현_재료.png', 4, '맛 표현별 주요 재료', '"매콤한 거" → 어떤 재료가 들어간 메뉴인지')

if __name__ == '__main__':
    chart4()
