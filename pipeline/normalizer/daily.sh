#!/usr/bin/env bash
# 매일 자동 실행 (cron 17:40): KAMIS 이어받기 · 최근 2개월 갱신 → YouTube 이어받기 → 적재 · 분석 · 차트 → (처음 · 일요일) 영양성분
# 수집 하나가 실패해도 나머지는 계속하고, 적재가 실패하면 omm_etl_runs 에 FAILED 를 남김
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")"
set -a; . ./omm.env; set +a
export LC_MESSAGES=C PGCLIENTENCODING=UTF8 OMM_LOCKED=1
PY="$PWD/.venv/bin/python"
mkdir -p logs
LOG="logs/daily_$(date +%F).log"
exec 9>/opt/pipeline/normalizer/logs/.omm_pipeline.lock
if ! flock -n 9; then echo "[$(date '+%F %T')] 이전 작업이 아직 실행 중이라 건너뜀" >> "$LOG"; exit 0; fi
exec >> "$LOG" 2>&1
step() { echo; echo "===== [$(date '+%F %T')] $* ====="; }
fail() { psql -q -c "INSERT INTO omm_etl_runs (source, job, finished_at, status, message) VALUES ('SRC_$1', 'daily', now(), 'ETL_FAILED', '$2')" || true; }
CUR=$(date +%Y-%m); PREV=$(date -d "$(date +%Y-%m-01) -1 month" +%Y-%m)

if [ "${OMM_SOURCE:-own}" = "team" ] || [ "${OMM_SOURCE:-own}" = "mongo" ]; then   # 팀 데이터 모드: 수집은 팀이 하고, 여기서는 정제 · 적재 · 분석 · 차트만
  step "팀 데이터(${OMM_SOURCE}) 정제 · 적재 · 분석 · 차트"
  if ! ./run_all.sh; then echo "적재 실패"; fail TEAM 'run_all(팀 데이터) 실패 · 로그 확인'; exit 1; fi
  step "몽고 사전 · 메뉴 맞추기 (PG → 몽고) → ES 다시 넣기"   # Monstache가 변경을 못 받아서 직접 맞춤
  if timeout 10m $PY sync_mongo_dict.py --apply | tail -1; then
    timeout 10m $PY es_reload.py --apply | grep -E '반영 후|오류' || fail TEAM 'es_reload 실패'
  else echo "몽고 동기화 실패"; fail TEAM 'sync_mongo_dict 실패'; fi
  find logs -name 'daily_*.log' -mtime +30 -delete; step "끝"; exit 0
fi

step "KAMIS ${KAMIS_START:-2024-01} ~ ${CUR} (받은 달은 건너뜀 · 최근 2개월은 다시)"
DONE=data/kamis_out/done_months.txt
mkdir -p data/kamis_out
if [ ! -f data/kamis_out/kamis_items.csv ]; then                          # 처음: 품목 코드 찾기 (약 500회)
  timeout 1h $PY kamis_monthly.py --start "$CUR" --end "$CUR" --discover | tail -3 || { echo "KAMIS discover 실패"; fail KAMIS 'discover 실패'; }
fi
[ -f "$DONE" ] && sed -i -e "/^${PREV}:/d" -e "/^${CUR}:/d" "$DONE"      # 최근 2개월은 매일 다시 받음 (새 조사일 반영)
if [ -f data/kamis_out/kamis_items.csv ]; then
  timeout 3h $PY kamis_monthly.py --start "${KAMIS_START:-2024-01}" --end "$CUR" | tail -5 || { echo "KAMIS 실패 (한도면 내일 이어서)"; fail KAMIS 'kamis_monthly 중단'; }
fi

step "YouTube ${YT_START:-2024-12} ~ ${CUR} 이어받기"
YD=data/youtube/youtube_done.txt
if [ "$(date +%u)" = "1" ] && [ -f "$YD" ]; then                       # 월요일: 이번 달 · 지난달 다시 (새 영상 반영)
  sed -i -e "/|${PREV}\$/d" -e "/|${CUR}\$/d" "$YD"
fi
( cd data/youtube && timeout 2h "$PY" ../../collect_youtube.py --start "${YT_START:-2024-12}" --end "$CUR" | tail -5 ) || { echo "YouTube 실패"; fail YOUTUBE 'collect_youtube 실패'; }

step "적재 · 분석 · 차트"
if ! ./run_all.sh; then echo "적재 실패"; fail MART 'run_all 실패 · 로그 확인'; exit 1; fi

# 영양성분: 처음(파일 없음) · 크롤링으로 새 레시피가 들어온 뒤 · 일요일 → DB의 재료 이름으로 검색 후 다시 적재
if [ ! -s data/nutrition_foods.csv ] || [ data/mangae/recipe_info.csv -nt data/nutrition_foods.csv ] || [ "$(date +%u)" = "7" ]; then
  step "영양성분 (새 재료 반영)"
  if timeout 2h $PY collect_nutrition.py --by-name | tail -2; then ./run_all.sh || fail MART 'run_all(영양) 실패'
  else echo "영양성분 실패"; fail NUTR 'collect_nutrition 실패'; fi
fi

find logs -name 'daily_*.log' -mtime +30 -delete
step "끝"
