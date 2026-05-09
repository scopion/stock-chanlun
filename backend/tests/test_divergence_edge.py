"""背驰检测边界：MACD 面积为 0 时不应抛异常。"""
import os
import sys
import unittest
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from chanlun.elements import Bi  # noqa: E402
from ai.divergence import (  # noqa: E402
    DivergenceDetector,
    calculate_rsi,
    macd_area,
    macd_area_directional,
)


def _make_bi(d0: datetime, direction: str, high: float, low: float) -> Bi:
    return Bi(
        id="1",
        start=d0,
        end=d0 + timedelta(days=1),
        direction=direction,  # type: ignore[arg-type]
        high=high,
        low=low,
        start_price=low,
        end_price=high,
    )


def _make_bi_one_bar(
    d0: datetime, direction: str, high: float, low: float
) -> Bi:
    """start==end，对应日线序列上仅一根 K 线落入区间"""
    return Bi(
        id="1",
        start=d0,
        end=d0,
        direction=direction,  # type: ignore[arg-type]
        high=high,
        low=low,
        start_price=low,
        end_price=high,
    )


class DivergenceZeroMacdTests(unittest.TestCase):
    def test_check_divergence_no_raise_when_macd_sum_zero(self):
        # 常数 close -> MACD 柱可全为 0
        t0 = datetime(2020, 1, 1)
        rows = []
        for i in range(30):
            d = t0 + timedelta(days=i)
            rows.append(
                {
                    "date": d,
                    "open": 10.0,
                    "high": 10.0,
                    "low": 10.0,
                    "close": 10.0,
                    "volume": 1.0,
                }
            )
        df = pd.DataFrame(rows)
        up1 = _make_bi(t0, "up", 10.0, 9.0)
        up2 = _make_bi(t0 + timedelta(days=5), "up", 10.1, 9.1)
        up3 = _make_bi(t0 + timedelta(days=10), "up", 10.2, 9.2)
        up4 = _make_bi(t0 + timedelta(days=15), "up", 10.3, 9.1)
        bis = [up1, up2, up3, up4]
        det = DivergenceDetector(df)
        # 之前 macd1==0 会 ZeroDivisionError；现应安全返回 None
        out = det.check_divergence(bis)
        self.assertIsNone(out)


class DivergenceSegmentGuardTests(unittest.TestCase):
    def test_single_bar_segments_skipped(self):
        """笔区间内不足 MIN_BARS_PER_SEGMENT 根 K 线时不应给出背驰"""
        t0 = datetime(2020, 1, 1)
        rows = []
        for i in range(20):
            d = t0 + timedelta(days=i)
            rows.append(
                {
                    "date": d,
                    "open": 10.0 + i * 0.01,
                    "high": 10.05 + i * 0.01,
                    "low": 9.95 + i * 0.01,
                    "close": 10.0 + i * 0.01,
                    "volume": 1.0,
                }
            )
        df = pd.DataFrame(rows)
        # 四笔向上，每笔只覆盖单日 → 段内仅 1 根 K 线
        bis = [
            _make_bi_one_bar(t0 + timedelta(days=i), "up", 10.2, 9.8)
            for i in range(4)
        ]
        det = DivergenceDetector(df)
        self.assertIsNone(det.check_divergence(bis))


class MacdAreaDirectionalTests(unittest.TestCase):
    def test_directional_top_only_positive(self):
        s = pd.Series([1.0, -2.0, 3.0, np.nan])
        self.assertAlmostEqual(macd_area_directional(s, "top"), 4.0)
        self.assertAlmostEqual(macd_area_directional(s, "bottom"), 2.0)

    def test_directional_equals_abs_when_one_sign(self):
        pos = pd.Series([1.0, 2.0, 0.5])
        neg = pd.Series([-1.0, -2.0])
        self.assertAlmostEqual(macd_area_directional(pos, "top"), macd_area(pos))
        self.assertAlmostEqual(macd_area_directional(neg, "bottom"), macd_area(neg))


class DivergenceRsiTests(unittest.TestCase):
    def test_calculate_rsi_wilder_in_valid_range(self):
        t0 = datetime(2020, 1, 1)
        rows = []
        x = 50.0
        for i in range(60):
            d = t0 + timedelta(days=i)
            x += (-1) ** i * 0.8
            rows.append(
                {
                    "date": d,
                    "open": x,
                    "high": x + 0.5,
                    "low": x - 0.5,
                    "close": x,
                    "volume": 1.0,
                }
            )
        df = pd.DataFrame(rows)
        rsi = calculate_rsi(df, period=14)
        valid = rsi.iloc[14:].dropna()
        self.assertFalse(valid.empty)
        self.assertTrue((valid >= 0).all() and (valid <= 100).all())


if __name__ == "__main__":
    unittest.main()
