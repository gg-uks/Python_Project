# OMM 자동 실행 (DB1 · Rocky Linux) 설치 안내

**VM이 수집부터 처음 시작해서 매일 이어가요.** 노트북 데이터를 복사할 필요는 없어요(복사하면 더 빨리 채워져요).

| 언제 | 무엇 | 처음 며칠 | 다 채운 뒤 |
|---|---|---|---|
| 매일 01:10 | 만개 크롤링 (`crawl.sh`, 최대 6시간) | 약 3만 개(`CRAWL_PER_VALUE=20`)를 약 6일 밤에 나눠서 (노트북에서 받은 걸 옮기면 바로 끝) | 분류마다 목록 1쪽만 다시 봐서 **새 레시피만** |
| 매일 17:40 | KAMIS → YouTube → 적재 · 분석 · 차트 → 영양성분 (`daily.sh`) | KAMIS 2024-01부터 (첫날 거의 다), YouTube 24개월 (약 4일) | KAMIS 최근 2개월 갱신, YouTube 새 달 추가 |

매일 17:40에 자동으로 실행되는 것:
1. **KAMIS**: 처음이면 품목 코드 찾기 → 2024-01부터 이어받기, 지난달 · 이번 달은 매일 다시 받아요(새 조사일 반영).
2. **YouTube**: 남은 (키워드 × 월)을 이어서 받아요. 하루 약 95회까지 받고, 월요일에는 이번 달 · 지난달을 다시 받아요.
3. **적재 · 분석 · 차트**: **바뀐 것만** DB에 넣어요(재료 · 메뉴 번호 유지). 그다음 마트 재계산 → 군집 · 네트워크 → 차트예요.
4. **영양성분**: 처음이거나, 크롤링으로 새 레시피가 들어왔거나, 일요일이면 새 재료의 영양값을 받고 다시 적재해요.

- 수집 하나가 실패해도 나머지는 계속 진행하고, 실패 기록을 `omm_etl_runs` 테이블에 남겨요.
- 이전 실행이 안 끝났으면 새 실행은 건너뛰어요(잠금).
- 로그는 `logs/daily_날짜.log`에 남고, 30일이 지나면 자동으로 지워져요.
- **크롤링은 새벽에 따로 돌아요**(`crawl.sh`). 요청 사이 3~4.5초씩 쉬고, 하루 최대 6시간이에요. 수업용 · 비공개 원칙은 그대로예요.

---

## 1. 파일 옮기기 (노트북 → DB1)
노트북 PowerShell에서 `omm_vm` 폴더(이 안내가 있는 폴더)를 옮겨요.
```powershell
scp -r omm_vm 사용자명@10.0.56.101:/tmp/
```
(선택) 노트북에서 모은 데이터를 같이 옮기면 처음 며칠이 빨라져요. 안 옮기면 VM이 처음부터 받아요. 아래 명령은 `omm_load_v4` 폴더 안에서 실행해요.
```powershell
scp -r data 사용자명@10.0.56.101:/tmp/omm_data
```
그다음 DB1에서 실행해요.
```bash
sudo mkdir -p /opt/omm && sudo chown $USER: /opt/omm
cp -r /tmp/omm_vm/. /opt/omm/
cp -r /tmp/omm_data/. /opt/omm/data/   # 노트북 데이터를 옮긴 경우만
cd /opt/omm
```

## 2. 설치 (최초 1회 · 약 5분)
```bash
bash setup_rocky.sh
```
파이썬 가상환경, 패키지, 한글 글꼴, cron을 설치하고, 시간대를 Asia/Seoul로 설정해요.

## 3. 키 · 비밀번호 넣기
```bash
vi omm.env          # 값을 작은따옴표 안에 넣기 · 저장
chmod 600 omm.env   # 본인만 읽을 수 있게
```
- `DATA_GO_KEY`: 공공데이터포털 Decoding 키 (**재발급한 새 키**)
- `YOUTUBE_KEY`: YouTube API 키
- `PGPASSWORD`: omm 계정 비밀번호 (바꾼 비밀번호)

## 4. DB 준비 (최초 1회)
```bash
sudo -u postgres createdb -O omm omm_insight
set -a; . ./omm.env; set +a
psql -f omm_schema_v4.sql          # 테이블 38개 · 공통코드 63개 · 끝에 COMMIT 이 나오면 성공
```
DB가 이미 있으면: 예전 버전 테이블(이름에 omm_ 이 없거나 테이블이 38개가 아님)이면 `sudo -u postgres dropdb omm_insight` 후 위를 다시 해요. 38개 그대로면 건너뛰어요.
확인: `psql -Atc "select count(*) from pg_tables where schemaname='public'"` → 38

## 5. 첫 실행 (선택)
노트북 데이터를 옮겼다면 바로 넣어 봐요. 안 옮겼으면 건너뛰어도 돼요(오늘 17:40부터 자동으로 시작).
```bash
./run_all.sh --full
./status.sh
```

## 6. 자동 실행 등록
```bash
crontab -e
```
아래 두 줄을 넣고 저장해요(vi: `i` → 붙여 넣기 → `Esc` → `:wq`).
```
CRON_TZ=Asia/Seoul
10 1 * * * /opt/omm/crawl.sh
40 17 * * * /opt/omm/daily.sh
```
- **17:40인 이유**: YouTube 하루 할당량이 한국 시간 오후 4~5시(미국 태평양 자정)에 초기화돼요. 그 직후에 받아야 하루치를 다 써요.
- 확인: `crontab -l`

등록한 날 바로 시작하고 싶으면 직접 실행해요(크롤링은 오래 걸리니 백그라운드로).
```bash
./daily.sh; ./status.sh
nohup ./crawl.sh &            # 크롤링 바로 시작 · 로그: logs/crawl_날짜.log
```

---

## 매일 확인하는 법
```bash
/opt/omm/status.sh
```
최근 로그 20줄, DB 실행 기록(OK / FAILED), 데이터 개수가 나와요.

## 크롤링 진행 확인
```bash
tail -5 /opt/omm/logs/crawl_$(date +%F).log
ls /opt/omm/data/mangae/.full_crawl_done   # 있으면 전체 받기가 끝나고 새 레시피만 받는 중
```
더 많이 받고 싶으면 `omm.env`의 `CRAWL_PER_VALUE`를 올리고(30 ≈ 4만 개) `rm data/mangae/.full_crawl_done` 하면, 다음 밤부터 추가로 받아요.

## 규칙을 고친 뒤 (norm_v4.py 등)
메뉴 이름이나 재료 통일 규칙을 크게 바꿨다면 한 번은 전부 다시 넣어요.
```bash
./run_all.sh --full
```
이때는 재료 · 메뉴 번호가 새로 매겨져요.

## 문제가 생기면
| 증상 | 확인 |
|---|---|
| `status.sh`에 KAMIS FAILED | `logs/daily_날짜.log`의 KAMIS 부분을 봐요. "연결이 계속 안 돼서"면 VM 인터넷 문제, "API 키나 하루 한도"면 키 문제예요 |
| YouTube FAILED | 할당량 초과면 다음 날 자동으로 이어서 받아요. "API 오류"면 키를 확인해요 |
| MART FAILED | 로그의 적재 부분 오류 메시지를 확인해요. 데이터는 이전 상태 그대로예요(한 트랜잭션) |
| cron이 안 도는 것 같음 | `systemctl status crond`, `grep CRON /var/log/cron` |
| 크롤링 로그에 Playwright · 브라우저 오류 | `./.venv/bin/python -m playwright install chromium` 다시 실행, 라이브러리 오류면 메시지에 나온 패키지를 `sudo dnf install` |
| 크롤링 로그에 `접속이 막혔어요 (HTTP 403/429)` | 사이트가 막은 거예요. 며칠 쉬었다가 자동으로 다시 시도돼요. 계속되면 `CRAWL_HOURS`를 줄여요 |
| 차트 한글이 네모로 나옴 | `sudo dnf install google-noto-sans-cjk-ttc-fonts` 후 `rm -rf ~/.cache/matplotlib` |

## 파일 목록
| 파일 | 역할 |
|---|---|
| `daily.sh` | cron 17:40: KAMIS · YouTube · 적재 · 분석 · 영양성분 |
| `crawl.sh` | cron 01:10: 만개 크롤링 (처음엔 전체, 그 뒤엔 새 레시피만) |
| `run_all.sh` | 적재 → 마트 → 분석 → 차트 (`--full` = 전부 다시) |
| `status.sh` | 상태 확인 |
| `setup_rocky.sh` | 최초 설치 |
| `omm.env.example` → `omm.env` | 키 · DB 접속 정보 (chmod 600) |
| `load_v4.py`, `norm_v4.py` | 적재 · 재료 정규화 |
| `kamis_monthly.py`, `collect_youtube.py`, `collect_nutrition.py`, `crawl_10000recipe.py`, `split_recipes.py` | 수집 |
| `mart_build_v4.sql`, `mart_python_v4.py`, `queries_v4.sql`, `charts_v4.py` | 분석 · 차트 |
| `omm_schema_v4.sql` | DB 테이블 생성 |

---

## 팀 공유 데이터로 돌리기 (OMM_SOURCE=team)
팀이 정리한 묶음(`omm_team_data_YYYYMMDD.zip`)을 그대로 쓰는 방법이에요. 이 모드에서는 **크롤링 · KAMIS · YouTube · 영양성분 수집을 하지 않고**, 묶음을 적재해서 분석 · 차트만 매일 다시 만들어요.

1. zip을 VM으로 옮김: `scp omm_team_data_20261122.zip 사용자명@10.0.56.101:/opt/omm/`
2. `omm.env` 에서
   ```
   OMM_SOURCE='team'
   TEAM_DATA='/opt/omm/omm_team_data_20261122.zip'
   ```
3. 처음 한 번: `./run_all.sh --full` (이후에는 cron 17:40 이 매일 실행 · 새벽 크롤링은 자동으로 건너뜀)
4. 새 묶음을 받으면 zip을 올리고 `TEAM_DATA` 경로만 바꾸면, 다음 실행 때 자동으로 다시 풀어서 적재해요.

| 팀 데이터에서 그대로 가져오는 것 | OMM이 계산하는 것 |
|---|---|
| 레시피 · 재료 표준명 · 1인분 g · 메뉴 사전 · 레시피 → 메뉴 · 월별 g당 가격 (KAMIS 소매 → 참가격 → KAMIS 도매) · 메뉴 영양성분 · 유튜브 트렌드 영상 | 수량 표기 분류 (분석 8) · 재료 분류 · 요리 종류 · 마트 (군집 · 네트워크 · 관심도 · 대체 재료 …) · 차트 |

자체 수집으로 돌아가려면 `OMM_SOURCE='own'` 으로 바꾸고 `./run_all.sh --full`.

---

## 팀 MongoDB 원문에서 바로 정제하기 (OMM_SOURCE=mongo)
zip 없이 팀 MongoDB(`OMM` DB · 레플리카셋 `omm-rs`)의 원문 컬렉션 6개를 매일 읽어서 정제 → PostgreSQL 적재 → 분석 · 차트까지 해요. 몽고에는 **읽기만** 해요.

```
OMM_mangae_recipes_raw · OMM_mangae_reviews_raw · OMM_kamis_prices_raw · OMM_chamgagyeok_raw · OMM_nutrition_foods_raw · OMM_youtube_videos
   → mongo_extract.py (omm_dict/ 사전 + norm_v4 규칙으로 정제) → mongo_stage/ → load_team.py → PostgreSQL → 마트 · 차트
```

1. 패키지 설치 (한 번): `./.venv/bin/pip install pymongo`
2. DB1에서 몽고 접속 확인: `nc -zv 몽고주소 27017`
3. `omm.env` 에 (비밀번호는 여기에만 · `chmod 600 omm.env`)
   ```
   OMM_SOURCE='mongo'
   MONGO_URI='mongodb://아이디:비밀번호@몽고주소:27017/?replicaSet=omm-rs&authSource=admin'
   MONGO_DB='OMM'
   ```
4. 값 형태 확인: `set -a; . ./omm.env; set +a; ./.venv/bin/python mongo_extract.py --peek`
5. 팀 zip 결과와 비교 (zip이 team_data/ 에 풀려 있으면): `./.venv/bin/python mongo_extract.py --out mongo_stage --verify team_data`
6. 처음 한 번: `./run_all.sh --full` (이후 cron 17:40 이 매일 몽고에서 다시 정제)

`omm_dict/` 는 팀이 1차 정제에 쓴 기준(재료 표기 → 표준명, 단위 → g, 메뉴 사전, KAMIS 품목 매핑, 식약처 음식 → 메뉴)을 `make_dicts.py` 로 팀 zip에서 뽑아둔 사전이에요. 사전에 없는 새 재료 · 음식은 `norm_v4.py` 규칙으로 정제해요.
