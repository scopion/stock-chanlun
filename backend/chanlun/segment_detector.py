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
        检测线段: 每 3 笔构成一段, 尾部不足 3 笔也成段
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

            # 取至多 3 笔
            end = min(i + 3, len(self.bis))
            seg_bis = self.bis[i:end]

            rng_high = max(b.high for b in seg_bis)
            rng_low = min(b.low for b in seg_bis)
            up_n = sum(1 for b in seg_bis if b.direction == "up")
            down_n = sum(1 for b in seg_bis if b.direction == "down")
            seg_dir = "up" if up_n >= down_n else "down"

            segments.append(XiangSegment(
                id=f"xiang_{len(segments)+1}",
                start=seg_bis[0].start,
                end=seg_bis[-1].end,
                direction=seg_dir,
                high=rng_high,
                low=rng_low,
                bi_ids=[b.id for b in seg_bis],
                level=2,
            ))
            i = end

        return segments

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
