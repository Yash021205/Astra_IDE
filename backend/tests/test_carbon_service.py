"""Tests for the carbon-intensity service.

Tests the fallback behavior without making real network calls (so CI runs offline).
A separate manual test in conftest hits the live API only when a key is configured.
"""
import time
import unittest
from unittest.mock import patch, MagicMock

from app.services.carbon_service import (
    CarbonService,
    CarbonReading,
    _FALLBACK_BY_ZONE,
)


class TestFallbackBehavior(unittest.TestCase):
    def test_fallback_used_when_no_token(self):
        with patch("app.services.carbon_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                electricity_maps_token=None,
                electricity_maps_url="https://api.electricitymap.org/v3",
                electricity_maps_zone="IN-NO",
            )
            svc = CarbonService()
            reading = svc.get_intensity("IN-NO")

            self.assertTrue(reading.is_fallback)
            self.assertEqual(reading.source, "fallback")
            self.assertEqual(reading.carbon_intensity, _FALLBACK_BY_ZONE["IN-NO"])

    def test_fallback_default_for_unknown_zone(self):
        with patch("app.services.carbon_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                electricity_maps_token=None,
                electricity_maps_url="https://api.electricitymap.org/v3",
                electricity_maps_zone="ZZ-ZZ",
            )
            svc = CarbonService()
            reading = svc.get_intensity("ZZ-ZZ")
            self.assertEqual(reading.carbon_intensity, _FALLBACK_BY_ZONE["default"])

    def test_normalized_value_clamped(self):
        with patch("app.services.carbon_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                electricity_maps_token=None,
                electricity_maps_url="https://api.electricitymap.org/v3",
                electricity_maps_zone="default",
            )
            svc = CarbonService()
            value = svc.get_normalized("default")
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)


class TestCaching(unittest.TestCase):
    def test_cache_hit_reuses_reading(self):
        with patch("app.services.carbon_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                electricity_maps_token=None,
                electricity_maps_url="https://api.electricitymap.org/v3",
                electricity_maps_zone="GB",
            )
            svc = CarbonService(cache_ttl_s=10)
            svc._cache["GB"] = CarbonReading(
                zone="GB", carbon_intensity=150.0, is_estimated=False,
                is_fallback=False, source="api", timestamp=time.time(),
            )
            r = svc.get_intensity("GB")
            self.assertEqual(r.source, "cache")
            self.assertEqual(r.carbon_intensity, 150.0)

    def test_cache_expires(self):
        with patch("app.services.carbon_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                electricity_maps_token=None,
                electricity_maps_url="https://api.electricitymap.org/v3",
                electricity_maps_zone="DK-DK1",
            )
            svc = CarbonService(cache_ttl_s=0)  # Already expired
            svc._cache["DK-DK1"] = CarbonReading(
                zone="DK-DK1", carbon_intensity=99.0, is_estimated=False,
                is_fallback=False, source="api", timestamp=time.time() - 100,
            )
            r = svc.get_intensity("DK-DK1")
            # Expired → goes to fallback (no token)
            self.assertEqual(r.source, "fallback")


if __name__ == "__main__":
    unittest.main(verbosity=2)
