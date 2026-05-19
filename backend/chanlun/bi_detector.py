"""
笔检测器 — 基于分型识别笔
"""
import pandas as pd
from typing import Optional
from datetime import datetime
from .elements import Bi
from .fenxing_detector import FenxingDetector, Fenxing


class BiDetector:
    """
    笔规则:
    1. 顶分型 + 底分型 = 一笔（向上笔: 底→顶，向下笔: 顶→底）
    2. 笔至少需要5根K线（含分型）
    3. 同级别笔由连续顶底分型构成
    """

    def __init__(self, klines: pd.DataFrame):
        self.klines = klines.reset_index(drop=True)
        self._fenxing_detector = FenxingDetector(klines)
        self._fenxings: list[Fenxing] = []

    @staticmethod
    def compress_fenxings(fenxings: list[Fenxing]) -> list[Fenxing]:
        """
        压缩分型序列：连续同类型分型仅保留更“极值”的那个。
        - 连续 top：保留 high 更高者
        - 连续 bottom：保留 low 更低者
        """
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
            else:  # bottom
                if fx.low <= last.low:
                    out[-1] = fx

        return out

    def detect(self, min_bars: int = 5) -> list[Bi]:
        """
        检测所有笔
        min_bars: 笔最少K线数（默认5根）
        增加独立K线校验：两个分型之间至少有一根不属于两者的K线
        """
        self._fenxings = self.compress_fenxings(self._fenxing_detector.detect())
        if len(self._fenxings) < 2:
            return []

        bis: list[Bi] = []
        i = 0

        while i < len(self._fenxings) - 1:
            fx1 = self._fenxings[i]
            fx2 = self._fenxings[i + 1]

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

        return bis

    def _is_valid_bi_pair(self, fx1: Fenxing, fx2: Fenxing,
                          min_bars: int) -> bool:
        """
        校验两个分型是否构成有效笔：
        1. K线数量 >= min_bars（含分型）
        2. 分型间隔 >= 3 个索引位（确保至少1根独立K线）
           分型占3根：[i-1,i,i+1]，间隔3意味着两分型窗口中心距离>=3
        """
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
