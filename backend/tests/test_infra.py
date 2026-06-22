"""Infra integrations: cache fallback, object-store graceful degradation, metrics."""
import unittest


class TestCache(unittest.TestCase):
    def test_memory_fallback_roundtrip(self):
        from app.services.cache import Cache
        # unreachable redis -> falls back to in-memory, still works
        c = Cache("redis://127.0.0.1:6390/0")
        self.assertEqual(c.backend, "memory")
        c.set("k", "v")
        self.assertEqual(c.get("k"), "v")
        self.assertEqual(c.incr("n"), 1)
        self.assertEqual(c.incr("n"), 2)
        self.assertIsNone(c.get("missing"))

    def test_memory_ttl_expiry(self):
        import time
        from app.services.cache import Cache
        c = Cache("redis://127.0.0.1:6390/0")
        c.set("temp", "x", ttl=1)
        self.assertEqual(c.get("temp"), "x")
        # negative-ttl style check: directly expire
        c._mem["temp"] = ("x", time.time() - 1)
        self.assertIsNone(c.get("temp"))


class TestObjectStore(unittest.TestCase):
    def test_unavailable_is_graceful(self):
        from app.services import object_store
        # no MinIO running on the default endpoint -> not available, no exception
        self.assertFalse(object_store.is_available())
        res = object_store.snapshot_workspace(987654)
        self.assertFalse(res.ok)
        self.assertIn("unavailable", res.detail)


class TestMetrics(unittest.TestCase):
    def test_metrics_exposition(self):
        from app.core.metrics import WORKSPACES_CREATED, metrics_response
        WORKSPACES_CREATED.inc()
        body = bytes(metrics_response().body).decode()
        self.assertIn("astra_workspaces_created_total", body)
        self.assertIn("astra_http_requests_total", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
