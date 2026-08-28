"""Best-effort secret redaction applied before anything is rendered.

The goal is that a replay is safe to hand to a colleague or post publicly
by default. It is pattern-based and cannot catch everything — review a
replay before sharing it outside your team."""
from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai-key",    re.compile(r"sk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}")),
    ("github-token",  re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b")),
    ("github-pat",    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("aws-key-id",    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("slack-token",   re.compile(r"\bxox[abpors]-[A-Za-z0-9\-]{10,}\b")),
    ("stripe-key",    re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("google-key",    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b")),
    ("vercel-token",  re.compile(r"\bvercel_[A-Za-z0-9]{20,}\b")),
    ("jwt",           re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("private-key",   re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("bearer",        re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9_\-\.=]{16,}")),
    ("env-secret",    re.compile(r"(?im)^(\s*(?:export\s+)?[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|PASSWD|API_KEY|APIKEY|PRIVATE_KEY)[A-Z0-9_]*\s*[=:]\s*)(['\"]?)[^\s'\"]{6,}\2")),
    ("url-basic-auth", re.compile(r"(?i)(https?://[^/\s:@]+:)[^@\s/]{3,}(@)")),
]


def redact(text: str) -> str:
    if not text:
        return text
    for name, pat in _PATTERNS:
        if name in ("bearer", "env-secret"):
            text = pat.sub(lambda m, n=name: m.group(1) + f"[REDACTED:{n}]", text)
        elif name == "url-basic-auth":
            text = pat.sub(lambda m: m.group(1) + "[REDACTED:password]" + m.group(2), text)
        else:
            text = pat.sub(f"[REDACTED:{name}]", text)
    return text


def redact_obj(obj):
    """Recursively redact every string inside a JSON-like structure."""
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, list):
        return [redact_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    return obj
