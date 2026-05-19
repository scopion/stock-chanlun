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

    def detect_segments(self, min_overlap_bis: int = 3,
                        max_iterations: int = 10000,
                        max_bi_per_segment: int = 18) -> list[XiangSegment]:
        """
        检测线段（基于重叠 + 反向破坏判断）

        max_bi_per_segment: 单线段最多包含的笔数，防止巨型线段吞噬整段历史。
        日线 500 根 K 约 30-50 笔，限制 18 笔/段可得 2-4 段。

        算法：
        1. 从第一笔开始，尝试建立线段
        2. 线段包含所有与当前"重叠箱体"有交集的笔（上限 max_bi_per_segment）
        3. 当遇到不重叠的笔时：
           - 若该笔反向破坏了线段起点 → 纳入该笔后终止线段
           - 否则 → 线段在此结束
        4. 继续从下一个未处理的笔开始
        """
        if len(self.bis) < min_overlap_bis:
            return []

        segments: list[XiangSegment] = []
        i = 0
        iterations = 0

        while i <= len(self.bis) - min_overlap_bis:
            iterations += 1
            if iterations > max_iterations:
                break

            # 检查起始3笔是否有重叠
            group = self.bis[i:i + min_overlap_bis]
            if not self._has_overlap(group):
                i += 1
                continue

            # 构建线段（限制最大笔数防止巨型线段）
            seg, next_i = self._build_one_segment(
                i, len(segments) + 1, max_bi_count=max_bi_per_segment)
            segments.append(seg)
            i = next_i

        return segments

    def _build_one_segment(self, start_idx: int,
                           seg_num: int,
                           max_bi_count: int = 0) -> tuple[XiangSegment, int]:
        """从 start_idx 开始构建一条线段，返回 (线段, 下一索引)

        max_bi_count: 单线段最多包含的笔数（0=不限制）。
        防止极宽区间吞噬全部历史笔形成巨型线段。
        """
        first = self.bis[start_idx]
        direction = first.direction
        seg_high = first.high
        seg_low = first.low
        seg_start = first.start
        seg_end = first.end
        bi_ids = [first.id]
        # 记录线段起点的关键价格（用于破坏判断）
        start_low = first.low
        start_high = first.high

        j = start_idx + 1
        while j < len(self.bis):
            nxt = self.bis[j]

            # 容量已满 → 停止扩展，在当前位置结束线段
            if max_bi_count > 0 and len(bi_ids) >= max_bi_count:
                break

            if self._overlaps(nxt, seg_high, seg_low):
                # 重叠 → 纳入线段，扩展箱体
                bi_ids.append(nxt.id)
                seg_high = max(seg_high, nxt.high)
                seg_low = min(seg_low, nxt.low)
                seg_end = nxt.end
                j += 1
            else:
                # 不重叠 → 检查是否为反向破坏
                destroyed = False
                if direction == "up" and nxt.low < start_low:
                    destroyed = True
                elif direction == "down" and nxt.high > start_high:
                    destroyed = True

                if destroyed:
                    bi_ids.append(nxt.id)
                    seg_high = max(seg_high, nxt.high)
                    seg_low = min(seg_low, nxt.low)
                    seg_end = nxt.end
                    j += 1
                break

        seg = XiangSegment(
            id=f"xiang_{seg_num}",
            start=seg_start,
            end=seg_end,
            direction=direction,
            high=seg_high,
            low=seg_low,
            bi_ids=bi_ids,
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
