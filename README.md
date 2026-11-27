# Python_Project · OMM (오늘 뭐 먹지)

데이터 분석 프로젝트 — 만개의레시피 레시피 · KAMIS 시세 · 식약처 영양성분 · YouTube 트렌드를 묶어
"오늘 뭐 먹을지"를 시세와 상황에 맞춰 추천하는 웹 서비스입니다.

## 폴더

| 폴더 | 내용 |
|---|---|
| `frontend/` | 화면 (React + Vite). 메뉴 추천 · 상황 문장 검색 · 레시피 · 냉장고 털기 · 재료 시세 · 트렌드 · 먹은 기록 · 챗봇 · 관리자 데이터 분석 |
| `backend/` | API (FastAPI · PostgreSQL · Redis · Elasticsearch · Gemini 챗봇) |
| `backend/report/` | 데이터 분석 8가지 (pandas + matplotlib). `analyses/` 에 분석별 파일, `notebooks/` 에 팀별 노트북 |
| `backend/sql/` | API 계정 · 추천 · 먹은 기록 테이블 SQL |
| `docs/` | 챗봇 흐름도 (draw.io) |

## 데이터 분석 8가지 (`backend/report/analyses/`)

| 담당 | 분석 | 파일 |
|---|---|---|
| 1팀 | ① 메뉴 군집 · ② 별점 × 재료비 | `a1_clusters.py` · `a2_rating_cost.py` |
| 2팀 | ③ 사람 이름 · ④ 맛 표현 | `a3_person.py` · `a4_taste.py` |
| 3팀 | ⑤ 트렌드 키워드 · ⑥ 영양 효율 | `a5_trend.py` · `a6_value.py` |
| 4팀 | ⑦ 재료 네트워크 · ⑧ 계량 신뢰도 | `a7_network.py` · `a8_measure.py` |

공통 코드는 `report/common.py`, 한 번에 그리기는 `report/charts_v4.py` (서버에서 매일 18:30).

## 서버 구성

```
사용자 → HAProxy(192.168.0.224) ─ /api → back1 (FastAPI, /opt/pipeline/api)
                                 └ 그 외 → web1 (nginx, /usr/share/nginx/html)
back1 → PostgreSQL(db1) · Redis · Elasticsearch · Gemini API
```

## 실행

- 화면: `frontend/README.md` (`npm install` → `npm run dev` / `npm run build`)
- API: `backend/README.md` (`omm-api.env.example` 을 `omm-api.env` 로 복사해 값 채우기)

> 비밀번호 · API 키(`omm-api.env`, `.pgenv`, `.env.local`)와 수집 원본 데이터(`mock-data.json`)는 저장소에 올리지 않습니다.
> 레시피 내용과 사진은 만개의레시피 작성자의 저작물로, 수업용으로만 사용합니다.
