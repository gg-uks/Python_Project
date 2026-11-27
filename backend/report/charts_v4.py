"""OMM 분석 차트 실행기 — 8가지 분석(+추가 3개)을 한 번에 그림 → REPORT_DIR (기본 /opt/pipeline/api/report)
   분석 코드는 analyses/ 폴더에 분석별로 나뉘어 있어요 (4팀이 2개씩 담당). 공통 부분은 common.py.
   실행:  set -a; . /opt/pipeline/api/omm-api.env; set +a; /opt/pipeline/api/.venv/bin/python report/charts_v4.py
   (매일 18:30 /etc/cron.d/omm-report · 관리자 화면 › 보고서 차트 › 다시 그리기)
"""
import os, sys, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

# (분석 파일, 함수) — 순서대로 그림
JOBS = [('a1_clusters', 'chart1'), ('a2_rating_cost', 'chart2'),      # 1팀
        ('a3_person', 'chart3'), ('a4_taste', 'chart4'),              # 2팀
        ('a5_trend', 'chart5'), ('a6_value', 'chart6'),               # 3팀
        ('a7_network', 'chart7'), ('a8_measure', 'chart8'),           # 4팀
        ('extra', 'chart9'), ('extra', 'chart10'), ('extra', 'chart11')]

if __name__ == '__main__':
    for mod, fn in JOBS:
        try:
            getattr(importlib.import_module(f'analyses.{mod}'), fn)()
        except Exception as ex:                 # 한 팀 코드가 틀려도 나머지는 그려지게
            print(f'  ✘ {fn} ({mod}.py): {type(ex).__name__}: {ex}')
    common.write_index()
