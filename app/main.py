import time
import logging
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.telemetry import telemetry_engine
from app.auth.tenant import authenticate_tenant, rate_limiter
from app.cache.semantic_cache import semantic_cache
from app.guardrails.input_guardrail import scan_and_mask_pii, validate_input_integrity
from app.guardrails.output_guardrail import sanitize_output
from app.guardrails.speculative_stream import speculative_guardrail_stream
from app.router.circuit_breaker import circuit_breaker
from app.router.fallback_router import fallback_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("EnterpriseAIGateway")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Enterprise AI Gateway: Multi-tenant auth, semantic caching, input/output guardrails, speculative streaming, circuit breakers, and provider fallback."
)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = Field(default="gpt-4o", description="Target model name")
    messages: List[ChatMessage]
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    stream: bool = Field(default=False, description="Enable SSE streaming with speculative guardrails")

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": time.time()
    }

@app.get("/admin/metrics")
async def get_metrics():
    """Retrieve gateway telemetry, latency, token consumption, and cache hit stats."""
    return telemetry_engine.get_summary()

@app.get("/admin/circuit-breaker")
async def get_circuit_status():
    """Retrieve current state of all downstream provider circuit breakers."""
    return circuit_breaker.get_status()

@app.delete("/admin/cache")
async def clear_cache():
    """Flush the semantic cache."""
    semantic_cache.clear()
    return {"message": "Semantic cache purged successfully."}

@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    tenant_meta: Dict = Depends(authenticate_tenant)
):
    start_time = time.time()
    tenant_id = tenant_meta["tenant_id"]
    rpm_limit = tenant_meta["rpm_limit"]
    tpm_limit = tenant_meta["tpm_limit"]

    # 1. Extract raw user prompt
    user_messages = [m.content for m in request.messages if m.role == "user"]
    raw_prompt = user_messages[-1] if user_messages else ""
    estimated_prompt_tokens = sum(len(m.content.split()) for m in request.messages)

    # 2. Rate Limiting Check (RPM / TPM)
    rate_limiter.check_and_record(
        tenant_id=tenant_id,
        rpm_limit=rpm_limit,
        estimated_tokens=estimated_prompt_tokens + 50,
        tpm_limit=tpm_limit
    )

    # 3. Input Guardrail: Fast Synchronous PII Scrubbing + Hard Injection Checks (<5ms)
    validate_input_integrity(raw_prompt)
    sanitized_prompt, pii_detected = scan_and_mask_pii(raw_prompt)
    if pii_detected:
        logger.info(f"Input Guardrail: PII detected and redacted for tenant '{tenant_id}'.")
        # Update sanitized prompt in messages
        for m in reversed(request.messages):
            if m.role == "user":
                m.content = sanitized_prompt
                break

    # 4. Semantic Cache Check (Threshold >= 0.96)
    if not request.stream:
        cached_result = semantic_cache.lookup(sanitized_prompt)
        if cached_result is not None:
            cached_response, similarity_score = cached_result
            total_latency = (time.time() - start_time) * 1000.0
            logger.info(f"Semantic Cache HIT! (Similarity: {similarity_score:.4f})")
            
            telemetry_engine.record_transaction(
                tenant_id=tenant_id,
                model_requested=request.model,
                model_executed="semantic-cache",
                prompt_tokens=estimated_prompt_tokens,
                completion_tokens=10,
                total_latency_ms=total_latency,
                ttft_ms=total_latency,
                cached=True,
                fallback_occurred=False
            )
            return JSONResponse(content=cached_response)

    # 5. Handle Streaming Request with Speculative Parallel Guardrails
    if request.stream:
        # Check chain to find candidate model
        chain = fallback_router.resolve_chain(request.model)
        chosen_model = chain[0]
        return StreamingResponse(
            speculative_guardrail_stream(
                tenant_id=tenant_id,
                model_requested=request.model,
                model_executed=chosen_model,
                raw_prompt=sanitized_prompt
            ),
            media_type="text/event-stream"
        )

    # 6. Non-Streaming Request Execution with Dynamic Router & Circuit Breaker
    response, executed_model, fallback_occurred = await fallback_router.execute_call(
        requested_model=request.model,
        messages=[{"role": m.role, "content": m.content} for m in request.messages],
        temperature=request.temperature,
        stream=False
    )

    # Convert response to standard dictionary format if needed
    if hasattr(response, "model_dump"):
        response_dict = response.model_dump()
    elif isinstance(response, dict):
        response_dict = response
    else:
        response_dict = dict(response)

    # 7. Output Guardrail (Leakage / Secret Redaction)
    assistant_content = ""
    if "choices" in response_dict and len(response_dict["choices"]) > 0:
        choice = response_dict["choices"][0]
        if "message" in choice and "content" in choice["message"]:
            assistant_content = choice["message"]["content"]
            clean_output, was_redacted = sanitize_output(assistant_content)
            choice["message"]["content"] = clean_output

    total_latency = (time.time() - start_time) * 1000.0

    # 8. Store in Semantic Cache
    semantic_cache.store(sanitized_prompt, response_dict)

    # 9. Record Telemetry
    usage = response_dict.get("usage", {})
    completion_tokens = usage.get("completion_tokens", len(assistant_content.split()))

    telemetry_engine.record_transaction(
        tenant_id=tenant_id,
        model_requested=request.model,
        model_executed=executed_model,
        prompt_tokens=estimated_prompt_tokens,
        completion_tokens=completion_tokens,
        total_latency_ms=total_latency,
        ttft_ms=total_latency,
        cached=False,
        fallback_occurred=fallback_occurred
    )

    return JSONResponse(content=response_dict)

