import re
import logging
from typing import Tuple

logger = logging.getLogger("OutputGuardrail")

# Output secret leak patterns
DB_CONN_REGEX = re.compile(r'postgres(ql)?://[a-zA-Z0-9_]+:[a-zA-Z0-9_]+@[a-zA-Z0-9_.-]+', re.IGNORECASE)
BEARER_TOKEN_REGEX = re.compile(r'Bearer\s+[a-zA-Z0-9-._~+/]+=*', re.IGNORECASE)
PRIVATE_KEY_REGEX = re.compile(r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----', re.IGNORECASE)

def sanitize_output(content: str) -> Tuple[str, bool]:
    """
    Scans generated LLM output to prevent leakage of credentials or sensitive internals.
    """
    redacted = False

    if DB_CONN_REGEX.search(content):
        content = DB_CONN_REGEX.sub("[REDACTED_DATABASE_URL]", content)
        redacted = True

    if BEARER_TOKEN_REGEX.search(content):
        content = BEARER_TOKEN_REGEX.sub("[REDACTED_AUTH_TOKEN]", content)
        redacted = True

    if PRIVATE_KEY_REGEX.search(content):
        content = PRIVATE_KEY_REGEX.sub("[REDACTED_PRIVATE_KEY]", content)
        redacted = True

    if redacted:
        logger.warning("Output Guardrail: Sensitive secrets intercepted and redacted from model response.")

    return content, redacted

