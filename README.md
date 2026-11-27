# Python_Project · OMM (오늘 뭐 먹지)

데이터 분석 프로젝트 — 만개의레시피 레시피 · KAMIS 시세 · 식약처 영양성분 · YouTube 트렌드를 묶어
"오늘 뭐 먹을지"를 시세와 상황에 맞춰 추천하는 웹 서비스입니다.

## 폴더

| 폴더 | 내용 |
|---|---|
| `frontend/` | 화면 (React + Vite). 메뉴 추천 · 상황 문장 검색 · 레시피 · 냉장고 털기 · 재료 시세 · 트렌드 · 먹은 기록 · 챗봇 · 관리자 데이터 분석 |
| `backend/` | API (FastAPI · PostgreSQL · Valkey · Elasticsearch · Gemini 챗봇) |
| `backend/report/` | 데이터 분석 8가지 (pandas + matplotlib). `analyses/` 에 분석별 파일, `notebooks/` 에 분석별 노트북 |
| `backend/sql/` | API 계정 · 추천 · 먹은 기록 테이블 SQL |
| `pipeline/` | 데이터 파이프라인: 수집기(collector) · 노멀라이저(normalizer) · 이중화(ha) · 매일 점검 · cron |
| `docs/` | 챗봇 흐름도 (draw.io) |

## 데이터 분석 8가지 (`backend/report/analyses/`)

| 분석 | 파일 | 노트북 |
| --- | --- | --- |
| ① 메뉴 군집 · ② 별점 × 재료비 | `a1_clusters.py` · `a2_rating_cost.py` | `notebooks/분석_①②.ipynb` |
| ③ 사람 이름 · ④ 맛 표현 | `a3_person.py` · `a4_taste.py` | `notebooks/분석_③④.ipynb` |
| ⑤ 트렌드 키워드 · ⑥ 영양 효율 | `a5_trend.py` · `a6_value.py` | `notebooks/분석_⑤⑥.ipynb` |
| ⑦ 재료 네트워크 · ⑧ 계량 신뢰도 | `a7_network.py` · `a8_measure.py` | `notebooks/분석_⑦⑧.ipynb` |

공통 코드는 `report/common.py`, 한 번에 그리기는 `report/charts_v4.py` (서버에서 매일 18:30).

## 서버 구성

```
사용자 → HAProxy(192.168.0.224) ─ 화면 → web1(10.0.10.11) · web2(10.0.10.12)   nginx · React
                                 └ /api → back1(10.0.10.21) · back2(10.0.10.22)  FastAPI
back → PostgreSQL(DB1 primary · DB3 replica) · Valkey · Elasticsearch(10.0.10.102) · Gemini API
수집기(back1) → Kafka(DB1~3) → Consumer → MongoDB(omm-rs) → 정제 · 적재 → PostgreSQL
모니터링(10.0.56.201): Prometheus · Loki · Tempo · Grafana · Slack 알림
```

## DB 테이블 (PostgreSQL `omm`)

원천 데이터를 표준 재료(`omm_ingredients.ingredient_id`)와 메뉴(`omm_menus.menu_id`)로 이어 붙이는 구조입니다. 설명은 DB 테이블 주석(`COMMENT ON TABLE`)에서 가져왔습니다.

### 레시피 · 메뉴

| 테이블 | 이름 | 설명 |
| --- | --- | --- |
| `omm_recipes` | 레시피 | 만개의레시피 레시피 1건. 작성자 닉네임 · 조리 단계 · 사진 파일은 저장하지 않음 (이미지는 URL만) |
| `omm_recipe_ingredients` | 레시피 재료 | 레시피 재료 한 줄. 원문(raw)은 그대로 두고 표준 재료 · 수량 · g · 정량 분류를 붙임 |
| `omm_recipe_categories` | 레시피 분류 | 레시피 ↔ 분류 (N:M) |
| `omm_recipe_category_codes` | 레시피 분류 코드 | 만개 분류: 종류별(cat4) · 상황별(cat2) · 재료별(cat3) · 방법별(cat1) |
| `omm_recipe_tags` | 레시피 태그 | 레시피 하단 해시태그 |
| `omm_recipe_tastes` | 레시피 맛 표현 | 제목 · 소개 · 태그 · 후기에서 찾은 맛 표현 횟수 |
| `omm_reviews` | 요리 후기 | 만개 후기. 작성자 닉네임은 저장하지 않음 |
| `omm_menus` | 메뉴 | 같은 요리 레시피를 묶은 단위 (돼지고기 고추장찌개 = 레시피 312개). 추천 · 관심도 · 트렌드는 메뉴 기준 |
| `omm_fs_recipes` | 식약처 레시피 | 식약처 조리식품 레시피 DB (COOKRCP01). 몽고 OMM_recipes 와 rcp_seq 로 연결. 조리 단계 · 단계 사진은 몽고에만 저장 |
| `omm_fs_recipe_ingredients` | 식약처 레시피 재료 | 식약처 레시피의 재료 한 줄. 몽고 OMM_recipes.ingredients 와 같은 내용을 분석용으로 정리 (재료 번호는 PG가 발급) |

### 재료 · 시세 · 영양

| 테이블 | 이름 | 설명 |
| --- | --- | --- |
| `omm_ingredients` | 표준 재료 | 4개 출처를 잇는 중심 테이블. 만개 재료 · KAMIS 품목 · 영양성분 · YouTube 키워드가 모두 ingredient_id로 연결 |
| `omm_ingredient_aliases` | 재료 별칭 | 여러 표기를 표준 재료로 (송송 썬 대파 · 파 → 대파, 달걀 → 계란). 크롤링 재료명 정규화 |
| `omm_ingredient_categories` | 재료 분류 | 채소 · 육류 · 수산 · 유제품 · 양념 … |
| `omm_unit_conversions` | 단위 환산 · 정량 분류 | 수량 단위 → g, 그리고 정량 / 개수 / 모호 분류 (분석 8). ingredient_id가 NULL이면 모든 재료에 공통 |
| `omm_kamis_items` | KAMIS 품목 · 품종 | discover로 찾은 품목 109개 · 품종 180개. 표준 재료와 연결하고, 재료당 대표 품종 하나를 is_primary로 |
| `omm_kamis_prices` | KAMIS 일별 가격 | perDay API 원본. se_cd 01 소매 · 02 도매 |
| `omm_price_monthly` | 재료 월별 시세 | 대표 품종 일별 가격 → 재료 · 월 · 소매/도매 평균. 평년 대비 · 작년 대비를 미리 계산 (배지 · 산점도 · 3년 흐름) |
| `omm_nutrition_foods` | 식품 영양성분 | 식약처 FoodNtrCpntDbInfo03 (원재료성 식품). 모두 100g당 |
| `omm_menu_nutrition` | 메뉴 영양성분 | 식약처 음식 영양성분 DB를 메뉴에 맞춘 값 (팀 공유 데이터 menu_nutrition.csv). 레시피 재료로 계산한 영양값이 없을 때 대신 씀 |
| `omm_kurly_products` | 컬리 상품 | 재료별 컬리 상품 목록. 날짜별 가격 · 품절은 몽고 OMM_kurly_prices, 제외 상품은 몽고 OMM_kurly_excluded |

### 분석 마트 (8가지 분석 · 관심도)

| 테이블 | 이름 | 설명 |
| --- | --- | --- |
| `omm_recipe_metrics` | 레시피 분석값 | 레시피 1건당 1행. 재료비 · 영양 · 신뢰도 · 사람 이름 · 군집 (분석 1·2·3·6·8) |
| `omm_menu_clusters` | 메뉴 군집 | 분석 1. 조리시간 × 재료비 K-means 4개 (자취형 · 대접형 …) |
| `omm_taste_words` | 맛 표현 사전 | 분석 4. 매콤 · 칼칼 · 얼큰 → 매운맛, 고소 · 담백 … |
| `omm_ingredient_network_nodes` | 재료 네트워크 노드 | 분석 7. 중심성 · 커뮤니티 (양념 제외) |
| `omm_ingredient_network_edges` | 재료 네트워크 연결 | 같은 레시피에 함께 쓰인 재료 쌍. a < b로 한 번만 저장 |
| `omm_ingredient_substitutes` | 대체 재료 | 비싸지면 무엇으로 바꿀까. NETWORK 이웃 유사 · REVIEW 후기 "대신" 언급 · TREND 같은 요리 종류에서 관심도 반대로 움직임 |
| `omm_menu_similarities` | 비슷한 메뉴 | 재료 겹침(Jaccard)으로 구한 비슷한 메뉴 (상세 화면) |
| `omm_menu_interest_monthly` | 메뉴 월별 관심도 | 메뉴 카드 관심도 ▲% · 상세 차트 · 뜨는/지는 메뉴 |
| `omm_ingredient_interest_monthly` | 재료 월별 관심도 | 재료가 들어간 신규 레시피 + 후기 + YouTube 영상. 같은 달 작년 대비로 계절 효과 제거 |
| `omm_price_interest_corr` | 가격-관심도 시차 상관 | 평년 대비 가격 vs 0~3개월 뒤 관심도 변화의 상관계수. ingredient_id NULL = 재료 전체 |

### 트렌드 (YouTube)

| 테이블 | 이름 | 설명 |
| --- | --- | --- |
| `omm_trend_keywords` | 트렌드 키워드 | YouTube 검색어 (로제, 두바이, 어묵탕 …). 메뉴나 재료와 연결할 수 있으면 연결 |
| `omm_keyword_trend_monthly` | 키워드 월별 트렌드 | 분석 5. YouTube 영상 수 · 조회수 + 같은 키워드의 만개 레시피 수 |
| `omm_youtube_videos` | YouTube 영상 | search.list + videos.list 결과. 채널은 ID만 저장 |
| `omm_youtube_video_keywords` | 영상 ↔ 키워드 | 어떤 키워드로 찾았는지 (N:M) |

### 추천 · 상황 사전

| 테이블 | 이름 | 설명 |
| --- | --- | --- |
| `omm_filter_tags` | 취향 태그 | 취향 입력 화면의 칩 (얼큰한 국물 · 고기 · 면 요리 / 제외: 오이 · 해산물). 태그 하나 = 규칙 하나 |
| `omm_situation_tags` | 상황 태그 | 문장에서 찾은 상황 · 맛 · 요리 형태 (해장, 매운맛, 국물 …) |
| `omm_situation_targets` | 상황 태그 규칙 | 어떤 레시피가 이 태그인가 |
| `omm_situation_keywords` | 상황 키워드 사전 | 공백은 무시하고 비교 (술 마시 = 술마시). 관리자 API 로 추가 · 삭제 |
| `omm_recommend_logs` | 추천 기록 | 입력 문장, 찾은 태그, 피한 것, 보여 준 메뉴 |

### 회원 · 주문

| 테이블 | 이름 | 설명 |
| --- | --- | --- |
| `omm_users` | 회원 | 회원 기본 정보. 몽고 OMM_fridge · OMM_receipts · OMM_user_events 의 user_id 가 참조. 비밀번호는 해시만 저장 |
| `omm_user_preferences` | 회원 취향 | 취향 입력 화면에서 고른 태그 (먹고 싶은 / 제외할). 입력 기록 원본은 몽고 OMM_user_events |
| `omm_user_ingredient_prefs` | 회원 취향 재료 | 회원이 직접 입력한 먹고 싶은 / 빼고 싶은 재료. 재료 사전에 있으면 ingredient_id, 없으면 raw_text 글자로 레시피 재료명 포함 여부를 봄 |
| `omm_user_meals` | 회원 식사 기록 | 회원이 먹었다고 체크한 메뉴 · 레시피 (v4.7). 메뉴 · 레시피 중 하나는 API가 꼭 채움 (원본이 지워지면 NULL로 남고 기록은 유지). 마이페이지 먹은 기록 · 주간 영양/재료비 요약 · 최근 먹은 메뉴 추천 제외에 씀 |
| `omm_orders` | 주문 | 장보기 주문 (OMM 구매). 몽고 OMM_fridge.items.order_id · OMM_user_events.order_id 가 참조 |
| `omm_order_items` | 주문 상품 | 주문에 담긴 컬리 상품. 가격은 주문 시점 값으로 저장 |

### 운영

| 테이블 | 이름 | 설명 |
| --- | --- | --- |
| `omm_common_codes` | 공통코드 | 상태 · 종류 값을 한곳에서 관리 (소매/도매, 정량/모호, 난이도, 신뢰도 …). 다른 테이블은 code_id 로 참조하고 화면 표시 이름 · 순서는 여기서 읽음 |
| `omm_etl_runs` | 수집 · 계산 기록 | 크롤링 · API 수집 · 마트 계산 실행 기록 (KAMIS 일 10,000건 · YouTube 일 10,000 units 관리) |

MongoDB(`omm-rs`)에는 수집 원문(`OMM_recipes` 조리 단계 · 사진, `OMM_kurly_prices`, `OMM_fridge`, `OMM_receipts`, `OMM_user_events`)을 두고, PostgreSQL에는 분석 · 서비스용으로 정리한 값만 둡니다. 추천 · 먹은 기록 테이블을 만드는 SQL은 `backend/sql/` 에 있습니다.

## 실행

- 화면: `frontend/README.md` (`npm install` → `npm run dev` / `npm run build`)
- API: `backend/README.md` (`omm-api.env.example` 을 `omm-api.env` 로 복사해 값 채우기)

> 비밀번호 · API 키(`omm-api.env`, `.pgenv`, `.env.local`)와 수집 원본 데이터(`mock-data.json`)는 저장소에 올리지 않습니다.
> 레시피 내용과 사진은 만개의레시피 작성자의 저작물로, 수업용으로만 사용합니다.
