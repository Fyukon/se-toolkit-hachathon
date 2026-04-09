import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.api.routes_actions import router as actions_router
from app.api.routes_auth import router as auth_router
from app.api.routes_health import router as health_router
from app.api.routes_summary import router as summary_router
from app.api.routes_sync import router as sync_router
from app.config import settings
from app.db.init_db import init_db


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


app = FastAPI(title="SE Toolkit Hackathon API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def ensure_local_sqlite_schema() -> None:
    if settings.database_url.startswith("sqlite"):
        logger.info("SQLite mode detected. Ensuring local schema exists.")
        init_db()


@app.middleware("http")
async def log_requests(request: Request, call_next) -> Response:
    started_at = time.perf_counter()
    logger.info("HTTP %s %s started", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("HTTP %s %s crashed", request.method, request.url.path)
        raise

    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "HTTP %s %s completed status=%s duration_ms=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response

app.include_router(health_router)
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(sync_router, prefix="/sync", tags=["sync"])
app.include_router(summary_router, prefix="/summary", tags=["summary"])
app.include_router(actions_router, prefix="/actions", tags=["actions"])
