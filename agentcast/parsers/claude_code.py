"""Parser for Claude Code session logs (~/.claude/projects/<proj>/<id>.jsonl)."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from ..model import Session, Step, FileOp
from ..util import iter_jsonl, parse_ts, truncate
from .. import diff as _diff
from .. import cost as _cost

MAX_OUTPUT = 20_000
_CMD_RE = re.compile(r"<command-name>(.*?)</command-name>", re.S)
_LOCAL_OUT_RE = re.compile(r"<local-command-stdout>(.*?)</local-command-stdout>", re.S)

READ_TOOLS = {"Read", "NotebookRead"}
SEARCH_TOOLS = {"Glob", "Grep", "LS"}


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    parts.append(b.get("text", ""))
                elif b.get("type") == "image":
                    parts.append("[image]")
            elif isinstance(b, str):
                parts.append(b)
        return "\n".join(parts)
    return str(content) if content is not None else ""


def _files_for(tool: str, inp: dict[str, Any]) -> tuple[list[FileOp], str | None]:
    files: list[FileOp] = []
    diff = None
    fp = inp.get("file_path") or inp.get("notebook_path") or inp.get("path")
    if tool in READ_TOOLS and fp:
        files.append(FileOp(fp, "read"))
    elif tool == "Edit" and fp:
        files.append(FileOp(fp, "edit"))
        old, new = inp.get("old_string", ""), inp.get("new_string", "")
        if isinstance(old, str) and isinstance(new, str):
            diff = _diff.unified(fp, old, new)
    elif tool == "MultiEdit" and fp:
        files.append(FileOp(fp, "edit"))
        chunks = []
        for e in inp.get("edits", []) or []:
            if isinstance(e, dict):
                chunks.append(_diff.unified(fp, e.get("old_string", ""), e.get("new_string", "")))
        diff = "\n".join(chunks) if chunks else None
    elif tool == "Write" and fp:
        files.append(FileOp(fp, "write"))
        c = inp.get("content", "")
        if isinstance(c, str):
            diff = _diff.whole_file(fp, c)
    elif tool == "NotebookEdit" and fp:
        files.append(FileOp(fp, "edit"))
    elif tool in SEARCH_TOOLS:
        files.append(FileOp(inp.get("pattern") or inp.get("path") or "", "search"))
    elif tool == "Bash":
        files.append(FileOp(inp.get("command", "")[:200], "command"))
    return files, diff


def parse(path: str) -> Session:
    sid = os.path.splitext(os.path.basename(path))[0]
    s = Session(id=sid, agent="claude-code", source=path)
    steps: list[Step] = []
    pending: dict[str, Step] = {}          # tool_use_id -> step
    seen_msg_usage: set[str] = set()
    usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    cost = 0.0
    models: list[str] = []
    first_prompt = ""

    for rec in iter_jsonl(path):
        t = rec.get("type")
        ts = rec.get("timestamp", "")
        if t == "ai-title" and rec.get("aiTitle"):
            s.title = rec["aiTitle"]
            continue
        if t in ("user", "assistant"):
            if not s.started and ts:
                s.started = ts
            if ts:
                s.ended = ts
            if not s.cwd and rec.get("cwd"):
                s.cwd = rec["cwd"]
            if not s.version and rec.get("version"):
                s.version = rec["version"]
        side = bool(rec.get("isSidechain"))
        msg = rec.get("message") or {}

        if t == "user":
            content = msg.get("content")
            if isinstance(content, list) and content and isinstance(content[0], dict) \
                    and content[0].get("type") == "tool_result":
                for b in content:
                    if not isinstance(b, dict) or b.get("type") != "tool_result":
                        continue
                    st = pending.pop(b.get("tool_use_id", ""), None)
                    if st is None:
                        continue
                    out = _text_of(b.get("content"))
                    st.output = truncate(out, MAX_OUTPUT)
                    st.error = bool(b.get("is_error"))
                    if ts and st.t:
                        st.duration_ms = int((parse_ts(ts) - parse_ts(st.t)).total_seconds() * 1000)
                continue
            if rec.get("isMeta"):
                continue
            text = _text_of(content)
            if not text.strip():
                continue
            m = _CMD_RE.search(text)
            if m:
                out = _LOCAL_OUT_RE.search(text)
                steps.append(Step(i=len(steps), t=ts, kind="note", sidechain=side,
                                  text=f"/{m.group(1).strip().lstrip('/')}"
                                       + (f"\n{out.group(1).strip()}" if out and out.group(1).strip() else "")))
                continue
            if text.startswith("<") and "system-reminder" in text[:40]:
                continue
            if not first_prompt:
                first_prompt = text
            steps.append(Step(i=len(steps), t=ts, kind="prompt", text=text, sidechain=side))
            continue

        if t == "assistant":
            model = msg.get("model", "")
            if model.startswith("<"):
                model = ""
            if model and model not in models:
                models.append(model)
            mid = msg.get("id", "")
            u = msg.get("usage") or {}
            if u and mid and mid not in seen_msg_usage:
                seen_msg_usage.add(mid)
                part = {
                    "input": int(u.get("input_tokens", 0) or 0),
                    "output": int(u.get("output_tokens", 0) or 0),
                    "cache_read": int(u.get("cache_read_input_tokens", 0) or 0),
                    "cache_write": int(u.get("cache_creation_input_tokens", 0) or 0),
                }
                for k in usage:
                    usage[k] += part[k]
                cost += _cost.estimate(part, model)
            for b in msg.get("content") or []:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if bt == "text" and b.get("text", "").strip():
                    steps.append(Step(i=len(steps), t=ts, kind="say", text=b["text"], model=model, sidechain=side))
                elif bt == "thinking" and (b.get("thinking") or "").strip():
                    steps.append(Step(i=len(steps), t=ts, kind="think", text=b["thinking"], model=model, sidechain=side))
                elif bt == "tool_use":
                    inp = b.get("input") if isinstance(b.get("input"), dict) else {"value": b.get("input")}
                    files, d = _files_for(b.get("name", ""), inp)
                    st = Step(i=len(steps), t=ts, kind="tool", tool=b.get("name", "?"),
                              input=inp, files=files, diff=d, model=model, sidechain=side)
                    steps.append(st)
                    pending[b.get("id", "")] = st
            continue

    if not s.title:
        s.title = (first_prompt.strip().splitlines() or ["(untitled)"])[0][:120]
    s.steps = steps
    s.models = models
    s.usage = usage
    s.cost_usd = round(cost, 4)
    if pending:
        s.warnings.append(f"{len(pending)} tool call(s) never received a result (session may have been interrupted)")
    return s
