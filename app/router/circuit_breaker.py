import time
import logging
from enum import Enum
from typing import Dict
from app.core.config import settings

logger = logging.getLogger("CircuitBreaker")

class CircuitState(Enum):
    CLOSED = "CLOSED"         # Normal operation: forwarding calls
    OPEN = "OPEN"             # Provider tripped: fail fast, skip calling
    HALF_OPEN = "HALF_OPEN"   # Testing provider recovery with sample call

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_time_sec: float = settings.CIRCUIT_BREAKER_RECOVERY_TIME_SEC
    ):
        self.failure_threshold = failure_threshold
        self.recovery_time_sec = recovery_time_sec
        # provider_name -> {state, failure_count, last_failure_time, total_requests, total_failures}
        self.registry: Dict[str, Dict] = {}

    def _get_entry(self, provider: str) -> Dict:
        if provider not in self.registry:
            self.registry[provider] = {
                "state": CircuitState.CLOSED,
                "failure_count": 0,
                "last_failure_time": 0.0,
                "total_requests": 0,
                "total_failures": 0
            }
        return self.registry[provider]

    def can_execute(self, provider: str) -> bool:
        entry = self._get_entry(provider)
        now = time.time()

        if entry["state"] == CircuitState.CLOSED:
            return True

        if entry["state"] == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if now - entry["last_failure_time"] >= self.recovery_time_sec:
                logger.info(f"Circuit Breaker for '{provider}' switching from OPEN to HALF_OPEN (probing).")
                entry["state"] = CircuitState.HALF_OPEN
                return True
            return False

        # HALF_OPEN allows probe
        return True

    def record_success(self, provider: str):
        entry = self._get_entry(provider)
        entry["total_requests"] += 1
        if entry["state"] == CircuitState.HALF_OPEN:
            logger.info(f"Circuit Breaker for '{provider}' recovered! Switching back to CLOSED.")
        entry["state"] = CircuitState.CLOSED
        entry["failure_count"] = 0

    def record_failure(self, provider: str):
        entry = self._get_entry(provider)
        entry["total_requests"] += 1
        entry["total_failures"] += 1
        entry["failure_count"] += 1
        entry["last_failure_time"] = time.time()

        if entry["failure_count"] >= self.failure_threshold:
            entry["state"] = CircuitState.OPEN
            logger.warning(
                f"Circuit Breaker for '{provider}' TRIPPED to OPEN! "
                f"({entry['failure_count']} consecutive failures. Cooldown: {self.recovery_time_sec}s)"
            )

    def get_status(self) -> Dict[str, Dict]:
        return {
            prov: {
                "state": data["state"].value,
                "failure_count": data["failure_count"],
                "total_requests": data["total_requests"],
                "total_failures": data["total_failures"]
            }
            for prov, data in self.registry.items()
        }

circuit_breaker = CircuitBreaker()

