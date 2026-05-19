import os
import sys
import unittest
from datetime import datetime, timedelta

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from chanlun.bi_detector import BiDetector
from chanlun.fenxing_detector import Fenxing


class BiDetectorFenxingCompressionTests(unittest.TestCase):
    def test_compress_keeps_most_extreme_of_same_type(self):
        t0 = datetime(2026, 1, 1)

        fenxings = [
            Fenxing(date=t0, type="top", high=10.0, low=9.0, index=1),
            # more extreme -> replaces previous top
            Fenxing(date=t0 + timedelta(days=1), type="top", high=12.0, low=11.0, index=2),
            # less extreme -> ignored
            Fenxing(date=t0 + timedelta(days=2), type="top", high=11.0, low=10.0, index=3),
            Fenxing(date=t0 + timedelta(days=3), type="bottom", high=8.0, low=7.0, index=4),
            # more extreme -> replaces previous bottom
            Fenxing(date=t0 + timedelta(days=4), type="bottom", high=7.5, low=6.5, index=5),
        ]

        compressed = BiDetector.compress_fenxings(fenxings)

        # 简单压缩: 只保留各类型最极值 -> top12, bottom6.5 = 2个
        self.assertEqual(len(compressed), 2)
        self.assertEqual(compressed[0].type, "top")
        self.assertEqual(compressed[0].high, 12.0)
        self.assertEqual(compressed[1].type, "bottom")
        self.assertEqual(compressed[1].low, 6.5)


if __name__ == "__main__":
    unittest.main()

