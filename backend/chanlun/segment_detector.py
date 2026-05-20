"""
线段与中枢检测器

线段规则（缠论标准）:
- 由连续多笔构成，笔之间交替方向
- 线段包含所有与前一笔范围重叠的笔（同向+反向）
- 线段被反向笔破坏后终止：
  * 向上线段：反向笔低点 < 线段起点低点 → 线段被破坏
  * 向下线段：反向笔高点 > 线段起点高点 → 线段被破坏

中枢规则:
- 3个（或以上）连续同级别线段的重叠区域构成中枢
"""
from typing import Optional
from datetime import datetime
from .elements import Bi, XiangSegment, Zhongshu


class SegmentDetector:
    """线段与中枢检测器"""

    def __init__(self, bis: list[Bi]):
        self.bis = bis

    # ── 线段 ────────────────────────────────────────────────────

    def detect_segments(self, max_iterations: int = 10000) -> list[XiangSegment]:
        """
        检测线段（缠论标准特征序列破坏法）

        线段终止条件（任一触发）:
        1. 新笔与滑动窗口(最近4笔)不重叠 → 趋势耗尽
        2. 反向笔破坏: 反向笔终点突破段起点 → 线段被破坏
        3. 区间膨胀: 总区间 > 窗口区间 × 3 → 走势漂移
        4. 安全上限 12 笔
        """
        if len(self.bis) == 0:
            return []

        segments: list[XiangSegment] = []
        i = 0
        iterations = 0

        while i < len(self.bis):
            iterations += 1
            if iterations > max_iterations:
                break

            seg, next_i = self._build_one_segment(i, len(segments) + 1)
            segments.append(seg)
            i = next_i

        return segments

    def _build_one_segment(self, start_idx: int,
                           seg_num: int) -> tuple[XiangSegment, int]:
        """构建一条线段, 返回 (线段, 下一笔索引)"""
        WINDOW = 4          # 滑动窗口(笔数)
        RANGE_RATIO = 3.0   # 总区间/窗口区间上限
        MAX_BI = 12         # 安全上限

        first = self.bis[start_idx]
        direction = first.direction
        seg_high = first.high
        seg_low = first.low
        seg_start = first.start
        seg_end = first.end
        bi_indices = [start_idx]
        start_low = first.low
        start_high = first.high

        j = start_idx + 1
        while j < len(self.bis):
            nxt = self.bis[j]

            if len(bi_indices) >= MAX_BI:
                break

            # 滑动窗口区间
            win_idx = bi_indices[-WINDOW:] if len(bi_indices) >= WINDOW else bi_indices
            win_bis = [self.bis[k] for k in win_idx]
            win_high = max(b.high for b in win_bis)
            win_low = min(b.low for b in win_bis)

            # 区间膨胀检查
            total_range = seg_high - seg_low
            win_range = max(win_high - win_low, 0.001)
            if total_range > win_range * RANGE_RATIO:
                break

            if self._overlaps(nxt, win_high, win_low):
                bi_indices.append(j)
                seg_high = max(seg_high, nxt.high)
                seg_low = min(seg_low, nxt.low)
                seg_end = nxt.end
                j += 1
            else:
                # 不重叠 → 检查反向破坏
                destroyed = False
                if direction == "up" and nxt.low < start_low:
                    destroyed = True
                elif direction == "down" and nxt.high > start_high:
                    destroyed = True

                if destroyed:
                    bi_indices.append(j)
                    seg_high = max(seg_high, nxt.high)
                    seg_low = min(seg_low, nxt.low)
                    seg_end = nxt.end
                    j += 1
                break

        seg_bis = [self.bis[k] for k in bi_indices]
        seg = XiangSegment(
            id=f"xiang_{seg_num}",
            start=seg_bis[0].start,
            end=seg_bis[-1].end,
            direction=direction,
            high=seg_high,
            low=seg_low,
            bi_ids=[b.id for b in seg_bis],
            level=2,
        )
        return seg, j

    def _has_overlap(self, bis_group: list[Bi]) -> bool:
        """判断一组笔是否有重叠"""
        if len(bis_group) < 2:
            return False
        high = min(b.high for b in bis_group)
        low = max(b.low for b in bis_group)
        return high > low  # 有重叠区域

    def _overlaps(self, bi: Bi, existing_high: float, existing_low: float) -> bool:
        """判断笔是否与已有区域重叠"""
        return bi.high > existing_low and bi.low < existing_high

    def detect_zhongshus(self, segments: list[XiangSegment]) -> list[Zhongshu]:
        """
        检测中枢（滑动窗口算法）：
        遍历线段序列，每取得连续3段计算重叠区间：
        - 有重叠 → 构成中枢，尝试向后延伸（后续线段若与之重叠则并入）
        - 无重叠 → 跳过，继续寻找下一组
        相邻中枢之间必然间隔至少3个线段，不会重复。
        """
        if len(segments) < 3:
            return []

        zhongshus: list[Zhongshu] = []
        i = 0

        while i <= len(segments) - 3:
            group = segments[i:i + 3]

            # 计算三段重叠区间
            range_high = min(s.high for s in group)
            range_low = max(s.low for s in group)

            if range_high > range_low:
                # 重叠 → 形成中枢，尝试向后延伸
                cur_start = group[0].start
                cur_end = group[-1].end
                xiang_ids = [s.id for s in group]
                extend_idx = i + 3

                while extend_idx < len(segments):
                    nxt = segments[extend_idx]
                    # 新段与当前中枢重叠 → 并入
                    if nxt.high > range_low and nxt.low < range_high:
                        range_high = max(range_high, nxt.high)
                        range_low = min(range_low, nxt.low)
                        cur_end = nxt.end
                        xiang_ids.append(nxt.id)
                        extend_idx += 1
                    else:
                        break

                zhongshus.append(Zhongshu(
                    id=f"zs_{len(zhongshus)+1}",
                    start=cur_start,
                    end=cur_end,
                    range_high=float(range_high),
                    range_low=float(range_low),
                    xiang_ids=xiang_ids,
                    level=group[0].level
                ))
                i = extend_idx  # 跳到中枢结束后的第一个线段
            else:
                i += 1

        return zhongshus

    def get_zhongshu_for_price(self, zhongshus: list[Zhongshu],
                                 price: float) -> Optional[Zhongshu]:
        """找到价格所在的中枢"""
        for zs in reversed(zhongshus):
            if zs.range_low <= price <= zs.range_high:
                return zs
        return None
