import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("Telemetry")

class TelemetryEngine:
    def __init__(self):
        self.metrics_history = []

    def record_transaction(
        self,
        tenant_id: str,
        model_requested: str,
        model_executed: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_latency_ms: float,
        ttft_ms: Optional[float] = None,
        cached: bool = False,
        fallback_occurred: bool = False,
        error: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Record and structure OpenTelemetry-style event log for analytics and billing.
        """
        metric = {
            "timestamp": time.time(),
            "tenant_id": tenant_id,
            "model_requested": model_requested,
            "model_executed": model_executed,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "total_latency_ms": round(total_latency_ms, 2),
            "ttft_ms": round(ttft_ms, 2) if ttft_ms is not None else None,
            "cached": cached,
            "fallback_occurred": fallback_occurred,
            "error": error
        }
        self.metrics_history.append(metric)
        logger.info(
            f"[TELEMETRY] Tenant='{tenant_id}' | Model='{model_executed}' | "
            f"Latency={metric['total_latency_ms']}ms | TTFT={metric['ttft_ms']}ms | "
            f"Cached={cached} | Fallback={fallback_occurred}"
        )
        return metric

    def get_summary(self) -> Dict[str, Any]:
        total_requests = len(self.metrics_history)
        if total_requests == 0:
            return {"total_requests": 0, "cache_hit_rate": 0.0, "fallback_rate": 0.0}

        cache_hits = sum(1 for m in self.metrics_history if m["cached"])
        fallbacks = sum(1 for m in self.metrics_history if m["fallback_occurred"])

        return {
            "total_requests": total_requests,
            "cache_hits": cache_hits,
            "cache_hit_rate": round(cache_hits / total_requests, 4),
            "fallbacks": fallbacks,
            "fallback_rate": round(fallbacks / total_requests, 4),
            "recent_metrics": self.metrics_history[-10:]
        }

telemetry_engine = TelemetryEngine()

