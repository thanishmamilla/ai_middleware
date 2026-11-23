import re
import asyncio
import logging
from typing import Tuple, Optional
from fastapi import HTTPException, status

logger = logging.getLogger("InputGuardrail")

# PII Patterns
SSN_REGEX = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
CREDIT_CARD_REGEX = re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b')
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
SECRET_KEY_REGEX = re.compile(r'(?:sk-[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16})')

# Jailbreak / Injection Patterns
JAILBREAK_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"system\s+prompt\s+override", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(DAN|unrestricted|jailbroken)", re.IGNORECASE),
    re.compile(r"drop\s+table\s+\w+", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(secret\s+)?(instructions|system\s+prompt)", re.IGNORECASE)
]

def scan_and_mask_pii(text: str) -> Tuple[str, bool]:
    """
    Fast synchronous PII detection and redaction (<5ms overhead).
    Redacts SSNs, credit cards, emails, and sensitive keys.
    """
    modified = False
    
    if SSN_REGEX.search(text):
        text = SSN_REGEX.sub("[REDACTED_SSN]", text)
        modified = True
    if CREDIT_CARD_REGEX.search(text):
        text = CREDIT_CARD_REGEX.sub("[REDACTED_CARD]", text)
        modified = True
    if SECRET_KEY_REGEX.search(text):
        text = SECRET_KEY_REGEX.sub("[REDACTED_SECRET_KEY]", text)
        modified = True
    if EMAIL_REGEX.search(text):
        text = EMAIL_REGEX.sub("[REDACTED_EMAIL]", text)
        modified = True

    return text, modified

def validate_input_integrity(text: str) -> None:
    """
    Validates against hard security threats (jailbreaks, prompt injections).
    Throws 400 Bad Request if detected.
    """
    for pattern in JAILBREAK_PATTERNS:
        match = pattern.search(text)
        if match:
            logger.warning(f"Input Guardrail Blocked Injection: {match.group(0)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Security Violation: Prompt injection / jailbreak detected: '{match.group(0)}'."
            )

async def evaluate_heavy_safety(prompt: str) -> Tuple[bool, Optional[str]]:
    """
    Heavy safety classifier (e.g. Llama Guard 3 / Moderation API).
    Designed to run asynchronously in parallel with streaming.
    Simulates ~100-200ms latency.
    """
    await asyncio.sleep(0.15)
    
    harmful_topics = [
        "synthesize chemical weapon",
        "ransomware script",
        "steal identity guide"
    ]
    
    for topic in harmful_topics:
        if topic in prompt.lower():
            return False, f"Flagged by Llama Guard: Category '{topic}' violation."

    return True, None

