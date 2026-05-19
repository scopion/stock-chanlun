"""
买卖点判定模块 — 基于MACD标准背驰检测
"""
import pandas as pd
import numpy as np
from typing import Optional, Literal
from datetime import datetime
from .elements import Bi, XiangSegment, Zhongshu, BuySellPoint, SupportResistanceLevel

# MACD 相关常量（与 divergence.py 保持一致）
_MACD_WEAKEN_RATIO = 0.85
_MACD_AREA_EPS = 1e-15


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
        一买: 下跌趋势的MACD背驰点

        标准缠论条件:
        - 至少2个同向（向下）段/笔
        - 后一段价格创新低 (curr.low < prev.low)
        - 后一段 MACD 绿柱面积 < 前一段 × 85%（力度背驰）

        只返回最近的背驰点（一日一买只有一个真正的背驰终点），
        避免历史信号堆积干扰判断。
        """
        candidates: list[tuple[int, BuySellPoint]] = []

        # 先用线段判断，线段不足时用笔
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

            macd_pre_ok = False
            force_ratio = 1.0

            if self._macd_df is not None:
                macd_prev = self._macd_area_for_entity(prev, "bottom")
                macd_curr = self._macd_area_for_entity(curr, "bottom")
                if macd_prev > _MACD_AREA_EPS and macd_curr > _MACD_AREA_EPS:
                    force_ratio = macd_curr / macd_prev
                    if macd_curr < macd_prev * _MACD_WEAKEN_RATIO:
                        macd_pre_ok = True

            if not macd_pre_ok and self._macd_df is not None:
                continue

            if self._macd_df is None:
                prev_power = (prev.high - prev.low) / max(1, (prev.end - prev.start).total_seconds())
                curr_power = (curr.high - curr.low) / max(1, (curr.end - curr.start).total_seconds())
                if curr_power >= prev_power * 0.8:
                    continue
                force_ratio = curr_power / max(prev_power, 1e-12)

            prob = round(min(1.0, abs(1 - force_ratio) + 0.5), 2)
            candidates.append((i, BuySellPoint(
                type="一买",
                level=self.level,
                price=float(curr.low),
                datetime=curr.end,
                confidence=prob,
                stop_loss=float(curr.low * 0.97),
                description=f"背驰一买: 价格{curr.low:.2f}新低，MACD力度{force_ratio:.0%}<85%"
            )))

        # 只保留最后一条（最近的背驰点）
        if candidates:
            return [candidates[-1][1]]
        return []

    def _detect_2nd_buy(self, first_buys: list[BuySellPoint]) -> list[BuySellPoint]:
        """
        二买: 一买后的回调低点（不破一买点），取所有有效回踩
        """
        signals: list[BuySellPoint] = []
        if not first_buys or not self.bis:
            return signals

        for fb in first_buys:
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
        一卖: 上涨趋势的MACD背驰点
        条件: 价格创新高但MACD红柱面积缩小
        只返回最近一个背驰点。
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

            macd_pre_ok = False
            force_ratio = 1.0

            if self._macd_df is not None:
                macd_prev = self._macd_area_for_entity(prev, "top")
                macd_curr = self._macd_area_for_entity(curr, "top")
                if macd_prev > _MACD_AREA_EPS and macd_curr > _MACD_AREA_EPS:
                    force_ratio = macd_curr / macd_prev
                    if macd_curr < macd_prev * _MACD_WEAKEN_RATIO:
                        macd_pre_ok = True

            if not macd_pre_ok and self._macd_df is not None:
                continue

            if self._macd_df is None:
                prev_power = (prev.high - prev.low) / max(1, (prev.end - prev.start).total_seconds())
                curr_power = (curr.high - curr.low) / max(1, (curr.end - curr.start).total_seconds())
                if curr_power >= prev_power * 0.8:
                    continue
                force_ratio = curr_power / max(prev_power, 1e-12)

            prob = round(min(1.0, abs(1 - force_ratio) + 0.5), 2)
            candidates.append((i, BuySellPoint(
                type="一卖",
                level=self.level,
                price=float(curr.high),
                datetime=curr.end,
                confidence=prob,
                stop_loss=float(curr.high * 1.03),
                description=f"背驰一卖: 价格{curr.high:.2f}新高，MACD力度{force_ratio:.0%}<85%"
            )))

        if candidates:
            return [candidates[-1][1]]
        return []

    def _detect_2nd_sell(self, first_sells: list[BuySellPoint]) -> list[BuySellPoint]:
        """
        二卖: 一卖后反弹高点（不破一卖前高），取所有有效反弹
        """
        signals: list[BuySellPoint] = []
        if not first_sells or not self.bis:
            return signals

        for fs in first_sells:
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
        盘整背驰：中枢内的背驰检测

        标准缠论中，价格在中枢内反复试探边界时，若
        后一次试探比前一次力度更弱（MACD面积缩小），
        则构成盘整背驰，预示中枢即将被突破或反转。

        顶盘整背驰（卖点）：中枢内向上段推高但 MACD 红柱递减
        底盘整背驰（买点）：中枢内向下段探低但 MACD 绿柱递减
        """
        signals: list[BuySellPoint] = []
        if len(self.zhongshus) == 0 or len(self.segments) < 2:
            return signals

        last_zs = self.zhongshus[-1]

        # 取中枢范围内的向上段（触及上沿 95% 以内视为试探上沿）
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
            if self._macd_df is None:
                continue
            macd_prev = self._macd_area_for_entity(prev, "top")
            macd_curr = self._macd_area_for_entity(curr, "top")
            if macd_prev > _MACD_AREA_EPS and macd_curr < macd_prev * _MACD_WEAKEN_RATIO:
                ratio = macd_curr / macd_prev
                prob = round(min(1.0, abs(1 - ratio) + 0.4), 2)
                signals.append(BuySellPoint(
                    type="一卖",
                    level=self.level,
                    price=float(curr.high),
                    datetime=curr.end,
                    confidence=prob,
                    stop_loss=float(curr.high * 1.03),
                    description=f"盘整背驰卖: 中枢内{curr.high:.2f}新高但MACD力度{ratio:.0%}<85%"
                ))

        # 取中枢范围内的向下段（触及下沿 105% 以内视为试探下沿）
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
            if self._macd_df is None:
                continue
            macd_prev = self._macd_area_for_entity(prev, "bottom")
            macd_curr = self._macd_area_for_entity(curr, "bottom")
            if macd_prev > _MACD_AREA_EPS and macd_curr < macd_prev * _MACD_WEAKEN_RATIO:
                ratio = macd_curr / macd_prev
                prob = round(min(1.0, abs(1 - ratio) + 0.4), 2)
                signals.append(BuySellPoint(
                    type="一买",
                    level=self.level,
                    price=float(curr.low),
                    datetime=curr.end,
                    confidence=prob,
                    stop_loss=float(curr.low * 0.97),
                    description=f"盘整背驰买: 中枢内{curr.low:.2f}新低但MACD力度{ratio:.0%}<85%"
                ))

        # 盘整背驰只保留最近一组（买卖各一个）
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
        统一趋势判断（被缠论分析和 AI 策略共用）

        判断优先级：
        1. 多中枢：中枢重心方向 + 中枢间隙方向
        2. 单中枢：价格位置 + 线段方向
        3. 无中枢：价格创新高/新低 + 线段方向

        关键改进：中枢重心代替边沿严格单调（允许中枢扩展中的波动），
        中枢间隙取多数方向（代替纯线段计数）。
        """
        if not self.segments:
            return "未知"

        # ── 1. 多中枢 ──────────────────────────────────────────
        if len(self.zhongshus) >= 2:
            # 中枢重心（更稳定，不易受单根K线波动影响）
            centers = [(zs.range_high + zs.range_low) / 2
                       for zs in self.zhongshus]

            # 重心严格递增 → 上涨趋势
            if all(centers[i] < centers[i + 1]
                   for i in range(len(centers) - 1)):
                return "上涨"
            # 重心严格递减 → 下跌趋势
            if all(centers[i] > centers[i + 1]
                   for i in range(len(centers) - 1)):
                return "下跌"

            # 重心不单调但中枢间隙有方向 → 按间隙多数方向判定
            up_gaps = 0
            down_gaps = 0
            for i in range(len(self.zhongshus) - 1):
                z1, z2 = self.zhongshus[i], self.zhongshus[i + 1]
                if z1.range_high < z2.range_low:
                    up_gaps += 1          # z2 完全在 z1 上方
                elif z2.range_high < z1.range_low:
                    down_gaps += 1        # z2 完全在 z1 下方
                # 否则两个中枢有重叠 → 不算间隙

            if up_gaps > down_gaps:
                return "上涨"
            if down_gaps > up_gaps:
                return "下跌"

            # 中枢全部重叠 → 价格位置兜底
            if current_price is not None:
                last_zs = self.zhongshus[-1]
                if current_price > last_zs.range_high:
                    return "上涨"
                if current_price < last_zs.range_low:
                    return "下跌"
            return "盘整"

        # ── 2. 单中枢 ──────────────────────────────────────────
        if len(self.zhongshus) == 1:
            zs = self.zhongshus[0]
            if current_price is not None:
                if current_price > zs.range_high:
                    return "上涨"
                if current_price < zs.range_low:
                    return "下跌"

            # 中枢内 → 线段多数方向（需显著差异）
            recent = self.segments[-5:] if len(self.segments) >= 5 else self.segments
            ups = sum(1 for s in recent if s.direction == "up")
            downs = sum(1 for s in recent if s.direction == "down")
            if ups >= downs + 2:
                return "上涨"
            if downs >= ups + 2:
                return "下跌"
            return "盘整"

        # ── 3. 无中枢 ──────────────────────────────────────────
        recent_segs = self.segments[-5:] if len(self.segments) >= 5 else self.segments
        up_segs = [s for s in recent_segs if s.direction == "up"]
        down_segs = [s for s in recent_segs if s.direction == "down"]

        # 最近向上段是否在创新高
        making_higher_highs = (
            len(up_segs) >= 2
            and all(up_segs[i].high > up_segs[i - 1].high
                    for i in range(1, min(3, len(up_segs))))
        )
        # 最近向下段是否在创新低
        making_lower_lows = (
            len(down_segs) >= 2
            and all(down_segs[i].low < down_segs[i - 1].low
                    for i in range(1, min(3, len(down_segs))))
        )

        if making_higher_highs and not making_lower_lows:
            return "上涨"
        if making_lower_lows and not making_higher_highs:
            return "下跌"
        if making_higher_highs and making_lower_lows:
            return "盘整"

        # 兜底：线段计数（仅段数≥3时可靠，否则跳过让笔判断）
        ups = len(up_segs)
        downs = len(down_segs)
        if ups + downs >= 3:
            if ups > downs:
                seg_trend = "上涨"
            elif downs > ups:
                seg_trend = "下跌"
            else:
                seg_trend = None

            if seg_trend is not None:
                # 笔交叉验证：段方向与最近笔方向矛盾 → 盘整（趋势转换期）
                if len(self.bis) >= 6:
                    check_bis = self.bis[-8:] if len(self.bis) >= 8 else self.bis
                    b_up = sum(1 for b in check_bis if b.direction == "up")
                    b_down = sum(1 for b in check_bis if b.direction == "down")
                    if (seg_trend == "上涨" and b_down > b_up) or \
                       (seg_trend == "下跌" and b_up > b_down):
                        return "盘整"
                return seg_trend

        # 线段不足（段数<3 或等数）→ 回退用笔判断
        # 多窗口策略：短窗口捕获最新反转，长窗口确认大方向
        if len(self.bis) >= 4:
            all_bis = self.bis[-12:] if len(self.bis) >= 12 else self.bis
            # 短窗口（最近5笔）：捕捉最新方向变化
            short = all_bis[-5:] if len(all_bis) >= 5 else all_bis
            s_up = sum(1 for b in short if b.direction == "up")
            s_down = sum(1 for b in short if b.direction == "down")
            # 超短窗口（最近3笔）：确认强方向
            last3 = short[-3:] if len(short) >= 3 else short
            l3_up = sum(1 for b in last3 if b.direction == "up")
            l3_down = sum(1 for b in last3 if b.direction == "down")
            # 长窗口：避免误判
            l_up = sum(1 for b in all_bis if b.direction == "up")
            l_down = sum(1 for b in all_bis if b.direction == "down")

            # 优先级：超短 > 短 > 长
            if l3_up == 3:
                return "上涨"
            if l3_down == 3:
                return "下跌"
            if s_up >= 4:
                return "上涨"
            if s_down >= 4:
                return "下跌"
            if s_up > s_down:
                # 补充价格验证：价格未创新高 → 可能只是震荡
                if s_up - s_down <= 1 and not _bis_making_higher_highs(short):
                    return "盘整"
                return "上涨"
            if s_down > s_up:
                if s_down - s_up <= 1 and not _bis_making_lower_lows(short):
                    return "盘整"
                return "下跌"
            if l_up > l_down + 1:
                return "上涨"
            if l_down > l_up + 1:
                return "下跌"

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
