from __future__ import annotations

import os
from typing import Callable

from ..model import Session
from . import claude_code, codex

PARSERS: dict[str, Callable[[str], Session]] = {
    "claude-code": claude_code.parse,
    "codex": codex.parse,
}


def detect(path: str) -> str | None:
    """Return the agent name for a log file, sniffing its first lines."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(4000)
    except OSError:
        return None
    if '"type":"session_meta"' in head.replace(" ", "") or '"originator"' in head:
        return "codex"
    if '"sessionId"' in head or '"parentUuid"' in head:
        return "claude-code"
    p = path.replace("\\", "/")
    if "/.codex/" in p:
        return "codex"
    if "/.claude/" in p:
        return "claude-code"
    return None


def parse_any(path: str) -> Session:
    agent = detect(path)
    if agent is None:
        raise ValueError(f"not a recognised agent log: {path}")
    return PARSERS[agent](os.path.abspath(path))
