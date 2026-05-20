"""缠论分析：K 线拉取 + 引擎（供路由与 AI 复用）。"""
from __future__ import annotations

import pandas as pd
from fastapi import HTTPException

from chanlun.elements import ChanlunAnalysis
from chanlun.engine import ChanlunEngine
from services.akshare_service import get_kline_hist
from utils import chanlun_cache


def level_to_period(level: str) -> str:
    mapping = {
        "60min": "60",
        "daily": "daily",
        "weekly": "weekly",
        "monthly": "monthly",
    }
    return mapping.get(level, "daily")


def run_analysis(code: str, level: str, kline_limit: int = 500) -> ChanlunAnalysis:
    cache_key = f"{code}:{level}"
    cached = chanlun_cache.get(cache_key)
    if cached is not None:
        return cached

    period = level_to_period(level)
    df = get_kline_hist(code, period=period, start_date=None, adjust="qfq")

    if df.empty or len(df) < 20:
        raise HTTPException(
            status_code=404,
            detail=f"{code} {level}级别K线数据不足（仅{len(df) if not df.empty else 0}根），请换日线/60分钟级别尝试",
        )

    if len(df) > kline_limit:
        df = df.tail(kline_limit).reset_index(drop=True)

    engine = ChanlunEngine(df)
    result = engine.analyze(level=level)
    result.stock_code = code

    chanlun_cache.set(cache_key, result)
    return result


def get_kline_df_for_ai(
    code: str, level: str, kline_limit: int = 500
) -> tuple[pd.DataFrame, ChanlunAnalysis]:
    cache_key = f"{code}:{level}"
    cached_result = chanlun_cache.get(cache_key)

    period = level_to_period(level)
    df = get_kline_hist(code, period=period, start_date=None, adjust="qfq")

    if df.empty or len(df) < 20:
        raise HTTPException(
            status_code=404,
            detail=f"{code} {level}级别K线数据不足（仅{len(df) if not df.empty else 0}根），请换日线/60分钟级别尝试",
        )

    if len(df) > kline_limit:
        df = df.tail(kline_limit).reset_index(drop=True)

    if cached_result is not None:
        cached_result.stock_code = code
        return df, cached_result

    engine = ChanlunEngine(df)
    result = engine.analyze(level=level)
    result.stock_code = code

    chanlun_cache.set(cache_key, result)
    return df, result
