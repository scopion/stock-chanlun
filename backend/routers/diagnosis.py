from __future__ import annotations

import asyncio
import json
import logging
import os

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from ai.chat_sessions import get_or_create_session
from core.chanlun_analysis import run_analysis
from deps import check_ai_diagnosis_rate_limits, client_ip
from services.akshare_service import get_stock_info, normalize_stock_code

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/api/ai/diagnosis", tags=["AI诊股"])
async def ai_diagnosis(
    request: Request,
    code: str = Query(..., description="股票代码"),
    question: str = Query(..., description="用户问题"),
    session_id: str = Query("default", description="会话ID"),
    model: str = Query("deepseek", description="AI模型"),
):
    check_ai_diagnosis_rate_limits(client_ip(request))

    log.info(
        "AI诊断 GET code=%s question=%s session=%s",
        code,
        question[:80],
        session_id,
    )

    if model not in ("deepseek", "gemini"):
        model = "deepseek"

    async def event_stream():
        try:
            # 必须为首条 yield：run_server 重定向 stdout 后，若在首次 chunk 前写 stdout 可能触发异常导致整块 500
            yield ": stream-open\n\n"

            log.debug("AI诊断 event_stream 启动 session=%s", session_id)
            log.debug("AI诊断 准备处理 model=%s", model)
            sym, _exchange = normalize_stock_code(code)

            stock_name = ""
            try:
                info = get_stock_info(sym)
                stock_name = str(info.get("名称", sym))
            except Exception:
                stock_name = sym

            analysis_context = ""
            try:
                result = await asyncio.to_thread(run_analysis, sym, "daily")
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

            session = get_or_create_session(session_id)
            session.add("user", question)

            messages = [{"role": "system", "content": system_prompt}] + session.history()

            full_text = ""
            try:
                if model.startswith("deepseek"):
                    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
                    if not key:
                        yield f"data: {json.dumps({'error': 'DEEPSEEK_API_KEY 未设置，请在 .env 中配置'}, ensure_ascii=False)}\n\n"
                        return

                    log.info("AI诊断 DeepSeek 流式开始 session=%s", session_id)
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
                            log.info(
                                "AI诊断 DeepSeek HTTP 状态 session=%s status=%s",
                                session_id,
                                resp.status_code,
                            )
                            resp.raise_for_status()
                            async for line in resp.aiter_lines():
                                if not line.strip() or not line.startswith("data:"):
                                    continue
                                data = line[5:].strip()
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                    content = (
                                        chunk.get("choices", [{}])[0]
                                        .get("delta", {})
                                        .get("content", "")
                                    )
                                    if content:
                                        full_text += content
                                        yield f"data: {json.dumps({'token': content}, ensure_ascii=False)}\n\n"
                                except json.JSONDecodeError:
                                    continue
                    log.info(
                        "AI诊断 DeepSeek 完成 session=%s chars=%s",
                        session_id,
                        len(full_text),
                    )

                elif model.startswith("gemini"):
                    key = os.environ.get("GEMINI_API_KEY", "").strip()
                    if not key:
                        yield f"data: {json.dumps({'error': 'GEMINI_API_KEY 未设置，请在 .env 中配置'}, ensure_ascii=False)}\n\n"
                        return

                    from ai.llm_client import LLMClient

                    gemini_client = LLMClient(model=model)
                    full_text = gemini_client.chat(
                        prompt=question,
                        system=system_prompt,
                        temperature=0.4,
                    )
                    for char in full_text:
                        yield f"data: {json.dumps({'token': char}, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0.02)

            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

            session.add("assistant", full_text)

            yield f"data: {json.dumps({'done': True, 'full': full_text}, ensure_ascii=False)}\n\n"

        except Exception as e:
            log.exception("AI诊断流未捕获异常 session=%s", session_id)
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/ai/diagnosis", tags=["AI诊股"])
async def ai_diagnosis_post(
    request: Request,
    code: str = Query(...),
    question: str = Query(...),
    session_id: str = Query("default"),
    model: str = Query("deepseek"),
):
    return await ai_diagnosis(
        request=request,
        code=code,
        question=question,
        session_id=session_id,
        model=model,
    )
