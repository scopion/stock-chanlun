"""
买卖点判定模块 — 基于MACD标准背驰检测
"""
import pandas as pd
import numpy as np
from typing import Optional, Literal
from datetime import datetime
from .elements import Bi, XiangSegment, Zhongshu, BuySellPoint, SupportResistanceLevel

# 成交量背驰阈值: 后段总量 < 前段总量 × 0.7 确认背驰
_VOL_DIVERGENCE_RATIO = 0.70


def _calc_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26,
               signal: int = 9) -> pd.DataFrame:
    """计算 MACD 指标列"""
    df = df.copy()
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    df['dif'] = ema_fast - ema_slow
    df['dea'] = df['dif'].ewm(span=signal, adjust=False).mean()
    df['bar'] = (df['dif'] - df['dea']) * 2
    return df


def _macd_area_directional(bars: pd.Series, seg_type: str) -> float:
    """与走势同向的 MACD 柱面积：顶背驰只算红柱(>0)，底背驰只算绿柱(<0)"""
    arr = bars.to_numpy(dtype=float)
    if seg_type == "top":
        return float(np.nansum(np.maximum(arr, 0.0)))
    return float(np.nansum(np.abs(np.minimum(arr, 0.0))))


def _bis_making_higher_highs(bis: list) -> bool:
    """最近2根向上笔的高点是否在抬高（确认上涨方向）"""
    up_bis = [b for b in bis if hasattr(b, 'direction') and b.direction == "up"]
    if len(up_bis) < 2:
        return False
    return up_bis[-1].high > up_bis[-2].high


def _bis_making_lower_lows(bis: list) -> bool:
    """最近2根向下笔的低点是否在降低（确认下跌方向）"""
    down_bis = [b for b in bis if hasattr(b, 'direction') and b.direction == "down"]
    if len(down_bis) < 2:
        return False
    return down_bis[-1].low < down_bis[-2].low


class SignalDetector:
    """
    三类买卖点判定（基于 MACD 面积的标准背驰检测）：

    一买(1st Buy): 下跌趋势背驰点
      → 两个相邻向下段，价格创新低但MACD绿柱面积不创新低
    二买(2nd Buy): 一买后回调低点（不破一买前低）
    三买(3rd Buy): 突破中枢后回踩，不跌入中枢

    一卖/二卖/三卖: 对称逻辑（上涨趋势）
    """

    def __init__(self, bis: list[Bi],
                 segments: list[XiangSegment],
                 zhongshus: list[Zhongshu],
                 level: str = "daily",
                 klines_df: Optional[pd.DataFrame] = None):
        self.bis = bis
        self.segments = segments
        self.zhongshus = zhongshus
        self.level = level
        self._macd_df: Optional[pd.DataFrame] = None
        if klines_df is not None:
            self._macd_df = _calc_macd(klines_df.copy())

    def _macd_area_for_entity(self, entity, seg_type: str) -> float:
        """提取 entity 时间区间内的 MACD 同向柱面积"""
        if self._macd_df is None:
            return 0.0
        mask = (
            (self._macd_df['date'] >= entity.start)
            & (self._macd_df['date'] <= entity.end)
        )
        subset = self._macd_df.loc[mask, 'bar']
        if len(subset) == 0:
            return 0.0
        return _macd_area_directional(subset, seg_type)

    def _dif_peak_for_entity(self, entity, seg_type: str) -> float:
        """提取 entity 区间内 DIF 的极值（顶背驰取高点，底背驰取低点）"""
        if self._macd_df is None:
            return 0.0
        mask = (
            (self._macd_df['date'] >= entity.start)
            & (self._macd_df['date'] <= entity.end)
        )
        subset = self._macd_df.loc[mask, 'dif']
        if len(subset) == 0:
            return 0.0
        if seg_type == "top":
            return float(subset.max())  # 顶背驰：DIF 高点
        return float(subset.min())      # 底背驰：DIF 低点

    def _volume_for_entity(self, entity) -> float:
        """提取 entity 区间内的总成交量"""
        if self._macd_df is None:
            return 0.0
        mask = (
            (self._macd_df['date'] >= entity.start)
            & (self._macd_df['date'] <= entity.end)
        )
        subset = self._macd_df.loc[mask, 'volume'] if 'volume' in self._macd_df.columns else None
        if subset is None or len(subset) == 0:
            return 0.0
        return float(subset.sum())

    def detect_all(self) -> list[BuySellPoint]:
        """检测所有买卖点（含盘整背驰）"""
        signals = []
        first_buys = self._detect_1st_buy()
        signals.extend(first_buys)
        signals.extend(self._detect_2nd_buy(first_buys))
        signals.extend(self._detect_3rd_buy())
        first_sells = self._detect_1st_sell()
        signals.extend(first_sells)
        signals.extend(self._detect_2nd_sell(first_sells))
        signals.extend(self._detect_3rd_sell())
        signals.extend(self._detect_consolidation_divergence())
        return sorted(signals, key=lambda s: s.datetime)

    # ── 下跌买卖点 ──────────────────────────────────────────────

    def _detect_1st_buy(self) -> list[BuySellPoint]:
        """
        一买: 成交量背驰法

        条件:
        1. 价格: 后一段创新低 (curr.low < prev.low)
        2. 成交量: 后一段总量 < 前一段总量 × 70%（资金推动力度衰竭）
        """
        candidates: list[tuple[int, BuySellPoint]] = []

        down_segments = [s for s in self.segments if s.direction == "down"]
        if len(down_segments) < 2:
            down_bis = [b for b in self.bis if b.direction == "down"]
            if len(down_bis) < 2:
                return []
            entities = down_bis
        else:
            entities = down_segments

        for i in range(1, len(entities)):
            prev = entities[i - 1]
            curr = entities[i]

            if curr.low >= prev.low:
                continue

            vol_prev = self._volume_for_entity(prev)
            vol_curr = self._volume_for_entity(curr)
            if vol_prev <= 0 or vol_curr <= 0:
                continue
            if vol_curr >= vol_prev * _VOL_DIVERGENCE_RATIO:
                continue

            vol_ratio = vol_curr / vol_prev
            prob = round(min(1.0, (1 - vol_ratio) * 2 + 0.4), 2)
            candidates.append((i, BuySellPoint(
                type="一买",
                level=self.level,
                price=float(curr.low),
                datetime=curr.end,
                confidence=prob,
                stop_loss=float(curr.low * 0.97),
                description=f"背驰一买: 价格{curr.low:.2f}新低，量缩至{vol_ratio:.0%}"
            )))

        if candidates:
            return [candidates[-1][1]]
        return []

    def _detect_2nd_buy(self, first_buys: list[BuySellPoint]) -> list[BuySellPoint]:
        """
        二买: 只参照最近一个一买（避免旧一买产生的二买与当前趋势矛盾）
        """
        signals: list[BuySellPoint] = []
        if not first_buys or not self.bis:
            return signals

        # 只用最近一个一买作为参照
        fb = first_buys[-1]
        after_first = [b for b in self.bis
                      if b.direction == "down"
                      and b.end > fb.datetime]
        for b in after_first:
            if b.low >= fb.price * 0.97:
                signals.append(BuySellPoint(
                    type="二买",
                    level=self.level,
                    price=float(b.low),
                    datetime=b.end,
                    confidence=0.70,
                    stop_loss=float(min(b.low * 0.97, fb.price * 0.95)),
                    description=f"回调二买: 回踩{b.low:.2f}不破一买{fb.price:.2f}"
                ))
        return signals

    def _detect_3rd_buy(self) -> list[BuySellPoint]:
        """
        三买: 向上笔突破某中枢后，回踩低点不跌入该中枢上沿。
        遍历所有中枢，支持多中枢三买信号。
        """
        signals = []
        if not self.zhongshus or not self.bis:
            return signals

        for zs in reversed(self.zhongshus):
            # 找向上笔是否突破本中枢（不再要求 b.end > zs.end，允许中枢内突破）
            break_up = None
            for b in self.bis:
                if b.direction == "up" and b.high > zs.range_high:
                    break_up = b
                    break

            if not break_up:
                continue

            # 找突破后紧接着的下探笔
            retest_candidates = [
                b for b in self.bis
                if b.direction == "down" and b.start > break_up.end
            ]
            if not retest_candidates:
                continue

            retest = retest_candidates[0]
            # 回踩低点不跌入中枢上沿 = 三买成立
            if retest.low > zs.range_high:
                signals.append(BuySellPoint(
                    type="三买",
                    level=self.level,
                    price=float(retest.low),
                    datetime=retest.end,
                    confidence=0.80,
                    stop_loss=float(zs.range_low),
                    take_profit=float(break_up.high * 1.05),
                    description=f"三买: 回踩{retest.low:.2f}不破中枢{zs.range_high:.2f}"
                ))

        return signals

    # ── 上涨买卖点 ──────────────────────────────────────────────

    def _detect_1st_sell(self) -> list[BuySellPoint]:
        """
        一卖: 成交量背驰法

        条件:
        1. 价格: 后一段创新高 (curr.high > prev.high)
        2. 成交量: 后一段总量 < 前一段总量 × 70%（资金推动力度衰竭）
        """
        candidates: list[tuple[int, BuySellPoint]] = []

        up_segments = [s for s in self.segments if s.direction == "up"]
        if len(up_segments) < 2:
            up_bis = [b for b in self.bis if b.direction == "up"]
            if len(up_bis) < 2:
                return []
            entities = up_bis
        else:
            entities = up_segments

        for i in range(1, len(entities)):
            prev = entities[i - 1]
            curr = entities[i]

            if curr.high <= prev.high:
                continue

            vol_prev = self._volume_for_entity(prev)
            vol_curr = self._volume_for_entity(curr)
            if vol_prev <= 0 or vol_curr <= 0:
                continue
            if vol_curr >= vol_prev * _VOL_DIVERGENCE_RATIO:
                continue

            vol_ratio = vol_curr / vol_prev
            prob = round(min(1.0, (1 - vol_ratio) * 2 + 0.4), 2)
            candidates.append((i, BuySellPoint(
                type="一卖",
                level=self.level,
                price=float(curr.high),
                datetime=curr.end,
                confidence=prob,
                stop_loss=float(curr.high * 1.03),
                description=f"背驰一卖: 价格{curr.high:.2f}新高，量缩至{vol_ratio:.0%}"
            )))

        if candidates:
            return [candidates[-1][1]]
        return []

    def _detect_2nd_sell(self, first_sells: list[BuySellPoint]) -> list[BuySellPoint]:
        """
        二卖: 只参照最近一个一卖（避免旧一卖产生的二卖与当前趋势矛盾）
        """
        signals: list[BuySellPoint] = []
        if not first_sells or not self.bis:
            return signals

        # 只用最近一个一卖作为参照
        fs = first_sells[-1]
        after_first = [b for b in self.bis
                      if b.direction == "up"
                      and b.end > fs.datetime]
        for b in after_first:
            if b.high <= fs.price * 1.03:
                signals.append(BuySellPoint(
                    type="二卖",
                    level=self.level,
                    price=float(b.high),
                    datetime=b.end,
                    confidence=0.65,
                    description=f"二卖: 反弹{b.high:.2f}不破一卖{fs.price:.2f}"
                ))
        return signals

    def _detect_3rd_sell(self) -> list[BuySellPoint]:
        """
        三卖: 向下笔跌破某中枢后，反弹高点不突破该中枢下沿。
        遍历所有中枢，支持多中枢三卖信号。
        """
        signals = []
        if not self.zhongshus or not self.bis:
            return signals

        for zs in reversed(self.zhongshus):
            # 找向下笔是否跌破本中枢（不再要求 b.end > zs.end，允许中枢内跌破）
            break_down = None
            for b in self.bis:
                if b.direction == "down" and b.low < zs.range_low:
                    break_down = b
                    break

            if not break_down:
                continue

            # 找跌破后紧接着的上探笔
            retest_candidates = [
                b for b in self.bis
                if b.direction == "up" and b.start > break_down.end
            ]
            if not retest_candidates:
                continue

            retest = retest_candidates[0]
            if retest.high < zs.range_low:
                signals.append(BuySellPoint(
                    type="三卖",
                    level=self.level,
                    price=float(retest.high),
                    datetime=retest.end,
                    confidence=0.75,
                    description=f"三卖: 反弹{retest.high:.2f}不破中枢{zs.range_low:.2f}"
                ))

        return signals

    # ── 盘整背驰 ────────────────────────────────────────────────

    def _detect_consolidation_divergence(self) -> list[BuySellPoint]:
        """
        盘整背驰(成交量法): 中枢内反复试探边界时量缩确认衰竭

        顶盘整背驰(卖): 中枢内向上段推高但成交量递减
        底盘整背驰(买): 中枢内向下段探低但成交量递减
        """
        signals: list[BuySellPoint] = []
        if len(self.zhongshus) == 0 or len(self.segments) < 2:
            return signals

        last_zs = self.zhongshus[-1]

        # 顶盘整背驰
        up_in_zs = [
            s for s in self.segments
            if s.direction == "up"
            and s.high >= last_zs.range_high * 0.95
            and s.start >= last_zs.start
        ]
        for i in range(1, len(up_in_zs)):
            prev = up_in_zs[i - 1]
            curr = up_in_zs[i]
            if curr.high <= prev.high:
                continue
            vol_prev = self._volume_for_entity(prev)
            vol_curr = self._volume_for_entity(curr)
            if vol_prev <= 0 or vol_curr <= 0:
                continue
            if vol_curr >= vol_prev * _VOL_DIVERGENCE_RATIO:
                continue
            vol_ratio = vol_curr / vol_prev
            prob = round(min(1.0, (1 - vol_ratio) * 2 + 0.3), 2)
            signals.append(BuySellPoint(
                type="一卖",
                level=self.level,
                price=float(curr.high),
                datetime=curr.end,
                confidence=prob,
                stop_loss=float(curr.high * 1.03),
                description=f"盘整背驰卖: 中枢内{curr.high:.2f}新高量缩至{vol_ratio:.0%}"
            ))

        # 底盘整背驰
        down_in_zs = [
            s for s in self.segments
            if s.direction == "down"
            and s.low <= last_zs.range_low * 1.05
            and s.start >= last_zs.start
        ]
        for i in range(1, len(down_in_zs)):
            prev = down_in_zs[i - 1]
            curr = down_in_zs[i]
            if curr.low >= prev.low:
                continue
            vol_prev = self._volume_for_entity(prev)
            vol_curr = self._volume_for_entity(curr)
            if vol_prev <= 0 or vol_curr <= 0:
                continue
            if vol_curr >= vol_prev * _VOL_DIVERGENCE_RATIO:
                continue
            vol_ratio = vol_curr / vol_prev
            prob = round(min(1.0, (1 - vol_ratio) * 2 + 0.3), 2)
            signals.append(BuySellPoint(
                type="一买",
                level=self.level,
                price=float(curr.low),
                datetime=curr.end,
                confidence=prob,
                stop_loss=float(curr.low * 0.97),
                description=f"盘整背驰买: 中枢内{curr.low:.2f}新低量缩至{vol_ratio:.0%}"
            ))

        buy_signals = [s for s in signals if s.type == "一买"]
        sell_signals = [s for s in signals if s.type == "一卖"]
        result: list[BuySellPoint] = []
        if buy_signals:
            result.append(buy_signals[-1])
        if sell_signals:
            result.append(sell_signals[-1])
        return result

    def detect_trend(self, current_price: float | None = None) -> str:
        """
        走势类型判断（严格缠论定义）:

        上涨趋势: >=2 个中枢, 不重叠, 后一个在上方
        下跌趋势: >=2 个中枢, 不重叠, 后一个在下方
        盘整:     <=1 个中枢, 或>=2 个但全部重叠
        未知:     无中枢且笔不足
        """
        if not self.segments:
            return "未知"

        # ── 多中枢: 检查不重叠的中枢方向 ──
        if len(self.zhongshus) >= 2:
            up_gaps = 0
            down_gaps = 0
            overlap_count = 0
            for i in range(len(self.zhongshus) - 1):
                z1, z2 = self.zhongshus[i], self.zhongshus[i + 1]
                if z1.range_high < z2.range_low:
                    up_gaps += 1       # z2 完全在 z1 上方 → 向上离开
                elif z2.range_high < z1.range_low:
                    down_gaps += 1     # z2 完全在 z1 下方 → 向下离开
                else:
                    overlap_count += 1 # 中枢重叠

            # 所有相邻中枢都不重叠且方向一致 → 趋势
            non_overlap = (up_gaps + down_gaps)
            total_pairs = len(self.zhongshus) - 1

            if non_overlap == total_pairs and up_gaps == total_pairs:
                return "上涨"
            if non_overlap == total_pairs and down_gaps == total_pairs:
                return "下跌"

            # 有重叠或无一致方向 → 盘整
            return "盘整"

        # ── 单中枢 → 盘整（无论价格在上在下, 都只是离开盘整）──
        if len(self.zhongshus) == 1:
            return "盘整"

        # ── 无中枢 → 笔方向兜底 ──
        if len(self.bis) >= 4:
            all_bis = self.bis[-12:] if len(self.bis) >= 12 else self.bis
            short = all_bis[-5:] if len(all_bis) >= 5 else all_bis
            s_up = sum(1 for b in short if b.direction == "up")
            s_down = sum(1 for b in short if b.direction == "down")
            last3 = short[-3:] if len(short) >= 3 else short
            l3_up = sum(1 for b in last3 if b.direction == "up")
            l3_down = sum(1 for b in last3 if b.direction == "down")

            if l3_up == 3:
                return "上涨"
            if l3_down == 3:
                return "下跌"
            if l3_up == 2 and l3_down == 1 and _bis_making_higher_highs(short):
                return "上涨"
            if l3_down == 2 and l3_up == 1 and _bis_making_lower_lows(short):
                return "下跌"
            if s_up >= 4:
                return "上涨"
            if s_down >= 4:
                return "下跌"
            if s_up > s_down:
                return "上涨" if _bis_making_higher_highs(short) else "盘整"
            if s_down > s_up:
                return "下跌" if _bis_making_lower_lows(short) else "盘整"

        return "盘整"

    def detect_support_resistance(self, klines: list, signals: list[BuySellPoint]) -> list[SupportResistanceLevel]:
        """
        计算支撑位和阻力位

        支撑位来源:
        - 中枢下沿 (resistance=支撑)
        - 笔低点 / 线段低点 (support)
        - 历史K线低点附近 (support)
        - 买卖点价位 (signal)

        阻力位来源:
        - 中枢上沿 (resistance)
        - 笔高点 / 线段高点 (resistance)
        - 历史K线高点附近 (resistance)
        """
        levels: list[SupportResistanceLevel] = []

        # ── 1. 中枢 ──────────────────────────────
        for zs in self.zhongshus:
            levels.append(SupportResistanceLevel(
                type="support",
                price=zs.range_low,
                source="zhongshu",
                related_id=zs.id,
                datetime=zs.start,
                strength=0.85
            ))
            levels.append(SupportResistanceLevel(
                type="resistance",
                price=zs.range_high,
                source="zhongshu",
                related_id=zs.id,
                datetime=zs.start,
                strength=0.85
            ))

        # ── 2. 笔 ───────────────────────────────
        # 只取最近10笔，太多反而干扰
        recent_bis = self.bis[-10:]
        for b in recent_bis:
            if b.direction == "down":
                levels.append(SupportResistanceLevel(
                    type="support",
                    price=b.low,
                    source="bi_low",
                    related_id=b.id,
                    datetime=b.end,
                    strength=0.6
                ))
            else:
                levels.append(SupportResistanceLevel(
                    type="resistance",
                    price=b.high,
                    source="bi_high",
                    related_id=b.id,
                    datetime=b.end,
                    strength=0.6
                ))

        # ── 3. 线段 ─────────────────────────────
        recent_xiangs = self.segments[-6:]
        for x in recent_xiangs:
            if x.direction == "down":
                levels.append(SupportResistanceLevel(
                    type="support",
                    price=x.low,
                    source="kline_low",
                    related_id=x.id,
                    datetime=x.end,
                    strength=0.75
                ))
            else:
                levels.append(SupportResistanceLevel(
                    type="resistance",
                    price=x.high,
                    source="kline_high",
                    related_id=x.id,
                    datetime=x.end,
                    strength=0.75
                ))

        # ── 4. 买卖点 ────────────────────────────
        for sig in signals:
            if "买" in sig.type:
                levels.append(SupportResistanceLevel(
                    type="support",
                    price=sig.price,
                    source="signal",
                    related_id="",
                    datetime=sig.datetime,
                    strength=sig.confidence
                ))
            else:
                levels.append(SupportResistanceLevel(
                    type="resistance",
                    price=sig.price,
                    source="signal",
                    related_id="",
                    datetime=sig.datetime,
                    strength=sig.confidence
                ))

        # ── 5. 近期K线高低价 ─────────────────────
        if klines:
            recent_kl = klines[-20:]
            lows = [k for k in recent_kl if k.get("low")]
            highs = [k for k in recent_kl if k.get("high")]
            if lows:
                min_kl = min(lows, key=lambda x: x.get("low", float("inf")))
                levels.append(SupportResistanceLevel(
                    type="support",
                    price=float(min_kl.get("low")),
                    source="kline_low",
                    related_id="",
                    datetime=min_kl.get("date") if isinstance(min_kl, dict) else min_kl.date,
                    strength=0.5
                ))
            if highs:
                max_kl = max(highs, key=lambda x: x.get("high", float("-inf")))
                levels.append(SupportResistanceLevel(
                    type="resistance",
                    price=float(max_kl.get("high")),
                    source="kline_high",
                    related_id="",
                    datetime=max_kl.get("date") if isinstance(max_kl, dict) else max_kl.date,
                    strength=0.5
                ))

        # ── 去重：相同价格 ±0.5% 内的只保留最强的 ─────
        deduped: list[SupportResistanceLevel] = []
        seen_prices: dict[str, int] = {}  # key -> index in deduped

        def price_key(p: float) -> str:
            return f"{p:.2f}"

        for lvl in levels:
            pk = price_key(lvl.price)
            if pk not in seen_prices:
                seen_prices[pk] = len(deduped)
                deduped.append(lvl)
            else:
                existing = deduped[seen_prices[pk]]
                if lvl.strength > existing.strength:
                    deduped[seen_prices[pk]] = lvl

        # 按强度降序返回
        return sorted(deduped, key=lambda x: -x.strength)
