from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter
from services.akshare_service import get_realtime_quote, get_kline_hist, normalize_stock_code
from chanlun.engine import ChanlunEngine
from stores.local_json import get_watchlist_map, watchlist_add, watchlist_remove

router = APIRouter()


def _get_60min_signal(code: str) -> dict | None:
    """获取单只股票60分钟级别的最近买卖信号"""
    try:
        df = get_kline_hist(code, period="60", adjust="qfq")
        if df.empty or len(df) < 50:
            return None
        r = ChanlunEngine(df.tail(1000)).analyze(level="60min")
        # 优先取一买/一卖, 其次最近信号
        sigs = sorted(r.signals, key=lambda s: s.datetime, reverse=True)
        buy = next((s for s in sigs if s.type in ('一买','二买','三买','盘整背驰买')), None)
        sell = next((s for s in sigs if s.type in ('一卖','二卖','三卖','盘整背驰卖')), None)
        latest = sigs[0] if sigs else None
        # 取最近的买卖中较晚的
        candidates = [s for s in [buy, sell] if s is not None]
        best = max(candidates, key=lambda s: s.datetime) if candidates else latest
        if best is None:
            return None
        return {
            "type": best.type,
            "datetime": str(best.datetime)[:10],
        }
    except Exception:
        return None


def _get_watchlist_response():
    wl = get_watchlist_map()
    if not wl:
        return {"stocks": []}

    codes = list(wl.keys())
    df = get_realtime_quote(codes)
    if df.empty:
        return {"stocks": [], "total": 0}

    # 并发获取60分钟缠论信号
    signal_map: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(len(codes), 10)) as pool:
        futures = {pool.submit(_get_60min_signal, c): c for c in codes}
        for f in as_completed(futures):
            code = futures[f]
            try:
                r = f.result(timeout=15)
                if r:
                    signal_map[code] = r
            except Exception:
                pass

    return {
        "stocks": [
            {
                "code": str(row.get("代码", "")),
                "name": str(row.get("名称", "")),
                "price": float(row.get("最新价", 0) or 0),
                "change_pct": float(row.get("涨跌幅", 0) or 0),
                "added_at": wl.get(str(row.get("代码", "")), ""),
                "signal_60": signal_map.get(str(row.get("代码", "")), None),
            }
            for _, row in df.iterrows()
        ],
        "total": len(wl),
    }


@router.get("/api/watchlist", tags=["自选"])
async def get_watchlist():
    return await asyncio.to_thread(_get_watchlist_response)


@router.post("/api/watchlist/{code}", tags=["自选"])
async def add_watchlist(code: str):
    sym, _ = normalize_stock_code(code)
    added_at, is_new = watchlist_add(sym)
    wl = get_watchlist_map()
    return {
        "code": sym,
        "added": True,
        "added_at": added_at,
        "total": len(wl),
    }


@router.delete("/api/watchlist/{code}", tags=["自选"])
async def remove_watchlist(code: str):
    sym, _ = normalize_stock_code(code)
    watchlist_remove(sym)
    wl = get_watchlist_map()
    return {"code": sym, "removed": True, "total": len(wl)}
