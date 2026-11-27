"""matplotlib 보고서 차트: 목록 · 이미지 · 다시 그리기.
그리는 일은 report/charts_v4.py 가 report/analyses/ 의 분석 파일 8개(+추가)를 불러서 하고, API 는 결과 PNG 를 보여주기만 합니다.
매일 적재 뒤 /etc/cron.d/omm-report 가 다시 그리고, 관리자는 POST /api/admin/report/refresh 로 바로 그릴 수 있습니다."""
import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from ..security import AdminUser

BASE = Path(__file__).resolve().parents[2]                 # /opt/pipeline/api
REPORT_DIR = Path(os.getenv("REPORT_DIR") or BASE / "report")
SCRIPT = BASE / "report" / "charts_v4.py"
LOCK = REPORT_DIR / ".running"
LOG = REPORT_DIR / "last_run.log"

router = APIRouter(tags=["Report"])
_proc: subprocess.Popen | None = None                     # 이 API 가 띄운 그리기 작업 (끝나면 poll 로 정리)


def _running() -> bool:
    global _proc
    if _proc is not None:
        if _proc.poll() is None:
            return True
        _proc = None                                         # 끝남 → 좀비 정리
        LOCK.unlink(missing_ok=True)
        return False
    if not LOCK.exists():                                    # cron 이 그리는 중인지
        return False
    try:
        pid = int(LOCK.read_text().strip() or 0)
        os.kill(pid, 0)                                      # 아직 살아 있는지
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        LOCK.unlink(missing_ok=True)
        return False


@router.get("/api/report", summary="보고서 차트 목록 (matplotlib PNG)")
def report_list():
    man = REPORT_DIR / "manifest.json"
    data = {"generatedAt": None, "charts": []}
    if man.exists():
        try:
            data = json.loads(man.read_text(encoding="utf-8"))
        except ValueError:
            pass
    running = _running()
    err = None
    if not running and LOG.exists() and "✘" in (log := LOG.read_text(encoding="utf-8", errors="replace")):
        err = "\n".join(l for l in log.splitlines() if "✘" in l)[-2000:]      # 실패한 차트만
    return {**data, "running": running, "error": err}


# 분석 번호 → 담당 파일 (report/analyses/). 팀원이 자기 파일을 고치면 화면 코드 칸도 바로 바뀜
SOURCES = {"chart1": "a1_clusters", "chart2": "a2_rating_cost", "chart3": "a3_person", "chart4": "a4_taste",
           "chart5": "a5_trend", "chart6": "a6_value", "chart7": "a7_network", "chart8": "a8_measure",
           "chart9": "extra", "chart10": "extra", "chart11": "extra"}


@router.get("/api/report/source", summary="분석 그림을 그린 실제 파이썬 코드 (report/analyses/ 의 담당 파일) · 노트북 화면용")
def report_source(fn: str):
    import re
    mod = SOURCES.get(fn)
    path = BASE / "report" / "analyses" / f"{mod}.py" if mod else None
    if not path or not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 함수예요")
    src = path.read_text(encoding="utf-8")
    if mod == "extra":                                       # 추가 그림은 함수 하나만
        m = re.search(rf"^def {fn}\(\):\n(?:(?:    .*|)\n)+", src, re.M)
        src = m.group(0) if m else src
    return {"fn": fn, "file": f"report/analyses/{mod}.py", "code": src.rstrip()}


@router.post("/api/admin/report/refresh", status_code=status.HTTP_202_ACCEPTED, summary="보고서 차트 다시 그리기 (관리자)")
def report_refresh(admin: AdminUser):
    global _proc
    if _running():
        return {"started": False, "message": "이미 그리는 중이에요"}
    if not SCRIPT.exists():
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "report/charts_v4.py 가 없어요")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "REPORT_DIR": str(REPORT_DIR), "MPLCONFIGDIR": str(REPORT_DIR / ".mpl")}
    log = open(LOG, "w", encoding="utf-8")
    # 백그라운드로 실행 (1~2분). 끝나면 manifest.json 이 바뀜
    p = _proc = subprocess.Popen([sys.executable, str(SCRIPT)], env=env, stdout=log, stderr=subprocess.STDOUT, cwd=str(BASE),
                         start_new_session=True)
    LOCK.write_text(str(p.pid))
    return {"started": True}
