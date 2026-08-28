"""Aggregate statistics across every session on the machine."""
from __future__ import annotations

import collections
import datetime as _dt
from typing import Any

from .discover import find_sessions, Found
from .parsers import parse_any
from .render import active_seconds
from .util import parse_ts


def aggregate(found: list[Found] | None = None, limit: int | None = None) -> dict[str, Any]:
    found = found if found is not None else find_sessions()
    if limit:
        found = found[:limit]
    tools: collections.Counter[str] = collections.Counter()
    files: collections.Counter[str] = collections.Counter()
    models: collections.Counter[str] = collections.Counter()
    agents: collections.Counter[str] = collections.Counter()
    days: collections.Counter[str] = collections.Counter()
    hours: collections.Counter[int] = collections.Counter()
    usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    cost = 0.0
    active = 0.0
    prompts = calls = errors = changed = 0
    longest: tuple[float, str, str] = (0.0, "", "")
    for f in found:
        try:
            s = parse_any(f.path)
        except Exception:
            continue
        agents[s.agent] += 1
        for m in s.models:
            models[m] += 1
        a = active_seconds(s)
        active += a
        if a > longest[0]:
            longest = (a, s.title, s.id)
        prompts += s.prompts
        calls += s.tool_calls
        for st in s.steps:
            if st.kind == "tool":
                tools[st.tool] += 1
                if st.error:
                    errors += 1
            if st.t:
                d = parse_ts(st.t).astimezone()
                days[d.strftime("%Y-%m-%d")] += 1
                hours[d.hour] += 1
        for p in s.blast_radius():
            files[p] += 1
        changed += len(s.blast_radius())
        for k in usage:
            usage[k] += s.usage.get(k, 0)
        cost += s.cost_usd or 0.0
    return {
        "sessions": len(found), "agents": dict(agents), "models": models.most_common(),
        "active_s": active, "prompts": prompts, "tool_calls": calls, "tool_errors": errors,
        "files_changed": changed, "top_tools": tools.most_common(15), "top_files": files.most_common(15),
        "usage": usage, "cost_usd": round(cost, 2), "days_active": len(days),
        "busiest_day": days.most_common(1)[0] if days else None,
        "hour_histogram": [hours.get(h, 0) for h in range(24)],
        "longest": {"active_s": longest[0], "title": longest[1], "id": longest[2]},
    }
