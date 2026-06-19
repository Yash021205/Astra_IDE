"""Carbon-intensity API endpoints (read-only)."""
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models import User
from app.services.carbon_service import get_carbon_service

router = APIRouter(prefix="/carbon", tags=["carbon"])


@router.get("/intensity")
def get_intensity(
    zone: str | None = None,
    _user: User = Depends(get_current_user),
):
    """
    Returns current carbon intensity in gCO2eq/kWh for the requested zone.
    Falls back to a historical average if the API is unreachable or quota
    is exhausted.
    """
    reading = get_carbon_service().get_intensity(zone)
    return {
        "zone":             reading.zone,
        "carbon_intensity": reading.carbon_intensity,
        "is_estimated":     reading.is_estimated,
        "is_fallback":      reading.is_fallback,
        "source":           reading.source,
        "timestamp":        reading.timestamp,
    }
