# Enterprise AI Safety, Moderation, & Fallback Gateway

An enterprise-grade reverse proxy sitting between microservices and external LLM providers (OpenAI, Anthropic, Mistral, vLLM). It decouples provider management, security, and resiliency from core application code.

## 🏛️ System Architecture

```
                  ┌─────────────────────────────────────────────────────────────┐
                  │                 ENTERPRISE AI GATEWAY                       │
                  │                                                             │
                  │   ┌──────────────────┐           ┌──────────────────────┐   │
                  │   │   Ingress API    ├──────────►│   Semantic Cache     │   │
                  │   └────────┬─────────┘           │  (Vector Cosine Sim) │   │
                  │            │                     └──────────┬───────────┘   │
                  │            ▼                                │ Cache Hit     │
                  │   ┌──────────────────┐                      ▼               │
                  │   │ Input Guardrail  ├──────────► Return Cached Answer      │
                  │   │ (PII & Injection)│                                      │
                  │   └────────┬─────────┘                                      │
                  │            │ Clean Input                                    │
                  │            ▼                                                │
                  │   ┌──────────────────┐           ┌──────────────────────┐   │
                  │   │ Dynamic Router & ├──────────►│ Circuit Breaker &    │   │
                  │   │ Cost Rate-Limiter│           │ Fallback Controller  │   │
                  │   └────────┬─────────┘           └──────────┬───────────┘   │
                  │            │                                │ Forward       │
                  └────────────┼────────────────────────────────┼───────────────┘
                               │                                │
                               ▼                                ▼
                    ┌─────────────────────┐          ┌────────────────────┐
                    │ Primary Provider    │          │ Backup Provider    │
                    │ (e.g., GPT-4o)      │          │ (e.g., Claude 3.5) │
                    └──────────┬──────────┘          └──────────┬─────────┘
                               │                                │
                               └────────────────┬───────────────┘
                                                │ Raw Output
                                                ▼
                  ┌─────────────────────────────────────────────────────────────┐
                  │   ┌──────────────────┐           ┌──────────────────────┐   │
                  │   │ Output Guardrail ├──────────►│ Telemetry & Logging  │   │
                  │   │ (PII Mask/Secrets│           │ (Latency, TTFT, Cost)│   │
                  │   └────────┬─────────┘           └──────────────────────┘   │
                  └────────────┼────────────────────────────────────────────────┘
                               │ Sanitized Response
                               ▼
                       Client Application
```

---

## 🔑 Key Features Implemented

1. **Virtual API Keys & Multi-Tenant Quotas**
   - Centralized authentication header (`Authorization: Bearer <virtual-key>`).
   - Token bucket sliding window for **Requests Per Minute (RPM)** and **Tokens Per Minute (TPM)** per tenant.

2. **Synchronous PII Scrubbing + Prompt Injection Defense**
   - High-speed regex/pattern parsing ($<5\text{ms}$) for SSN, credit cards, emails, and database/token leaks.
   - Immediate rejection (`HTTP 400`) of adversarial prompt injections (e.g., `"ignore previous instructions"`).

3. **High-Performance Semantic Vector Cache**
   - Computes cosine similarity between incoming queries and cached embeddings.
   - If similarity $\ge 0.96$, serves response instantly with near-zero latency and zero model cost.

4. **Speculative Parallel Guardrail Streaming (Solves the Latency Trap)**
   - When streaming is enabled, immediately initiates token streaming to minimize **Time-to-First-Token (TTFT)**.
   - Asynchronously runs the heavy safety classifier in parallel.
   - If a safety violation is detected mid-stream, aborts the SSE stream immediately and emits a safety refusal event.

5. **Dynamic Fallback Router & Circuit Breaker**
   - Automatic cascade across backup providers: `gpt-4o` $\rightarrow$ `claude-3-5-sonnet` $\rightarrow$ `mistral-large`.
   - Circuit Breaker tracks provider errors with states: `CLOSED`, `OPEN`, and `HALF_OPEN` to avoid hammering broken APIs.

6. **Output Guardrail & OpenTelemetry Metrics**
   - Sanitizes generated LLM responses to prevent leakage of credentials or sensitive internals.
   - Real-time telemetry tracking TTFT, total latency, token count, cache hit rate, and fallback rates.

---

## 🚀 Quickstart & Testing

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Start the Gateway
```bash
python run_server.py
```
Server runs at `http://127.0.0.1:8000`. API docs available at `http://127.0.0.1:8000/docs`.

### 3. Run the Verification Test Suite
```bash
python test_gateway.py
```

---

## 📡 API Endpoints

- `POST /v1/chat/completions` - OpenAI-compatible chat completion endpoint (supports `stream=True`).
- `GET /health` - Service health status.
- `GET /admin/metrics` - Aggregated telemetry (cache hit rate, fallbacks, token counts, latency).
- `GET /admin/circuit-breaker` - Real-time provider circuit breaker states.
- `DELETE /admin/cache` - Purges the semantic cache.

