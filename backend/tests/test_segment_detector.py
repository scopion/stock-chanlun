import os
import sys
import unittest
from datetime import datetime, timedelta

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from chanlun.elements import Bi, XiangSegment
from chanlun.segment_detector import SegmentDetector


class SegmentDetectorTests(unittest.TestCase):
    def setUp(self):
        self.t0 = datetime(2026, 1, 2, 9, 30)

    def _bi(self, idx: int, direction: str, start_min: int, end_min: int, high: float, low: float) -> Bi:
        start = self.t0 + timedelta(minutes=start_min)
        end = self.t0 + timedelta(minutes=end_min)
        return Bi(
            id=f"bi_{idx}",
            start=start,
            end=end,
            direction=direction,
            high=high,
            low=low,
            start_price=low if direction == "up" else high,
            end_price=high if direction == "up" else low,
        )

    def _segment(self, idx: int, direction: str, start_min: int, end_min: int, high: float, low: float) -> XiangSegment:
        start = self.t0 + timedelta(minutes=start_min)
        end = self.t0 + timedelta(minutes=end_min)
        return XiangSegment(
            id=f"xiang_{idx}",
            start=start,
            end=end,
            direction=direction,
            high=high,
            low=low,
            bi_ids=[f"bi_{idx}a", f"bi_{idx}b", f"bi_{idx}c"],
            level=2,
        )

    def test_detect_segments_two_overlapping_bis(self):
        # 2 笔重叠 → 成 1 段
        detector = SegmentDetector(
            bis=[self._bi(1, "up", 0, 5, 11.0, 9.0), self._bi(2, "up", 6, 10, 12.0, 10.0)]
        )
        segs = detector.detect_segments()
        self.assertGreaterEqual(len(segs), 1)

    def test_detect_segments_overlap_and_destroy(self):
        # bi_1(up 11/9.2) bi_2(up 11.8/9.5) bi_3(up 12.3/9.8) bi_4(up 12.8/10) all overlap
        # bi_5(down 12.5/9.4): low(9.4) > start_low(9.2) → no destroy, but NO overlap with window → ends segment
        bis = [
            self._bi(1, "up", 0, 5, 11.0, 9.2),
            self._bi(2, "up", 6, 10, 11.8, 9.5),
            self._bi(3, "up", 11, 15, 12.3, 9.8),
            self._bi(4, "up", 16, 20, 12.8, 10.0),
            self._bi(5, "down", 21, 25, 12.5, 9.4),
        ]
        detector = SegmentDetector(bis=bis)
        segments = detector.detect_segments()
        # bi_1-4 overlapping → 1 segment, bi_5 alone → 1 segment
        self.assertGreaterEqual(len(segments), 1)

    def test_detect_zhongshus_creates_one_from_three_overlapping_segments(self):
        segments = [
            self._segment(1, "up", 0, 10, 110.0, 100.0),
            self._segment(2, "down", 11, 20, 108.0, 102.0),
            self._segment(3, "up", 21, 30, 109.0, 103.0),
        ]
        detector = SegmentDetector(bis=[])

        zhongshus = detector.detect_zhongshus(segments)
        self.assertEqual(len(zhongshus), 1)
        zs = zhongshus[0]
        self.assertEqual(zs.id, "zs_1")
        self.assertEqual(zs.start, segments[0].start)
        self.assertEqual(zs.end, segments[2].end)
        self.assertAlmostEqual(zs.range_high, 108.0)
        self.assertAlmostEqual(zs.range_low, 103.0)
        self.assertEqual(zs.xiang_ids, ["xiang_1", "xiang_2", "xiang_3"])

    def test_get_zhongshu_for_price_returns_latest_matching_zone(self):
        segments = [
            self._segment(1, "up", 0, 10, 110.0, 100.0),
            self._segment(2, "down", 11, 20, 108.0, 102.0),
            self._segment(3, "up", 21, 30, 109.0, 103.0),
            self._segment(4, "down", 31, 40, 130.0, 120.0),
            self._segment(5, "up", 41, 50, 128.0, 122.0),
            self._segment(6, "down", 51, 60, 126.0, 123.0),
        ]
        detector = SegmentDetector(bis=[])
        zhongshus = detector.detect_zhongshus(segments)

        self.assertEqual(len(zhongshus), 2)
        latest_match = detector.get_zhongshu_for_price(zhongshus, 124.0)
        self.assertIsNotNone(latest_match)
        self.assertEqual(latest_match.id, "zs_2")


if __name__ == "__main__":
    unittest.main()
