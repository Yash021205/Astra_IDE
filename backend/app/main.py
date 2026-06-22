"""ASTRA-IDE FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.config import get_settings
from app.core.metrics import PrometheusMiddleware, metrics_response
from app.db.session import Base, engine

# Import models to register them with SQLAlchemy's metadata
from app.models import User, Workspace, WorkspaceMember, SchedulerEvent  # noqa: F401
from app.services import telemetry_loop

settings = get_settings()


def _ensure_columns() -> None:
    """
    Lightweight additive migration: add columns introduced after the tables were
    first created (create_all only creates missing TABLES, not columns). Safe to
    run every startup; works on both SQLite (dev) and PostgreSQL (prod).
    """
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    wanted = {
        "users":      [("avatar_url", "VARCHAR(512)"),
                       ("is_admin", "BOOLEAN DEFAULT FALSE"),
                       ("github_id", "BIGINT"),
                       ("github_login", "VARCHAR(128)"),
                       ("github_access_token", "VARCHAR(2048)")],
        "workspaces": [("forked_from_id", "INTEGER"),
                       ("frozen", "BOOLEAN DEFAULT FALSE"),
                       ("shared_excludes", "TEXT DEFAULT ''")],
    }
    with engine.begin() as conn:
        for table, cols in wanted.items():
            try:
                existing = {c["name"] for c in insp.get_columns(table)}
            except Exception:
                continue
            for name, ddl in cols:
                if name not in existing:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))


def _bootstrap_admins() -> None:
    """Promote configured admins. The first registered user (id=1) is always an
    admin; additional admins can be listed in the ADMIN_EMAILS env var."""
    import os
    from sqlalchemy import text
    emails = [e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()]
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE users SET is_admin = TRUE WHERE id = 1"))
            for e in emails:
                conn.execute(text("UPDATE users SET is_admin = TRUE WHERE lower(email) = :e"), {"e": e})
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (for dev — use Alembic in production)
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    _bootstrap_admins()
    # Kick off the background telemetry/event simulator
    await telemetry_loop.start()
    try:
        yield
    finally:
        await telemetry_loop.stop()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
    openapi_url=f"{settings.api_prefix}/openapi.json",
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(PrometheusMiddleware)


@app.get("/healthz", tags=["health"])
def health_check():
    return {"status": "ok", "service": settings.app_name, "env": settings.environment}


@app.get("/metrics", tags=["monitoring"])
def metrics():
    """Prometheus scrape endpoint (kube-prometheus-stack / ServiceMonitor)."""
    # Refresh the queue-depth gauge KEDA scales on, at scrape time.
    try:
        from app.core.metrics import WORKSPACE_PENDING_QUEUE
        from app.db.session import SessionLocal
        from app.models import Workspace
        db = SessionLocal()
        try:
            pending = db.query(Workspace).filter(Workspace.status == "PENDING").count()
            WORKSPACE_PENDING_QUEUE.set(pending)
        finally:
            db.close()
    except Exception:
        pass
    return metrics_response()


app.include_router(api_router, prefix=settings.api_prefix)
