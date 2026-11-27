# OMM API (FastAPI)

API 명세서(Python_Project.xlsx · API 명세서 시트)의 29개 경로를 모두 등록해 둔 뼈대입니다.
명세서의 API 전부와 관리자 사전 조회 · 삭제 API 를 구현했습니다 (실제 PostgreSQL 마트를 읽음).
담당자는 `raise not_implemented()` 자리를 채우면 됩니다.

## 구조

```
omm-api/
├── app/
│   ├── main.py          앱 생성 · 라우터 등록 · 에러 처리 · /api/docs
│   ├── config.py        omm-api.env 읽기
│   ├── db.py            연결 풀 · Conn (요청 끝나면 자동 commit / 에러면 rollback)
│   ├── security.py      bcrypt · JWT · CurrentUser · AdminUser
│   ├── common.py        not_implemented · not_found · 취향 태그 → SQL 조건 (tag_conditions)
│   └── routers/
│       ├── common.py       /api/health · /api/filter-tags · /api/main
│       ├── recipes.py      /api/recipes …
│       ├── menus.py        /api/menus …
│       ├── ingredients.py  /api/ingredients …
│       ├── trends.py       /api/trends … · /api/analysis/{type}
│       ├── auth.py         /api/auth … · /api/users/me
│       └── admin.py        /api/admin …
├── sql/omm_api_role.sql    API 전용 DB 계정 omm_api
├── deploy/omm-api.service  systemd
├── omm-api.env.example
└── requirements.txt
```

## 구현 현황 (35개 모두 구현)

명세서와 다르거나 명세서에 없는 부분 (프론트와 맞출 것):

| API | 내용 |
| --- | --- |
| `GET /api/main` | 토큰이 있으면 취향 반영: 가성비 레시피는 먹고 싶은 · 제외 태그 모두, 뜨는 메뉴는 제외 태그만. 응답에 `personalized` · `trendMonth` · `priceMonth` 추가 |
| `POST /api/recipes/by-ingredients` | 양념 빼고 계산. 항목마다 `haveCnt` · `totalCnt` · `missingCost`(부족한 재료비 합) 추가 |
| `GET /api/menus/{id}` | 군집 = 대표 레시피의 군집. `interest`(최근 달 관심도) · `costPerServing` 추가 |
| `GET /api/ingredients/{id}/pairings` | `?sort=count`(기본, 같이 나온 레시피 수) `|lift` · `?minCount=5`(lift 정렬 때 드문 쌍 빼기) |
| `GET /api/ingredients/{id}/substitutes` | `?limit=10` 추가. `basisName`(근거) · `vsNormalPct` 추가 |
| `GET /api/trends/menus` · `/keywords` | 응답이 `{"ym": "2026-11", "items": [...]}`. 메뉴는 `?minCnt=5` (관심도 작은 메뉴의 % 급등 빼기) |
| `GET /api/analysis/{type}` | `items` 외에 type 별 추가 칸: clusters `points`(산점도 1,500개), network `edges`, price-interest `r` · `lags`, measure `grades` · `vague`. interest = 키워드별 월별 YouTube 영상 수 vs 레시피 수 |
| `GET /api/admin/etl-runs` · `/users` | 페이지 정보 때문에 `{"total", "page", "size", "items"}` (20개씩) |
| `PUT /api/users/me` | 보낸 칸만 바뀜. 취향 태그는 보내면 통째로 교체 |
| `PATCH /api/admin/users/{id}` | 관리자 자기 계정은 400 |

## 상황 문장 메뉴 추천 ("오늘 뭐 먹지" 워크북 방식, ES 없이)

먼저 `sql/user_meals_owner.sql` (db1 postgres: 기존 식사 기록 테이블 omm_user_meals 주인 → omm, API 권한) → `sql/recommend_schema.sql` (omm: 상황 사전 3개 + 추천 기록 테이블, 여러 번 실행해도 안전).

| API | 내용 |
| --- | --- |
| `POST /api/recommend` | `{"text": "어제 회식해서 속이 안 좋아", "recentDays": 3, "excludeMenuIds": [], "limit": 6}` → 메뉴 6개 + 추천 이유 + 문장 분석 결과. 토큰이 있으면 취향 태그 · 최근 식사 반영 |
| `POST /api/meals` | "이걸로 정할래요" `{"menuId": 12, "mealType": "끼니코드", "servings": 1, "memo": ""}` → omm_user_meals (로그인, recipeId 없으면 대표 레시피) |
| `GET /api/users/me/meals?days=7` · `DELETE /api/meals/{id}` | 내 식사 기록 |
| `GET /api/admin/situations` | 상황 태그 · 규칙 · 키워드 |
| `POST · DELETE /api/admin/situations/{tagId}/keywords` | 키워드 추가 · 삭제 (30초 안에 반영) |
| `GET /api/admin/recommend-stats?days=7` | 많이 들어온 상황 · 피한 것 · 고른 메뉴 · **못 알아들은 문장** (키워드 추가 후보) |

동작
1. 문장을 절로 나눔 (~는데 · ~어서 · ~지만 · 먹고 · 싫어 · 말고 · 빼고 뒤). "먹고 싶어"는 안 나눔, "망고 · 표고"의 고에서도 안 나눔
2. 절마다: 피하는 절(싫어 · 못 먹 · 빼고 · 안 들어간 …) / 이미 먹은 절(어제 … 먹어서) / 찾는 절
3. 찾는 절 → 상황 태그 19개 (해장 · 야식 · 술안주 · 매운맛 · 국물 · 고단백 · 가성비 …), "먹고 싶은" 재료 · 메뉴
   피하는 절 → 재료(하위 재료까지: 호박 → 애호박 · 단호박, 파 → 대파 · 쪽파, 닭고기 → 닭가슴살 · 닭발) · 재료 분류(고기 · 생선) · 메뉴 이름 · 태그
4. 태그 → 메뉴 점수: 메뉴 레시피 중 태그에 맞는 비율. 태그 규칙 = 만개 상황 분류 · 후기 맛 묶음 · 요리 종류 · 재료 · 제목/소개 글 · 단백질 · 재료비
5. 빼기: 주재료(레시피 30% 이상)가 싫은 재료인 메뉴, 최근 N일 먹은 메뉴와 아주 비슷한 메뉴, 취향 "제외" 태그, 김치류. 디저트는 간식 · 달달일 때만
6. 6개 고르기: 문장에 맞은 메뉴 먼저 (종류마다 3개), 나머지는 인기순 (종류마다 2개)

- 태그별 점수는 무거운 집계라 적재 버전마다 한 번 계산해 프로세스 메모리 + Valkey 에 둠. 서버 시작 때 백그라운드로 미리 계산 (`/api/health` 의 `recommendWarmUp`)
- Elasticsearch 가 준비되면 4번에 "문장 검색 점수"를 더하는 자리만 추가하면 됨 (지금은 RULE_TEXT 정규식이 대신)

## Redis (db2 마스터 · db3 복제본 · db1~3 Sentinel)

| 용도 | 동작 |
| --- | --- |
| 응답 캐시 | 메인 · 필터 태그 · 레시피 검색/상세/냉장고 · 메뉴 3개 · 재료 4개 · 트렌드 2개 · 분석. 키에 마지막 적재 번호가 들어가서 매일 적재가 끝나면 자동으로 새로 계산 (최대 `CACHE_TTL`초). 메인은 취향 태그 조합별 |
| 로그아웃 차단 | 토큰에 `jti` 를 넣고, 로그아웃하면 만료 시각까지 Redis 에 기록 → 같은 토큰은 401 |
| 로그인 제한 | 같은 이메일 + IP 로 10분에 5번 틀리면 429 |
| 인기 집계 | 레시피 상세 조회 · 검색어(첫 페이지)를 날짜별로 셈 → `GET /api/popular/recipes`, `GET /api/popular/keywords` (`?days=1~7`) |

- 관리자: `DELETE /api/admin/cache` 로 캐시 비우기. 공통코드 · 메뉴 키워드 · 재료 별칭을 바꾸면 자동으로 비움
- Redis 가 꺼져도 API 는 그대로 동작 (캐시 없이 DB, 차단 · 제한 · 집계만 멈춤). `/api/health` 의 `redis` 가 `down`
- 설정: `omm-api.env` 의 `REDIS_SENTINELS` · `REDIS_MASTER_NAME` · `REDIS_PASSWORD` (비우면 Redis 안 씀)

## 규칙

- **SQL 값은 `%s` 로만** 넣습니다. f-string 으로 값을 이어 붙이지 않습니다 (SQL 인젝션). 정렬처럼 값이 아닌 부분은 `SORTS` 같은 허용 목록에서 고릅니다.
- **응답 JSON 은 camelCase** (명세서와 같게). SQL 에서 `AS "recipeId"` 처럼 별칭을 주거나 dict 키를 직접 씁니다.
- 날짜 월은 `common.ym_text()` 로 `"2026-11"`, 공통코드 접미사는 `common.code_suffix()` 로 `"A"`.
- 토큰이 필요하면 인자에 `user: CurrentUser`, 관리자만이면 `admin: AdminUser`.
- 없는 대상은 `raise not_found("레시피")` → 404.
- 관리자는 `omm_users` 에 역할 컬럼이 없어서 `ADMIN_EMAILS` 설정으로 정합니다.

## 개발 PC · back1 에서 실행

```bash
cd /opt/pipeline/api
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp omm-api.env.example omm-api.env && vi omm-api.env && chmod 600 omm-api.env
set -a; . ./omm-api.env; set +a
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

확인:

```bash
curl -s localhost:8000/api/health
curl -s "localhost:8000/api/recipes?q=김치&sort=rating&size=3"
curl -s localhost:8000/api/recipes/7086714
curl -s -X POST localhost:8000/api/auth/signup -H 'Content-Type: application/json' \
     -d '{"email":"test@omm.kr","password":"testtest1","nickname":"테스트"}'
curl -s -X POST localhost:8000/api/auth/login -H 'Content-Type: application/json' \
     -d '{"email":"test@omm.kr","password":"testtest1"}'
curl -s localhost:8000/api/users/me -H "Authorization: Bearer <위 accessToken>"
```

브라우저에서 `http://10.0.10.21:8000/api/docs` 를 열면 모든 API 를 바로 눌러볼 수 있습니다 (내부망 · HAProxy 경유).

## 처음 한 번: DB 계정 (db1)

```bash
# db1 에서 (sudo 가능한 계정)
sudo -u postgres psql -d omm -v pw="'원하는_비밀번호'" -f omm_api_role.sql
echo "host  omm  omm_api  10.0.10.0/24  scram-sha-256" | sudo tee -a /var/lib/pgsql/data/pg_hba.conf
sudo -u postgres psql -c "select pg_reload_conf()"
```

## 서비스로 등록 (back1 · root)

```bash
id ommapi &>/dev/null || useradd -r -s /sbin/nologin -G wheel ommapi
chown -R ommapi:wheel /opt/pipeline/api && chmod 600 /opt/pipeline/api/omm-api.env
cp /opt/pipeline/api/deploy/omm-api.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now omm-api
systemctl status omm-api --no-pager | grep Active      # active (running)
tail -20 /opt/pipeline/api/api.log
```

포트 8000 은 PC2 내부망에서만 열어 둡니다 (HAProxy 가 10.0.10.1 에서 들어옴).

```bash
# firewalld 를 쓰는 경우
firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address=10.0.10.0/24 port port=8000 protocol=tcp accept'
firewall-cmd --reload
# iptables 를 쓰는 경우
iptables -I INPUT 1 -s 10.0.10.0/24 -p tcp --dport 8000 -j ACCEPT && service iptables save
```

## 메뉴 · 재료 사전 (결정: 원본 = PostgreSQL, 삭제 지원)

- 메뉴 키워드(`omm_menus.match_keywords`)와 재료 별칭(`omm_ingredient_aliases`)은 **DB 가 원본**입니다.
  `omm_dict/*.csv` 는 DB 에 없는 새 메뉴 · 새 표기를 넣을 때만 씁니다.
- 관리자 API 로 고친 값은 **다음 적재(normalizer 배치) 때 매칭에 반영**됩니다.
- 별칭 삭제는 행을 지우지 않고 `is_active = false` 로 남깁니다 (CSV 에서 다시 살아나지 않게).

| API | 동작 |
| --- | --- |
| `GET /api/admin/menus/{id}/keywords` | 키워드 조회 |
| `PUT /api/admin/menus/{id}/keywords` | `{"keywords": [...]}` 목록 전체 교체 (빼면 삭제). 메뉴 이름은 항상 포함. 응답 `sharedWith` = 다른 메뉴와 겹치는 키워드 |
| `GET /api/admin/ingredients/{id}/aliases?includeDeleted=true` | 별칭 조회 |
| `POST /api/admin/ingredients/{id}/aliases` | `{"alias": "파(대)"}` 추가 (공백 제거 저장). 지운 별칭이면 다시 살림. 다른 재료가 쓰는 중이면 409 |
| `DELETE /api/admin/ingredients/{id}/aliases/{alias}` | 별칭 지우기 (204) |

적용 순서: `sql/dict_source_pg.sql` (db1) → normalizer 패치 (back1) → API 재시작.
