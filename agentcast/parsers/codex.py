"""Parser for OpenAI Codex CLI rollouts (~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl)."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from ..model import Session, Step, FileOp
from ..util import iter_jsonl, parse_ts, truncate
from .. import cost as _cost

MAX_OUTPUT = 20_000
_PATCH_FILE_RE = re.compile(r"^\*\*\* (Add|Update|Delete) File: (.+)$", re.M)
_IDE_CTX_RE = re.compile(r"## My request for Codex:\s*(.*)", re.S)


def _args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            v = json.loads(raw)
            return v if isinstance(v, dict) else {"value": v}
        except json.JSONDecodeError:
            return {"value": raw}
    return {}


def _patch_to_unified(patch: str) -> tuple[str, list[FileOp]]:
    """Codex apply_patch format is already diff-like; normalise headers."""
    files: list[FileOp] = []
    out: list[str] = []
    for ln in patch.splitlines():
        m = _PATCH_FILE_RE.match(ln)
        if m:
            kind, p = m.group(1), m.group(2).strip()
            op = {"Add": "create", "Update": "edit", "Delete": "delete"}[kind]
            files.append(FileOp(p, op))
            out.append(f"--- {'/dev/null' if op == 'create' else 'a/' + p}")
            out.append(f"+++ {'/dev/null' if op == 'delete' else 'b/' + p}")
            continue
        if ln.startswith("*** Begin Patch") or ln.startswith("*** End Patch"):
            continue
        if ln.startswith("@@"):
            out.append(ln if ln.strip() != "@@" else "@@ @@")
            continue
        out.append(ln)
    return "\n".join(out) + "\n", files


def parse(path: str) -> Session:
    sid = os.path.splitext(os.path.basename(path))[0]
    s = Session(id=sid, agent="codex", source=path)
    steps: list[Step] = []
    pending: dict[str, Step] = {}
    models: list[str] = []
    last_total: dict[str, int] | None = None
    first_prompt = ""

    for rec in iter_jsonl(path):
        t = rec.get("type")
        ts = rec.get("timestamp", "")
        p = rec.get("payload") or {}
        if ts:
            if not s.started:
                s.started = ts
            s.ended = ts
        if t == "session_meta":
            s.id = p.get("id") or p.get("session_id") or s.id
            s.cwd = p.get("cwd", s.cwd)
            s.version = p.get("cli_version", s.version)
            continue
        if t == "turn_context":
            m = p.get("model")
            if m and m not in models:
                models.append(m)
            continue
        if t == "event_msg":
            pt = p.get("type")
            if pt == "user_message":
                text = p.get("message", "") or ""
                m = _IDE_CTX_RE.search(text)
                if m:
                    text = m.group(1).strip()
                if text.strip():
                    if not first_prompt:
                        first_prompt = text
                    steps.append(Step(i=len(steps), t=ts, kind="prompt", text=text))
            elif pt == "agent_message" and (p.get("message") or "").strip():
                steps.append(Step(i=len(steps), t=ts, kind="say", text=p["message"]))
            elif pt == "agent_reasoning" and (p.get("text") or "").strip():
                steps.append(Step(i=len(steps), t=ts, kind="think", text=p["text"]))
            elif pt == "token_count":
                info = p.get("info") or {}
                tot = info.get("total_token_usage")
                if tot:
                    last_total = tot
            continue
        if t == "response_item":
            pt = p.get("type")
            if pt in ("function_call", "custom_tool_call"):
                name = p.get("name", "?")
                inp = _args(p.get("arguments") if pt == "function_call" else p.get("input"))
                files: list[FileOp] = []
                diff = None
                if name == "apply_patch":
                    raw = inp.get("value") if "value" in inp else inp.get("input", "")
                    if isinstance(raw, str):
                        diff, files = _patch_to_unified(raw)
                        inp = {"patch": raw}
                elif name in ("exec_command", "shell", "shell_command", "container.exec"):
                    cmd = inp.get("cmd") or inp.get("command") or ""
                    if isinstance(cmd, list):
                        cmd = " ".join(str(c) for c in cmd)
                    files.append(FileOp(str(cmd)[:200], "command"))
                st = Step(i=len(steps), t=ts, kind="tool", tool=name, input=inp, files=files, diff=diff)
                steps.append(st)
                pending[p.get("call_id", "")] = st
            elif pt in ("function_call_output", "custom_tool_call_output"):
                st = pending.pop(p.get("call_id", ""), None)
                if st is None:
                    continue
                out = p.get("output", "")
                if not isinstance(out, str):
                    out = json.dumps(out)
                st.output = truncate(out, MAX_OUTPUT)
                st.error = bool(re.search(r"^Exit code: [1-9]|Process exited with code [1-9]", out, re.M))
                if ts and st.t:
                    st.duration_ms = int((parse_ts(ts) - parse_ts(st.t)).total_seconds() * 1000)
            elif pt == "reasoning":
                summ = p.get("summary") or []
                text = "\n".join(x.get("text", "") for x in summ if isinstance(x, dict)).strip()
                if text:
                    steps.append(Step(i=len(steps), t=ts, kind="think", text=text))
            elif pt == "message" and p.get("role") == "user":
                # Only count user messages that were not already captured by event_msg
                pass
            continue

    if last_total:
        inp = int(last_total.get("input_tokens", 0) or 0)
        cached = int(last_total.get("cached_input_tokens", 0) or 0)
        s.usage = {"input": max(0, inp - cached), "output": int(last_total.get("output_tokens", 0) or 0),
                   "cache_read": cached, "cache_write": 0}
        s.cost_usd = round(_cost.estimate(s.usage, models[0] if models else "gpt-5"), 4)
    if not s.title:
        s.title = (first_prompt.strip().splitlines() or ["(untitled)"])[0][:120]
    s.steps = steps
    s.models = models
    if pending:
        s.warnings.append(f"{len(pending)} tool call(s) never received a result")
    return s
