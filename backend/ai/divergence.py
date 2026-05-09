"""
背驰自动判断 — MACD面积 + RSI/KDJ背离检测
"""
import pandas as pd
import numpy as np
from typing import Optional

from chanlun.elements import Bi


# MACD：后一段面积低于前一段该比例以下视为力度显著减弱
MACD_WEAKEN_RATIO = 0.85
MACD_AREA_EPS = 1e-15
PRICE_EPS = 1e-12
MIN_BIS_FOR_DIV = 4
# 每段至少若干根 K 线才参与力度对比，避免单子线噪声
MIN_BARS_PER_SEGMENT = 2
# MACD 已满足背驰时，RSI 或 KDJ(J) 同向背离各小幅抬高概率上限
OSC_CONFIRM_BOOST = 0.07


def calculate_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> pd.DataFrame:
    """
    计算 MACD 指标
    返回 DataFrame 追加 dif/dea/bar 列
    """
    df = df.copy()
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    df['dif'] = ema_fast - ema_slow
    df['dea'] = df['dif'].ewm(span=signal, adjust=False).mean()
    df['bar'] = (df['dif'] - df['dea']) * 2
    return df


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """计算 RSI（Wilder 平滑，与常见行情软件一致）"""
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta.clip(upper=0))
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def calculate_kdj(
    df: pd.DataFrame,
    n: int = 9,
    m1: int = 3,
    m2: int = 3
) -> pd.DataFrame:
    """计算 KDJ 指标"""
    df = df.copy()
    low_n = df['low'].rolling(n, min_periods=1).min()
    high_n = df['high'].rolling(n, min_periods=1).max()
    rsv = (df['close'] - low_n) / (high_n - low_n + 1e-9) * 100
    df['K'] = rsv.ewm(com=m1 - 1, adjust=False).mean()
    df['D'] = df['K'].ewm(com=m2 - 1, adjust=False).mean()
    df['J'] = 3 * df['K'] - 2 * df['D']
    return df


def money(v: float) -> float:
    """格式化金额显示"""
    return round(v, 2)


def macd_area(bars: pd.Series) -> float:
    """计算 MACD 柱全绝对值面积（近似积分），忽略 NaN"""
    arr = bars.to_numpy(dtype=float)
    return float(np.nansum(np.abs(arr)))


def macd_area_directional(bars: pd.Series, seg_type: str) -> float:
    """
    与走势同向的 MACD 柱累计面积（忽略反向柱），更符合「上涨笔比红柱、下跌笔比绿柱」的习惯。
    top（向上笔顶背驰）：累计 bar > 0 部分；bottom（向下笔底背驰）：累计 bar < 0 的绝对值。
    """
    arr = bars.to_numpy(dtype=float)
    if seg_type == "top":
        return float(np.nansum(np.maximum(arr, 0.0)))
    if seg_type == "bottom":
        return float(np.nansum(np.abs(np.minimum(arr, 0.0))))
    raise ValueError(f"seg_type must be 'top' or 'bottom', got {seg_type!r}")


def _nan_extreme(series: pd.Series, *, high_extreme: bool) -> float:
    """段内 RSI/KDJ 极值；无有效数据时返回 nan"""
    a = series.to_numpy(dtype=float)
    if high_extreme:
        return float(np.nanmax(a))
    return float(np.nanmin(a))


class DivergenceDetector:
    """
    背驰检测:
    1. MACD 同向柱面积对比（向上笔累计红柱、向下笔累计绿柱；过小则回退为绝对值面积）
    2. RSI/KDJ 顶底背离（在 MACD 背驰前提下抬升概率）
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.df = calculate_macd(self.df)
        self.df['rsi'] = calculate_rsi(self.df)
        self.df = calculate_kdj(self.df)
        self.df.reset_index(drop=True, inplace=True)

    def check_divergence(self, bis: list[Bi]) -> Optional[dict]:
        """
        检测背驰: 比较最近两个同向段的力度
        返回: type、probability、macd_ratio、price_drop|price_rise、description，
        以及 rsi_confirm / kdj_confirm（是否与 MACD 背驰同向的振荡器背离）。
        顶、底同时满足时取概率更高者；概率相同则取第二段结束时间更晚者。
        """
        if len(bis) < MIN_BIS_FOR_DIV:
            return None

        up_segments = [b for b in bis if b.direction == "up"]
        down_segments = [b for b in bis if b.direction == "down"]

        candidates: list[tuple[dict, object]] = []

        if len(up_segments) >= 2:
            seg_a, seg_b = up_segments[-2], up_segments[-1]
            result = self._check_segment_divergence(seg_a, seg_b, "top")
            if result:
                candidates.append((result, seg_b.end))

        if len(down_segments) >= 2:
            seg_a, seg_b = down_segments[-2], down_segments[-1]
            result = self._check_segment_divergence(seg_a, seg_b, "bottom")
            if result:
                candidates.append((result, seg_b.end))

        if not candidates:
            return None

        # 概率优先；同概率则第二段结束时间更晚（更贴近当下走势）
        best = max(
            candidates,
            key=lambda item: (item[0]["probability"], item[1]),
        )
        return best[0]

    def _rsi_confirms(self, seg_type: str, s1_df: pd.DataFrame, s2_df: pd.DataFrame) -> bool:
        """顶: 价新高但段内 RSI 高点不及前一段；底: 价新低但 RSI 低点抬高"""
        if "rsi" not in s1_df.columns:
            return False
        if seg_type == "top":
            r1 = _nan_extreme(s1_df["rsi"], high_extreme=True)
            r2 = _nan_extreme(s2_df["rsi"], high_extreme=True)
            if np.isnan(r1) or np.isnan(r2):
                return False
            return r2 < r1
        r1 = _nan_extreme(s1_df["rsi"], high_extreme=False)
        r2 = _nan_extreme(s2_df["rsi"], high_extreme=False)
        if np.isnan(r1) or np.isnan(r2):
            return False
        return r2 > r1

    def _kdj_j_confirms(self, seg_type: str, s1_df: pd.DataFrame, s2_df: pd.DataFrame) -> bool:
        """以 J 线为快速振荡器，逻辑同 RSI"""
        if "J" not in s1_df.columns:
            return False
        if seg_type == "top":
            j1 = _nan_extreme(s1_df["J"], high_extreme=True)
            j2 = _nan_extreme(s2_df["J"], high_extreme=True)
            if np.isnan(j1) or np.isnan(j2):
                return False
            return j2 < j1
        j1 = _nan_extreme(s1_df["J"], high_extreme=False)
        j2 = _nan_extreme(s2_df["J"], high_extreme=False)
        if np.isnan(j1) or np.isnan(j2):
            return False
        return j2 > j1

    def _check_segment_divergence(
        self, seg1: Bi, seg2: Bi, seg_type: str
    ) -> Optional[dict]:
        """比较两段的力度差异"""
        s1_df = self._get_segment_df(seg1.start, seg1.end)
        s2_df = self._get_segment_df(seg2.start, seg2.end)

        if (
            len(s1_df) < MIN_BARS_PER_SEGMENT
            or len(s2_df) < MIN_BARS_PER_SEGMENT
        ):
            return None

        d1 = macd_area_directional(s1_df["bar"], seg_type)
        d2 = macd_area_directional(s2_df["bar"], seg_type)
        if d1 > MACD_AREA_EPS and d2 > MACD_AREA_EPS:
            macd1, macd2 = d1, d2
            macd_force_kind = "directional"
        else:
            macd1 = macd_area(s1_df["bar"])
            macd2 = macd_area(s2_df["bar"])
            macd_force_kind = "abs"
        if macd1 <= MACD_AREA_EPS:
            return None

        threshold = macd1 * MACD_WEAKEN_RATIO

        if seg_type == "bottom":
            price1 = float(seg1.low)
            price2 = float(seg2.low)
            if price1 <= PRICE_EPS:
                return None
            if not (price2 < price1 and macd2 < threshold):
                return None
            change_key = "price_drop"
            desc_prefix = "价格新低"
        else:
            price1 = float(seg1.high)
            price2 = float(seg2.high)
            if price1 <= PRICE_EPS:
                return None
            if not (price2 > price1 and macd2 < threshold):
                return None
            change_key = "price_rise"
            desc_prefix = "价格新高"

        ratio = macd2 / macd1
        prob = min(1.0, (1 - ratio) + 0.5)

        rsi_ok = self._rsi_confirms(seg_type, s1_df, s2_df)
        kdj_ok = self._kdj_j_confirms(seg_type, s1_df, s2_df)
        if rsi_ok:
            prob = min(1.0, prob + OSC_CONFIRM_BOOST)
        if kdj_ok:
            prob = min(1.0, prob + OSC_CONFIRM_BOOST)

        tags: list[str] = []
        if rsi_ok:
            tags.append("RSI背离")
        if kdj_ok:
            tags.append("KDJ背离")
        extra_txt = f"，{'/'.join(tags)}共振" if tags else ""

        delta = abs(price2 - price1)
        pct_move = round(delta / price1, 3)

        return {
            "type": seg_type,
            "probability": round(prob, 2),
            change_key: pct_move,
            "macd_ratio": round(ratio, 2),
            "macd_force": macd_force_kind,
            "rsi_confirm": rsi_ok,
            "kdj_confirm": kdj_ok,
            "description": (
                f"{desc_prefix}{money(delta):.2f}但力度减弱至{ratio:.0%}{extra_txt}"
            ),
        }

    def _get_segment_df(self, start, end) -> pd.DataFrame:
        mask = (self.df['date'] >= start) & (self.df['date'] <= end)
        return self.df[mask]

