from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import config
from app.media_api.router import router as media_router
from app.chat.router import router as chat_router
from app.store.router import router as store_router
from app.core.database import get_db
from app.core.limiter import redis_client
from app.core.logger import logger
from app.media_api.services import MEDIA_ROOT


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Chatbot service starting up", extra={"env": "production"})
    keys = await redis_client.keys("ws_conn:*")
    if keys:
        await redis_client.delete(*keys)
    yield
    await redis_client.aclose()
    logger.info("Chatbot service shutting down")


app = FastAPI(
    title="Dealnux Chatbot API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.mount(config.FASTAPI_MEDIA_URL, StaticFiles(directory=str(MEDIA_ROOT)), name="media")
app.include_router(chat_router)
app.include_router(media_router)
app.include_router(store_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", extra={"path": request.url.path, "error": str(exc)})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as exc:
        logger.error("Health check DB failure", extra={"error": str(exc)})
        raise HTTPException(status_code=503, detail="Database unavailable")
