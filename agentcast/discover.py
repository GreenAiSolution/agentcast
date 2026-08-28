"""Find agent session logs on this machine."""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass

from .parsers import detect


@dataclass
class Found:
    path: str
    agent: str
    mtime: float
    size: int


def default_roots() -> list[str]:
    home = os.path.expanduser("~")
    roots = [os.path.join(home, ".claude", "projects"), os.path.join(home, ".codex", "sessions")]
    extra = os.environ.get("AGENTCAST_ROOTS")
    if extra:
        roots += [os.path.expanduser(r) for r in extra.split(os.pathsep) if r]
    return roots


def find_sessions(roots: list[str] | None = None, min_bytes: int = 2_000) -> list[Found]:
    roots = roots or default_roots()
    out: list[Found] = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for p in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
            try:
                st = os.stat(p)
            except OSError:
                continue
            if st.st_size < min_bytes:
                continue
            # Claude Code stores sub-agent transcripts one level deeper; skip them
            base = os.path.basename(p)
            if "/.claude/" in p.replace("\\", "/") and (base.startswith("agent-") or os.path.basename(os.path.dirname(p)).startswith("agent-")):
                continue
            agent = detect(p)
            if agent:
                out.append(Found(p, agent, st.st_mtime, st.st_size))
    out.sort(key=lambda f: f.mtime, reverse=True)
    return out


def resolve(ref: str, roots: list[str] | None = None) -> str:
    """Turn a path, a session id, or an id prefix into a log path."""
    if os.path.isfile(ref):
        return os.path.abspath(ref)
    matches = [f.path for f in find_sessions(roots, min_bytes=0)
               if os.path.basename(f.path).startswith(ref) or ref in os.path.basename(f.path)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise FileNotFoundError(f"no session matches {ref!r}")
    raise ValueError(f"{ref!r} is ambiguous ({len(matches)} matches) — give more characters")
