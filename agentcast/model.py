"""Normalised session model shared by every parser and the renderer."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class FileOp:
    path: str
    op: str  # read | edit | write | create | delete | search | command


@dataclass
class Step:
    i: int
    t: str                      # ISO-8601 timestamp of the step
    kind: str                   # prompt | say | think | tool | note
    text: str = ""              # prompt / say / think text
    tool: str = ""              # tool name for kind == tool
    input: dict[str, Any] = field(default_factory=dict)
    output: str = ""            # tool result text
    error: bool = False
    duration_ms: int | None = None
    files: list[FileOp] = field(default_factory=list)
    diff: str | None = None     # unified diff text if the step changed a file
    model: str = ""
    sidechain: bool = False     # produced inside a sub-agent
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class Session:
    id: str
    agent: str                  # claude-code | codex
    source: str                 # path of the log this came from
    cwd: str = ""
    title: str = ""
    started: str = ""
    ended: str = ""
    models: list[str] = field(default_factory=list)
    version: str = ""
    steps: list[Step] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float | None = None
    warnings: list[str] = field(default_factory=list)

    # ---- derived -------------------------------------------------------
    @property
    def prompts(self) -> int:
        return sum(1 for s in self.steps if s.kind == "prompt")

    @property
    def tool_calls(self) -> int:
        return sum(1 for s in self.steps if s.kind == "tool")

    def duration_s(self) -> float:
        from .util import parse_ts
        if not self.started or not self.ended:
            return 0.0
        return max(0.0, (parse_ts(self.ended) - parse_ts(self.started)).total_seconds())

    def files_touched(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for s in self.steps:
            for f in s.files:
                if f.op in ("command", "search"):
                    continue
                out.setdefault(f.path, {})
                out[f.path][f.op] = out[f.path].get(f.op, 0) + 1
        return out

    def blast_radius(self) -> list[str]:
        """Files the agent actually changed (edit/write/create/delete)."""
        return sorted(p for p, ops in self.files_touched().items()
                      if any(k in ops for k in ("edit", "write", "create", "delete")))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["prompts"] = self.prompts
        d["tool_calls"] = self.tool_calls
        d["duration_s"] = self.duration_s()
        d["files"] = self.files_touched()
        d["blast_radius"] = self.blast_radius()
        return d
