# OMM 프론트 (React + Vite)

홈에서 원형 카테고리, 사진 중심 레시피 피드와 장바구니 시세를 볼 수 있어요.

## 실행
```
npm install
npm run dev        # http://localhost:5173
npm run build      # dist/ 에 배포용 파일
```

## 데이터
- 지금은 `public/mock-data.json`(우리 PostgreSQL 에서 뽑은 실제 데이터 일부)으로 동작해요.
- 백엔드가 준비되면 `.env.example` 을 `.env` 로 복사하고 `VITE_API_BASE=http://백엔드주소` 를 넣으면,
  `src/api.js` 가 구글 시트 **API 명세서** 경로(`/api/recipes`, `/api/menus/{id}` …)로 바로 요청해요.
- 예시 데이터 다시 뽑기: `python tools/export_mock.py omm public/mock-data.json` (PG 접속은 PGPASSWORD 등 환경변수)

## 화면 (경로 → API)
| 경로 | 화면 | 쓰는 API |
|---|---|---|
| `/` | 메인 (가성비 · 뜨는 메뉴 · 시세 · 인기) | GET /api/main |
| `/recipes` | 레시피 검색 (종류 · 상황 칩, 시간 · 비용 · 정렬) | GET /api/recipes, /api/filter-tags |
| `/recipes/:id` | 레시피 상세 (재료 · 재료비 · 영양 · 후기 · 원문 링크) | GET /api/recipes/{id} |
| `/fridge` | 냉장고 털기 | GET /api/ingredients, POST /api/recipes/by-ingredients |
| `/menus/:id` | 메뉴 상세 (영양 · 관심도 그래프 · 비슷한 메뉴) | GET /api/menus/{id}, /interest, /similar |
| `/ingredients/:id` | 재료 시세 그래프 · 대체 재료 · 궁합 | GET /api/ingredients/{id}/prices, /substitutes, /pairings |
| `/trends` | 뜨는 메뉴 · 유튜브 검색어 · 영상 | GET /api/trends/menus, /keywords |
| `/analysis?t=` | 분석 8가지 탭 | GET /api/analysis/{type} |
| `/login` `/signup` `/mypage` | 로그인 · 가입 · 취향 설정 · 탈퇴 | /api/auth/*, /api/users/me |
| `/admin` | 적재 현황 · 공통코드 · 회원 | /api/admin/* |

예시 데이터에서는 아무 이메일 · 비밀번호로 로그인돼요. `admin` 으로 시작하는 이메일로 로그인하면 관리자 메뉴가 보여요.

## 폴더
```
src/api.js              API 호출 (백엔드 / 예시 데이터 전환)
src/components/ui.jsx   카드 · 썸네일 · 칩 · 섹션 등 공통 UI
src/components/charts.jsx  선 그래프 · 막대 · 재료 네트워크 (라이브러리 없이 SVG)
src/pages/*.jsx         화면별 페이지
src/styles.css          전체 스타일 (색은 맨 위 :root 변수)
```
- 썸네일은 생성형 이미지로 만든 요리 종류별 예시예요. 개별 레시피의 원본 사진은 저장하지 않아요.

## 실제 백엔드(FastAPI) 연결

1. `.env.example` 을 `.env.local` 로 복사 (`VITE_API_BASE=/`, `API_TARGET=http://192.168.0.224`)
2. `npm run dev` → `/api` 요청이 vite 프록시로 HAProxy(192.168.0.224) 백엔드에 감
3. 백엔드 응답 이름(recipeId, kcalPerServing, pricePer100g …)은 `src/adapt.js` 에서 화면 이름으로 바꿈. 백엔드 필드 이름이 바뀌면 이 파일만 고치면 됨
4. `.env.local` 을 지우면 다시 예시 데이터(mock-data.json)로 동작

### 백엔드에 요청할 것 (지금은 화면에 '-' 또는 '기타'로 보임)

| 화면 | 필요한 것 | 지금 백엔드 |
|---|---|---|
| 회원가입 · 마이페이지 | `SignupReq` · `UpdateMeReq` · `GET /api/users/me` 에 `wantItems` · `excludeItems` (omm_user_ingredient_prefs 저장 · 조회) | 태그 번호만 받음 |
| 레시피 목록 | 직접 입력한 재료까지 제외 (칩 태그 제외는 프론트가 `tags` 로 넘겨서 지금도 됨) | 태그만 |
| 레시피 목록 · 카드 | 항목에 `dishType`, `reviewCount`, `pricedRatio`, `reliability`, `proteinPer1000won` / 검색 조건 `dishType`, `situation`, 정렬 `recent` | 없음 |
| 레시피 상세 | 재료 줄에 `ingredientId`, `isSeasoning` (재료 상세로 가는 링크 · 양념 구분), `dishType` | 이름만 |
| 재료 상세 | `GET /api/ingredients/{id}` (이름 · 분류 · 쓰인 레시피 수) | 404 → 화면은 '재료 #번호'로 표시 |
| 냉장고 털기 | `GET /api/ingredients` 에서 q 없이 자주 쓰는 재료 목록, 항목에 `isSeasoning` | q 필수 |
| 메뉴 상세 | `recipes` (이 메뉴 레시피 8개), cluster 의 `centerCookMin` · `centerCostWon` | 없음 → 프론트가 레시피 검색으로 대신 채움 |
| 메인 · 트렌드 · 비슷한 메뉴 | 메뉴 항목에 `recipeCount`, `kcal` / 메인에 `popularRecipes` | 없음 → 인기 레시피는 /api/popular/recipes 로 대신 |
| 트렌드 | `videos` (많이 본 영상: id · title · publishedAt · views) | 없음 |
| 필터 태그 | `situations` (상황 칩) | 없음 |
| 로그인 | 응답에 `admin` (ADMIN_EMAILS 에 있는지) | 없음 → 프론트가 관리자 API 를 한 번 불러서 판단 |
