"""⑤ 트렌드 키워드 — YouTube Data API 로 본 최근 레시피 트렌드 키워드 (예: 로제 · 두바이)
담당: 3팀 (⑤⑥) · 이 파일만 고치면 돼요.
  - 노트북 notebooks/3팀_⑤⑥.ipynb 에서 고치고 바로 실행해 볼 수 있어요.
  - 서버는 매일 18:30 charts_v4.py 가 이 파일의 chart5() 을 불러 그림을 다시 그려요.
  - 관리자 화면 › 데이터 분석 탭의 '차트 그리기' 코드 칸에 이 파일 내용이 그대로 보여요.
"""
from common import *

# [1단계] DB에서 데이터 불러오기 (q = SQL → pandas DataFrame)
# [2단계] pandas 로 가공
# [3단계] matplotlib 으로 그리고 save() 로 저장 (PNG + SVG)

def chart5():
    d = q("""SELECT k.keyword, kt.ym, kt.yt_video_cnt AS yt, kt.yt_view_sum AS views, kt.recipe_cnt AS rc
             FROM omm_keyword_trend_monthly kt JOIN omm_trend_keywords k USING (keyword_id) WHERE kt.ym <= date_trunc('month', current_date) ORDER BY kt.ym""")
    if d.empty: return empty('5_트렌드.png', 5, '최근 레시피 트렌드 키워드', 'YouTube 수집 후 다시 실행')
    d['ym'] = pd.to_datetime(d.ym)
    top = d.groupby('keyword').views.sum().sort_values(ascending=False).head(4).index.tolist()
    color = {k: S[i] for i, k in enumerate(top)}
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
    for k in top:
        g = d[d.keyword == k]
        a1.plot(g.ym, g.views / 1e4, color=color[k], lw=2, marker='o', ms=4, label=k)
        a1.annotate(k, (g.ym.iloc[-1], g.views.iloc[-1] / 1e4), xytext=(6, 0), textcoords='offset points', color=INK, va='center')
        a2.plot(g.ym, g.rc, color=color[k], lw=2, marker='o', ms=4, label=k)
    a1.set_title('⑤ 트렌드 키워드 — YouTube 월 게시 영상 조회수 합 (만 회)'); a1.legend(loc='upper left', ncol=4)
    a2.set_title('같은 키워드가 제목에 든 만개 신규 레시피 수'); a2.set_ylabel('레시피 수')
    note(a2, '조회수 합 상위 4개 키워드 · 키워드 × 월마다 조회수 상위 50개 영상 기준 · 두 지표는 단위가 달라 따로 그림')
    g = d.groupby('keyword').views.sum().sort_values().tail(12) / 1e4
    fig2, ax = plt.subplots(figsize=(9, 0.5 + len(g) * 0.45))
    ax.barh(g.index, g.values, color=[color.get(k, MUTED) for k in g.index], height=0.6)
    for y, v in enumerate(g.values): ax.text(v, y, f'  {v:,.0f}만', va='center', color=INK2, fontsize=11)
    ax.set_title('키워드별 전체 조회수 합 (만 회)'); ax.grid(axis='y', visible=False)
    save(fig, '5_트렌드.png', 5, '트렌드 키워드 월별 흐름', 'YouTube 조회수와 만개 레시피 수를 같은 색으로 비교')
    save(fig2, '5_트렌드_순위.png', 5, '트렌드 키워드 순위', '전체 기간 조회수 합')

if __name__ == '__main__':
    chart5()
