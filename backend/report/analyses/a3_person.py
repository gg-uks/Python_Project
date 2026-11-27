"""③ 사람 이름 — 제목의 사람 이름 포함 여부 × 조회수 · 별점
이 파일만 고치면 돼요.
  - 노트북 notebooks/분석_③④.ipynb 에서 고치고 바로 실행해 볼 수 있어요.
  - 서버는 매일 18:30 charts_v4.py 가 이 파일의 chart3() 을 불러 그림을 다시 그려요.
  - 관리자 화면 › 데이터 분석 탭의 '차트 그리기' 코드 칸에 이 파일 내용이 그대로 보여요.
"""
from common import *

# [1단계] DB에서 데이터 불러오기 (q = SQL → pandas DataFrame)
# [2단계] pandas 로 가공
# [3단계] matplotlib 으로 그리고 save() 로 저장 (PNG + SVG)

def chart3():
    d = q("""SELECT (rm.person_name IS NOT NULL) AS p, rm.person_name AS nm, r.view_count AS v, r.avg_rating AS r
             FROM omm_recipes r JOIN omm_recipe_metrics rm USING (recipe_id) WHERE r.view_count > 0""")
    if d.empty or d.p.nunique() < 2: return empty('3_사람이름.png', 3, '사람 이름 vs 조회수 · 별점', '사람 이름이 든 레시피가 없음')
    fig, axs = plt.subplots(1, 3, figsize=(15, 5.5), gridspec_kw={'width_ratios': [1.3, 1, 1]})
    grp = [d[~d.p].v, d[d.p].v]; lab = [f'이름 없음\n(n={len(grp[0]):,})', f'이름 있음\n(n={len(grp[1]):,})']
    bp = axs[0].boxplot(grp, tick_labels=lab, patch_artist=True, widths=0.5, showfliers=False, medianprops={'color': INK, 'lw': 2})
    for p, c in zip(bp['boxes'], [S[0], S[1]]): p.set_facecolor(c); p.set_alpha(0.5); p.set_edgecolor(c)
    for i, g in enumerate(grp, 1): axs[0].text(i + 0.3, g.median(), f'중앙 {g.median():,.0f}', va='center', fontsize=11, color=INK2)
    axs[0].set_yscale('log'); logticks(axs[0].yaxis, [100, 1000, 10000, 100000, 1000000], lambda v, p: f'{v:,.0f}'); axs[0].set_title('③ 조회수 (로그)')
    m = [d[~d.p].r.mean(), d[d.p].r.mean()]
    axs[1].bar(['이름 없음', '이름 있음'], m, color=[S[0], S[1]], width=0.5)
    for i, v in enumerate(m): axs[1].text(i, v, f'★{v:.2f}', ha='center', va='bottom', color=INK)
    axs[1].set_ylim(max(0, min(m) - 0.8), 5.2); axs[1].set_title('평균 별점'); axs[1].grid(axis='x', visible=False)
    t = d[d.p].groupby('nm').agg(n=('v', 'size'), v=('v', 'median')).sort_values('n').tail(10)
    axs[2].barh(t.index, t.n, color=S[1], height=0.6)
    for y, (n, v) in enumerate(zip(t.n, t.v)): axs[2].text(n, y, f'  {n}개 · 중앙 {v:,.0f}회', va='center', fontsize=11, color=INK2)
    axs[2].set_title('많이 나온 이름'); axs[2].grid(axis='y', visible=False)
    note(axs[0], '사람 이름 = 제목에 백종원 · 류수영 등 사전에 있는 이름이 들어간 레시피')
    save(fig, '3_사람이름.png', 3, '사람 이름 vs 조회수 · 별점', '이름 있는 레시피와 없는 레시피 비교')

if __name__ == '__main__':
    chart3()
