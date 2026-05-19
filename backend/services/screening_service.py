"""
选股服务 — 按基础指标、缠论买卖点、MACD+SKDJ 双金叉筛选股票。
"""
import threading
import time
from typing import Optional
import pandas as pd
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from chanlun.elements import BuySellPoint
from chanlun.engine import ChanlunEngine
from services.akshare_service import (
    get_kline_hist,
    get_daily_hot_stocks,
    get_realtime_quote,
    get_stock_info,
    get_stock_boards_em,
)
from utils import chanlun_cache


# ─── MACD / SKDJ（同前端 stockIndicators.ts 算法） ────────────────────────────

def _ema(data, period):
    k = 2 / (period + 1)
    out = [data[0]]
    for i in range(1, len(data)):
        out.append(data[i] * k + out[-1] * (1 - k))
    return out


def _calc_macd(closes):
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif = [a - b for a, b in zip(ema12, ema26)]
    dea = _ema(dif, 9)
    return dif, dea


def _calc_skdj(highs, lows, closes, n=9, smooth_n=3, smooth_m=1):
    rsv = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        ln = min(lows[i - n + 1:i + 1])
        hn = max(highs[i - n + 1:i + 1])
        rsv[i] = 50 if hn == ln else (closes[i] - ln) / (hn - ln) * 100

    sk = [None] * len(closes)
    prev_sk = None
    for i in range(len(closes)):
        r = rsv[i]
        if r is None:
            continue
        prev_sk = r if prev_sk is None else (smooth_m * r + (smooth_n - smooth_m) * prev_sk) / smooth_n
        sk[i] = prev_sk

    sd = [None] * len(closes)
    prev_sd = None
    for i in range(len(closes)):
        s = sk[i]
        if s is None:
            continue
        prev_sd = s if prev_sd is None else (smooth_m * s + (smooth_n - smooth_m) * prev_sd) / smooth_n
        sd[i] = prev_sd

    return sk, sd


def _macd_gold_crosses(dif, dea):
    crosses = []
    for i in range(1, len(dif)):
        if dif[i - 1] <= dea[i - 1] and dif[i] > dea[i]:
            crosses.append(i)
    return crosses


def _skdj_gold_crosses(sk, sd):
    crosses = []
    for i in range(1, len(sk)):
        a, b = sk[i - 1], sk[i]
        ap, bp = sd[i - 1], sd[i]
        if a is None or b is None or ap is None or bp is None:
            continue
        if a <= ap and b > bp:
            crosses.append(i)
    return crosses


def _dual_cross_info(klines_df: pd.DataFrame):
    """
    计算 MACD+SKDJ 双金叉共振。
    返回 (has_dual_cross, dual_cross_date_str)

    注意：须取「最近」一次有效双金叉（bar 索引最大），不能命中第一对就返回，
    否则在 200 根 K 线内会错误展示数月前的日期。
    """
    if len(klines_df) < 30:
        return False, None

    df = klines_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    closes = df["close"].tolist()
    highs = df["high"].tolist()
    lows = df["low"].tolist()

    dif, dea = _calc_macd(closes)
    sk, sd = _calc_skdj(highs, lows, closes)

    macd_g = _macd_gold_crosses(dif, dea)
    skdj_g = _skdj_gold_crosses(sk, sd)

    WINDOW = 3
    best_hi = -1

    for m in macd_g:
        for s in skdj_g:
            if abs(m - s) > WINDOW:
                continue
            hi = max(m, s)
            if hi <= best_hi:
                continue
            # 当日必须 DIF>DEA 且 SK>SD，且不是死叉日
            if not (dif[hi] > dea[hi]):
                continue
            if sk[hi] is None or sd[hi] is None or sk[hi] <= sd[hi]:
                continue
            if dif[hi - 1] >= dea[hi - 1] and dif[hi] < dea[hi]:
                continue
            if sk[hi - 1] >= sd[hi - 1] and sk[hi] < sd[hi]:
                continue
            best_hi = hi

    if best_hi < 0:
        return False, None

    d = df["date"].iloc[best_hi]
    date_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
    return True, date_str


# ─── 单只股票分析 ─────────────────────────────────────────────────────────────

def _analyze_stock(code: str, level: str) -> dict | None:
    """
    对单只股票执行选股分析。
    返回字典或 None（分析失败时跳过）。
    """
    try:
        period_map = {
            "1min": "1", "5min": "5", "15min": "15",
            "30min": "30", "60min": "60",
            "daily": "day", "weekly": "week", "monthly": "month",
        }
        period = period_map.get(level, "day")
        df = get_kline_hist(code, period=period, adjust="qfq")
        if df.empty or len(df) < 20:
            return None

        # 取最近 200 根 K 线加速
        df = df.tail(200).reset_index(drop=True)
        dates = df['date'].astype(str).tolist()

        # 优先从缠论缓存读取
        cache_key = f"{code}:{level}"
        cached_result = chanlun_cache.get(cache_key)
        if cached_result is not None:
            result = cached_result
        else:
            engine = ChanlunEngine(df)
            result = engine.analyze(level=level)
            chanlun_cache.set(cache_key, result)

        # 取最近一笔信号
        latest_signal: BuySellPoint | None = None
        if result.signals:
            sorted_sigs = sorted(result.signals, key=lambda s: s.datetime, reverse=True)
            latest_signal = sorted_sigs[0]

        # MACD+SKDJ 双金叉
        has_dual_cross, dual_cross_date = _dual_cross_info(df)

        return {
            "code": code,
            "trend": result.trend,
            "latest_signal": latest_signal,
            "has_dual_cross": has_dual_cross,
            "dual_cross_date": dual_cross_date,
            "dates": dates,
        }
    except Exception:
        return None


# ─── 实时行情 & 基本面 ────────────────────────────────────────────────────────

def _normalize_code(code: str) -> str:
    """统一转换为纯6位数字码，便于跨数据源匹配"""
    code = str(code).strip()
    # 去掉 sh/sz 前缀
    if code.startswith("sh") or code.startswith("sz") or code.startswith("bj"):
        code = code[2:]
    return code.zfill(6)


def _get_quote_and_info(codes: list[str], need_industry: bool = False) -> dict[str, dict]:
    """
    批量获取实时行情 + 基本面信息。

    need_industry: True 时并发拉取行业/PE/PB，False 时跳过（用于无行业/PE/PB 过滤条件时加速）。
    """
    result = {}

    # 统一码格式（6位数字）
    normalized_codes = [_normalize_code(c) for c in codes]

    # 实时行情（批量，一次 HTTP）
    quotes_df = get_realtime_quote(codes)
    quotes_records = quotes_df.to_dict("records") if not quotes_df.empty else []

    qmap = {}
    for q in quotes_records:
        code_key = _normalize_code(q.get("代码") or q.get("code") or "")
        qmap[code_key] = q

    for code in codes:
        norm_code = _normalize_code(code)
        q = qmap.get(norm_code, {})
        price = float(q.get("最新价") or q.get("price") or 0)
        # 直接使用 API 返回的涨跌幅（data[32]），而非自行计算
        change_pct = float(q.get("涨跌幅") or q.get("change_pct") or 0)

        result[code] = {
            "price": price,
            "change_pct": round(change_pct, 2),
            "volume": float(q.get("成交量") or q.get("volume") or 0),
            "amount": float(q.get("成交额") or q.get("amount") or 0),
            "name": q.get("名称") or q.get("name") or code,
            "industry": None,
            "pe": None,
            "pb": None,
        }

    # 基本面（行业、PE、PB）— 有过滤条件时并发拉取，否则跳过
    if need_industry and codes:
        def fetch_one(code: str) -> tuple[str, str | None, float | None, float | None]:
            try:
                info = get_stock_boards_em(code)
                return code, info.get("industry"), info.get("pe"), info.get("pb")
            except Exception:
                return code, None, None, None

        workers = min(30, len(codes))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for code, ind, pe, pb in pool.map(fetch_one, codes):
                if code in result:
                    result[code]["industry"] = ind
                    result[code]["pe"] = pe
                    result[code]["pb"] = pb

    return result


# ─── 主选股函数（生成器版）────────────────────────────────────────────────

def screen_stocks_stream(
    change_pct_min: float | None = None,
    change_pct_max: float | None = None,
    volume_min: float | None = None,
    volume_max: float | None = None,
    industry: str | None = None,
    pe_max: float | None = None,
    pb_max: float | None = None,
    signal_types: list[str] | None = None,
    require_dual_cross: bool = False,
    level: str = "daily",
    pool_size: int = 100,
    max_results: int = 50,
):
    """
    选股主入口（生成器版）。yield 每条符合条件的结果，前端可边算边展示。

    yield dict:
        type: "progress" → { done, total }  进度
        type: "result"   → 选股结果 dict
        type: "done"     → None（全部完成）
    """
    import time
    t0 = time.time()

    # Step 1：候选池
    hot_list = get_daily_hot_stocks(pool_size)
    t1 = time.time()
    print(f"[选股] 候选池获取 {len(hot_list)} 只，耗时 {t1-t0:.1f}s")
    if not hot_list:
        yield {"type": "done", "total": 0}
        return

    candidates = [item["code"] for item in hot_list]
    total = len(candidates)

    # 是否有基本面过滤条件
    need_industry = any(v is not None for v in [industry, pe_max, pb_max])

    # Step 2：行情 + 基本面
    quote_map = _get_quote_and_info(candidates, need_industry=need_industry)
    t2 = time.time()
    print(f"[选股] 行情+基本面，耗时 {t2-t1:.1f}s")

    # Step 3：基础指标预过滤
    prefiltered = []
    for code in candidates:
        q = quote_map.get(code, {})
        pct = q.get("change_pct", 0)
        vol = q.get("volume", 0)
        if change_pct_min is not None and pct < change_pct_min:
            continue
        if change_pct_max is not None and pct > change_pct_max:
            continue
        if volume_min is not None and vol < volume_min:
            continue
        if volume_max is not None and vol > volume_max:
            continue
        if industry is not None and q.get("industry") != industry:
            continue
        if pe_max is not None and q.get("pe") is not None and q["pe"] > pe_max:
            continue
        if pb_max is not None and q.get("pb") is not None and q["pb"] > pb_max:
            continue
        prefiltered.append(code)

    if not prefiltered:
        yield {"type": "done", "total": 0}
        return

    yield {"type": "progress", "done": 0, "total": len(prefiltered)}
    t3 = time.time()
    print(f"[选股] 预过滤剩余 {len(prefiltered)} 只，耗时 {t3-t2:.1f}s")

    # Step 4：并发缠论分析，结果随算随 yield
    WORKERS = 20
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(_analyze_stock, c, level): c for c in prefiltered}
        done_count = 0
        from concurrent.futures import as_completed

        for future in as_completed(futures):
            code = futures[future]
            done_count += 1
            if done_count % 50 == 0 or done_count == len(prefiltered):
                yield {"type": "progress", "done": done_count, "total": len(prefiltered)}

            try:
                analysis = future.result(timeout=30)  # 单只股票分析超时 30 秒
            except (FuturesTimeoutError, TimeoutError):
                analysis = None

            if analysis is None:
                continue

            if signal_types:
                if analysis["latest_signal"] is None:
                    continue
                if analysis["latest_signal"].type not in signal_types:
                    continue

            if require_dual_cross and not analysis["has_dual_cross"]:
                continue

            q = quote_map.get(code, {})
            sig = analysis["latest_signal"]
            sig_date_str = None
            sig_conf = None
            if sig is not None:
                sig_date_str = str(sig.datetime)[:10]
                sig_conf = round(sig.confidence, 2)

            yield {
                "type": "result",
                "data": {
                    "code": code,
                    "name": q.get("name", code),
                    "price": q.get("price", 0),
                    "change_pct": q.get("change_pct", 0),
                    "volume": q.get("volume", 0),
                    "amount": q.get("amount", 0),
                    "industry": q.get("industry"),
                    "pe": q.get("pe"),
                    "pb": q.get("pb"),
                    "latest_signal": sig.type if sig else None,
                    "latest_signal_date": sig_date_str,
                    "latest_signal_conf": sig_conf,
                    "has_dual_cross": analysis["has_dual_cross"],
                    "dual_cross_date": analysis["dual_cross_date"],
                    "trend": analysis["trend"],
                }
            }

    t4 = time.time()
    print(f"[选股] 完成，缠论分析耗时 {t4-t3:.1f}s")
    yield {"type": "done", "total": done_count}


def screen_stocks(
    change_pct_min: float | None = None,
    change_pct_max: float | None = None,
    volume_min: float | None = None,
    volume_max: float | None = None,
    industry: str | None = None,
    pe_max: float | None = None,
    pb_max: float | None = None,
    signal_types: list[str] | None = None,
    require_dual_cross: bool = False,
    level: str = "daily",
    pool_size: int = 100,
    max_results: int = 50,
) -> list[dict]:
    """
    选股主入口（兼容版）。内部调用生成器，等全部算完返回列表。
    """
    output = []
    for item in screen_stocks_stream(
        change_pct_min=change_pct_min,
        change_pct_max=change_pct_max,
        volume_min=volume_min,
        volume_max=volume_max,
        industry=industry,
        pe_max=pe_max,
        pb_max=pb_max,
        signal_types=signal_types,
        require_dual_cross=require_dual_cross,
        level=level,
        pool_size=pool_size,
        max_results=max_results,
    ):
        if item["type"] == "result":
            output.append(item["data"])
            if len(output) >= max_results:
                break
    return output
