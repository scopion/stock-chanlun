"""
ChanStock — 缠论智能股票分析系统
FastAPI 后端入口
"""
# requests 补丁：只 patch HTTPAdapter.send，这是所有请求的最终出口。
# 对 eastmoney 等金融域名自动禁用代理（Windows 系统代理导致 SSL 挂起）。
import requests as _req_mod
_NO_PROXY = {"http": None, "https": None}
_EM_HOSTS = ("eastmoney", "qt.gtimg", "sinajs", "ifzq", "10jqka")
_orig_send = _req_mod.adapters.HTTPAdapter.send

def _patched_send(adapter, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
    url = getattr(request, 'url', '') or ''
    if timeout is None and url:
        timeout = 12.0
    if proxies is None and url and any(h in url for h in _EM_HOSTS):
        proxies = _NO_PROXY
        verify = False
    return _orig_send(adapter, request, stream=stream, timeout=timeout, verify=verify, cert=cert, proxies=proxies)

_req_mod.adapters.HTTPAdapter.send = _patched_send
print("[补丁] requests: timeout=12s + 禁用代理 for eastmoney")

import math
import os
import json
import uuid
import asyncio
from datetime import datetime, timezone

import httpx

# 加载 .env 环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # 未安装 python-dotenv 时忽略
import sys
from pathlib import Path
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import Optional
import pandas as pd

from chanlun.elements import ChanlunAnalysis, ASignal, StockInfo
from chanlun.engine import ChanlunEngine
from ai.divergence import DivergenceDetector
from ai.wave_classifier import WaveClassifier
from ai.strategy_engine import StrategyEngine
from ai.llm_client import get_llm_client, set_llm_model
from ai.analysis_agent import build_analysis_prompt, parse_llm_response, SYSTEM_PROMPT
from services.akshare_service import (
    get_kline_hist, get_realtime_quote, search_stocks,
    get_stock_info, get_index_quote, normalize_stock_code,
    get_daily_hot_stocks, warm_hot_cache,
    get_market_overview_bundle, get_stock_news,
    get_stock_depth_em, get_stock_boards_em, get_stock_symbol_news_em,
    get_board_constituents_em,
)

# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="ChanStock API",
    description="缠论智能股票分析系统 API",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── 工具函数 ──────────────────────────────────────────────────────────────

def _finite_float(x, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def _level_to_period(level: str) -> str:
    """缠论级别 → AKShare period 参数"""
    mapping = {
        "1min": "5", "5min": "5", "15min": "15",
        "30min": "30", "60min": "60",
        "daily": "daily", "weekly": "weekly", "monthly": "monthly"
    }
    return mapping.get(level, "daily")


def _run_analysis(code: str, level: str, kline_limit: int = 500) -> ChanlunAnalysis:
    """执行缠论分析（与 /api/stocks/{code}/kline 默认 limit=500 对齐，避免笔日期落在前端 K 线之外）"""
    period = _level_to_period(level)
    df = get_kline_hist(code, period=period,
                        start_date=None, adjust="qfq")

    if df.empty or len(df) < 20:
        raise HTTPException(status_code=404,
                            detail=f"{code} {level}级别K线数据不足（仅{len(df) if not df.empty else 0}根），请换日线/30分钟级别尝试")

    if len(df) > kline_limit:
        df = df.tail(kline_limit).reset_index(drop=True)

    engine = ChanlunEngine(df)
    result = engine.analyze(level=level)
    result.stock_code = code
    return result


# ─── 股票数据 API ───────────────────────────────────────────────────────────

@app.get("/api/stocks/search", tags=["数据"])
def search_stock(q: str = Query(..., min_length=1)):
    """搜索股票"""
    df = search_stocks(q)
    if df.empty:
        return {"stocks": [], "total": 0}
    return {
        "stocks": df.head(20)[['code', 'name']].to_dict(orient='records'),
        "total": len(df)
    }


@app.get("/api/stocks/hot", tags=["数据"])
def hot_stocks(limit: int = Query(15, ge=1, le=50)):
    """当日涨幅榜（新浪财经），按涨跌幅从高到低；获取失败时返回空列表。"""
    stocks = get_daily_hot_stocks(limit)
    return {"stocks": stocks, "total": len(stocks), "error": None if stocks else "获取失败，请稍后重试"}


@app.get("/api/stocks/screen", tags=["选股"])
def screen_stocks_api(
    change_pct_min: Optional[float] = Query(None, description="最小涨跌幅（%）"),
    change_pct_max: Optional[float] = Query(None, description="最大涨跌幅（%）"),
    volume_min: Optional[float] = Query(None, description="最小成交量（手）"),
    volume_max: Optional[float] = Query(None, description="最大成交量（手）"),
    industry: Optional[str] = Query(None, description="行业板块名称（精确匹配）"),
    pe_max: Optional[float] = Query(None, description="市盈率上限"),
    pb_max: Optional[float] = Query(None, description="市净率上限"),
    signals: Optional[str] = Query(None, description="逗号分隔买卖点类型，如 一买,二买"),
    dual_cross: bool = Query(False, description="是否必须 MACD+SKDJ 双金叉共振"),
    level: str = Query("daily", pattern="^(1min|5min|15min|30min|60min|daily|weekly|monthly)$"),
    pool_size: int = Query(100, ge=10, le=1000, description="候选池大小（最高 1000）"),
):
    """
    选股接口 — 按基础指标、缠论买卖点、MACD+SKDJ 双金叉共振筛选股票。

    signals 逗号分隔，支持：一买、二买、三买、一卖、二卖、三卖
    """
    import ast
    from services.screening_service import screen_stocks

    signal_types: list[str] | None = None
    if signals:
        raw = [s.strip() for s in signals.split(",") if s.strip()]
        if raw:
            signal_types = raw

    results = screen_stocks(
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
    return {"results": results, "total": len(results)}


@app.get("/api/stocks/screen-stream", tags=["选股"])
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
    level: str = Query("daily", pattern="^(1min|5min|15min|30min|60min|daily|weekly|monthly)$"),
    pool_size: int = Query(100, ge=10, le=1000, description="候选池大小（最高 1000）"),
    max_results: int = Query(50, ge=1, le=200, description="最多返回条数"),
):
    """
    SSE 流式选股接口 — 边分析边推送结果，前端可实时增量展示，无超时问题。
    """
    from services.screening_service import screen_stocks_stream
    import json

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
@app.get("/api/market/overview", tags=["数据"])
def market_overview():
    """大盘概览：主要指数、A股涨跌家数、行业板块领涨/领跌"""
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


@app.get("/api/news", tags=["数据"])
def news(limit: int = Query(10, ge=1, le=30)):
    """财经新闻列表"""
    return {"items": get_stock_news(limit)}


@app.get("/api/sector/{name}/stocks", tags=["数据"])
def sector_stocks(name: str):
    """板块成分股（行业/概念）：返回按涨跌幅降序排列的成分股列表"""
    try:
        return get_board_constituents_em(name)
    except Exception as e:
        print(f"[板块] 「{name}」获取失败: {e}")
        return {"sector_name": name, "board_type": None, "stocks": [], "total": 0}


@app.get("/api/stocks/{code}/info", tags=["数据"])
def stock_info(code: str):
    """获取股票基本信息"""
    sym, exchange = normalize_stock_code(code)
    info = get_stock_info(sym)
    return {"code": sym, "exchange": exchange, "info": info}


@app.get("/api/stocks/{code}/extras", tags=["数据"])
def stock_extras(
    code: str,
    news_limit: int = Query(8, ge=1, le=20),
):
    """个股扩展：五档盘口、行业/资料要点、东方财富个股新闻（聚合，减少前端请求次数）"""
    sym, exchange = normalize_stock_code(code)
    return {
        "code": sym,
        "exchange": exchange,
        "depth": get_stock_depth_em(sym),
        "boards": get_stock_boards_em(sym),
        "news": get_stock_symbol_news_em(sym, news_limit),
    }


@app.get("/api/stocks/{code}/quote", tags=["数据"])
def realtime_quote(code: str):
    """实时行情（腾讯列表解析失败时用 get_stock_info 同一数据源兜底）"""
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
            "price": _finite_float(info.get("现价")),
            "change_pct": _finite_float(info.get("涨跌幅")),
            "volume": _finite_float(info.get("成交量")),
            "amount": _finite_float(info.get("成交额")),
            "high": _finite_float(info.get("最高")),
            "low": _finite_float(info.get("最低")),
            "open": _finite_float(info.get("今开")),
            "prev_close": _finite_float(info.get("昨收")),
        }

    raise HTTPException(status_code=404, detail="股票未找到")


@app.get("/api/stocks/{code}/kline", tags=["数据"])
def stock_kline(
    code: str,
    level: str = Query("daily", pattern="^(1min|5min|15min|30min|60min|daily|weekly|monthly)$"),
    limit: int = Query(500, le=2000),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD")
):
    """获取K线数据"""
    period = _level_to_period(level)
    df = get_kline_hist(code, period=period, adjust="qfq")
    if df.empty:
        return {"klines": [], "total": 0}

    # 时间范围筛选
    if start_date:
        df = df[df['date'] >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df['date'] <= pd.Timestamp(end_date) + pd.Timedelta(days=1)]

    df = df.tail(limit).reset_index(drop=True)

    return {
        "klines": [
            {
                "date": str(r['date'])[:19],
                "open": float(r['open']),
                "high": float(r['high']),
                "low": float(r['low']),
                "close": float(r['close']),
                "volume": float(r.get('volume', 0) or 0)
            }
            for _, r in df.iterrows()
        ],
        "total": len(df)
    }


# ─── 缠论分析 API ───────────────────────────────────────────────────────────

@app.get("/api/chanlun/{code}", tags=["缠论"])
def analyze_chanlun(
    code: str,
    level: str = Query("daily", pattern="^(1min|5min|15min|30min|60min|daily|weekly|monthly)$"),
):
    """缠论完整分析"""
    try:
        result = _run_analysis(code, level)

        return {
            "stock_code": result.stock_code,
            "level": result.level,
            "trend": result.trend,
            "summary": result.summary,
            "bis": [
                {
                    "id": b.id,
                    "start": str(b.start)[:19],
                    "end": str(b.end)[:19],
                    "direction": b.direction,
                    "high": b.high,
                    "low": b.low
                }
                for b in result.bis
            ],
            "xiangs": [
                {
                    "id": s.id,
                    "start": str(s.start)[:19],
                    "end": str(s.end)[:19],
                    "direction": s.direction,
                    "high": s.high,
                    "low": s.low
                }
                for s in result.xiangs
            ],
            "zhongshus": [
                {
                    "id": z.id,
                    "start": str(z.start)[:19],
                    "end": str(z.end)[:19],
                    "range_high": z.range_high,
                    "range_low": z.range_low
                }
                for z in result.zhongshus
            ],
            "signals": [
                {
                    "type": s.type,
                    "level": s.level,
                    "price": s.price,
                    "datetime": str(s.datetime)[:19],
                    "confidence": s.confidence,
                    "stop_loss": s.stop_loss,
                    "take_profit": s.take_profit,
                    "description": s.description
                }
                for s in result.signals
            ],
            "supportResistance": [
                {
                    "type": lvl.type,
                    "price": lvl.price,
                    "source": lvl.source,
                    "relatedId": lvl.related_id,
                    "datetime": str(lvl.datetime)[:19],
                    "strength": lvl.strength
                }
                for lvl in result.support_resistance
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chanlun/{code}/ai", tags=["缠论"])
def ai_signal(
    code: str,
    level: str = Query("daily"),
    model: str = Query("deepseek", description="AI 模型：deepseek / gemini")
):
    """
    AI 策略信号：
    - rule-based：背驰检测 + 缠论规则（始终执行）
    - LLM：DeepSeek / Gemini 增强分析（需要 API Key）
    """
    try:
        result = _run_analysis(code, level)
        current_price = float(result.klines[-1].close) if result.klines else 0.0

        # 背驰检测 — 直接复用已有K线DataFrame，不重复请求
        period = _level_to_period(level)
        df_for_div = get_kline_hist(code, period=period, adjust="qfq")
        divergence = None
        if not df_for_div.empty:
            try:
                div_detector = DivergenceDetector(df_for_div.tail(200))
                divergence = div_detector.check_divergence(result.bis)
            except Exception:
                pass

        # 走势分类
        classifier = WaveClassifier()
        wave_class = classifier.classify(result.xiangs, result.zhongshus, current_price)

        # 规则策略
        engine = StrategyEngine(
            signals=result.signals,
            trend=wave_class['trend'],
            current_price=current_price,
            current_level=level,
            zhongshus=result.zhongshus,
            divergence=divergence
        )
        signal = engine.generate_signal()
        signal.stock_code = code

        # 多级别共振（日 + 30分钟）— 只取日线趋势，不重跑完整分析
        resonance = None
        if level == "30min":
            try:
                daily_df = get_kline_hist(code, period="daily", adjust="qfq")
                if not daily_df.empty:
                    from chanlun.engine import ChanlunEngine
                    daily_result = ChanlunEngine(daily_df).analyze(level="daily")
                    daily_cls = WaveClassifier().classify(
                        daily_result.xiangs, daily_result.zhongshus,
                        float(daily_result.klines[-1].close) if daily_result.klines else 0.0
                    )
                    resonance = classifier.multi_level_resonance([
                        {"trend": wave_class, "level": level},
                        {"trend": daily_cls, "level": "daily"}
                    ])
            except Exception:
                pass

        # LLM 增强
        llm_result = None
        llm_error = None
        try:
            llm = get_llm_client(model)
            prompt = build_analysis_prompt(
                code=code,
                level=level,
                klines=[k.__dict__ for k in result.klines],
                trend=wave_class['trend'],
                divergence=divergence,
                signals=[s.__dict__ for s in result.signals],
                zhongshus=[z.__dict__ for z in result.zhongshus],
                bis=[b.__dict__ for b in result.bis],
            )
            raw = llm.chat(prompt, system=SYSTEM_PROMPT, temperature=0.3)
            llm_result = parse_llm_response(raw)
        except Exception as e:
            llm_error = str(e)

        return {
            "stock_code": signal.stock_code,
            "level": signal.level,
            "direction": llm_result.get("direction") if llm_result else signal.direction,
            "confidence": llm_result.get("confidence") if llm_result else signal.confidence,
            "risk_level": llm_result.get("risk_level") if llm_result else signal.risk_level,
            "entry_price": llm_result.get("entry_price") or signal.entry_price,
            "stop_loss": llm_result.get("stop_loss") or signal.stop_loss,
            "take_profit": llm_result.get("take_profit") or signal.take_profit,
            "holding_period": llm_result.get("holding_period") if llm_result else signal.holding_period,
            "description": llm_result.get("reasoning") if llm_result else signal.description,
            "trend": wave_class['trend'],
            "divergence": divergence,
            "resonance": resonance,
            "llm": {
                "model": model,
                "used": llm_result is not None,
                "error": llm_error,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── 自选股管理 API（持久化到 JSON 文件）──────────────────────────────────────

_WATCHLIST_FILE = Path(__file__).parent / "watchlist.json"


def _load_watchlist() -> dict[str, str]:
    """返回 {股票代码: 添加时间ISO字符串}"""
    try:
        if _WATCHLIST_FILE.exists():
            data = json.loads(_WATCHLIST_FILE.read_text(encoding="utf-8"))
            return {str(k).zfill(6): str(v) for k, v in data.items() if str(k).strip()}
    except Exception as e:
        print(f"自选股加载失败: {e}")
    return {}


def _save_watchlist(data: dict[str, str]):
    try:
        _WATCHLIST_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"自选股保存失败: {e}")


_watchlist: dict[str, str] = _load_watchlist()


@app.get("/api/watchlist", tags=["自选"])
def get_watchlist():
    """获取自选股列表"""
    if not _watchlist:
        return {"stocks": []}

    codes = list(_watchlist.keys())
    df = get_realtime_quote(codes)
    if df.empty:
        return {"stocks": [], "total": 0}

    return {
        "stocks": [
            {
                "code": str(row.get("代码", "")),
                "name": str(row.get("名称", "")),
                "price": float(row.get("最新价", 0) or 0),
                "change_pct": float(row.get("涨跌幅", 0) or 0),
                "added_at": _watchlist.get(str(row.get("代码", "")), ""),
            }
            for _, row in df.iterrows()
        ],
        "total": len(_watchlist)
    }


@app.post("/api/watchlist/{code}", tags=["自选"])
def add_watchlist(code: str):
    """添加自选股"""
    sym, _ = normalize_stock_code(code)
    if sym not in _watchlist:
        _watchlist[sym] = datetime.now().isoformat()
        _save_watchlist(_watchlist)
    return {"code": sym, "added": True, "added_at": _watchlist[sym], "total": len(_watchlist)}


@app.delete("/api/watchlist/{code}", tags=["自选"])
def remove_watchlist(code: str):
    """删除自选股"""
    sym, _ = normalize_stock_code(code)
    if sym in _watchlist:
        del _watchlist[sym]
        _save_watchlist(_watchlist)
    return {"code": sym, "removed": True, "total": len(_watchlist)}


# ─── 评论笔记 API（持久化到 JSON 文件）────────────────────────────────────

_COMMENTS_FILE = Path(__file__).parent / "comments.json"


def _load_comments() -> dict[str, list[dict]]:
    """返回 {stock_code: [comment, ...]}"""
    try:
        if _COMMENTS_FILE.exists():
            return json.loads(_COMMENTS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[评论] 加载失败: {e}")
    return {}


def _save_comments(data: dict[str, list[dict]]):
    try:
        _COMMENTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[评论] 保存失败: {e}")


_comments: dict[str, list[dict]] = _load_comments()


@app.get("/api/comments/{stock_code}", tags=["评论"])
def get_comments(stock_code: str):
    """获取指定股票的全部笔记（按日期降序）"""
    sym, _ = normalize_stock_code(stock_code)
    items = _comments.get(sym, [])
    # 按 createdAt 降序
    items = sorted(items, key=lambda x: x.get("createdAt", ""), reverse=True)
    return {"comments": items, "total": len(items)}


@app.post("/api/comments/{stock_code}", tags=["评论"])
def add_comment(stock_code: str, comment_in: dict):
    """新增笔记"""
    sym, _ = normalize_stock_code(stock_code)
    content = (comment_in.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="笔记内容不能为空")

    now = datetime.utcnow().isoformat() + "Z"
    comment = {
        "id": str(uuid.uuid4()),
        "stockCode": sym,
        "content": content,
        "createdAt": now,
        "updatedAt": now,
    }
    if sym not in _comments:
        _comments[sym] = []
    _comments[sym].append(comment)
    _save_comments(_comments)
    return {"comment": comment, "added": True}


@app.put("/api/comments/{stock_code}/{comment_id}", tags=["评论"])
def update_comment(stock_code: str, comment_id: str, comment_in: dict):
    """更新笔记"""
    sym, _ = normalize_stock_code(stock_code)
    content = (comment_in.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="笔记内容不能为空")

    items = _comments.get(sym, [])
    for c in items:
        if c.get("id") == comment_id:
            c["content"] = content
            c["updatedAt"] = datetime.utcnow().isoformat() + "Z"
            _save_comments(_comments)
            return {"comment": c, "updated": True}
    raise HTTPException(status_code=404, detail="笔记不存在")


@app.delete("/api/comments/{stock_code}/{comment_id}", tags=["评论"])
def delete_comment(stock_code: str, comment_id: str):
    """删除笔记"""
    sym, _ = normalize_stock_code(stock_code)
    items = _comments.get(sym, [])
    original = len(items)
    items = [c for c in items if c.get("id") != comment_id]
    if len(items) == original:
        raise HTTPException(status_code=404, detail="笔记不存在")
    _comments[sym] = items
    _save_comments(_comments)
    return {"id": comment_id, "deleted": True}


# ─── AI 模型设置 ──────────────────────────────────────────────────────────

_SETTINGS_FILE = Path(__file__).parent / "settings.json"


def _load_settings() -> dict:
    try:
        if _SETTINGS_FILE.exists():
            return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"ai_model": "deepseek"}


def _save_settings(s: dict):
    try:
        _SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"设置保存失败: {e}")


@app.get("/api/settings", tags=["系统"])
def get_settings():
    """获取当前设置"""
    return _load_settings()


@app.put("/api/settings", tags=["系统"])
def update_settings(model: str = Query(..., description="AI 模型 deepseek / gemini")):
    """切换 AI 模型"""
    if model not in ("deepseek", "gemini"):
        raise HTTPException(status_code=400, detail="只支持 deepseek 和 gemini")
    set_llm_model(model)
    s = _load_settings()
    s["ai_model"] = model
    _save_settings(s)
    return {"ai_model": model, "ok": True}


# ─── AI 诊股对话 API（流式 SSE）────────────────────────────────────────────────

class _ChatSession:
    """轻量对话会话：维护最近 N 轮历史"""

    def __init__(self, max_turns: int = 10):
        self.messages: list[dict] = []
        self.max_turns = max_turns

    def add(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        if len(self.messages) > self.max_turns * 2:
            self.messages = self.messages[-self.max_turns * 2:]

    def history(self) -> list[dict]:
        return self.messages


# 内存中会话（进程重启后清空）
_chat_sessions: dict[str, _ChatSession] = {}


def _get_or_create_session(session_id: str) -> _ChatSession:
    if session_id not in _chat_sessions:
        _chat_sessions[session_id] = _ChatSession(max_turns=10)
    return _chat_sessions[session_id]


@app.get("/api/ai/diagnosis", tags=["AI诊股"])
async def ai_diagnosis(
    code: str = Query(..., description="股票代码"),
    question: str = Query(..., description="用户问题"),
    session_id: str = Query("default", description="会话ID"),
    model: str = Query("deepseek", description="AI模型"),
):
    """
    AI 诊股对话接口（流式 SSE）。
    用户描述股票问题，AI 结合缠论数据给出诊断。
    """
    sys.stdout.write(f"[AI诊断] GET 请求进入，code={code}, question={question[:20]}, session={session_id}\n")
    sys.stdout.flush()
    from ai.llm_client import get_llm_client, set_llm_model
    from chanlun.engine import ChanlunEngine

    # 加载/切换模型
    if model not in ("deepseek", "gemini"):
        model = "deepseek"

    async def event_stream():
        sys.stdout.write(f"[AI诊断] event_stream 启动，session={session_id}\n")
        sys.stdout.flush()
        try:
            sys.stdout.write(f"[AI诊断] 准备加载 LLM，model={model}\n")
            sys.stdout.flush()
            llm = get_llm_client(model)
            sys.stdout.write(f"[AI诊断] LLM 加载成功\n")
            sys.stdout.flush()
            sym, exchange = normalize_stock_code(code)

            # 尝试获取股票名称
            stock_name = ""
            try:
                info = get_stock_info(sym)
                stock_name = str(info.get("名称", sym))
            except Exception:
                stock_name = sym

            # 尝试获取缠论分析数据
            analysis_context = ""
            try:
                result = _run_analysis(sym, "daily")
                current_price = float(result.klines[-1].close) if result.klines else 0.0

                # 构建分析上下文
                recent_kl = result.klines[-20:] if len(result.klines) > 20 else result.klines
                kl_lines = "\n".join(
                    f"{k.date[:10]}  开:{k.open:.2f} 高:{k.high:.2f} 低:{k.low:.2f} 收:{k.close:.2f}"
                    for k in recent_kl
                )
                bi_lines = "\n".join(
                    f"[{b.start[:10]}] {b.direction} 高:{b.high:.2f} 低:{b.low:.2f}"
                    for b in result.bis[-5:]
                )
                zs_lines = "\n".join(
                    f"[{z.start[:10]}] 中枢 高:{z.range_high:.2f} 低:{z.range_low:.2f}"
                    for z in result.zhongshus[-3:]
                )
                sig_lines = "\n".join(
                    f"{s.datetime[:10]} {s.type}@{s.price:.2f} 置信:{s.confidence}"
                    for s in result.signals[-5:]
                )

                analysis_context = f"""
【{stock_name}({sym}) 日线数据】
最近K线：\n{kl_lines}
笔：\n{bi_lines or '暂无'}
中枢：\n{zs_lines or '暂无'}
买卖点：\n{sig_lines or '暂无'}
趋势：{result.trend}"""
            except Exception as e:
                analysis_context = f"[缠论数据获取失败: {e}]"

            # 系统提示词
            system_prompt = f"""你是专业的缠论技术分析助手，名称"缠师"。

用户会向你询问股票诊断问题。请结合以下缠论数据，
用通俗易懂的语言给出诊断建议，避免过于专业的术语堆砌。

当前股票数据：
{analysis_context}

回答要求：
1. 先确认用户问的股票，分析当前走势和位置
2. 结合缠论关键点（笔、中枢、背驰、买卖点）
3. 给出明确操作建议（买入/卖出/观望）
4. 如需要，提示风险和止损位
5. 保持友好专业的语气，像一个老练的分析师在聊天

重要：如果没有股票数据，请直接说明并建议用户提供股票代码。"""

            # 添加用户消息到历史
            session = _get_or_create_session(session_id)
            session.add("user", question)

            # 构建消息列表
            messages = [{"role": "system", "content": system_prompt}] + session.history()

            # 流式调用 DeepSeek
            full_text = ""
            try:
                if model.startswith("deepseek"):
                    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
                    if not key:
                        yield f"data: {json.dumps({'error': 'DEEPSEEK_API_KEY 未设置，请在 .env 中配置'}, ensure_ascii=False)}\n\n"
                        return

                    sys.stdout.write(f"[AI诊断] DeepSeek 流式调用开始，session={session_id}\n")
                    sys.stdout.flush()
                    # 使用 SSE 流式 API，禁用代理避免网络问题
                    body = {
                        "model": "deepseek-chat",
                        "messages": messages,
                        "temperature": 0.4,
                        "stream": True,
                    }
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        async with client.stream(
                            "POST",
                            "https://api.deepseek.com/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {key}",
                                "Content-Type": "application/json",
                            },
                            json=body,
                        ) as resp:
                            sys.stdout.write(f"[AI诊断] DeepSeek 响应状态: {resp.status_code}\n")
                            sys.stdout.flush()
                            resp.raise_for_status()
                            async for line in resp.aiter_lines():
                                if not line.strip() or not line.startswith("data:"):
                                    continue
                                data = line[5:].strip()
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                    content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                    if content:
                                        full_text += content
                                        yield f"data: {json.dumps({'token': content}, ensure_ascii=False)}\n\n"
                                except json.JSONDecodeError:
                                    continue
                    sys.stdout.write(f"[AI诊断] DeepSeek 流式完成，回复长度: {len(full_text)}\n")
                    sys.stdout.flush()

                elif model.startswith("gemini"):
                    key = os.environ.get("GEMINI_API_KEY", "").strip()
                    if not key:
                        yield f"data: {json.dumps({'error': 'GEMINI_API_KEY 未设置，请在 .env 中配置'}, ensure_ascii=False)}\n\n"
                        return

                    # Gemini 非流式
                    from ai.llm_client import LLMClient
                    gemini_client = LLMClient(model=model)
                    full_text = gemini_client.chat(
                        prompt=question,
                        system=system_prompt,
                        temperature=0.4,
                    )
                    for char in full_text:
                        yield f"data: {json.dumps({'token': char}, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0.02)  # 打字机效果延迟

            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

            # 保存助手回复到历史
            session.add("assistant", full_text)

            # 结束信号
            yield f"data: {json.dumps({'done': True, 'full': full_text}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/ai/diagnosis", tags=["AI诊股"])
async def ai_diagnosis_post(
    code: str = Query(...),
    question: str = Query(...),
    session_id: str = Query("default"),
    model: str = Query("deepseek"),
):
    """POST 版本的诊股接口（URL 编码问题少）"""
    return await ai_diagnosis(code=code, question=question, session_id=session_id, model=model)


# ─── 健康检查 ───────────────────────────────────────────────────────────────

@app.get("/health", tags=["系统"])
def health_check():
    return {"status": "ok", "version": "0.1.0"}


# ─── 启动 ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup():
    warm_hot_cache()
    # 恢复 AI 模型设置
    try:
        settings = _load_settings()
        model = settings.get("ai_model", "deepseek")
        set_llm_model(model)
        print(f"AI 模型已恢复: {model}")
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)