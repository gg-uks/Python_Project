"""공통 코드 (4명이 같이 쓰는 부분) — DB 접속 q() · 색 · 글꼴 · 그림 저장 save()
분석 파일(analyses/a1_~a8_)은 맨 위에서  from common import *  로 이걸 불러 써요.
여기를 고치면 8개 분석 모두에 영향이 가니, 바꿀 때는 팀에 먼저 알려 주세요.
"""
import os, sys, math, html, json
import numpy as np, pandas as pd, psycopg
from psycopg.types.numeric import FloatLoader
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

OUT = os.getenv('REPORT_DIR') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'charts')   # 서버: /opt/pipeline/api/report · 노트북: notebooks/_out
os.makedirs(OUT, exist_ok=True)

# ── 색 (검증된 기본 팔레트) · 글꼴 ──
S = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']
INK, INK2, MUTED, GRID, SURF = '#0b0b0b', '#52514e', '#8a8984', '#e6e5e0', '#fcfcfb'
for f in ('Malgun Gothic', 'AppleGothic', 'NanumGothic', 'Noto Sans CJK KR', 'Noto Sans KR'):
    if any(f == x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams['font.family'] = f; break
plt.rcParams.update({'axes.unicode_minus': False, 'figure.facecolor': SURF, 'axes.facecolor': SURF, 'axes.edgecolor': GRID,
                     'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2, 'axes.grid': True, 'grid.color': GRID,
                     'grid.linewidth': 0.8, 'axes.axisbelow': True, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.titlesize': 14, 'axes.titleweight': 'bold', 'axes.titlecolor': INK, 'axes.titlelocation': 'left',
                     'font.size': 13, 'legend.frameon': False, 'savefig.dpi': 200, 'savefig.bbox': 'tight',
                     'axes.titlesize': 16, 'axes.labelsize': 13, 'xtick.labelsize': 12, 'ytick.labelsize': 12, 'legend.fontsize': 12,
                     'svg.fonttype': 'path'})   # SVG 글자를 도형으로 저장 → 어느 컴퓨터에서나 선명 · 글꼴 걱정 없음

conn = None
def connect():
    global conn
    if conn is None or conn.closed:
        conn = psycopg.connect(host=os.getenv('PGHOST', 'localhost'), port=os.getenv('PGPORT', '5432'), dbname=os.getenv('PGDATABASE', 'omm'),
                               user=os.getenv('PGUSER', 'omm_api'), password=os.getenv('PGPASSWORD'), autocommit=True)
        conn.adapters.register_loader('numeric', FloatLoader)   # NUMERIC → float (pandas 계산용)
    return conn

QUERIES = []   # 노트북에서 "이 분석이 불러온 데이터"를 표로 보려고 기록 (sql, DataFrame)
def q(sql):
    cur = connect().cursor(); cur.execute(sql)
    df = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
    QUERIES.append((sql, df))
    return df

def queries():
    """마지막으로 실행한 분석이 DB에서 불러온 DataFrame 목록을 돌려주고 기록을 비움 (노트북용)"""
    out = list(QUERIES); QUERIES.clear(); return out

SHOW = False   # 노트북에서 True 로 두면 save() 할 때 그림을 셀 아래에 바로 보여 줌

made = []   # (파일, 분석 번호, 제목, 설명)
def save(fig, name, no, title, note):
    # 화면용 SVG(벡터 · 확대해도 선명) + 내려받기용 PNG(200dpi)
    fig.savefig(os.path.join(OUT, name)); fig.savefig(os.path.join(OUT, name[:-4] + '.svg'))
    if SHOW:
        from IPython.display import display; display(fig)
    plt.close(fig); made.append((name, no, title, note)); print(f'  ✔ {name} (+svg)')

def empty(name, no, title, why):
    fig, ax = plt.subplots(figsize=(8, 3)); ax.axis('off')
    ax.text(0.5, 0.55, title, ha='center', fontsize=14, weight='bold', color=INK)
    ax.text(0.5, 0.35, f'데이터가 아직 없어요 · {why}', ha='center', color=MUTED)
    save(fig, name, no, title, why)

def note(ax, text):
    ax.text(0, -0.16, text, transform=ax.transAxes, color=MUTED, fontsize=11, va='top')

won = lambda v, p=None: f'{v:,.0f}원'
from matplotlib.ticker import FixedLocator, NullFormatter, FuncFormatter
def logticks(axis, ticks, fmt):
    lo, hi = axis.get_view_interval()                       # 데이터 범위 안의 1 · 2 · 5 눈금만
    ticks = [m * 10 ** k for k in range(-1, 8) for m in (1, 2, 5) if lo <= m * 10 ** k <= hi]
    if len(ticks) > 7: ticks = [t for t in ticks if str(int(t))[0] in '15'] if len(ticks) <= 14 else [t for t in ticks if str(int(t))[0] == '1']
    axis.set_major_locator(FixedLocator(ticks)); axis.set_major_formatter(FuncFormatter(fmt)); axis.set_minor_formatter(NullFormatter())

def write_index():
    """그린 그림 목록 → index.html · manifest.json (관리자 화면 › 보고서 차트가 읽음)"""
    cards = ''.join(f'<section><h2>{no}. {html.escape(t)}</h2><p>{html.escape(n)}</p><img src="{f}" alt="{html.escape(t)}">'
                    + ('<p><a href="7_네트워크.html">마우스로 보는 네트워크 열기 →</a></p>' if f == '7_네트워크.png' else '') + '</section>'
                    for f, no, t, n in made)
    open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(
        f'''<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>OMM 분석 차트</title><style>
body{{margin:0;padding:32px;background:#f5f4ef;font-family:"Malgun Gothic","Apple SD Gothic Neo",sans-serif;color:#0b0b0b}}
section{{background:#fcfcfb;border:1px solid #e6e5e0;border-radius:12px;padding:20px;margin:0 0 24px;max-width:1300px}}
h1{{margin:0 0 20px}} h2{{margin:0 0 4px;font-size:18px}} p{{margin:0 0 12px;color:#52514e}} img{{max-width:100%}}</style></head>
<body><h1>OMM 분석 차트 (분석 1~8)</h1>{cards}</body></html>''')
    print(f'\n차트 {len(made)}개 → {os.path.join(OUT, "index.html")} 을 브라우저로 여세요')
    # API(/api/report) 가 읽는 목록
    import datetime
    json.dump({'generatedAt': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
               'charts': [{'file': f, 'svg': f[:-4] + '.svg', 'no': no, 'title': t, 'note': n} for f, no, t, n in made]},
              open(os.path.join(OUT, 'manifest.json'), 'w', encoding='utf-8'), ensure_ascii=False)
