# OMM 공유 데이터 (2026-11-22)

| 파일 | 한 줄 = | 키 | 줄 수 | 설명 |
|---|---|---|---|---|
| `data/clean/recipes_clean.csv` | 레시피 1개 | `recipe_id` | 19,171 | 만개의레시피 최근 1년 레시피. 인분 · 시간(분) · 난이도 1~5 · 조회수 · 평점 · 상황/테마 |
| `data/clean/reviews_clean.csv` | 후기 1개 | `review_id → recipe_id` | 809 | 후기 원문(깨끗하게만, 형태소 분석은 ES Nori/Kiwi에서) · 별점 · 글자 수 · 레시피 게시 후 며칠 |
| `data/clean/recipe_ingredients_clean.csv` | 레시피 × 재료 1줄 | `recipe_id + line_no` | 174,618 | 재료 표준명 · 양 · 단위 · g 환산 · 1인분 g · 양념 여부 |
| `data/clean/ingredient_dictionary.csv` | 재료 1개 | `std_name` | 4,629 | 재료 사전 (레시피 수, 양념 비율, 원래 표기 예, 평균 1인분 g) |
| `data/clean/recipe_menu.csv` | 레시피 1개 | `recipe_id → menu` | 19,171 | 레시피 → 메뉴 (메뉴 사전 기준) · 묶은 방법 · 상위 메뉴 |
| `data/clean/menu_summary.csv` | 메뉴 1개 | `menu` | 741 | 메뉴별 레시피 수 · 후기 수 · 대표 레시피 · 핵심 재료 |
| `data/price/recipe_price.csv` | 레시피 1개 | `recipe_id` | 19,171 | 주재료 재료비 (게시 당시 · 현재, 1인분) · 가격 붙은 비율. 소스 · 양념 제외 |
| `data/price/recipe_ingredient_price.csv` | 레시피 × 재료 1줄 | `recipe_id + line_no` | 167,641 | 재료별 g당 가격 · 출처(KAMIS 소매 → 참가격 → KAMIS 도매) · 재료비 |
| `data/price/ingredient_price_monthly.csv` | 재료 × 월 | `key + month` | 4,069 | 재료비 계산에 쓴 월별 g당 가격 (출처 우선순위 적용) |
| `data/price/kamis_daily.csv` | 재료 × 날짜 × 소매/도매 | `ingredient + date + cls` | 201,290 | KAMIS 일별 시세 |
| `data/price/kamis_monthly.csv` | 재료 × 월 | `ingredient + month` | 3,337 | KAMIS 월평균 · 평년 대비(%) |
| `data/price/chamgagyeok_price.csv` | 재료 × 조사일 | `ingredient + date` | 1,449 | 참가격 g당 가격 (정상가만) · 직전 조사 대비(%) |
| `data/price/chamgagyeok_change.csv` | 재료 × 조사일 | `ingredient + date` | 50 | 참가격 직전 조사 · 전월 대비 등락 |
| `data/nutrition/menu_nutrition.csv` | 메뉴 1개 | `menu` | 405 | 식약처 음식 영양성분 (100g당 · 1인분). value_kind 로 분석값 / 시판 제품 구분 |
| `data/nutrition/food_menu.csv` | 식약처 음식 1개 | `food_cd → menu` | 8,677 | 식약처 음식 → 메뉴 매칭 내역 (근거 확인용) |
| `data/nutrition/menu_nutrition_unmatched.csv` | 메뉴 1개 | `menu` | 336 | 식약처에 없어서 영양값이 빈 메뉴 · 찾아본 검색어 |
| `data/youtube/trend_videos.csv` | 영상 × 검색어 × 기간 × 회차 | `run_date + query + period + video_id` | 2,369 | 넓은 검색어(먹방 등) 쇼츠 · 조회수 · 제목 메뉴 · 제목에서 찾은 음식(foods, | 로 구분) |
| `data/youtube/trend_foods.csv` | 회차 × 음식 | `run_date + food → menu` | 34 | 요즘 뜨는 음식 · 최근 영상 수 · 증가율 |
| `dict/menu_seed.csv` | 메뉴 1개 | `menu` | 809 | 메뉴 사전 (모든 소스가 같이 씀). aliases 는 | 로 구분 |
| `dict/tables/spelling_norm.csv` | 표기 1개 | `from` | 16 | 표기 통일 (달걀 → 계란 등). 레시피 · 식약처 · 사전 모두 적용 |
| `dict/kamis_item_map.csv` | 재료 1개 | `ingredient` | 277 | 레시피 재료 ↔ KAMIS 품목 · 품종 · 등급 코드 |

## 파일 잇는 법

| 무엇 | 키 |
|---|---|
| 레시피 ↔ 후기 · 재료 · 재료비 · 메뉴 | `recipe_id` |
| 레시피 → 메뉴 | `recipe_menu.csv` 의 `menu` |
| 메뉴 ↔ 메뉴 요약 · 영양 · 유튜브 | `menu` · 유튜브 영상은 `title_menu` (모두 같은 메뉴 사전 `menu_seed.csv` 기준) |
| 재료 ↔ 재료 사전 · 재료비 | `std_name` |
| 날짜 | `published_month` · `month` 는 `YYYY-MM` |

## 주의
- 재료비는 **주재료만** (소스 · 양념 제외). `priced_share` 가 낮은 레시피는 비교에서 빼는 게 좋음
- 영양값은 **메뉴 단위** 식약처 값 (레시피마다 다르지 않음). 식약처에 없는 메뉴는 비어 있음
- 재료 파일은 한 레시피에 같은 재료가 여러 줄일 수 있음 (양념 소금 · 해감 소금). 재료별로 볼 땐 합쳐서
- 유튜브는 '먹방' 같은 넓은 검색어로 모은 쇼츠에서 제목 속 음식을 찾은 것. 조회수는 수집 시점 누적값, 같은 날 다시 돌리면 그날 회차를 덮어씀
- 가격 이상치 · 재료별 등락은 정제하지 않았음 (분석 단계에서)
- CSV 는 UTF-8 (BOM). 엑셀로 열어 다시 저장하지 말 것

## 컬럼
- `recipes_clean.csv`: `recipe_id`, `title`, `title_clean`, `image`, `description`, `published_at`, `published_date`, `published_month`, `weekday`, `servings_raw`, `servings`, `time_raw`, `time_min`, `difficulty_raw`, `difficulty`, `difficulty_level`, `views`, `rating`, `review_count`, `reviews_collected`, `n_ingredients`, `n_groups`, `has_ingredients`, `crawled_at`, `situation`, `theme`, `reviews_clean`, `stars_mean`
- `reviews_clean.csv`: `review_id`, `recipe_id`, `written_at`, `written_month`, `days_after_publish`, `stars`, `text`, `text_len`
- `recipe_ingredients_clean.csv`: `recipe_id`, `line_no`, `servings`, `group`, `is_seasoning`, `raw_name`, `std_name`, `material_id`, `raw_amount`, `qty`, `unit`, `unit_std`, `grams`, `grams_per_serving`, `status`, `check`
- `ingredient_dictionary.csv`: `std_name`, `recipes`, `seasoning_share`, `raw_examples`, `material_ids`, `avg_grams_per_serving`, `grams_ok`
- `recipe_menu.csv`: `recipe_id`, `title`, `menu`, `match_by`, `parent_menu`
- `menu_summary.csv`: `menu`, `parent_menu`, `recipes`, `reviews`, `rep_recipe_id`, `rep_title`, `core_ingredients`
- `recipe_price.csv`: `recipe_id`, `title`, `published_at`, `servings`, `time`, `difficulty`, `views`, `rating`, `review_count`, `month`, `servings_n`, `main_lines`, `main_priced`, `cost_at_publish`, `cost_now`, `priced_share`, `cost_per_serving_now`
- `recipe_ingredient_price.csv`: `recipe_id`, `line_no`, `servings`, `group`, `is_seasoning`, `raw_name`, `std_name`, `material_id`, `raw_amount`, `qty`, `unit`, `unit_std`, `grams`, `grams_per_serving`, `status`, `check`, `month`, `won_per_g`, `source`, `won_per_g_now`, `cost_at_publish`, `cost_now`, `seasoning`, `in_cost`
- `ingredient_price_monthly.csv`: `key`, `month`, `source`, `unit`, `price`, `won_per_g`
- `kamis_daily.csv`: `ingredient`, `key`, `date`, `cls`, `unit`, `avg_price`, `markets`
- `kamis_monthly.csv`: `ingredient`, `key`, `month`, `wholesale_avg`, `retail_avg`, `wholesale_normal`, `retail_normal`, `vs_normal_pct`
- `chamgagyeok_price.csv`: `ingredient`, `date`, `products`, `stores`, `won_per_g`, `prev_pct`
- `chamgagyeok_change.csv`: `ingredient`, `date`, `won_per_g`, `products`, `stores`, `prev_pct`, `mom_pct`
- `menu_nutrition.csv`: `menu`, `recipes`, `value_kind`, `foods`, `food_names`, `rows`, `serving_g`, `research_ymd`, `energy_kcal_100g`, `energy_kcal_serving`, `water_g_100g`, `water_g_serving`, `protein_g_100g`, `protein_g_serving`, `fat_g_100g`, `fat_g_serving`, `ash_g_100g`, `ash_g_serving`, `carb_g_100g`, `carb_g_serving`, `sugar_g_100g`, `sugar_g_serving`, `fiber_g_100g`, `fiber_g_serving`, `calcium_mg_100g`, `calcium_mg_serving`, `iron_mg_100g`, `iron_mg_serving`, `phosphorus_mg_100g`, `phosphorus_mg_serving`, `potassium_mg_100g`, `potassium_mg_serving`, `sodium_mg_100g`, `sodium_mg_serving`
- `food_menu.csv`: `food_cd`, `food_name`, `food_ref`, `menu`, `match_by`, `kind`, `serving_size`, `z10500`, `energy_kcal_100g`
- `menu_nutrition_unmatched.csv`: `menu`, `recipes`, `searched_as`, `status`
- `trend_videos.csv`: `run_date`, `query`, `period`, `video_id`, `title`, `channel`, `published_at`, `views`, `likes`, `comments`, `title_menu`, `foods`
- `trend_foods.csv`: `run_date`, `food`, `menu`, `status`, `recent_videos`, `recent_channels`, `before_videos_scaled`, `growth`, `recent_views`, `example_title`
- `menu_seed.csv`: `menu`, `aliases`
- `spelling_norm.csv`: `from`, `to`, `memo`
- `kamis_item_map.csv`: `ingredient`, `category_code`, `item_code`, `kind_code`, `rank_code`, `memo`
