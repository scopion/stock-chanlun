"""
缠论分析引擎 — 整合所有组件
"""
import pandas as pd
from datetime import datetime
from .elements import (
    KLine, Bi, XiangSegment, Zhongshu, BuySellPoint,
    ChanlunAnalysis
)
from .fenxing_detector import FenxingDetector
from .bi_detector import BiDetector
from .segment_detector import SegmentDetector
from .signals import SignalDetector


class ChanlunEngine:
    """
    缠论分析引擎
    用法:
        engine = ChanlunEngine(klines_df)
        result = engine.analyze(level="daily")
    """

    def __init__(self, klines: pd.DataFrame):
        """
        klines: DataFrame, columns=[date, open, high, low, close, volume]
        """
        self.raw_klines = klines.copy()
        self._ensure_columns()

    def _ensure_columns(self):
        col_map = {
            '日期': 'date', '开盘': 'open', '收盘': 'close',
            '最高': 'high', '最低': 'low', '成交量': 'volume',
            '时间': 'date'
        }
        self.raw_klines.rename(columns=col_map, inplace=True)
        if 'date' in self.raw_klines.columns:
            self.raw_klines['date'] = pd.to_datetime(self.raw_klines['date'])
        self.raw_klines.sort_values('date', inplace=True)
        self.raw_klines.reset_index(drop=True, inplace=True)

    def analyze(self, level: str = "daily") -> ChanlunAnalysis:
        """执行完整缠论分析"""
        # 1. 分型检测
        fx_detector = FenxingDetector(self.raw_klines)
        fenxings = fx_detector.detect()

        # 2. 笔识别
        bi_detector = BiDetector(self.raw_klines)
        bis = bi_detector.detect(min_bars=5)

        # 3. 线段识别
        seg_detector = SegmentDetector(bis)
        segments = seg_detector.detect_segments()

        # 4. 中枢识别
        zhongshus = seg_detector.detect_zhongshus(segments)

        # 5. 买卖点判定（传入原始K线DataFrame用于MACD背驰计算）
        sig_detector = SignalDetector(bis, segments, zhongshus,
                                       level=level,
                                       klines_df=self.raw_klines)
        signals = sig_detector.detect_all()
        current_price = float(self.raw_klines['close'].iloc[-1]) if len(self.raw_klines) > 0 else None
        trend = sig_detector.detect_trend(current_price=current_price)

        # 6. K线对象（必须先创建，再传给支撑阻力位计算）
        kline_objects = self._to_klines()

        # 5b. 支撑阻力位
        klines_dict = [{"date": k.date, "high": k.high, "low": k.low} for k in kline_objects]
        support_resistance = sig_detector.detect_support_resistance(klines_dict, signals)

        # 7. 自然语言总结
        summary = self._make_summary(trend, signals, zhongshus)

        return ChanlunAnalysis(
            stock_code="",
            level=level,
            klines=kline_objects,
            bis=bis,
            xiangs=segments,
            zhongshus=zhongshus,
            signals=signals,
            trend=trend,
            summary=summary,
            support_resistance=support_resistance
        )

    def _to_klines(self) -> list[KLine]:
        rows = []
        for _, row in self.raw_klines.iterrows():
            rows.append(KLine(
                date=row['date'].to_pydatetime()
                     if hasattr(row['date'], 'to_pydatetime') else row['date'],
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=float(row.get('volume', 0) or 0),
                amount=float(row.get('amount', 0) or 0)
            ))
        return rows

    def _make_summary(self, trend: str, signals: list[BuySellPoint],
                      zhongshus: list[Zhongshu]) -> str:
        parts = [f"当前走势: {trend}"]
        if zhongshus:
            last_zs = zhongshus[-1]
            parts.append(
                f"中枢区间: [{last_zs.range_low:.2f}, {last_zs.range_high:.2f}]"
            )
        if signals:
            latest = signals[-1]
            parts.append(f"最近信号: {latest.type} @ {latest.price:.2f}")
        else:
            parts.append("暂无明确信号")
        return " | ".join(parts)
