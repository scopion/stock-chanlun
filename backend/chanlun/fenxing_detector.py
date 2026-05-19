"""
分型检测器 — 顶分型 & 底分型识别
"""
import pandas as pd
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional


@dataclass
class Fenxing:
    """分型"""
    date: datetime
    type: Literal["top", "bottom"]
    high: float
    low: float
    index: int


class FenxingDetector:
    """
    顶分型: 中间K线高点最高、低点也最高 → 顶
    底分型: 中间K线高点最低、低点也最低 → 底
    """

    def __init__(self, klines: pd.DataFrame):
        """
        klines: DataFrame, sorted by date, columns: date/open/high/low/close/volume
        """
        self.klines = klines.reset_index(drop=True)
        self._process_inclusion()

    def _process_inclusion(self):
        """
        处理包含关系（缠论标准规则）：

        包含判断：
        - prev 包含 cur: prev.low <= cur.low AND prev.high >= cur.high
        - cur  包含 prev: cur.low  <= prev.low AND cur.high  >= prev.high

        合并方向由「最近两根非包含K线的趋势方向」决定（不是由单根K线自身决定）：
        - 向上趋势（前一根低/高点均低于后一根）→ 取高高（保留最高高点、较高低点）
        - 向下趋势（前一根低/高点均高于后一根）→ 取低低（保留最低低点、较低高点）

        趋势方向仅在无包含关系的相邻K线对上更新，包含合并时沿用之前的方向。
        """
        rows = self.klines.to_dict("records")
        result = [rows[0]]
        # True = 向上趋势, False = 向下趋势, None = 尚未确定
        direction_up: Optional[bool] = None

        for i in range(1, len(rows)):
            cur = rows[i]
            prev = result[-1]

            prev_contains_cur = (prev["low"] <= cur["low"]
                                 and prev["high"] >= cur["high"])
            cur_contains_prev = (cur["low"] <= prev["low"]
                                 and cur["high"] >= prev["high"])
            has_inclusion = prev_contains_cur or cur_contains_prev

            if has_inclusion:
                # 方向未确定时，用两根K线的重心关系初始化
                if direction_up is None:
                    direction_up = (
                        (prev["high"] + prev["low"])
                        < (cur["high"] + cur["low"])
                    )

                # 日期：谁包含对方则保留谁的日期（cur包含prev时取cur日期）
                new_date = cur["date"] if cur_contains_prev else prev["date"]

                if direction_up:
                    # 向上趋势 → 取高高
                    result[-1] = {
                        "date": new_date,
                        "open": prev["open"],
                        "high": max(prev["high"], cur["high"]),
                        "low": max(prev["low"], cur["low"]),
                        "close": cur["close"],
                        "volume": prev.get("volume", 0) + cur.get("volume", 0),
                    }
                else:
                    # 向下趋势 → 取低低
                    result[-1] = {
                        "date": new_date,
                        "open": prev["open"],
                        "high": max(prev["high"], cur["high"]),
                        "low": min(prev["low"], cur["low"]),
                        "close": cur["close"],
                        "volume": prev.get("volume", 0) + cur.get("volume", 0),
                    }
            else:
                # 无包含 → 追加当前K线，并根据最近两根非包含K线更新趋势方向
                result.append(cur)

                if len(result) >= 2:
                    p1, p2 = result[-2], result[-1]
                    if p2["high"] > p1["high"] and p2["low"] > p1["low"]:
                        direction_up = True
                    elif p2["high"] < p1["high"] and p2["low"] < p1["low"]:
                        direction_up = False
                    # 否则：K线方向不明确（如包含后首根K线与前一根呈内外包等），
                    # 保留之前的方向不变

        self.klines = pd.DataFrame(result).reset_index(drop=True)

    def detect(self) -> list[Fenxing]:
        """
        识别所有分型（标准五笔窗口）：
        顶分型 = 中间K线高点 > 左1 且 > 右1，且低点 > 左1 且 > 右1
        底分型 = 中间K线高点 < 左1 且 < 右1，且低点 < 左1 且 < 右1
        窗口取前后各1根（共3根），严格对应缠论标准定义。
        """
        df = self.klines
        fenxings = []

        for i in range(1, len(df) - 1):
            prev = df.iloc[i - 1]
            middle = df.iloc[i]
            next_ = df.iloc[i + 1]

            mid_h, mid_l = middle['high'], middle['low']

            # 顶分型：中间K线"高"最高、"低"也最高（∧形）
            if (mid_h > prev['high'] and mid_h > next_['high'] and
                    mid_l > prev['low'] and mid_l > next_['low']):
                fenxings.append(Fenxing(
                    date=middle['date'],
                    type="top",
                    high=float(mid_h),
                    low=float(mid_l),
                    index=i
                ))
            # 底分型：中间K线"高"最低、"低"也最低（∨形）
            elif (mid_h < prev['high'] and mid_h < next_['high'] and
                  mid_l < prev['low'] and mid_l < next_['low']):
                fenxings.append(Fenxing(
                    date=middle['date'],
                    type="bottom",
                    high=float(mid_h),
                    low=float(mid_l),
                    index=i
                ))

        return fenxings
