"""System status — surfaces which optional infra backends are live."""
from fastapi import APIRouter

from app.core.config import get_settings
from app.services import object_store
from app.services.cache import get_cache

router = APIRouter(prefix="/system", tags=["system"])
settings = get_settings()


@router.get("/status")
def status() -> dict:
    """Which tech-stack backends are wired/live right now (for ops + the report)."""
    return {
        "environment":   settings.environment,
        "database":      settings.database_url.split(":")[0],   # sqlite | postgresql
        "cache_backend": get_cache().backend,                   # redis | memory
        "object_store":  "minio" if object_store.is_available() else "unavailable",
        "metrics":       "/metrics (prometheus)",
        "carbon_api":    "configured" if settings.electricity_maps_token else "fallback",
        "google_oauth":  "configured" if settings.google_client_id else "unconfigured",
    }
