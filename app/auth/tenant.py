import time
from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
from app.core.config import settings
from typing import Dict, Tuple

api_key_header = APIKeyHeader(name="Authorization", auto_error=False)

class TenantRateLimiter:
    """
    In-memory Token Bucket / Sliding-window Rate Limiter for RPM and TPM.
    Can be replaced with Redis token bucket for multi-node deployments.
    """
    def __init__(self):
        # tenant_id -> [(timestamp, tokens)]
        self.request_records: Dict[str, list] = {}

    def check_and_record(self, tenant_id: str, rpm_limit: int, estimated_tokens: int, tpm_limit: int):
        now = time.time()
        one_minute_ago = now - 60.0

        if tenant_id not in self.request_records:
            self.request_records[tenant_id] = []

        # Evict records older than 1 minute
        self.request_records[tenant_id] = [
            (ts, tok) for ts, tok in self.request_records[tenant_id] if ts > one_minute_ago
        ]

        current_requests = len(self.request_records[tenant_id])
        current_tokens = sum(tok for _, tok in self.request_records[tenant_id])

        if current_requests >= rpm_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {current_requests}/{rpm_limit} Requests Per Minute for tenant '{tenant_id}'."
            )

        if current_tokens + estimated_tokens > tpm_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Token quota exceeded: {current_tokens + estimated_tokens}/{tpm_limit} Tokens Per Minute for tenant '{tenant_id}'."
            )

        # Record this request
        self.request_records[tenant_id].append((now, estimated_tokens))

rate_limiter = TenantRateLimiter()

async def authenticate_tenant(api_key: str = Security(api_key_header)) -> Dict:
    """
    Authenticates virtual API key against configured tenant keys.
    Accepts raw key or 'Bearer <key>'.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header."
        )

    clean_key = api_key.replace("Bearer ", "").strip()

    tenant_meta = settings.VIRTUAL_API_KEYS.get(clean_key)
    if not tenant_meta:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Virtual API Key. Access denied by Gateway."
        )

    return tenant_meta

