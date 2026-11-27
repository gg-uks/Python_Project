"""① 메뉴 군집 — 조리시간 · 1인분 재료비로 메뉴를 4유형으로 나눔 → 상황별 추천 기준
담당: 1팀 (①②) · 이 파일만 고치면 돼요.
  - 노트북 notebooks/1팀_①②.ipynb 에서 고치고 바로 실행해 볼 수 있어요.
  - 서버는 매일 18:30 charts_v4.py 가 이 파일의 chart1() 을 불러 그림을 다시 그려요.
  - 관리자 화면 › 데이터 분석 탭의 '차트 그리기' 코드 칸에 이 파일 내용이 그대로 보여요.
"""
from common import *

# [1단계] DB에서 데이터 불러오기 (q = SQL → pandas DataFrame)
# [2단계] pandas 로 가공
# [3단계] matplotlib 으로 그리고 save() 로 저장 (PNG + SVG)

def chart1():
    d = q("""SELECT r.cook_time_min AS t, rm.cost_per_serving AS c, mc.name AS cl, mc.center_cook_min AS ct, mc.center_cost_won AS cc
             FROM omm_recipes r JOIN omm_recipe_metrics rm USING (recipe_id) JOIN omm_menu_clusters mc USING (cluster_id)
             WHERE rm.cost_per_serving > 0 AND r.cook_time_min > 0""")
    if d.empty: return empty('1_군집.png', 1, '조리시간 × 1인분 재료비 군집', 'mart_python_v4.py를 먼저 실행')
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14, 6), gridspec_kw={'width_ratios': [2.2, 1]})
    names = sorted(d.cl.unique(), key=lambda n: d[d.cl == n].ct.iloc[0] * 1e6 + d[d.cl == n].cc.iloc[0])
    rng = np.random.default_rng(0)
    for i, n in enumerate(names):
        g = d[d.cl == n]
        ax.scatter(g.t * np.exp(rng.normal(0, 0.06, len(g))), g.c, s=26, color=S[i], alpha=0.55, edgecolor=SURF, linewidth=0.6,
                   marker='ospD'[i % 4], label=f'{n} ({len(g):,})', rasterized=True)
        ax.scatter(g.ct.iloc[0], g.cc.iloc[0], s=260, marker='X', color=S[i], edgecolor=INK, linewidth=1.2, zorder=5)
        ax.annotate(n, (g.ct.iloc[0], g.cc.iloc[0]), xytext=(10, 8), textcoords='offset points', weight='bold', color=INK, fontsize=12)
    ax.set_xscale('log'); ax.set_yscale('log')
    logticks(ax.xaxis, [5, 10, 15, 20, 30, 60, 90, 120, 180], lambda v, p: f'{v:.0f}분')
    logticks(ax.yaxis, [300, 500, 1000, 2000, 3000, 5000, 10000, 20000], won); ax.set_xlabel('조리시간 (로그)'); ax.set_ylabel('1인분 재료비 (로그)')
    ax.set_title('① 조리시간 × 1인분 재료비 — 메뉴 4유형'); ax.legend(loc='upper left', fontsize=12)
    note(ax, '점 = 레시피 · X = 군집 중심 · K-means(로그 스케일 표준화) · 가격을 60% 이상 찾은 레시피만')
    cnt = d.cl.value_counts().reindex(names)
    ax2.barh(cnt.index, cnt.values, color=[S[i] for i in range(len(names))], height=0.6)
    for y, v in enumerate(cnt.values): ax2.text(v, y, f'  {v:,}', va='center', color=INK2)
    ax2.invert_yaxis(); ax2.set_title('유형별 레시피 수'); ax2.grid(axis='y', visible=False)
    save(fig, '1_군집.png', 1, '조리시간 × 재료비 군집', '메뉴를 자취형 · 대접형 등 4유형으로 나눈 결과')

if __name__ == '__main__':
    chart1()
