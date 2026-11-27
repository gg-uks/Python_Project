"""⑦ 재료 네트워크 — 레시피 간 식재료 공유 네트워크 → 레시피마다 재료의 연관성
담당: 4팀 (⑦⑧) · 이 파일만 고치면 돼요.
  - 노트북 notebooks/4팀_⑦⑧.ipynb 에서 고치고 바로 실행해 볼 수 있어요.
  - 서버는 매일 18:30 charts_v4.py 가 이 파일의 chart7() 을 불러 그림을 다시 그려요.
  - 관리자 화면 › 데이터 분석 탭의 '차트 그리기' 코드 칸에 이 파일 내용이 그대로 보여요.
"""
from common import *

# [1단계] DB에서 데이터 불러오기 (q = SQL → pandas DataFrame)
# [2단계] pandas 로 가공
# [3단계] matplotlib 으로 그리고 save() 로 저장 (PNG + SVG)

def net_data(n_menu=12, n_ing=14, min_share=0.4):
    d = q("""SELECT m.menu_id, m.name AS menu, m.recipe_count AS mc, i.name AS ing, count(DISTINCT r.recipe_id) AS n
             FROM omm_menus m JOIN omm_recipes r USING (menu_id) JOIN omm_recipe_ingredients ri USING (recipe_id)
             JOIN omm_ingredients i ON i.ingredient_id = ri.ingredient_id AND NOT i.is_seasoning
             GROUP BY m.menu_id, m.name, m.recipe_count""".replace('GROUP BY m.menu_id, m.name, m.recipe_count', 'GROUP BY m.menu_id, m.name, m.recipe_count, i.name'))
    if d.empty: return None
    d['share'] = d.n / d.mc
    omm_menus = d.drop_duplicates('menu').nlargest(n_menu, 'mc').menu.tolist()
    e = d[d.menu.isin(omm_menus) & (d.share >= min_share)]
    deg = e.groupby('ing').menu.nunique()
    ings = deg[deg >= 2].sort_values(ascending=False).head(n_ing).index.tolist() or deg.sort_values(ascending=False).head(n_ing).index.tolist()
    e = e[e.ing.isin(ings)]
    omm_menus = [m for m in omm_menus if m in set(e.menu)]
    # 선이 덜 겹치게: 연결된 반대편 순서의 평균으로 여러 번 정렬
    for _ in range(8):
        pos = {m: i for i, m in enumerate(omm_menus)}
        ings.sort(key=lambda x: e[e.ing == x].menu.map(pos).mean())
        pos = {g: i for i, g in enumerate(ings)}
        omm_menus.sort(key=lambda x: e[e.menu == x].ing.map(pos).mean())
    return ings, omm_menus, e

def chart7():
    nd = net_data()
    if not nd: return empty('7_네트워크.png', 7, '레시피 간 식재료 공유 네트워크', '메뉴 · 재료 데이터 없음')
    ings, omm_menus, e = nd
    H = max(len(ings), len(omm_menus))
    yi = {g: (i + 0.5) * H / len(ings) for i, g in enumerate(ings)}; ym = {m: (i + 0.5) * H / len(omm_menus) for i, m in enumerate(omm_menus)}
    fig, ax = plt.subplots(figsize=(11, 1.4 + H * 0.95)); ax.axis('off'); ax.grid(False)
    for _, r in e.iterrows():
        ax.plot([0.12, 0.86], [yi[r.ing], ym[r.menu]], color='#9b9a95', lw=0.6 + r.share * 3, alpha=0.35 + r.share * 0.4, solid_capstyle='round', zorder=1)
    for g in ings:
        ax.scatter(0.08, yi[g], s=2200, color='#dbe9fb', edgecolor=S[0], linewidth=2, zorder=3)
        ax.text(0.08, yi[g], g, ha='center', va='center', color='#1d4f9a', weight='bold', fontsize=11, zorder=4)
    for m in omm_menus:
        ax.text(0.92, ym[m], m, ha='center', va='center', color='#0b5d1e', weight='bold', fontsize=12, zorder=4,
                bbox=dict(boxstyle='round,pad=0.6,rounding_size=0.8', fc='#e2f7e6', ec='#1a9a3c', lw=2))
    ax.set_xlim(0, 1); ax.set_ylim(H + 0.5, -0.6)
    ax.text(0.08, -0.45, '식재료', ha='center', color=INK2); ax.text(0.92, -0.45, '메뉴', ha='center', color=INK2)
    ax.set_title('⑦ 레시피 간 식재료 공유 네트워크 — 재료 ↔ 메뉴', loc='left')
    ax.text(0, -0.02, '선 = 그 메뉴 레시피의 40% 이상에 들어가는 재료 · 선이 굵을수록 비율 ↑ · 메뉴 2개 이상에 걸친 재료만 (양념 제외) · 마우스로 보려면 7_네트워크.html',
            transform=ax.transAxes, color=MUTED, fontsize=11)
    save(fig, '7_네트워크.png', 7, '재료 ↔ 메뉴 공유 네트워크', '같은 재료를 쓰는 메뉴끼리 이어짐')
    net_html(ings, omm_menus, e)
    n = q("""SELECT i.name, n.degree, n.betweenness, n.community_id FROM omm_ingredient_network_nodes n JOIN omm_ingredients i USING (ingredient_id)
             ORDER BY n.degree DESC, n.betweenness DESC LIMIT 15""")
    if not n.empty:
        fig, ax = plt.subplots(figsize=(9, 0.6 + len(n) * 0.42)); n = n[::-1]
        ax.barh(n.name, n.degree, color=S[0], height=0.6)
        for y, (dg, b) in enumerate(zip(n.degree, n.betweenness)): ax.text(dg, y, f'  {dg}개 재료와 연결 · 매개 {b:.2f}', va='center', fontsize=11, color=INK2)
        ax.set_title('만능 재료 — 함께 쓰이는 재료 수 (연결 중심성)'); ax.grid(axis='y', visible=False)
        note(ax, '매개 중심성이 높을수록 서로 다른 요리군을 잇는 "다리" 재료')
        save(fig, '7_중심성.png', 7, '만능 재료 순위', '연결 · 매개 중심성')

def net_html(ings, omm_menus, e):
    W, row = 760, 64; H = max(len(ings), len(omm_menus)) * row + 40
    yi = {g: 30 + (i + 0.5) * (H - 40) / len(ings) for i, g in enumerate(ings)}; ym = {m: 30 + (i + 0.5) * (H - 40) / len(omm_menus) for i, m in enumerate(omm_menus)}
    esc = html.escape
    lines = ''.join(f'<line x1="130" y1="{yi[r.ing]:.0f}" x2="560" y2="{ym[r.menu]:.0f}" data-i="{esc(r.ing)}" data-m="{esc(r.menu)}" '
                    f'stroke-width="{1 + r.share * 4:.1f}"><title>{esc(r.ing)} → {esc(r.menu)}: 레시피의 {r.share * 100:.0f}%</title></line>' for _, r in e.iterrows())
    nodes = ''.join(f'<g class="ing" data-i="{esc(g)}"><circle cx="90" cy="{yi[g]:.0f}" r="28"/><text x="90" y="{yi[g]:.0f}">{esc(g)}</text></g>' for g in ings)
    nodes += ''.join(f'<g class="menu" data-m="{esc(m)}"><rect x="560" y="{ym[m] - 22:.0f}" width="170" height="44" rx="12"/><text x="645" y="{ym[m]:.0f}">{esc(m)}</text></g>' for m in omm_menus)
    rows = ''.join(f'<tr><td>{esc(r.ing)}</td><td>{esc(r.menu)}</td><td>{r.share * 100:.0f}%</td></tr>' for _, r in e.sort_values(['menu', 'share'], ascending=[True, False]).iterrows())
    page = f'''<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>⑦ 재료 ↔ 메뉴 공유 네트워크</title><style>
body{{margin:0;padding:24px;background:#fcfcfb;color:#0b0b0b;font-family:"Malgun Gothic","Apple SD Gothic Neo",sans-serif}}
h1{{font-size:20px;margin:0 0 4px}} p{{color:#52514e;margin:0 0 16px;font-size:14px}}
svg line{{stroke:#9b9a95;stroke-opacity:.45;stroke-linecap:round;transition:.15s}}
svg text{{text-anchor:middle;dominant-baseline:central;font-weight:700;font-size:14px;pointer-events:none}}
.ing circle{{fill:#dbe9fb;stroke:#2a78d6;stroke-width:2}} .ing text{{fill:#1d4f9a}}
.menu rect{{fill:#e2f7e6;stroke:#1a9a3c;stroke-width:2}} .menu text{{fill:#0b5d1e}}
.ing,.menu{{cursor:pointer}} .dim{{opacity:.15}} line.on{{stroke:#2a78d6;stroke-opacity:.9}}
details{{margin-top:16px}} table{{border-collapse:collapse;font-size:13px}} td{{padding:3px 10px;border-bottom:1px solid #e6e5e0}}
</style></head><body><h1>⑦ 레시피 간 식재료 공유 네트워크</h1>
<p>왼쪽 재료나 오른쪽 메뉴에 마우스를 올리면 연결된 것만 강조돼요 · 선 굵기 = 그 메뉴 레시피 중 재료가 들어간 비율 · 선 위에 올리면 비율이 보여요</p>
<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}"><text x="90" y="12" style="font-weight:400;fill:#52514e">식재료</text>
<text x="645" y="12" style="font-weight:400;fill:#52514e">메뉴</text>{lines}{nodes}</svg>
<details><summary>표로 보기</summary><table><tr><td><b>재료</b></td><td><b>메뉴</b></td><td><b>비율</b></td></tr>{rows}</table></details>
<script>
const L=[...document.querySelectorAll('line')],G=[...document.querySelectorAll('.ing,.menu')];
function hi(key,val){{const on=new Set();L.forEach(l=>{{const h=l.dataset[key]===val;l.classList.toggle('on',h);l.classList.toggle('dim',!h);if(h){{on.add('i:'+l.dataset.i);on.add('m:'+l.dataset.m)}}}});
G.forEach(g=>g.classList.toggle('dim',!on.has(g.dataset.i!==undefined?'i:'+g.dataset.i:'m:'+g.dataset.m)))}}
function off(){{L.forEach(l=>l.classList.remove('on','dim'));G.forEach(g=>g.classList.remove('dim'))}}
G.forEach(g=>{{g.addEventListener('mouseenter',()=>g.dataset.i!==undefined?hi('i',g.dataset.i):hi('m',g.dataset.m));g.addEventListener('mouseleave',off)}});
</script></body></html>'''
    open(os.path.join(OUT, '7_네트워크.html'), 'w', encoding='utf-8').write(page); print('  ✔ 7_네트워크.html')

if __name__ == '__main__':
    chart7()
