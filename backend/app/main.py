"""OMM API 진입점.  실행: uvicorn app.main:app --host 0.0.0.0 --port 8000
문서(Swagger): http://<서버>:8000/api/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import pool
from .routers import admin, auth, common, ingredients, insight, meals, menus, popular, recipes, report, trends
from .routers import chat                  # OMM 도우미 챗봇 (Gemini + 도구 호출) POST /api/chat · GET /api/chat/status
from .routers import recommend_text      # 상황 문장 · 비슷한 메뉴 추천 (POST /api/recommend/text, GET /api/recommend/similar)
from .routers import search_es           # 엘라스틱서치 검색 (GET /api/search/recipes · /suggest · /status)
from .routers import recommend_mongo     # (비교용) MongoDB 전문검색 추천 POST /api/recommend/mongo


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open(wait=True, timeout=10)      # DB 에 못 붙으면 여기서 바로 실패 → 로그로 원인 확인
    recommend_text.warm_up()              # 상황 추천 미리 데우기 (백그라운드, 실패해도 서비스는 계속)
    yield
    pool.close()


app = FastAPI(title="OMM API", version="0.1.0", lifespan=lifespan,
              docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")

if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # 예상 못 한 에러는 내용을 숨기고 500 (자세한 내용은 api.log 의 traceback)
    import logging
    logging.getLogger("omm-api").exception("unhandled error: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "서버 오류가 났어요"})


for r in (common, recipes, menus, insight, ingredients, trends, popular, auth, meals, chat, admin, report):
    app.include_router(r.router)
app.include_router(recommend_text.router)
app.include_router(recommend_text.admin_router)
app.include_router(search_es.router)
app.include_router(search_es.rec_router)
app.include_router(recommend_mongo.router)

# 보고서 차트 PNG · HTML (report/charts_v4.py 가 그린 파일). 폴더가 아직 없어도 API 는 뜸
app.mount("/api/report/files", StaticFiles(directory=str(report.REPORT_DIR), check_dir=False), name="report-files")
