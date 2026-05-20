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
    3. 笔间空白段振幅>=10%时补一笔
    """

    GAP_AMP_THRESHOLD = 0.10  # 空白段补笔振幅阈值 10%

    def __init__(self, klines: pd.DataFrame):
        self.klines = klines.reset_index(drop=True)
        self._fenxing_detector = FenxingDetector(klines)
        self._fenxings: list[Fenxing] = []

    @staticmethod
    def compress_fenxings(fenxings: list[Fenxing]) -> list[Fenxing]:
        """压缩分型序列: 连续同类型仅保留更极值者"""
        if not fenxings:
            return []

        out: list[Fenxing] = [fenxings[0]]
        for fx in fenxings[1:]:
            last = out[-1]
            if fx.type != last.type:
                out.append(fx)
                continue
            if fx.type == "top":
                if fx.high >= last.high:
                    out[-1] = fx
            else:
                if fx.low <= last.low:
                    out[-1] = fx
        return out

    def detect(self, min_bars: int = 5) -> list[Bi]:
        """检测所有笔, 含空白段补笔"""
        raw_fenxings = self._fenxing_detector.detect()
        self._fenxings = self.compress_fenxings(raw_fenxings)
        if len(self._fenxings) < 2:
            return []

        # 标准笔
        bis: list[Bi] = []
        i = 0
        while i < len(self._fenxings) - 1:
            fx1 = self._fenxings[i]
            fx2 = self._fenxings[i + 1]
            if fx1.type == fx2.type:
                i += 1
                continue
            if not self._is_valid_bi_pair(fx1, fx2, min_bars):
                i += 1
                continue
            if fx1.type == "bottom" and fx2.type == "top":
                bis.append(Bi(
                    id=f"bi_up_{len(bis)+1}",
                    start=fx1.date, end=fx2.date,
                    direction="up",
                    high=float(fx2.high), low=float(fx1.low),
                    start_price=float(fx1.low), end_price=float(fx2.high),
                ))
            elif fx1.type == "top" and fx2.type == "bottom":
                bis.append(Bi(
                    id=f"bi_down_{len(bis)+1}",
                    start=fx1.date, end=fx2.date,
                    direction="down",
                    high=float(fx1.high), low=float(fx2.low),
                    start_price=float(fx1.high), end_price=float(fx2.low),
                ))
            i += 1

        # 空白段补笔: 相邻笔之间振幅>=10%时插入一笔
        bis = self._fill_bi_gaps(bis, min_bars)
        return bis

    def _fill_bi_gaps(self, bis: list[Bi], min_bars: int) -> list[Bi]:
        """笔间空白段振幅>=10%时补一笔"""
        if len(bis) < 1:
            return bis

        filled: list[Bi] = [bis[0]]
        for i in range(1, len(bis)):
            prev = filled[-1]
            curr = bis[i]

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

            # 振幅 = (最高-最低)/最低
            amp = (gap_high - gap_low) / gap_low

            if amp >= self.GAP_AMP_THRESHOLD:
                # 按价格方向决定笔方向
                if gap_high - gap_low >= 0:
                    # 向上
                    filled.append(Bi(
                        id=f"bi_up_gap_{len(filled)+1}",
                        start=prev.end, end=curr.start,
                        direction="up",
                        high=gap_high, low=gap_low,
                        start_price=gap_low,
                        end_price=gap_high,
                    ))
                else:
                    # 向下
                    filled.append(Bi(
                        id=f"bi_down_gap_{len(filled)+1}",
                        start=prev.end, end=curr.start,
                        direction="down",
                        high=gap_high, low=gap_low,
                        start_price=gap_high,
                        end_price=gap_low,
                    ))

            filled.append(curr)

        return filled

    def _is_valid_bi_pair(self, fx1: Fenxing, fx2: Fenxing,
                          min_bars: int) -> bool:
        """校验分型对: K线数量>=min_bars 且分型间隔>=3索引位"""
        bar_count = self._count_klines_between(fx1.date, fx2.date)
        if bar_count < min_bars:
            return False
        if abs(fx2.index - fx1.index) < 3:
            return False
        return True

    def _count_klines_between(self, start: datetime, end: datetime) -> int:
        """计算两个时间之间的K线数量"""
        mask = (self.klines['date'] >= start) & (self.klines['date'] <= end)
        return int(mask.sum())
