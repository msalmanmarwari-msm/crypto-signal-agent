import unittest

import numpy as np

from agent import mmc


class FakeCols:
    def __init__(self, **cols):
        self.arrays = {k: np.asarray(v, dtype=float) for k, v in cols.items()}

    def get(self, row, name):
        arr = self.arrays.get(name)
        if arr is None or row < 0 or row >= arr.shape[0]:
            return float("nan")
        return float(arr[row])


def _flat(n, value=100.0):
    return [value] * n


class TestStructureBreak(unittest.TestCase):
    def test_long_break(self):
        n = 30
        c = FakeCols(
            open=_flat(n),
            high=_flat(n, 100.5),
            low=_flat(n, 99.5),
            close=_flat(n),
        )
        c.arrays["high"][29] = 102.0
        self.assertTrue(mmc._structure_break(c, 29, "LONG"))

    def test_short_break(self):
        n = 30
        c = FakeCols(
            open=_flat(n),
            high=_flat(n, 100.5),
            low=_flat(n, 99.5),
            close=_flat(n),
        )
        c.arrays["low"][29] = 98.0
        self.assertTrue(mmc._structure_break(c, 29, "SHORT"))

    def test_no_break_inside_range(self):
        n = 30
        c = FakeCols(open=_flat(n), high=_flat(n, 100.5), low=_flat(n, 99.5), close=_flat(n))
        self.assertFalse(mmc._structure_break(c, 29, "LONG"))
        self.assertFalse(mmc._structure_break(c, 29, "SHORT"))


class TestFVG(unittest.TestCase):
    def test_long_fvg_rebalance(self):
        n = 15
        c = FakeCols(open=_flat(n), high=_flat(n), low=_flat(n), close=_flat(n))
        c.arrays["low"][12] = 102.0
        c.arrays["high"][13] = 104.0
        c.arrays["low"][13] = 103.5
        c.arrays["close"][13] = 103.0
        c.arrays["low"][14] = 101.0
        c.arrays["close"][14] = 101.5
        self.assertTrue(mmc._fvg(c, 14, "LONG"))

    def test_no_fvg_without_gap(self):
        n = 15
        c = FakeCols(open=_flat(n), high=_flat(n), low=_flat(n), close=_flat(n))
        self.assertFalse(mmc._fvg(c, 14, "LONG"))
        self.assertFalse(mmc._fvg(c, 14, "SHORT"))


class TestSweep(unittest.TestCase):
    def test_short_sweep(self):
        n = 15
        c = FakeCols(
            open=_flat(n),
            high=_flat(n),
            low=_flat(n, 90.0),
            close=_flat(n),
            swing_high20=_flat(n, 100.0),
            swing_low20=_flat(n, 80.0),
        )
        c.arrays["high"][14] = 101.0
        c.arrays["close"][14] = 99.0
        self.assertTrue(mmc._sweep(c, 14, "SHORT"))

    def test_long_sweep(self):
        n = 15
        c = FakeCols(
            open=_flat(n),
            high=_flat(n, 110.0),
            low=_flat(n),
            close=_flat(n),
            swing_high20=_flat(n, 120.0),
            swing_low20=_flat(n, 95.0),
        )
        c.arrays["low"][14] = 94.0
        c.arrays["close"][14] = 96.0
        self.assertTrue(mmc._sweep(c, 14, "LONG"))


class TestRangePosition(unittest.TestCase):
    def test_midpoint(self):
        n = 61
        c = FakeCols(high=_flat(n, 110.0), low=_flat(n, 100.0))
        self.assertAlmostEqual(mmc.range_position(c, 60, 105.0), 0.5)

    def test_bounds(self):
        n = 61
        c = FakeCols(high=_flat(n, 110.0), low=_flat(n, 100.0))
        self.assertAlmostEqual(mmc.range_position(c, 60, 110.0), 1.0)
        self.assertAlmostEqual(mmc.range_position(c, 60, 100.0), 0.0)


class TestQflQb(unittest.TestCase):
    def _long_setup(self, retest_low=100.2, retest_close=101.0):
        n = 30
        c = FakeCols(
            open=_flat(n, 100.0),
            high=_flat(n, 100.5),
            low=_flat(n, 99.5),
            close=_flat(n, 100.0),
            atr=_flat(n, 1.0),
        )
        # base candle 25 ke baad impulse 26-28, phir 29 par retest
        c.arrays["high"][26:29] = [101.0, 103.0, 104.0]
        c.arrays["low"][26:29] = [100.5, 102.0, 103.0]
        c.arrays["close"][26:29] = [100.8, 102.5, 103.5]
        c.arrays["low"][29] = retest_low
        c.arrays["close"][29] = retest_close
        c.arrays["high"][29] = max(retest_close, 101.5)
        return c

    def test_long_zone_found(self):
        c = self._long_setup()
        zone = mmc._origin_zone(c, 29, "LONG")
        self.assertIsNotNone(zone)
        qfl, box_lo, box_hi, _ = zone
        self.assertAlmostEqual(qfl, 100.5)
        self.assertAlmostEqual(box_lo, 99.5)
        self.assertAlmostEqual(box_hi, 100.5)

    def test_long_qfl_and_qb(self):
        c = self._long_setup()
        qfl_ok, qb_ok = mmc._qfl_qb(c, 29, "LONG")
        self.assertTrue(qfl_ok)
        self.assertTrue(qb_ok)

    def test_shallow_touch_is_qfl_only(self):
        c = self._long_setup(retest_low=100.6)
        qfl_ok, qb_ok = mmc._qfl_qb(c, 29, "LONG")
        self.assertTrue(qfl_ok)
        self.assertFalse(qb_ok)

    def test_close_below_line_fails(self):
        c = self._long_setup(retest_low=100.2, retest_close=100.0)
        qfl_ok, qb_ok = mmc._qfl_qb(c, 29, "LONG")
        self.assertFalse(qfl_ok)
        self.assertFalse(qb_ok)

    def test_short_qfl_and_qb(self):
        n = 30
        c = FakeCols(
            open=_flat(n, 100.0),
            high=_flat(n, 100.5),
            low=_flat(n, 99.5),
            close=_flat(n, 100.0),
            atr=_flat(n, 1.0),
        )
        c.arrays["low"][26:29] = [99.0, 97.0, 96.0]
        c.arrays["high"][26:29] = [99.5, 97.5, 96.5]
        c.arrays["close"][26:29] = [99.2, 97.5, 96.5]
        c.arrays["high"][29] = 99.8
        c.arrays["close"][29] = 99.0
        c.arrays["low"][29] = 98.5
        qfl_ok, qb_ok = mmc._qfl_qb(c, 29, "SHORT")
        self.assertTrue(qfl_ok)
        self.assertTrue(qb_ok)

    def test_analyze_reports_qfl_reason(self):
        n = 30
        n1h = 61
        c15 = self._long_setup()
        c15.arrays["swing_high20"] = np.full(n, 120.0)
        c15.arrays["swing_low20"] = np.full(n, 80.0)
        c1h = FakeCols(high=_flat(n1h, 110.0), low=_flat(n1h, 100.0))
        res = mmc.analyze(c15, c1h, 29, 60, "LONG", 101.0)
        self.assertTrue(res.has_qfl)
        self.assertTrue(res.has_qb)
        self.assertTrue(any("QFL" in r for r in res.reasons))
        # QFL/QB core gate ko nahi badalte, sirf confirmation points dete hain
        self.assertEqual(res.core_points, res.points - 2)


class TestCcp(unittest.TestCase):
    def _cols(self, o, h, l, c):
        n = len(c)
        return FakeCols(open=o, high=h, low=l, close=c)

    def test_long_engulfing(self):
        c = self._cols(
            [100.0, 99.4],
            [100.2, 101.0],
            [99.8, 99.3],
            [99.5, 100.8],
        )
        self.assertTrue(mmc._ccp(c, 1, "LONG"))

    def test_long_strong_close(self):
        c = self._cols([100.0, 99.0], [100.2, 100.6], [99.8, 98.9], [100.0, 100.5])
        self.assertTrue(mmc._ccp(c, 1, "LONG"))

    def test_doji_rejected(self):
        c = self._cols([100.0, 100.0], [100.2, 101.0], [99.8, 99.0], [100.0, 100.05])
        self.assertFalse(mmc._ccp(c, 1, "LONG"))
        self.assertFalse(mmc._ccp(c, 1, "SHORT"))

    def test_short_engulfing(self):
        c = self._cols([100.0, 100.6], [100.2, 100.7], [99.8, 99.2], [100.0, 99.4])
        self.assertTrue(mmc._ccp(c, 1, "SHORT"))


class TestRoom(unittest.TestCase):
    def _c1h(self, swing_highs):
        n = len(swing_highs)
        return FakeCols(high=_flat(n, 110.0), low=_flat(n, 90.0), swing_high20=swing_highs)

    def test_resistance_too_close(self):
        c15 = FakeCols(atr=_flat(2, 1.0))
        c1h = self._c1h([101.0] * 61)
        c1h.arrays["swing_low20"] = np.full(61, 90.0)
        self.assertFalse(mmc._room(c15, c1h, 1, 60, "LONG", 100.0))

    def test_resistance_far_enough(self):
        c15 = FakeCols(atr=_flat(2, 1.0))
        c1h = self._c1h([103.0] * 61)
        c1h.arrays["swing_low20"] = np.full(61, 90.0)
        self.assertTrue(mmc._room(c15, c1h, 1, 60, "LONG", 100.0))

    def test_short_support_far(self):
        c15 = FakeCols(atr=_flat(2, 1.0))
        c1h = self._c1h(np.full(61, 110.0))
        c1h.arrays["swing_low20"] = np.full(61, 97.0)
        self.assertTrue(mmc._room(c15, c1h, 1, 60, "SHORT", 100.0))


class TestAnalyze(unittest.TestCase):
    def test_structure_gives_points_and_reason(self):
        n = 15
        n1h = 61
        c15 = FakeCols(
            open=_flat(n),
            high=_flat(n, 100.5),
            low=_flat(n, 99.5),
            close=_flat(n),
            swing_high20=_flat(n, 90.0),
            swing_low20=_flat(n, 110.0),
        )
        c1h = FakeCols(high=_flat(n1h, 110.0), low=_flat(n1h, 100.0))
        c15.arrays["high"][14] = 102.0
        res = mmc.analyze(c15, c1h, 14, 60, "LONG", 101.0)
        self.assertTrue(res.has_structure)
        self.assertGreaterEqual(res.points, 3)
        self.assertTrue(any("BOS" in r for r in res.reasons))


if __name__ == "__main__":
    unittest.main()
