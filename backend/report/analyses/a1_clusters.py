"""① 메뉴 군집 — 조리시간 · 1인분 재료비로 메뉴를 4유형으로 나눔 → 상황별 추천 기준
이 파일만 고치면 돼요.
  - 노트북 notebooks/분석_①②.ipynb 에서 고치고 바로 실행해 볼 수 있어요.
  - 서버는 매일 18:30 charts_v4.py 가 이 파일의 chart1() 을 불러 그림을 다시 그려요.
  - 관리자 화면 › 데이터 분석 탭의 '차트 그리기' 코드 칸에 이 파일 내용이 그대로 보여요.
"""
from common import *

GRAY = '#8a8984'   # 중앙선 · 칸 이름 (흐린 회색)
SITU = {'자취형': '혼밥 · 간단하게', '간편 고급형': '퇴근 후 · 근사하게',
        '주말 요리형': '주말 · 밑반찬', '대접형': '손님상 · 명절'}

# [1단계] DB에서 데이터 불러오기 (q = SQL → pandas DataFrame)
# [2단계] pandas 로 가공
# [3단계] matplotlib 으로 그리고 save() 로 저장 (PNG + SVG)

def chart1():
    d = q("""SELECT r.cook_time_min AS t, rm.cost_per_serving AS c, mc.name AS cl, mc.center_cook_min AS ct, mc.center_cost_won AS cc
             FROM omm_recipes r JOIN omm_recipe_metrics rm USING (recipe_id) JOIN omm_menu_clusters mc USING (cluster_id)
             WHERE rm.cost_per_serving > 0 AND r.cook_time_min > 0""")
    if d.empty: return empty('1_군집.png', 1, '조리시간 × 1인분 재료비 군집', 'mart_python_v4.py를 먼저 실행')
    names = sorted(d.cl.unique(), key=lambda n: d[d.cl == n].ct.iloc[0] * 1e6 + d[d.cl == n].cc.iloc[0])
    col = {n: S[i] for i, n in enumerate(names)}
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14, 6.2), gridspec_kw={'width_ratios': [2.3, 1]})

    # 점: 조리시간이 10 · 20 · 30분처럼 딱 떨어져 세로줄로 겹치므로 옆으로 조금 흩뜨리고 옅게
    rng = np.random.default_rng(0)
    for n in names:
        g = d[d.cl == n]
        g = g.sample(min(len(g), 2500), random_state=0)          # 유형별 최대 2,500개만 (너무 빽빽하지 않게)
        ax.scatter(g.t * np.exp(rng.normal(0, 0.09, len(g))), g.c, s=7, color=col[n], alpha=0.22,
                   linewidth=0, rasterized=True)
    ax.set_xscale('log'); ax.set_yscale('log')
    ax.set_xlim(d.t.quantile(0.005) * 0.7, d.t.quantile(0.995) * 1.4)
    ax.set_ylim(d.c.quantile(0.005) * 0.7, d.c.quantile(0.995) * 1.4)

    # 전체 중앙값 선 2개 → 네 칸
    mt, mc = d.t.median(), d.c.median()
    ax.axvline(mt, color=GRAY, lw=1, ls='--', zorder=2); ax.axhline(mc, color=GRAY, lw=1, ls='--', zorder=2)
    kw = dict(transform=ax.transAxes, color=GRAY, fontsize=10)
    ax.text(0.01, 0.98, '빠르고 비쌈', va='top', **kw); ax.text(0.99, 0.98, '오래 걸리고 비쌈', va='top', ha='right', **kw)
    ax.text(0.01, 0.02, '빠르고 쌈', **kw);              ax.text(0.99, 0.02, '오래 걸리고 쌈', ha='right', **kw)

    # 유형 중심: 큰 점 + 이름 · 숫자 이름표
    for n in names:
        g = d[d.cl == n]
        x, y = g.t.median(), g.c.median()
        ax.scatter(x, y, s=300, color=col[n], edgecolor='white', linewidth=2.5, zorder=6)
        ax.annotate(f'{n}\n{x:.0f}분 · {y:,.0f}원', (x, y), xytext=(14, 0), textcoords='offset points', va='center',
                    fontsize=11, weight='bold', color=INK, zorder=7,
                    bbox=dict(boxstyle='round,pad=0.35', fc='white', ec=col[n], lw=1.5))
    logticks(ax.xaxis, [5, 10, 15, 20, 30, 60, 90, 120, 180], lambda v, p: f'{v:.0f}분')
    logticks(ax.yaxis, [300, 500, 1000, 2000, 3000, 5000, 10000, 20000], won)
    ax.set_xlabel('조리시간'); ax.set_ylabel('1인분 재료비')
    ax.set_title('레시피는 조리시간과 재료비로 4가지 유형으로 나뉜다', pad=12)
    note(ax, f'점 하나 = 레시피 1개 (유형별 최대 2,500개) · 큰 점 = 유형별 중앙값 · '
             f'점선 = 전체 중앙값 ({mt:.0f}분 · {mc:,.0f}원) · 두 축 로그 눈금')

    # 오른쪽: 유형별 레시피 수 (많은 순) + 어울리는 상황
    cnt = d.cl.value_counts()
    ax2.barh(range(len(cnt)), cnt.values, color=[col[n] for n in cnt.index], height=0.62)
    ax2.set_yticks(range(len(cnt)), [f'{n}\n{SITU.get(n, "")}' for n in cnt.index], fontsize=10)
    for y, v in enumerate(cnt.values):
        ax2.text(v, y, f' {v:,}개 ({v / cnt.sum() * 100:.0f}%)', va='center', color=INK2, fontsize=10)
    ax2.invert_yaxis(); ax2.set_xlim(0, cnt.max() * 1.45)
    ax2.set_title('유형별 레시피 수', pad=12); ax2.grid(axis='y', visible=False); ax2.set_xticks([])
    ax2.spines['bottom'].set_visible(False)
    fig.tight_layout(w_pad=3)
    save(fig, '1_군집.png', 1, '조리시간 × 재료비 군집', '레시피를 자취형 · 대접형 등 4유형으로 나눈 결과')

if __name__ == '__main__':
    chart1()