"""
B2 tests: HashPipe Top-K precision (eHashPipe trend) + aggregator windowing.
"""
import random
import unittest

from ml.telemetry.hashpipe import HashPipe, topk_precision
from ml.telemetry.aggregator import Event, aggregate, syscall_stream, WINDOW_MS


def _zipf_stream(n_events, n_pids, seed=0, skew=1.3):
    rng = random.Random(seed)
    weights = [1.0 / (i ** skew) for i in range(1, n_pids + 1)]
    pids = list(range(1, n_pids + 1))
    return rng.choices(pids, weights=weights, k=n_events)


def _true_topk(stream, k):
    from collections import Counter
    return [p for p, _ in Counter(stream).most_common(k)]


class TestHashPipeTopK(unittest.TestCase):
    """Reproduce eHashPipe: ~100% Top-K precision at small k, degrading as k grows."""

    @classmethod
    def setUpClass(cls):
        cls.stream = _zipf_stream(200_000, n_pids=500, seed=1)
        cls.hp = HashPipe(stages=4, slots=64)
        for pid in cls.stream:
            cls.hp.update(pid, 1.0)

    def _precision_at(self, k):
        return topk_precision(self.hp.top_k(k), _true_topk(self.stream, k))

    def test_perfect_for_small_k(self):
        # paper: 100% precision at k in {1,5,10}
        for k in (1, 5, 10):
            self.assertEqual(self._precision_at(k), 1.0, f"k={k}")

    def test_degrades_gracefully_for_larger_k(self):
        # paper: ~0.90-0.95 at k=20 — assert still high but may dip below 1.0
        p20 = self._precision_at(20)
        self.assertGreaterEqual(p20, 0.80, f"k=20 precision {p20:.2f}")

    def test_memory_is_bounded(self):
        # tracks 500 distinct PIDs in only stages*slots slots
        self.assertLessEqual(self.hp.memory_slots(), 4 * 64)


class TestAggregator(unittest.TestCase):
    def test_windows_split_by_500ms(self):
        evs = [
            Event(ts_ms=0,   pid=1, comm="py", syscall="read",  cpu_ns=1e8, bytes_io=2048),
            Event(ts_ms=100, pid=1, comm="py", syscall="write", cpu_ns=1e8, bytes_net=1e6),
            Event(ts_ms=700, pid=2, comm="cc", syscall="open",  cpu_ns=2e8),
        ]
        ws = aggregate(evs, window_ms=WINDOW_MS, n_cores=4)
        self.assertEqual(len(ws), 2)                     # 0-500, 500-1000
        # window 0: two events, pid 1; cpu = (1e8+1e8)/(500e6*4)
        self.assertAlmostEqual(ws[0].cpu_util, 2e8 / (500e6 * 4), places=4)
        self.assertEqual(ws[0].active_pids, 1)
        self.assertEqual(ws[0].syscalls, ["read", "write"])
        self.assertEqual(ws[1].syscalls, ["open"])

    def test_syscall_stream_ids(self):
        evs = [Event(ts_ms=i * 10, pid=1, comm="x", syscall=s)
               for i, s in enumerate(["a", "b", "a", "c", "b"])]
        seq = syscall_stream(aggregate(evs))
        self.assertEqual(len(seq), 5)
        self.assertEqual(seq[0], seq[2])                 # both "a" → same id
        self.assertEqual(seq[1], seq[4])                 # both "b"

    def test_empty(self):
        self.assertEqual(aggregate([]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
