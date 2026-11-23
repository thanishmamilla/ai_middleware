import time
import json
import asyncio
import logging
from typing import AsyncGenerator, Dict, Any, Optional
from app.guardrails.input_guardrail import evaluate_heavy_safety
from app.guardrails.output_guardrail import sanitize_output
from app.core.telemetry import telemetry_engine

logger = logging.getLogger("SpeculativeStream")

async def mock_stream_tokens(model: str) -> AsyncGenerator[str, None]:
    """
    Simulates streaming tokens from an LLM provider for demonstration/testing.
    """
    sample_text = (
        f"Hello from enterprise gateway via {model}! "
        "Here is the detailed analysis you requested. "
        "Enterprise gateways ensure maximum uptime, zero-leakage security, and low latency."
    )
    words = sample_text.split()
    for word in words:
        await asyncio.sleep(0.04)  # ~40ms token interval
        yield word + " "

async def speculative_guardrail_stream(
    tenant_id: str,
    model_requested: str,
    model_executed: str,
    raw_prompt: str,
    token_generator: Optional[AsyncGenerator[str, None]] = None
) -> AsyncGenerator[str, None]:
    """
    Races heavy safety classifier concurrently with the live streaming token generation.
    If safety triggers midway, aborts the stream immediately and transmits a policy refusal.
    """
    start_time = time.time()
    ttft_time: Optional[float] = None
    accumulated_content = []

    # 1. Spawn heavy safety check in parallel
    safety_task = asyncio.create_task(evaluate_heavy_safety(raw_prompt))

    # Fallback to simulated stream if generator is not provided
    stream_source = token_generator if token_generator is not None else mock_stream_tokens(model_executed)

    aborted = False
    try:
        async for chunk in stream_source:
            if ttft_time is None:
                ttft_time = (time.time() - start_time) * 1000.0

            # 2. Check if the parallel safety check has completed with a violation
            if safety_task.done():
                is_safe, violation_reason = safety_task.result()
                if not is_safe:
                    logger.warning(f"Parallel Safety Classifier TRIPPED: {violation_reason}. Aborting stream.")
                    aborted = True
                    # Emit SSE event indicating early termination
                    error_payload = {
                        "error": {
                            "type": "safety_violation",
                            "message": f"[GATEWAY SAFETY ABORT]: {violation_reason}"
                        }
                    }
                    yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"
                    break

            accumulated_content.append(chunk)

            # Format standard OpenAI SSE chunk
            sse_chunk = {
                "id": f"chatcmpl-stream-{int(time.time()*1000)}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model_executed,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": chunk},
                        "finish_reason": None
                    }
                ]
            }
            yield f"data: {json.dumps(sse_chunk)}\n\n"

        # 3. Final verification if safety check was still running when generation ended
        if not aborted and not safety_task.done():
            is_safe, violation_reason = await safety_task
            if not is_safe:
                logger.warning(f"Post-stream safety classifier flagged input: {violation_reason}")
                error_payload = {
                    "error": {
                        "type": "safety_violation",
                        "message": f"[GATEWAY SAFETY ABORT]: {violation_reason}"
                    }
                }
                yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"
                aborted = True

        if not aborted:
            # Emit final [DONE]
            end_chunk = {
                "id": f"chatcmpl-stream-{int(time.time()*1000)}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model_executed,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop"
                    }
                ]
            }
            yield f"data: {json.dumps(end_chunk)}\n\n"
            yield "data: [DONE]\n\n"

    finally:
        if not safety_task.done():
            safety_task.cancel()

        total_latency = (time.time() - start_time) * 1000.0
        full_text = "".join(accumulated_content)
        sanitized_text, was_sanitized = sanitize_output(full_text)

        telemetry_engine.record_transaction(
            tenant_id=tenant_id,
            model_requested=model_requested,
            model_executed=model_executed,
            prompt_tokens=len(raw_prompt.split()),
            completion_tokens=len(accumulated_content),
            total_latency_ms=total_latency,
            ttft_ms=ttft_time,
            cached=False,
            fallback_occurred=False,
            error="Safety Violation" if aborted else None
        )

