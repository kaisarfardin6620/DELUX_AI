import os
from dotenv import load_dotenv

load_dotenv(override=True)

def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Required environment variable '{key}' is not set.")
    return val

def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)

# ── Database (shared with Django — must match exactly) ──────────────────────
DB_USER     = _require("DB_USER")
DB_PASSWORD = _require("DB_PASSWORD")
DB_HOST     = _require("DB_HOST")
DB_PORT     = _optional("DB_PORT", "5432")
DB_NAME     = _require("DB_NAME")

# ── Auth (must match Django's SECRET_KEY exactly) ───────────────────────────
SECRET_KEY  = _require("SECRET_KEY")

# ── OpenAI ───────────────────────────────────────────────────────────────────
OPENAI_API_KEY = _require("OPENAI_API_KEY")

# ── Media (Django's MEDIA_URL + your domain) ─────────────────────────────────
DJANGO_MEDIA_URL = _require("DJANGO_MEDIA_URL")   # e.g. https://yourdomain.com/media/

# ── CORS (comma-separated origins) ───────────────────────────────────────────
_raw_origins = _optional("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS: list[str] = (
    [o.strip() for o in _raw_origins.split(",") if o.strip()]
    if _raw_origins else ["*"]
)

# ── Rate limiting ─────────────────────────────────────────────────────────────
WS_MAX_CONNECTIONS_PER_USER = int(_optional("WS_MAX_CONNECTIONS_PER_USER", "5"))
WS_MAX_MESSAGE_LENGTH       = int(_optional("WS_MAX_MESSAGE_LENGTH", "2000"))
WS_MAX_HISTORY_TURNS        = int(_optional("WS_MAX_HISTORY_TURNS", "20"))

# ── DB Pool ───────────────────────────────────────────────────────────────────
DB_POOL_SIZE     = int(_optional("DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW  = int(_optional("DB_MAX_OVERFLOW", "20"))
DB_POOL_TIMEOUT  = int(_optional("DB_POOL_TIMEOUT", "30"))

# ── OpenAI timeouts ───────────────────────────────────────────────────────────
OPENAI_TIMEOUT_SECONDS = int(_optional("OPENAI_TIMEOUT_SECONDS", "30"))