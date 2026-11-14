import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import unittest

from agent import indicators


def synthetic(n=400, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.004, n))
    high = close * (1 + rng.uniform(0.0005, 0.006, n))
    low = close * (1 - rng.uniform(0.0005, 0.006, n))
    open_ = np.r_[close[0], close[:-1]]
    vol = rng.uniform(100, 1000, n)
    ts = np.arange(n, dtype="int64") * 900_000
    return pd.DataFrame(
        {
            "open_time": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": vol,
            "close_time": ts + 899_999,
        }
    )


class IndicatorTests(unittest.TestCase):
    def test_rsi_bounds(self):
        df = synthetic()
        r = indicators.rsi(df["close"], 14).dropna()
        self.assertTrue(len(r) > 300)
        self.assertGreaterEqual(r.min(), 0.0)
        self.assertLessEqual(r.max(), 100.0)

    def test_atr_positive(self):
        df = synthetic()
        a = indicators.atr(df, 14).dropna()
        self.assertTrue((a > 0).all())

    def test_add_indicators_columns(self):
        df = indicators.add_indicators(synthetic())
        for col in ("ema20", "ema50", "ema200", "rsi", "macd_hist", "atr", "vol_ratio", "swing_low20"):
            self.assertIn(col, df.columns)

    def test_swing_low_uses_past_only(self):
        df = indicators.add_indicators(synthetic())
        self.assertTrue(np.isnan(df["swing_low20"].iloc[0]))
        self.assertLessEqual(df["swing_low20"].iloc[-1], df["low"].iloc[-20])

    def test_h4_trend_direction(self):
        n = 1200
        up = synthetic(n)
        up["open_time"] = np.arange(n, dtype="int64") * 3_600_000
        up["close"] = np.linspace(100, 300, n)
        self.assertEqual(int(indicators.add_htf_trend(up)["h4_trend"].iloc[-1]), 1)

        down = synthetic(n)
        down["open_time"] = np.arange(n, dtype="int64") * 3_600_000
        down["close"] = np.linspace(300, 100, n)
        self.assertEqual(int(indicators.add_htf_trend(down)["h4_trend"].iloc[-1]), -1)

    def test_h4_trend_no_lookahead(self):
        df = synthetic(1200)
        df["open_time"] = np.arange(1200, dtype="int64") * 3_600_000
        base = indicators.add_htf_trend(df)
        future = df.copy()
        future.loc[900:, "close"] *= 0.5
        changed = indicators.add_htf_trend(future)
        self.assertTrue((base["h4_trend"].iloc[:800] == changed["h4_trend"].iloc[:800]).all())


if __name__ == "__main__":
    unittest.main()
