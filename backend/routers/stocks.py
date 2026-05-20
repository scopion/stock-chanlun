from __future__ import annotations

import asyncio
import csv
import io
import json
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from core.chanlun_analysis import level_to_period
from core.numbers import finite_float
from deps import check_kline_rate_limits, client_ip
from services.akshare_service import (
    get_board_constituents_em,
    get_daily_hot_stocks,
    get_kline_hist,
    get_market_overview_bundle,
    get_realtime_quote,
    get_stock_boards_em,
    get_stock_depth_em,
    get_stock_info,
    get_stock_news,
    get_stock_symbol_news_em,
    normalize_stock_code,
    search_stocks,
)

router = APIRouter()


def _search_stock_impl(q: str):
    df = search_stocks(q)
    if df.empty:
        return {"stocks": [], "total": 0}
    return {
        "stocks": df.head(20)[["code", "name"]].to_dict(orient="records"),
        "total": len(df),
    }


@router.get("/api/stocks/search", tags=["数据"])
async def search_stock(q: str = Query(..., min_length=1)):
    return await asyncio.to_thread(_search_stock_impl, q)


@router.get("/api/stocks/hot", tags=["数据"])
async def hot_stocks(limit: int = Query(15, ge=1, le=50)):
    def _run():
        stocks = get_daily_hot_stocks(limit)
        return {
            "stocks": stocks,
            "total": len(stocks),
            "error": None if stocks else "获取失败，请稍后重试",
        }

    return await asyncio.to_thread(_run)


@router.get("/api/stocks/screen", tags=["选股"])
async def screen_stocks_api(
    change_pct_min: Optional[float] = Query(None, description="最小涨跌幅（%）"),
    change_pct_max: Optional[float] = Query(None, description="最大涨跌幅（%）"),
    volume_min: Optional[float] = Query(None, description="最小成交量（手）"),
    volume_max: Optional[float] = Query(None, description="最大成交量（手）"),
    industry: Optional[str] = Query(None, description="行业板块名称（精确匹配）"),
    pe_max: Optional[float] = Query(None, description="市盈率上限"),
    pb_max: Optional[float] = Query(None, description="市净率上限"),
    signals: Optional[str] = Query(None, description="逗号分隔买卖点类型，如 一买,二买"),
    dual_cross: bool = Query(False, description="是否必须 MACD+SKDJ 双金叉共振"),
    level: str = Query(
        "daily",
        pattern="^(60min|daily|weekly|monthly)$",
    ),
    pool_size: int = Query(100, ge=10, le=1000, description="候选池大小（最高 1000）"),
):
    from services.screening_service import screen_stocks

    signal_types: list[str] | None = None
    if signals:
        raw = [s.strip() for s in signals.split(",") if s.strip()]
        if raw:
            signal_types = raw

    def _run():
        return screen_stocks(
            change_pct_min=change_pct_min,
            change_pct_max=change_pct_max,
            volume_min=volume_min,
            volume_max=volume_max,
            industry=industry,
            pe_max=pe_max,
            pb_max=pb_max,
            signal_types=signal_types,
            require_dual_cross=dual_cross,
            level=level,
            pool_size=pool_size,
        )

    results = await asyncio.to_thread(_run)
    return {"results": results, "total": len(results)}


@router.get("/api/stocks/screen-stream", tags=["选股"])
def screen_stocks_stream_api(
    change_pct_min: Optional[float] = Query(None, description="最小涨跌幅（%）"),
    change_pct_max: Optional[float] = Query(None, description="最大涨跌幅（%）"),
    volume_min: Optional[float] = Query(None, description="最小成交量（手）"),
    volume_max: Optional[float] = Query(None, description="最大成交量（手）"),
    industry: Optional[str] = Query(None, description="行业板块名称（精确匹配）"),
    pe_max: Optional[float] = Query(None, description="市盈率上限"),
    pb_max: Optional[float] = Query(None, description="市净率上限"),
    signals: Optional[str] = Query(None, description="逗号分隔买卖点类型，如 一买,二买"),
    dual_cross: bool = Query(False, description="是否必须 MACD+SKDJ 双金叉共振"),
    level: str = Query(
        "daily",
        pattern="^(60min|daily|weekly|monthly)$",
    ),
    pool_size: int = Query(100, ge=10, le=1000, description="候选池大小（最高 1000）"),
    max_results: int = Query(50, ge=1, le=200, description="最多返回条数"),
):
    from services.screening_service import screen_stocks_stream

    signal_types: list[str] | None = None
    if signals:
        raw = [s.strip() for s in signals.split(",") if s.strip()]
        if raw:
            signal_types = raw

    async def event_stream():
        for item in screen_stocks_stream(
            change_pct_min=change_pct_min,
            change_pct_max=change_pct_max,
            volume_min=volume_min,
            volume_max=volume_max,
            industry=industry,
            pe_max=pe_max,
            pb_max=pb_max,
            signal_types=signal_types,
            require_dual_cross=dual_cross,
            level=level,
            pool_size=pool_size,
            max_results=max_results,
        ):
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/market/overview", tags=["数据"])
async def market_overview():
    def _run():
        try:
            return get_market_overview_bundle()
        except Exception as e:
            print(f"大盘概览获取失败: {e}")
            return {
                "indices": {},
                "market_breadth": {"advancers": 0, "decliners": 0, "unchanged": 0},
                "sectors": [],
                "sectors_top": [],
                "sectors_bottom": [],
            }

    return await asyncio.to_thread(_run)


@router.get("/api/news", tags=["数据"])
async def news(limit: int = Query(10, ge=1, le=30)):
    return await asyncio.to_thread(lambda: {"items": get_stock_news(limit)})


@router.get("/api/sector/{name}/stocks", tags=["数据"])
async def sector_stocks(name: str):
    def _run():
        try:
            return get_board_constituents_em(name)
        except Exception as e:
            print(f"[板块] 「{name}」获取失败: {e}")
            return {"sector_name": name, "board_type": None, "stocks": [], "total": 0}

    return await asyncio.to_thread(_run)


@router.get("/api/stocks/{code}/info", tags=["数据"])
async def stock_info(code: str):
    def _run():
        sym, exchange = normalize_stock_code(code)
        info = get_stock_info(sym)
        return {"code": sym, "exchange": exchange, "info": info}

    return await asyncio.to_thread(_run)


@router.get("/api/stocks/{code}/extras", tags=["数据"])
async def stock_extras(
    code: str,
    news_limit: int = Query(8, ge=1, le=20),
):
    def _run():
        sym, exchange = normalize_stock_code(code)
        return {
            "code": sym,
            "exchange": exchange,
            "depth": get_stock_depth_em(sym),
            "boards": get_stock_boards_em(sym),
            "news": get_stock_symbol_news_em(sym, news_limit),
        }

    return await asyncio.to_thread(_run)


def _realtime_quote_impl(code: str):
    sym, _ = normalize_stock_code(code)
    df = get_realtime_quote([code])
    if not df.empty:
        row = df.iloc[0]
        return {
            "code": row.get("代码", sym),
            "name": row.get("名称", ""),
            "price": float(row.get("最新价", 0) or 0),
            "change_pct": float(row.get("涨跌幅", 0) or 0),
            "volume": float(row.get("成交量", 0) or 0),
            "amount": float(row.get("成交额", 0) or 0),
            "high": float(row.get("最高", 0) or 0),
            "low": float(row.get("最低", 0) or 0),
            "open": float(row.get("今开", 0) or 0),
            "prev_close": float(row.get("昨收", 0) or 0),
        }

    info = get_stock_info(code)
    if info and (info.get("现价") or info.get("名称")):
        return {
            "code": str(info.get("代码", sym)),
            "name": str(info.get("名称", "")),
            "price": finite_float(info.get("现价")),
            "change_pct": finite_float(info.get("涨跌幅")),
            "volume": finite_float(info.get("成交量")),
            "amount": finite_float(info.get("成交额")),
            "high": finite_float(info.get("最高")),
            "low": finite_float(info.get("最低")),
            "open": finite_float(info.get("今开")),
            "prev_close": finite_float(info.get("昨收")),
        }
    raise HTTPException(status_code=404, detail="股票未找到")


@router.get("/api/stocks/{code}/quote", tags=["数据"])
async def realtime_quote(code: str, request: Request):
    check_kline_rate_limits(client_ip(request))
    return await asyncio.to_thread(_realtime_quote_impl, code)


def _stock_kline_impl(
    code: str,
    level: str,
    limit: int,
    start_date: Optional[str],
    end_date: Optional[str],
):
    period = level_to_period(level)
    df = get_kline_hist(code, period=period, adjust="qfq")
    if df.empty:
        return {"klines": [], "total": 0}

    if start_date:
        df = df[df["date"] >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df["date"] <= pd.Timestamp(end_date) + pd.Timedelta(days=1)]

    df = df.tail(limit).reset_index(drop=True)

    return {
        "klines": [
            {
                "date": str(r["date"])[:19],
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r.get("volume", 0) or 0),
            }
            for _, r in df.iterrows()
        ],
        "total": len(df),
    }


@router.get("/api/stocks/{code}/kline", tags=["数据"])
async def stock_kline(
    code: str,
    request: Request,
    level: str = Query(
        "daily",
        pattern="^(60min|daily|weekly|monthly)$",
    ),
    limit: int = Query(500, le=2000),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
):
    check_kline_rate_limits(client_ip(request))
    return await asyncio.to_thread(
        _stock_kline_impl, code, level, limit, start_date, end_date
    )


def _export_stock_csv_impl(code: str, level: str, limit: int):
    period = level_to_period(level)
    df = get_kline_hist(code, period=period, adjust="qfq")
    if df.empty:
        raise HTTPException(status_code=404, detail="K线数据为空，无法导出")

    df = df.tail(limit).reset_index(drop=True)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["日期", "开盘", "收盘", "最高", "最低", "成交量"])
    for _, r in df.iterrows():
        writer.writerow(
            [
                str(r["date"])[:10],
                f"{r['open']:.2f}",
                f"{r['close']:.2f}",
                f"{r['high']:.2f}",
                f"{r['low']:.2f}",
                f"{r.get('volume', 0):.0f}",
            ]
        )

    filename = f"{code}_{level}_{str(df['date'].iloc[-1])[:10]}.csv"
    output.seek(0)
    return output.getvalue(), filename


@router.get("/api/stocks/{code}/export", tags=["数据"])
async def export_stock_csv(
    code: str,
    request: Request,
    level: str = Query(
        "daily",
        pattern="^(60min|daily|weekly|monthly)$",
    ),
    limit: int = Query(500, le=2000),
):
    check_kline_rate_limits(client_ip(request))
    body, filename = await asyncio.to_thread(_export_stock_csv_impl, code, level, limit)
    return StreamingResponse(
        iter([body]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
        },
    )
