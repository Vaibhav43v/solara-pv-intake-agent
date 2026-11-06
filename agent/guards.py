"""Input guardrails: PII minimisation and prompt-injection detection.
Runs BEFORE any text reaches an LLM."""
import re

PII_PATTERNS = [
    ("AADHAAR", re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")),
    ("PHONE", re.compile(r"(?:\+91[\s-]?)?\b[6-9]\d{4}\s?\d{5}\b")),
]
INJECTION = re.compile(
    r"(ignore (all )?(previous|prior|above) instructions|disregard .*instructions|"
    r"mark this case as|you are now|system prompt|do not escalate)", re.I)


def mask_pii(text: str):
    found = []
    for label, pat in PII_PATTERNS:
        if pat.search(text):
            found.append(label)
            text = pat.sub(f"[{label}-MASKED]", text)
    return text, found


def detect_injection(text: str) -> bool:
    return bool(INJECTION.search(text))
