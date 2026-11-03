import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import Base, engine
from . import models  # noqa: F401
from .auth import bootstrap_admin_if_configured
from .database import SessionLocal
from .api.routes import router
from .migrations import apply_schema_migrations

logging.basicConfig(level=logging.INFO)
apply_schema_migrations(engine, Base.metadata)

try:
    with SessionLocal() as bootstrap_db:
        bootstrap_admin_if_configured(bootstrap_db)
except Exception:
    logging.getLogger(__name__).exception("Could not apply configured administrator bootstrap")

app = FastAPI(title="FDR Nexus API", description="Security Deposit & FDR Management", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"], allow_credentials=True)
app.include_router(router)
