#!/usr/bin/env bash
# OMM 매일 작업 (만개 수집은 run 으로 따로 계속 돌고 있다고 가정)
# 순서: 정제 → KAMIS 시세 · 재료비 → 유튜브 → (매월) 영양 → 몽고 적재
# 등록 예 (매일 오후 6시: 유튜브 한도가 오후 5시에 초기화된 뒤):
#   crontab -e
#   0 18 * * * /home/adminb/omm_10000recipe/daily_pipeline.sh
# 이 파일은 omm_10000recipe 폴더 안에 두고, 처음 한 번 chmod +x daily_pipeline.sh

cd "$(dirname "$0")" || exit 1
PY=${PY:-python3}
mkdir -p logs
LOG="logs/daily_$(date +%F).log"
exec >> "$LOG" 2>&1

step() {                       # 한 단계가 실패해도 다음 단계는 계속
  echo "===== $(date '+%F %T') $* ====="
  "$PY" "$@" || echo "!!!!! 실패: $* (종료 코드 $?)"
}

# 1. 정제: 하지 않음 (2026-11-25부터 collect는 수집만, 정제는 normalizer)
# step clean/ingredient_clean.py   # 2026-11-25: 정제는 normalizer(RDB)에서 함, collector 정제는 안 돌림(clean/의 ingredient_clean·menu_group·changes는 KAMIS·유튜브·영양이 import)
# step clean/recipe_clean.py   # 2026-11-25: 정제는 normalizer(RDB)에서 함, collector 정제는 안 돌림(clean/의 ingredient_clean·menu_group·changes는 KAMIS·유튜브·영양이 import)
# step clean/menu_group.py   # 2026-11-25: 정제는 normalizer(RDB)에서 함, collector 정제는 안 돌림(clean/의 ingredient_clean·menu_group·changes는 KAMIS·유튜브·영양이 import)

# 2. KAMIS: 레시피 가장 옛날 달부터 자동 → 재료비
step price/kamis_for_recipes.py fetch --months auto --normal-years 5   # 2026-11-25: 평년(직전 5년 같은 달)용
# step price/kamis_for_recipes.py join   # 2026-11-25: 재료비는 normalizer(PG)에서 계산

# 3. 유튜브 (하루 1번만. 같은 날 다시 돌리면 그날 회차를 덮어씀)
step collect/youtube_trend.py

# 4. 영양: 매월 1일에만 (새 메뉴만 찾음)
if [ "$(date +%d)" = "01" ]; then
  step nutrition/nutrition_fetch.py fetch --missing
fi

# 5. 몽고 원본 적재 (upsert 라 매일 돌려도 중복 없음)
step load/load_mongo.py kamis nutrition chamgagyeok categories   # 2026-11-25: 레시피·후기·유튜브는 omm-sink(카프카)가 넣음 → 매일 전부 다시 쓰지 않음(ES 재동기화 부하)

echo "===== $(date '+%F %T') 끝 ====="
d=${LOG#logs/daily_}; echo "${d%.log}" > data/raw/daily_done.txt   # 끝까지 돎 → 수집기가 그날 다시 안 돌림 (시작한 날짜로 적음 · 도중에 끊기면 안 써져서 다시 돎)
