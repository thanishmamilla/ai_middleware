import os
from pydantic_settings import BaseSettings
from typing import Dict, List

class Settings(BaseSettings):
    APP_NAME: str = "Enterprise AI Safety & Fallback Gateway"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Default fallback chains for routing
    MODEL_FALLBACK_CHAINS: Dict[str, List[str]] = {
        "gpt-4o": ["gpt-4o", "claude-3-5-sonnet-20241022", "mistral/mistral-large-latest"],
        "gpt-4o-mini": ["gpt-4o-mini", "claude-3-haiku-20240307", "groq/llama-3.1-8b-instant"],
        "claude-3-5-sonnet": ["claude-3-5-sonnet-20241022", "gpt-4o", "gemini/gemini-1.5-pro"]
    }

    # Semantic Cache Settings
    SEMANTIC_CACHE_SIMILARITY_THRESHOLD: float = 0.96
    SEMANTIC_CACHE_ENABLED: bool = True
    CACHE_MAX_ENTRIES: int = 1000

    # Rate Limiting & Multi-Tenancy (Virtual Keys)
    # Maps virtual API Key -> {"tenant_id": str, "rpm": int, "tpm": int}
    VIRTUAL_API_KEYS: Dict[str, Dict] = {
        "sk-ent-finance-prod-101": {
            "tenant_id": "finance_team",
            "rpm_limit": 60,
            "tpm_limit": 100000,
        },
        "sk-ent-support-bot-202": {
            "tenant_id": "customer_support",
            "rpm_limit": 120,
            "tpm_limit": 200000,
        },
        "sk-ent-dev-test-303": {
            "tenant_id": "rnd_engineering",
            "rpm_limit": 1000,
            "tpm_limit": 500000,
        }
    }

    # Circuit Breaker thresholds
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    CIRCUIT_BREAKER_RECOVERY_TIME_SEC: float = 20.0
    PROVIDER_TIMEOUT_SEC: float = 8.0

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()

