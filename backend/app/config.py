import os
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]
load_dotenv(BASE.parent / ".env")
DATA_DIR = Path(os.getenv("FDR_DATA_DIR", BASE / "data"))  # DB lives outside source dirs, gitignored
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'fdr_nexus.db'}")
AICTE_API_BASE = os.getenv("AICTE_API_BASE", "")
AICTE_API_KEY = os.getenv("AICTE_API_KEY", "")
WARN_DAYS = int(os.getenv("MATURITY_WARNING_DAYS", "60"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "5")) * 1024 * 1024
SESSION_TTL_MINUTES = max(5, int(os.getenv("SESSION_TTL_MINUTES", "60")))
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "fdr_session")
CSRF_COOKIE_NAME = os.getenv("CSRF_COOKIE_NAME", "fdr_csrf")
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
AUTH_COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "strict").strip().lower()
if AUTH_COOKIE_SAMESITE not in {"strict", "lax", "none"}:
    AUTH_COOKIE_SAMESITE = "strict"
if AUTH_COOKIE_SAMESITE == "none" and not AUTH_COOKIE_SECURE:
    AUTH_COOKIE_SAMESITE = "lax"
BOOTSTRAP_ADMIN_USERNAME = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip()
BOOTSTRAP_ADMIN_PASSWORD = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")


def _reminder_thresholds():
    default = (30, 15, 7, 1)
    try:
        values = tuple(int(item.strip()) for item in os.getenv("MATURITY_REMINDER_THRESHOLDS", "30,15,7,1").split(","))
    except ValueError:
        return default
    if not values or values[-1] != 1 or any(value <= 0 for value in values) or any(values[i] <= values[i + 1] for i in range(len(values) - 1)):
        return default
    return values


MATURITY_REMINDER_THRESHOLDS = _reminder_thresholds()
