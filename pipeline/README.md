# OMM 데이터 파이프라인 (back1 · back2 `/opt/pipeline`)

수집 → Kafka → MongoDB(원문) → 정제 · 마트 계산 → PostgreSQL → API 순서로 매일 돕니다. 서버 두 대(back1 · back2)가 역할을 나눠 맡고, 한 대가 꺼지면 남은 쪽이 이어받습니다.

| 폴더 · 파일 | 서버 위치 | 하는 일 |
| --- | --- | --- |
| `collector/` | `/opt/pipeline/collector` | 수집기: 만개의레시피 · KAMIS · 참가격 · 식약처 영양 · YouTube 수집 → Kafka(`kafka_bus.py`) · MongoDB 적재. `daily_pipeline.sh` 가 매일 18:00 |
| `normalizer/` | `/opt/pipeline/normalizer` | 노멀라이저: MongoDB → 정제(`norm_v4.py`) → 적재(`load_v4.py`) → 마트 계산(`mart_python_v4.py`, `mart_build_v4.sql`) → ES 재적재(`es_reload.py`). `daily.sh` |
| `ha/omm_ha.py` · `ha/ha.conf` | `/opt/pipeline/ha` | 이중화: Valkey 임대로 수집기 주인 정하기, 노멀라이저 main/backup 실행, 수집기 폴더 rsync |
| `check_daily.sh` | `/opt/pipeline/check_daily.sh` | 매일 점검 → 슬랙 (수집 · 정제 · 서비스 · 데이터 수 · API) |
| `cron/` | `/etc/cron.d/omm-*` | 매일 일정 (아래) |

## 하루 일정 (`cron/`)

| 시각 | 작업 | 서버 |
| --- | --- | --- |
| 18:00 | 수집 일일 작업 (`collector/daily_pipeline.sh`) | 수집기 주인 (평소 back1) |
| 18:30 | 분석 그림 다시 그리기 (`backend/report/charts_v4.py`) | `omm-report` |
| 20:30 | 노멀라이저 main (`ha/omm_ha.py normalizer --slot main`) | 우선 서버 (평소 back2) |
| 21:30 · 23:30 | 노멀라이저 backup (오늘 아직 성공 못 했을 때만) | 살아 있는 쪽 |
| 22:00 | 매일 점검 → 슬랙 (`check_daily.sh --slack --if-owner`) | 수집기 주인 |

## 설정 (저장소에 올리지 않음)

| 파일 | 내용 | 예시 파일 |
| --- | --- | --- |
| `collector/config.ini` | 공공데이터 인증키 · YouTube API 키 · MongoDB 접속 · Kafka 주소 | `collector/config.ini.example` |
| `normalizer/omm.env` | PostgreSQL · MongoDB 접속 (`MONGO_URI`) | `normalizer/omm.env.example` |
| `/opt/pipeline/slack.env` | 슬랙 웹훅 (`SLACK_WEBHOOK_URL`) | — |

자세한 내용은 `collector/README.md`, `normalizer/README_사전관리.md`, `normalizer/docs/README_VM.md` 를 보세요.
