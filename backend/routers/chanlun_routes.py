from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, HTTPException, Query, Request

from ai.analysis_agent import SYSTEM_PROMPT, build_analysis_prompt, parse_llm_response
from ai.divergence import DivergenceDetector
from ai.llm_client import get_llm_client
from ai.strategy_engine import StrategyEngine
from ai.wave_classifier import WaveClassifier
from chanlun.elements import ChanlunAnalysis
from chanlun.engine import ChanlunEngine
from core.chanlun_analysis import get_kline_df_for_ai, level_to_period, run_analysis
from deps import check_chanlun_rate_limits, client_ip
from services.akshare_service import get_kline_hist
from utils import chanlun_cache

router = APIRouter()


@router.get("/api/chanlun/{code}", tags=["缠论"], summary="缠论完整分析")
async def analyze_chanlun(
    request: Request,
    code: str,
    level: str = Query(
        "daily",
        pattern="^(60min|daily|weekly|monthly)$",
    ),
):
    check_chanlun_rate_limits(client_ip(request))
    result = await asyncio.to_thread(run_analysis, code, level)
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
                "low": b.low,
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
                "low": s.low,
            }
            for s in result.xiangs
        ],
        "zhongshus": [
            {
                "id": z.id,
                "start": str(z.start)[:19],
                "end": str(z.end)[:19],
                "range_high": z.range_high,
                "range_low": z.range_low,
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
                "description": s.description,
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
                "strength": lvl.strength,
            }
            for lvl in result.support_resistance
        ],
    }


@router.get("/api/chanlun/{code}/multi-level", tags=["缠论"], summary="多级别并行缠论分析")
async def chanlun_multi_level(
    request: Request,
    code: str,
    levels: str = Query(
        "daily,weekly",
        description="逗号分隔的分析级别，如 daily,weekly,60min",
    ),
):
    check_chanlun_rate_limits(client_ip(request))
    t0 = time.time()

    level_list = [l.strip() for l in levels.split(",") if l.strip()]
    level_list = list(dict.fromkeys(level_list))

    def _serialize_result(result: ChanlunAnalysis) -> dict:
        return {
            "level": result.level,
            "trend": result.trend,
            "summary": result.summary,
            "bis_count": len(result.bis),
            "zhongshus_count": len(result.zhongshus),
            "signals_count": len(result.signals),
            "signals": [
                {
                    "type": s.type,
                    "price": s.price,
                    "datetime": str(s.datetime)[:19],
                    "confidence": s.confidence,
                    "description": s.description,
                }
                for s in result.signals[-3:]
            ],
            "supportResistance": [
                {
                    "type": lvl.type,
                    "price": lvl.price,
                    "datetime": str(lvl.datetime)[:19],
                    "strength": lvl.strength,
                }
                for lvl in result.support_resistance[-5:]
            ],
        }

    results: dict[str, dict | str] = {}

    def _safe_analyze(level: str) -> tuple[str, dict | str]:
        try:
            cache_key = f"{code}:{level}"
            cached = chanlun_cache.get(cache_key)
            if cached is not None:
                return level, _serialize_result(cached)

            period = level_to_period(level)
            df = get_kline_hist(code, period=period, adjust="qfq")
            if df.empty or len(df) < 20:
                return level, "数据不足"

            engine = ChanlunEngine(df)
            result = engine.analyze(level=level)
            result.stock_code = code
            chanlun_cache.set(cache_key, result)
            return level, _serialize_result(result)
        except HTTPException:
            return level, "数据不足"
        except Exception as e:
            return level, str(e)

    def _run_pool():
        with ThreadPoolExecutor(max_workers=min(len(level_list), 4)) as pool:
            futures = {pool.submit(_safe_analyze, lv): lv for lv in level_list}
            for future in as_completed(futures):
                lv, data = future.result(timeout=60)
                results[lv] = data

    await asyncio.to_thread(_run_pool)

    ordered = {lv: results.get(lv, "未知错误") for lv in level_list}
    t1 = time.time()
    return {
        "code": code,
        "levels": ordered,
        "count": len(level_list),
        "elapsed_ms": round((t1 - t0) * 1000, 1),
    }


@router.get("/api/chanlun/{code}/ai", tags=["缠论"], summary="AI 策略信号（背驰 + 规则 + LLM）")
async def ai_signal(
    request: Request,
    code: str,
    level: str = Query("daily"),
    model: str = Query("deepseek", description="AI 模型：deepseek / gemini"),
):
    check_chanlun_rate_limits(client_ip(request))

    try:
        return await _ai_signal_impl(code, level, model)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI 策略生成失败: {e!s}",
        ) from e


async def _ai_signal_impl(code: str, level: str, model: str) -> dict:
    df_for_ai, result = await asyncio.to_thread(get_kline_df_for_ai, code, level)
    current_price = float(result.klines[-1].close) if result.klines else 0.0

    divergence = None
    if not df_for_ai.empty:
        try:
            div_detector = DivergenceDetector(df_for_ai.tail(200))
            divergence = div_detector.check_divergence(result.bis)
        except Exception:
            pass

    # 使用缠论引擎统一趋势（与前端展示一致），WaveClassifier 仅用于多级别共振
    trend = result.trend

    engine = StrategyEngine(
        signals=result.signals,
        trend=trend,
        current_price=current_price,
        current_level=level,
        zhongshus=result.zhongshus,
        divergence=divergence,
    )
    signal = engine.generate_signal()
    signal.stock_code = code

    resonance = None

    llm_result = None
    llm_error = None
    try:
        llm = get_llm_client(model)
        prompt = build_analysis_prompt(
            code=code,
            level=level,
            klines=[k.__dict__ for k in result.klines],
            trend=trend,
            divergence=divergence,
            signals=[s.__dict__ for s in result.signals],
            zhongshus=[z.__dict__ for z in result.zhongshus],
            bis=[b.__dict__ for b in result.bis],
        )
        raw = llm.chat(prompt, system=SYSTEM_PROMPT, temperature=0.3)
        llm_result = parse_llm_response(raw)
        if not isinstance(llm_result, dict):
            llm_result = None
            llm_error = "LLM 解析结果非对象"
    except Exception as e:
        llm_error = str(e)

    lr = llm_result if isinstance(llm_result, dict) else None

    return {
        "stock_code": signal.stock_code,
        "level": signal.level,
        "direction": (lr.get("direction") if lr else None) or signal.direction,
        "confidence": lr["confidence"] if lr and "confidence" in lr else signal.confidence,
        "risk_level": (lr.get("risk_level") if lr else None) or signal.risk_level,
        "entry_price": (lr.get("entry_price") if lr else None) or signal.entry_price,
        "stop_loss": (lr.get("stop_loss") if lr else None) or signal.stop_loss,
        "take_profit": (lr.get("take_profit") if lr else None) or signal.take_profit,
        "holding_period": (lr.get("holding_period") if lr else None) or signal.holding_period,
        "description": (lr.get("reasoning") if lr else None) or signal.description,
        "trend": trend,
        "divergence": divergence,
        "divergence_level": level if divergence else None,
        "resonance": resonance,
        "llm": {
            "model": model,
            "used": lr is not None and llm_error is None,
            "error": llm_error,
        },
    }
