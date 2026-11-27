"""② 별점 × 재료비 — 별점과 예상 재료비의 상관 → 약하면 "싸도 만족도 높은 메뉴" 추천 근거
이 파일만 고치면 돼요.
  - 노트북 notebooks/분석_①②.ipynb 에서 고치고 바로 실행해 볼 수 있어요.
  - 서버는 매일 18:30 charts_v4.py 가 이 파일의 chart2() 을 불러 그림을 다시 그려요.
  - 관리자 화면 › 데이터 분석 탭의 '차트 그리기' 코드 칸에 이 파일 내용이 그대로 보여요.
"""
from common import *

# [1단계] DB에서 데이터 불러오기 (q = SQL → pandas DataFrame)
# [2단계] pandas 로 가공
# [3단계] matplotlib 으로 그리고 save() 로 저장 (PNG + SVG)

def chart2():
    sql = """SELECT r.title, r.avg_rating AS r, r.review_count AS n, rm.cost_per_serving AS c
             FROM omm_recipes r JOIN omm_recipe_metrics rm USING (recipe_id) WHERE r.review_count >= {} AND rm.cost_per_serving >= 300 AND rm.priced_ratio >= 0.6 AND r.avg_rating IS NOT NULL"""
    MINREV = 5
    d = q(sql.format(MINREV))
    if len(d) < 30: MINREV = 1; d = q(sql.format(MINREV))        # 최근 1년 레시피처럼 후기가 적으면 후기 1개 이상으로 낮춤
    if len(d) < 3: return empty('2_별점_재료비.png', 2, '별점 vs 재료비', '후기 있는 레시피가 부족')
    rr = np.corrcoef(np.log(d.c), d.r)[0, 1]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(15, 6.5), gridspec_kw={'width_ratios': [1.3, 1], 'wspace': 0.75})
    ax.scatter(d.c, d.r, s=20 + np.clip(d.n, 5, 200) * 1.2, color=S[0], alpha=0.45, edgecolor=SURF, linewidth=0.6, rasterized=True)
    b = np.polyfit(np.log(d.c), d.r, 1); xs = np.linspace(np.log(d.c).min(), np.log(d.c).max(), 50)
    ax.plot(np.exp(xs), b[0] * xs + b[1], color=INK2, lw=2, ls='--')
    ax.set_xscale('log'); logticks(ax.xaxis, [300, 500, 1000, 2000, 3000, 5000, 10000, 20000], won); ax.set_xlabel('1인분 재료비 (로그)'); ax.set_ylabel('평균 별점')
    strength = '거의 없음' if abs(rr) < 0.1 else '약함' if abs(rr) < 0.3 else '보통' if abs(rr) < 0.5 else '강함'
    ax.set_title(f'② 별점 vs 1인분 재료비 (r = {rr:.2f}, {strength})')
    note(ax, f'점 크기 = 후기 수 · 점선 = 추세선 · 후기 {MINREV}개 이상 · 가격 붙은 재료 60% 이상 · 1인분 300원 이상 ({len(d):,}개) · 상관이 약하면 "싸도 만족도 높은 메뉴"를 추천할 근거')
    cut = d.c.quantile(0.25)
    top = d[d.c <= cut].sort_values(['r', 'n'], ascending=False).head(12)[::-1]
    ax2.barh([t[:12] + ('…' if len(t) > 12 else '') for t in top.title], top.r, color=S[2], height=0.6)
    for y, (v, c) in enumerate(zip(top.r, top.c)): ax2.text(v, y, f'  ★{v:.2f} · {c:,.0f}원', va='center', fontsize=11, color=INK2)
    ax2.set_xlim(max(0, top.r.min() - 0.6) if len(top) else 0, 5.6); ax2.set_title(f'싸도 만족도 높은 레시피\n(재료비 하위 25% · {cut:,.0f}원 이하)')
    ax2.grid(axis='y', visible=False)
    save(fig, '2_별점_재료비.png', 2, '별점 vs 재료비', f'상관 r = {rr:.2f}')

if __name__ == '__main__':
    chart2()
