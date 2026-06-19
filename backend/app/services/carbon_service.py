"""
Carbon-intensity client for the PPO reward function.

Uses the electricityMaps API to get gCO2/kWh per zone. Sandbox keys only
return data for zone DK-DK1 (Denmark West); production keys cover all zones.

When the API is unreachable or no key is configured, we fall back to a
zone-specific historical average so the scheduler always gets a number.
The fallback prevents reward-function NaNs from breaking PPO training.

Free alternatives if electricityMaps quota is exhausted:
  - WattTime (free for researchers, real-time, US/EU)
  - UK Carbon Intensity API (no key, UK only)
  - Static `_FALLBACK_BY_ZONE` table (this file)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ── Static fallbacks (long-term yearly averages, gCO2eq/kWh) ────────────────
# Sources: IEA 2023, Ember Climate, electricityMaps historical aggregates.
_FALLBACK_BY_ZONE: dict[str, float] = {
    "IN-NO":  710.0,    # India North
    "IN-SO":  680.0,    # India South
    "IN-EA":  750.0,    # India East (coal-heavy)
    "IN-WE":  700.0,    # India West
    "US-CAL-CISO": 220.0,   # California
    "US-MIDA-PJM": 380.0,   # PJM (US East)
    "GB":     180.0,    # United Kingdom
    "DE":     380.0,    # Germany
    "DK-DK1": 100.0,    # Denmark West (lots of wind)
    "FR":      55.0,    # France (mostly nuclear)
    "NO":      30.0,    # Norway (hydro)
    "default": 500.0,
}


@dataclass
class CarbonReading:
    zone: str
    carbon_intensity: float       # gCO2eq/kWh
    is_estimated: bool
    is_fallback: bool             # True if we couldn't reach the API
    source: str                   # "api" | "fallback" | "cache"
    timestamp: float


class CarbonService:
    """
    Lightweight caching client. Caches readings per zone for `cache_ttl_s`
    seconds to stay well within the free quota (1000 req/month).
    """

    def __init__(self, cache_ttl_s: int = 300):
        settings = get_settings()
        self._token   = settings.electricity_maps_token
        self._url     = settings.electricity_maps_url
        self._zone    = settings.electricity_maps_zone
        self._cache:  dict[str, CarbonReading] = {}
        self._ttl    = cache_ttl_s

    # ── Public API ────────────────────────────────────────────────────────────

    def get_intensity(self, zone: Optional[str] = None) -> CarbonReading:
        zone = zone or self._zone
        cached = self._cache.get(zone)
        if cached and (time.time() - cached.timestamp) < self._ttl:
            return CarbonReading(**{**cached.__dict__, "source": "cache"})

        if not self._token:
            return self._fallback(zone, reason="no token configured")

        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(
                    f"{self._url}/carbon-intensity/latest",
                    params={"zone": zone},
                    headers={"auth-token": self._token},
                )
            if resp.status_code != 200:
                logger.warning("electricityMaps %s: %s", resp.status_code, resp.text[:200])
                return self._fallback(zone, reason=f"http {resp.status_code}")
            data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("electricityMaps request failed: %s", exc)
            return self._fallback(zone, reason=str(exc))

        reading = CarbonReading(
            zone=zone,
            carbon_intensity=float(data["carbonIntensity"]),
            is_estimated=bool(data.get("isEstimated", False)),
            is_fallback=False,
            source="api",
            timestamp=time.time(),
        )
        self._cache[zone] = reading
        return reading

    def get_normalized(self, zone: Optional[str] = None) -> float:
        """Return intensity normalized to roughly [0, 1] for PPO state vector."""
        reading = self.get_intensity(zone)
        # 1000 gCO2/kWh is a high upper bound (coal-only); clamp anything above.
        return min(reading.carbon_intensity / 1000.0, 1.0)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _fallback(self, zone: str, reason: str) -> CarbonReading:
        value = _FALLBACK_BY_ZONE.get(zone, _FALLBACK_BY_ZONE["default"])
        logger.info("Carbon fallback for %s: %.0f gCO2/kWh (%s)", zone, value, reason)
        return CarbonReading(
            zone=zone,
            carbon_intensity=value,
            is_estimated=True,
            is_fallback=True,
            source="fallback",
            timestamp=time.time(),
        )


# Module-level singleton so caches are shared across requests
_default: Optional[CarbonService] = None


def get_carbon_service() -> CarbonService:
    global _default
    if _default is None:
        _default = CarbonService()
    return _default
