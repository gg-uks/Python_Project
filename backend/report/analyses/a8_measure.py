"""⑧ 계량 신뢰도 — "넉넉히 · 약간" 같은 모호 표기 비율로 레시피 신뢰도 분류
이 파일만 고치면 돼요.
  - 노트북 notebooks/분석_⑦⑧.ipynb 에서 고치고 바로 실행해 볼 수 있어요.
  - 서버는 매일 18:30 charts_v4.py 가 이 파일의 chart8() 을 불러 그림을 다시 그려요.
  - 관리자 화면 › 데이터 분석 탭의 '차트 그리기' 코드 칸에 이 파일 내용이 그대로 보여요.
"""
from common import *

# [1단계] DB에서 데이터 불러오기 (q = SQL → pandas DataFrame)
# [2단계] pandas 로 가공
# [3단계] matplotlib 으로 그리고 save() 로 저장 (PNG + SVG)

def chart8():
    a = q("SELECT amount_class AS c, count(*) AS n FROM omm_recipe_ingredients GROUP BY 1")
    if a.empty: return empty('8_신뢰도.png', 8, '수량 표기 신뢰도', '레시피 재료 데이터 없음')
    lab = {'AMOUNT_MEASURED': '정량 (g · T · 컵)', 'AMOUNT_COUNTED': '개수 (개 · 모 · 대)', 'AMOUNT_VAGUE': '모호 (약간 · 넉넉히)', 'AMOUNT_MISSING': '수량 없음'}
    col = {'AMOUNT_MEASURED': S[0], 'AMOUNT_COUNTED': S[2], 'AMOUNT_VAGUE': S[1], 'AMOUNT_MISSING': MUTED}
    a = a.set_index('c').reindex(list(lab)).fillna(0)
    g = q("""SELECT rm.reliability_grade AS g, count(*) AS n, avg(r.avg_rating) AS r, percentile_cont(0.5) WITHIN GROUP (ORDER BY r.view_count) AS v
             FROM omm_recipe_metrics rm JOIN omm_recipes r USING (recipe_id) WHERE rm.reliability_grade IS NOT NULL GROUP BY 1 ORDER BY 1""")
    v = q("SELECT unit AS u, count(*) AS n FROM omm_recipe_ingredients WHERE amount_class = 'AMOUNT_VAGUE' AND unit IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 10")
    fig, axs = plt.subplots(1, 4, figsize=(17, 6), gridspec_kw={'width_ratios': [1.2, 1, 1, 1]})
    w, _ = axs[0].pie(a.n, colors=[col[c] for c in a.index], startangle=90, counterclock=False,
                      wedgeprops={'width': 0.38, 'edgecolor': SURF, 'linewidth': 2})
    tot = a.n.sum()
    axs[0].legend(w, [f'{lab[c]}  {n / tot * 100:.1f}%' for c, n in zip(a.index, a.n)], loc='upper center', bbox_to_anchor=(0.5, 0.02), ncol=2, fontsize=11)
    axs[0].text(0, 0, f'재료줄\n{tot:,.0f}', ha='center', va='center', color=INK, weight='bold'); axs[0].set_title('⑧ 재료 수량 표기 방식')
    gc = {'REL_A': S[0], 'REL_B': S[2], 'REL_C': S[3], 'REL_D': S[1]}
    g['lbl'] = g.g.str.replace('REL_', '', regex=False)     # 화면에는 A · B · C · D
    axs[1].bar(g.lbl, g.n, color=[gc[x] for x in g.g], width=0.6)
    for i, n in enumerate(g.n): axs[1].text(i, n, f'{n:,}', ha='center', va='bottom', color=INK2)
    axs[1].set_title('레시피 신뢰도 등급'); axs[1].grid(axis='x', visible=False)
    axs[2].bar(g.lbl, g.r, color=[gc[x] for x in g.g], width=0.6)
    for i, r in enumerate(g.r): axs[2].text(i, r, f'★{r:.2f}', ha='center', va='bottom', color=INK)
    axs[2].set_ylim(max(0, g.r.min() - 0.8) if len(g) else 0, 5.2); axs[2].set_title('등급별 평균 별점'); axs[2].grid(axis='x', visible=False)
    vv = v[::-1]
    axs[3].barh(vv.u, vv.n, color=S[1], height=0.6)
    for y, n in enumerate(vv.n): axs[3].text(n, y, f'  {n:,}', va='center', color=INK2, fontsize=11)
    axs[3].set_title('자주 쓰는 모호한 표현'); axs[3].grid(axis='y', visible=False)
    note(axs[1], '등급 = 정량 · 개수로 적은 재료 비율 · A ≥ 90% · B ≥ 70% · C ≥ 50% · D < 50%')
    save(fig, '8_신뢰도.png', 8, '수량 표기 신뢰도', '"약간 · 넉넉히"처럼 대충 적은 레시피 비율과 별점')

if __name__ == '__main__':
    chart8()
