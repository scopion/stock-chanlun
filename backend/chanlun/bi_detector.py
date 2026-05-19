"""
笔检测器 - 基于分型识别笔
"""
import pandas as pd
from typing import Optional
from datetime import datetime
from .elements import Bi
from .fenxing_detector import FenxingDetector, Fenxing


class BiDetector:
    """
    笔规则:
    1. 顶分型 + 底分型 = 一笔(向上笔: 底->顶, 向下笔: 顶->底)
    2. 笔至少需要5根K线(含分型)
    3. 同级别笔由连续顶底分型构成
    4. 同类型分型振幅>=7%时保留双方并成笔(捕捉单边行情中缺失的反向分型)
    """

    SAME_TYPE_AMP_THRESHOLD = 0.07

    def __init__(self, klines: pd.DataFrame):
        self.klines = klines.reset_index(drop=True)
        self._fenxing_detector = FenxingDetector(klines)
        self._fenxings: list[Fenxing] = []

    @staticmethod
    def compress_fenxings(fenxings: list[Fenxing],
                          amp_threshold: float = 0.07) -> list[Fenxing]:
        """
        压缩分型序列:
        - 连续不同类型 -> 保留
        - 连续同类型 -> 保留更极值者
        - 若同类型间振幅 >= amp_threshold -> 两者都保留(单边大行情成笔用)
        """
        if not fenxings:
            return []

        out: list[Fenxing] = [fenxings[0]]
        for fx in fenxings[1:]:
            last = out[-1]
            if fx.type != last.type:
                out.append(fx)
                continue

            # 同类型: 先算振幅
            if fx.type == "top":
                amp = (fx.high - last.high) / last.high if last.high > 0 else 0
                keep_both = amp >= amp_threshold
                if keep_both:
                    out.append(fx)
                elif fx.high >= last.high:
                    out[-1] = fx
            else:  # bottom
                amp = (last.low - fx.low) / last.low if last.low > 0 else 0
                keep_both = amp >= amp_threshold
                if keep_both:
                    out.append(fx)
                elif fx.low <= last.low:
                    out[-1] = fx

        return out

    def detect(self, min_bars: int = 5) -> list[Bi]:
        """
        检测所有笔
        min_bars: 笔最少K线数(默认5根)
        增加同类型分型成笔: 两同类型分型振幅>=7%时形成一笔
        """
        self._fenxings = self.compress_fenxings(
            self._fenxing_detector.detect(),
            amp_threshold=self.SAME_TYPE_AMP_THRESHOLD)
        if len(self._fenxings) < 2:
            return []

        bis: list[Bi] = []
        i = 0

        while i < len(self._fenxings) - 1:
            fx1 = self._fenxings[i]
            fx2 = self._fenxings[i + 1]

            # 同类型分型 -> 检查振幅是否达标, 降级成笔
            if fx1.type == fx2.type:
                amp = self._same_type_amplitude(fx1, fx2)
                if amp >= self.SAME_TYPE_AMP_THRESHOLD:
                    bar_count = self._count_klines_between(fx1.date, fx2.date)
                    if bar_count >= min_bars:
                        if fx1.type == "top":
                            # 两顶之间: 向上笔(前顶当底, 后顶当顶)
                            bis.append(Bi(
                                id=f"bi_up_tt_{len(bis)+1}",
                                start=fx1.date, end=fx2.date,
                                direction="up",
                                high=float(fx2.high),
                                low=float(fx1.low),
                                start_price=float(fx1.low),
                                end_price=float(fx2.high),
                            ))
                        else:
                            # 两底之间: 向下笔(前底当顶, 后底当底)
                            bis.append(Bi(
                                id=f"bi_down_bb_{len(bis)+1}",
                                start=fx1.date, end=fx2.date,
                                direction="down",
                                high=float(fx1.high),
                                low=float(fx2.low),
                                start_price=float(fx1.high),
                                end_price=float(fx2.low),
                            ))
                i += 1
                continue

            # 不同类型分型 -> 标准笔
            if not self._is_valid_bi_pair(fx1, fx2, min_bars):
                i += 1
                continue

            if fx1.type == "bottom" and fx2.type == "top":
                bis.append(Bi(
                    id=f"bi_up_{len(bis)+1}",
                    start=fx1.date,
                    end=fx2.date,
                    direction="up",
                    high=float(fx2.high),
                    low=float(fx1.low),
                    start_price=float(fx1.low),
                    end_price=float(fx2.high),
                ))
                i += 1

            elif fx1.type == "top" and fx2.type == "bottom":
                bis.append(Bi(
                    id=f"bi_down_{len(bis)+1}",
                    start=fx1.date,
                    end=fx2.date,
                    direction="down",
                    high=float(fx1.high),
                    low=float(fx2.low),
                    start_price=float(fx1.high),
                    end_price=float(fx2.low),
                ))
                i += 1
            else:
                i += 1

        # 后处理: 填补笔间空白(分型缺失导致的大区间无笔)
        bis = self._fill_bi_gaps(bis, min_bars)

        return bis

    def _fill_bi_gaps(self, bis: list[Bi], min_bars: int) -> list[Bi]:
        """
        填补相邻笔之间的空白区间:
        若两笔之间价格涨跌幅>=7%且K线足够, 插入一笔
        """
        if len(bis) < 1:
            return bis

        GAP_THRESHOLD = 0.07  # 7%
        filled: list[Bi] = [bis[0]]

        for i in range(1, len(bis)):
            prev = filled[-1]
            curr = bis[i]

            # 找空白区间: prev.end ~ curr.start
            gap_mask = ((self.klines['date'] > prev.end)
                        & (self.klines['date'] < curr.start))
            gap_df = self.klines[gap_mask]
            if len(gap_df) < min_bars:
                filled.append(curr)
                continue

            gap_high = float(gap_df['high'].max())
            gap_low = float(gap_df['low'].min())
            if gap_low <= 0:
                filled.append(curr)
                continue

            # 从 prev 结尾到 gap 内部的涨跌幅
            change_up = (gap_high - prev.low) / prev.low
            change_down = (prev.high - gap_low) / prev.high

            if change_up >= GAP_THRESHOLD:
                # 空白区间向上突破 -> 插入向上笔
                filled.append(Bi(
                    id=f"bi_up_gap_{len(filled)+1}",
                    start=prev.end,
                    end=curr.start,
                    direction="up",
                    high=gap_high,
                    low=min(prev.low, gap_low),
                    start_price=float(prev.end_price),
                    end_price=gap_high,
                ))
            elif change_down >= GAP_THRESHOLD:
                # 空白区间向下突破 -> 插入向下笔
                filled.append(Bi(
                    id=f"bi_down_gap_{len(filled)+1}",
                    start=prev.end,
                    end=curr.start,
                    direction="down",
                    high=max(prev.high, gap_high),
                    low=gap_low,
                    start_price=float(prev.end_price),
                    end_price=gap_low,
                ))

            filled.append(curr)

        return filled

    def _is_valid_bi_pair(self, fx1: Fenxing, fx2: Fenxing,
                          min_bars: int) -> bool:
        """
        校验两个分型是否构成有效笔:
        1. K线数量 >= min_bars(含分型)
        2. 分型间隔 >= 3 个索引位(确保至少1根独立K线)
           分型占3根: [i-1,i,i+1], 间隔3意味着两分型窗口中心距离>=3
        """
        bar_count = self._count_klines_between(fx1.date, fx2.date)
        if bar_count < min_bars:
            return False
        if abs(fx2.index - fx1.index) < 3:
            return False
        return True

    @staticmethod
    def _same_type_amplitude(fx1: Fenxing, fx2: Fenxing) -> float:
        """两同类型分型之间的振幅(用于判断是否需要补笔)"""
        if fx1.type != fx2.type:
            return 0.0
        if fx1.type == "top":
            if fx1.high <= 0:
                return 0.0
            return (fx2.high - fx1.high) / fx1.high
        else:
            if fx1.low <= 0:
                return 0.0
            return (fx1.low - fx2.low) / fx1.low

    def _count_klines_between(self, start: datetime, end: datetime) -> int:
        """计算两个时间之间的K线数量"""
        mask = (self.klines['date'] >= start) & (self.klines['date'] <= end)
        return int(mask.sum())
