from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Iterator, Any


def parse_ts(s: str) -> _dt.datetime:
    """Parse an ISO-8601 timestamp (with or without Z / fractional seconds)."""
    if not s:
        return _dt.datetime.fromtimestamp(0, _dt.timezone.utc)
    s = s.replace("Z", "+00:00")
    try:
        d = _dt.datetime.fromisoformat(s)
    except ValueError:
        # e.g. 2026-08-15T02:38:12.792123456+00:00 (too many fraction digits)
        head, _, tail = s.partition(".")
        frac = "".join(ch for ch in tail if ch.isdigit())[:6]
        tz = tail[len("".join(ch for ch in tail if ch.isdigit())):]
        d = _dt.datetime.fromisoformat(f"{head}.{frac or '0'}{tz}")
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d


def iter_jsonl(path: str) -> Iterator[dict[str, Any]]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(d, dict):
                yield d


def shorten_home(p: str) -> str:
    home = os.path.expanduser("~")
    if p and home and p.startswith(home):
        return "~" + p[len(home):]
    return p


def human_duration(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


def human_int(n: int | float) -> str:
    n = int(n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n/1000:.0f}k"
    if n >= 1000:
        return f"{n/1000:.1f}k"
    return str(n)


def truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n… [{len(s) - limit:,} more characters truncated by agentcast]"
