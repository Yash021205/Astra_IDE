"""
B7 tests — the CRDT convergence guarantee (Eg-walker's core property): replicas
converge to the same text regardless of the order operations are applied.
"""
import random
import unittest

from ml.collab.crdt import Doc, alloc_between


class TestAlloc(unittest.TestCase):
    def test_strictly_between(self):
        for lo, hi in [([], []), ([5], [6]), ([], [128]), ([200], []), ([5], [5, 10])]:
            k = alloc_between(lo, hi)
            # lo < k < hi as int-lists (missing => 0 / BASE handled by comparison)
            self.assertTrue(lo < k, f"{lo} !< {k}")
            if hi:
                self.assertTrue(k < hi, f"{k} !< {hi}")


class TestSingleReplica(unittest.TestCase):
    def test_basic_edit(self):
        d = Doc(1)
        for i, ch in enumerate("hello"):
            d.local_insert(i, ch)
        self.assertEqual(d.text(), "hello")
        d.local_insert(5, "!")
        self.assertEqual(d.text(), "hello!")
        d.local_delete(0)                       # remove 'h'
        self.assertEqual(d.text(), "ello!")


class TestConvergence(unittest.TestCase):
    def test_order_independent(self):
        # author types a string -> a log of ops; a peer applies them shuffled.
        author = Doc(1)
        ops = []
        for i, ch in enumerate("collaborative editing converges"):
            ops.append(author.local_insert(i, ch))
        rng = random.Random(0)
        for _ in range(5):
            shuffled = ops[:]
            rng.shuffle(shuffled)
            peer = Doc(2)
            peer.apply_all(shuffled)
            self.assertEqual(peer.text(), author.text())

    def test_concurrent_inserts_converge(self):
        # two replicas insert at the SAME position concurrently, then exchange ops
        a, b = Doc(1), Doc(2)
        base_ops = [a.local_insert(i, ch) for i, ch in enumerate("XY")]
        b.apply_all(base_ops)                   # both start from "XY"
        opa = a.local_insert(1, "a")            # A inserts between X and Y
        opb = b.local_insert(1, "b")            # B inserts between X and Y (concurrent)
        a.apply(opb)                            # exchange
        b.apply(opa)
        self.assertEqual(a.text(), b.text())    # converged
        self.assertIn(a.text(), ("XabY", "XbaY"))

    def test_concurrent_delete_and_insert(self):
        a, b = Doc(1), Doc(2)
        ops = [a.local_insert(i, ch) for i, ch in enumerate("hello")]
        b.apply_all(ops)
        od = a.local_delete(0)                  # A deletes 'h'
        oi = b.local_insert(5, "!")             # B appends '!'
        a.apply(oi); b.apply(od)
        self.assertEqual(a.text(), b.text())
        self.assertEqual(a.text(), "ello!")


if __name__ == "__main__":
    unittest.main(verbosity=2)
