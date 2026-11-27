# OMM 데이터 파이프라인 (만개의레시피 · KAMIS · 참가격 · 식약처 영양 · YouTube)

## 폴더

```
omm_10000recipe/
├─ config.ini            API 키 (공유 · 업로드 금지. config.ini.example 을 복사해서 만듦)
├─ paths.py              모든 스크립트가 쓰는 폴더 · 파일 위치
├─ export_team.py        팀 공유 묶음 만들기
├─ collect/              1. 수집
├─ clean/                2. 정제
├─ price/                3. 가격 (KAMIS · 참가격 · 재료비)
├─ nutrition/            4. 영양 (식약처 음식 영양성분)
├─ load/                 5. MongoDB 적재
├─ dict/                 사람이 고치는 사전 · 매핑표
│   └─ tables/           단위 · 무게 · 밀도 · 별칭
├─ share/                팀 공유 zip (git 제외)
└─ data/
    ├─ raw/              수집 원본 (손대지 않음)
    ├─ clean/            정제 결과
    ├─ price/            가격 결과
    ├─ nutrition/        영양 결과
    └─ youtube/          유튜브 결과
```

## 실행 순서 (프로젝트 폴더에서)

| 단계 | 명령 | 결과 |
|---|---|---|
| 수집 · 목록 | `python collect/collect_10000.py list --min-id 7066694` | data/raw/recipe_categories.csv |
| 수집 · 상세 | `python collect/collect_10000.py --delay 1.5 detail --workers 2` | data/raw/recipes.jsonl · reviews.csv |
| **매일 (카프카)** | `python collect/collect_10000.py --delay 2.5 daily --backfill-minutes 120` | ① 새 레시피 확인 → ② 새 레시피 상세 → ③ 남는 시간에 더 옛날 레시피 → ④ 그 레시피 분류 붙이기 (data/raw/list_top.json · backfill_progress.json) |
| 옛날 레시피 분류 | `python collect/collect_10000.py --delay 2.5 tags --max-minutes 30` | 상세 페이지엔 분류가 없어서 분류 목록을 backfill 번호까지 내려가며 recipe_categories.csv 에 추가 (data/raw/list_deep.json) |
| 과거만 따로 | `python collect/collect_10000.py --delay 2.5 backfill --max-minutes 120` | 가진 것 중 가장 옛날 번호 아래로 한 개씩. 막히면(403·429·503) 저장 후 종료 코드 2 |
| 재료 정제 | `python clean/ingredient_clean.py` | data/clean/recipe_ingredients_clean.csv · ingredient_dictionary.csv |
| 레시피 · 후기 정제 | `python clean/recipe_clean.py` | data/clean/recipes_clean.csv · reviews_clean.csv |
| 메뉴 묶기 | `python clean/menu_group.py` | data/clean/recipe_menu.csv · menu_summary.csv |
| KAMIS 코드표 | `python price/kamis_for_recipes.py codes` | data/price/kamis_codes.csv |
| KAMIS 매핑 | `python price/kamis_for_recipes.py map` | dict/kamis_item_map.csv · data/price/kamis_map_review.csv |
| KAMIS 시세 | `python price/kamis_for_recipes.py fetch` | data/price/kamis_daily.csv · kamis_monthly.csv |
| 참가격 | `python price/chamgagyeok.py load` → `map` → `price` | data/price/chamgagyeok_price.csv |
| 재료비 | `python price/kamis_for_recipes.py join` | data/price/recipe_price.csv · recipe_ingredient_price.csv |
| 영양성분 | `python nutrition/nutrition_fetch.py test 김치찌개` → `fetch` | data/nutrition/menu_nutrition.csv |
| 유튜브 (매일 1번) | `python collect/youtube_trend.py` | data/youtube/trend_videos.csv · trend_foods.csv |
| 몽고 적재 | `python load/load_mongo.py` (`--dry-run` 으로 먼저 확인) | MongoDB OMM DB 원본 컬렉션 6개 |
| 팀 공유 | `python export_team.py` | share/omm_team_data_날짜.zip |

## 주기 작업 (카프카)

| 주기 | 순서 | 명령 |
|---|---|---|
| **계속 (이것 하나로 전부)** | 만개 수집 + 매일 18시에 2~5번 자동 | `nohup python collect/collect_10000.py --delay 2.5 run --stop-date 2024-11-01 --daily-at 18:00 >> collect.log 2>&1 &` |
| 매일 | 2. 정제 | `python clean/ingredient_clean.py` → `python clean/recipe_clean.py` → `python clean/menu_group.py` |
| 매일 | 3. KAMIS (레시피 기간에 맞춰 자동) | `python price/kamis_for_recipes.py fetch --months auto` → `python price/kamis_for_recipes.py join` |
| 매일 | 4. 유튜브 (하루 1번만) | `python collect/youtube_trend.py` |
| 매일 | 5. 몽고 적재 | `python load/load_mongo.py` |
| 매월 (새 CSV 가 들어왔을 때만) | 참가격 | `data/raw/chamgagyeok_raw/` 에 새 CSV → `python price/chamgagyeok.py load` → `map` → `price` → `python price/kamis_for_recipes.py join` |
| 매월 | 영양 | `python nutrition/nutrition_fetch.py fetch --missing` |

- `--daily-at` 을 주면 2~5번(daily_pipeline.sh)을 하루 한 번 알아서 띄움 → cron 필요 없음. 매일 작업 로그는 logs/daily_날짜.log
- 1번은 한 시간마다 새 레시피 확인 → 옛날 레시피 → 반복. 막히면 30분부터 점점 길게 쉬고 알아서 다시 시작
- 2~5번은 1번이 도는 중에 돌려도 됨 (받은 데까지 읽음). 1번을 두 개 띄우면 잠금(data/raw/collect.lock) 때문에 두 번째는 바로 끝남
- 사전(dict/)은 사람이 고침. 고친 뒤 2번부터 다시 돌리면 반영

## 카프카 (수집 → 토픽 → 몽고)

수집기가 레시피 · 후기 · 유튜브 영상을 받을 때마다 토픽에 보내고, 싱크가 토픽에서 꺼내 몽고에 바로 넣음.
카프카가 수집 속도와 몽고 쓰기 속도 사이를 맞춰 줌 (몽고가 잠깐 죽어도 토픽에 남아 있다가 이어서 들어감).

| 토픽 | 키 (= 몽고 _id) | 컬렉션 | 보내는 곳 |
|---|---|---|---|
| `omm.raw.mangae.recipes` | recipe_id | OMM_mangae_recipes_raw | collect_10000.py (detail · backfill) |
| `omm.raw.mangae.reviews` | review_id | OMM_mangae_reviews_raw | collect_10000.py |
| `omm.raw.youtube` | run_date\|query\|period\|video_id | OMM_youtube_videos | youtube_trend.py (이번 회차) |

1. config.ini 에 `[kafka]` (enabled = yes, bootstrap) 와 `[mongo] password` 채우기
2. 토픽 만들기 (자동 생성이 꺼져 있으면, 카프카 서버 한 대에서)
   ```
   for t in omm.raw.mangae.recipes omm.raw.mangae.reviews omm.raw.youtube; do
     kafka-topics.sh --bootstrap-server 10.0.56.101:9092 --create --if-not-exists --topic $t --partitions 3 --replication-factor 3
   done
   ```
3. 확인: `python kafka_bus.py test`
4. 싱크 띄우기 (수집기와 따로 계속): `nohup python load/kafka_to_mongo.py >> sink.log 2>&1 &`

- 카프카가 꺼져 있으면 수집기는 경고만 찍고 파일에만 씀 (수집은 계속)
- KAMIS · 참가격 · 영양 원본은 크고 자주 안 바뀌어서 매일 load_mongo.py 배치로 넣음
- 매일 load_mongo.py 는 레시피 · 후기 · 유튜브도 파일에서 한 번 더 넣음 (카프카로 못 간 것 메우기). 같은 _id · 같은 모양이라 중복 없음

## 사람이 고치는 파일 (dict/)

| 파일 | 내용 |
|---|---|
| menu_seed.csv | 메뉴 사전 (menu, aliases: `\|` 로 구분) |
| kamis_item_map.csv | 레시피 재료명 ↔ KAMIS 품목 · 품종 · 등급 코드 |
| kamis_code_table.xlsx | KAMIS 공식 코드표 |
| youtube_queries.csv | 유튜브 검색어 · 쇼츠 여부 |
| nutrition_override.csv | 영양 검색어를 직접 지정할 메뉴 |
| tables/ingredient_alias.csv | 재료 별칭 (달걀 → 계란) |
| tables/spelling_norm.csv | 표기 통일 |
| tables/ingredient_weight.csv | 재료 1단위 g (양파 개 200) |
| tables/unit_table.csv | 단위 환산 (큰술 15ml) |
| tables/ingredient_density.csv | 밀도 (간장 1.2) |

