from __future__ import annotations

import difflib

MAX_DIFF_CHARS = 60_000


def unified(path: str, old: str, new: str) -> str:
    path = path.lstrip("/")
    a = old.splitlines(keepends=True)
    b = new.splitlines(keepends=True)
    if a and not a[-1].endswith("\n"):
        a[-1] += "\n"
    if b and not b[-1].endswith("\n"):
        b[-1] += "\n"
    out = "".join(difflib.unified_diff(a, b, fromfile=f"a/{path}", tofile=f"b/{path}", n=3))
    if len(out) > MAX_DIFF_CHARS:
        out = out[:MAX_DIFF_CHARS] + "\n… [diff truncated by agentcast]\n"
    return out


def whole_file(path: str, content: str) -> str:
    """A diff for a file written whole (no previous content known)."""
    path = path.lstrip("/")
    lines = content.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    body = "".join("+" + ln for ln in lines)
    out = f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n{body}"
    if len(out) > MAX_DIFF_CHARS:
        out = out[:MAX_DIFF_CHARS] + "\n… [diff truncated by agentcast]\n"
    return out


def diff_stats(diff: str) -> tuple[int, int]:
    add = rem = 0
    for ln in diff.splitlines():
        if ln.startswith("+++") or ln.startswith("---"):
            continue
        if ln.startswith("+"):
            add += 1
        elif ln.startswith("-"):
            rem += 1
    return add, rem
