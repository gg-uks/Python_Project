#!/usr/bin/env bash
# 자동 실행 상태 확인: 최근 로그 끝부분 + DB 실행 기록 + 데이터 개수
cd "$(dirname "$(readlink -f "$0")")"
set -a; . ./omm.env; set +a
L=$(ls -t logs/daily_*.log 2>/dev/null | head -1)
echo "── 최근 로그: ${L:-없음}"; [ -n "$L" ] && tail -20 "$L"
echo; echo "── DB 실행 기록 (최근 10개)"
psql -c "SELECT run_id, source, job, status, finished_at::timestamp(0), left(message, 70) AS message FROM omm_etl_runs ORDER BY run_id DESC LIMIT 10"
psql -c "SELECT (SELECT count(*) FROM omm_recipes) 레시피, (SELECT count(*) FROM omm_menus) 메뉴, (SELECT count(*) FROM omm_price_monthly) 월별시세,
                (SELECT to_char(max(ym), 'YYYY-MM') FROM omm_price_monthly) 최근시세월, (SELECT count(*) FROM omm_nutrition_foods) + (SELECT count(*) FROM omm_menu_nutrition) 영양,
                (SELECT count(*) FROM omm_youtube_videos) 영상, (SELECT count(*) FROM omm_recipe_metrics) 분석레시피"
