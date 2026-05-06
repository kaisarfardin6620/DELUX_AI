import os
from pathlib import Path
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env", override=True)

def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Required environment variable '{key}' is not set.")
    return val

def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)

DB_USER     = _require("DB_USER")
DB_PASSWORD = _require("DB_PASSWORD")
DB_HOST     = _require("DB_HOST")
DB_PORT     = _optional("DB_PORT", "5432")
DB_NAME     = _require("DB_NAME")

SECRET_KEY  = _require("SECRET_KEY")
OPENAI_API_KEY = _require("OPENAI_API_KEY")
FASTAPI_MEDIA_URL = _optional("FASTAPI_MEDIA_URL", "/media")
if not FASTAPI_MEDIA_URL.startswith("/"):
    raise RuntimeError("FASTAPI_MEDIA_URL must be a relative path like '/media'.")

REDIS_URL = _optional("REDIS_URL", "redis://redis:6379/0")

_raw_origins = _optional("CORS_ALLOWED_ORIGINS", "")
if not _raw_origins:
    raise RuntimeError("Required environment variable 'CORS_ALLOWED_ORIGINS' is not set.")

CORS_ALLOWED_ORIGINS: list[str] =[o.strip() for o in _raw_origins.split(",") if o.strip()]
if not CORS_ALLOWED_ORIGINS:
    raise RuntimeError("CORS_ALLOWED_ORIGINS must contain at least one origin.")
if "*" in CORS_ALLOWED_ORIGINS:
    raise RuntimeError("CORS_ALLOWED_ORIGINS cannot include '*' when credentials are enabled.")

WS_MAX_CONNECTIONS_PER_USER = int(_optional("WS_MAX_CONNECTIONS_PER_USER", "5"))
WS_MAX_MESSAGE_LENGTH       = int(_optional("WS_MAX_MESSAGE_LENGTH", "2000"))
WS_MAX_HISTORY_TURNS        = int(_optional("WS_MAX_HISTORY_TURNS", "20"))
WS_MAX_MESSAGES_PER_MINUTE  = int(_optional("WS_MAX_MESSAGES_PER_MINUTE", "30"))
MEDIA_MAX_UPLOAD_MB         = int(_optional("MEDIA_MAX_UPLOAD_MB", "10"))
WEB_CONCURRENCY             = int(_optional("WEB_CONCURRENCY", "2"))
GUNICORN_TIMEOUT_SECONDS    = int(_optional("GUNICORN_TIMEOUT_SECONDS", "90"))
GUNICORN_GRACEFUL_SECONDS   = int(_optional("GUNICORN_GRACEFUL_SECONDS", "30"))
GUNICORN_KEEPALIVE_SECONDS  = int(_optional("GUNICORN_KEEPALIVE_SECONDS", "5"))

DB_POOL_SIZE     = int(_optional("DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW  = int(_optional("DB_MAX_OVERFLOW", "20"))
DB_POOL_TIMEOUT  = int(_optional("DB_POOL_TIMEOUT", "30"))

OPENAI_TIMEOUT_SECONDS = int(_optional("OPENAI_TIMEOUT_SECONDS", "30"))
OPENAI_MODEL_CHAT = _optional("OPENAI_MODEL_CHAT", "gpt-4o-mini")
OPENAI_MODEL_VISION = _optional("OPENAI_MODEL_VISION", "gpt-4o")
