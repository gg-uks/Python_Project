#!/usr/bin/env bash
# 적재 → 마트 계산 → Python 분석 → 차트 (리눅스용 run_all)
#   ./run_all.sh          바뀐 것만 적재 (매일 자동 실행용)
#   ./run_all.sh --full   전부 지우고 다시 넣기 (규칙을 크게 고쳤을 때)
#   omm.env 의 OMM_SOURCE:  own = 자체 수집 · team = 팀 공유 zip(TEAM_DATA) · mongo = 팀 MongoDB 원문(MONGO_URI)을 직접 정제
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
[ -f omm.env ] || { echo "omm.env 가 없어요 (omm.env.example 참고)"; exit 1; }
set -a; . ./omm.env; set +a
export LC_MESSAGES=C PGCLIENTENCODING=UTF8
PY=./.venv/bin/python
if [ -z "${OMM_LOCKED:-}" ]; then                     # daily.sh 에서 부를 때는 이미 잠금이 있음
  exec 9>/opt/pipeline/normalizer/logs/.omm_pipeline.lock
  flock -n 9 || { echo "다른 OMM 작업이 실행 중이라 건너뜀"; exit 0; }
fi
echo "[$(date '+%F %T')] [1/4] 적재 $*"
if [ "${OMM_SOURCE:-own}" = "mongo" ]; then           # 팀 MongoDB(OMM) 원문 → mongo_extract.py 로 정제 → mongo_stage/ → 적재
  $PY mongo_extract.py --out mongo_stage
  $PY load_team.py --team-dir mongo_stage "$@"
elif [ "${OMM_SOURCE:-own}" = "team" ]; then            # 팀 공유 데이터 묶음으로 (omm.env 의 TEAM_DATA: zip 또는 푼 폴더)
  SRC="${TEAM_DATA:-team_data}"
  if [[ "$SRC" == *.zip ]]; then                       # zip이 바뀌었을 때만 team_data 폴더에 다시 풂
    if [ ! -f team_data/.from ] || [ "$SRC" -nt team_data/.from ] || [ "$(cat team_data/.from)" != "$SRC" ]; then
      rm -rf team_data && mkdir team_data && unzip -q -o "$SRC" -d team_data && echo "$SRC" > team_data/.from
    fi
    SRC=team_data
  fi
  $PY load_team.py --team-dir "$SRC" "$@"
else
  $PY load_v4.py --recipe-dir data/mangae --kamis-dir data/kamis_out --nutrition data/nutrition_foods.csv --youtube-dir data/youtube "$@"
fi
echo "[$(date '+%F %T')] [2/4] mart_build_v4.sql"
psql -v ON_ERROR_STOP=1 -q -f mart_build_v4.sql
echo "[$(date '+%F %T')] [3/4] mart_python_v4.py"
$PY mart_python_v4.py
echo "[$(date '+%F %T')] [4/4] 차트"
$PY charts_v4.py | tail -1 || echo "차트 실패 (적재 · 분석은 완료)"
echo "[$(date '+%F %T')] 끝"
