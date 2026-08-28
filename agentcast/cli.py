from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import webbrowser

from . import __version__
from .discover import find_sessions, resolve
from .parsers import parse_any
from .render import render_html, session_payload, active_seconds
from .util import human_duration, human_int, shorten_home


def _p(*a):
    print(*a, file=sys.stdout)


def cmd_list(a):
    found = find_sessions()[: a.limit]
    if not found:
        _p("No sessions found. Looked in ~/.claude/projects and ~/.codex/sessions "
           "(set AGENTCAST_ROOTS to add more).")
        return 1
    _p(f"{'agent':<12}{'started':<17}{'active':>8}  {'prompts':>7} {'tools':>6} {'changed':>7} {'tokens':>7} {'cost':>7}  id            title")
    for f in found:
        try:
            s = parse_any(f.path)
        except Exception as e:  # noqa: BLE001
            _p(f"{f.agent:<12}(unreadable: {e})")
            continue
        cost = f"${s.cost_usd:.2f}" if s.cost_usd is not None else "—"
        _p(f"{s.agent:<12}{s.started[:16].replace('T',' '):<17}{human_duration(active_seconds(s)):>8}  "
           f"{s.prompts:>7} {s.tool_calls:>6} {len(s.blast_radius()):>7} {human_int(sum(s.usage.values())):>7} {cost:>7}  "
           f"{os.path.basename(f.path)[:12]:<12}  {s.title[:60]}")
    return 0


def _load(ref: str):
    path = resolve(ref)
    return parse_any(path)


def cmd_render(a):
    s = _load(a.session)
    html = render_html(s, do_redact=not a.no_redact, anon_paths=not a.keep_paths)
    out = a.output or f"agentcast-{s.id[:8]}.html"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    _p(f"wrote {out}  ({len(html)/1024:.0f} KB · {s.tool_calls} tool calls · {len(s.blast_radius())} files changed)")
    if a.open:
        webbrowser.open("file://" + os.path.abspath(out))
    return 0


def cmd_open(a):
    s = _load(a.session)
    html = render_html(s, do_redact=not a.no_redact, anon_paths=not a.keep_paths)
    fd, out = tempfile.mkstemp(prefix="agentcast-", suffix=".html")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(html)
    webbrowser.open("file://" + out)
    _p(f"opened {out}")
    return 0


def cmd_json(a):
    s = _load(a.session)
    d = session_payload(s, do_redact=not a.no_redact, anon_paths=not a.keep_paths)
    json.dump(d, sys.stdout, indent=None if a.compact else 2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def cmd_ui(a):
    from .serve import serve
    serve(port=a.port, open_browser=not a.no_open, redact=not a.no_redact, anon=not a.keep_paths, limit=a.limit)
    return 0


def cmd_stats(a):
    from .stats import aggregate
    r = aggregate(limit=a.limit)
    if a.json:
        json.dump(r, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    u = r["usage"]
    _p(f"agentcast stats — {r['sessions']} sessions  ({', '.join(f'{k}: {v}' for k, v in r['agents'].items())})")
    _p(f"  active time      {human_duration(r['active_s'])}  across {r['days_active']} days")
    _p(f"  prompts          {r['prompts']:,}")
    _p(f"  tool calls       {r['tool_calls']:,}  ({r['tool_errors']:,} errors)")
    _p(f"  files changed    {r['files_changed']:,}")
    _p(f"  tokens           {human_int(sum(u.values()))}  (in {human_int(u['input'])} · out {human_int(u['output'])} · cache read {human_int(u['cache_read'])} · cache write {human_int(u['cache_write'])})")
    _p(f"  est. API cost    ${r['cost_usd']:,.2f}  (list price; subscriptions bill differently)")
    if r["busiest_day"]:
        _p(f"  busiest day      {r['busiest_day'][0]}  ({r['busiest_day'][1]:,} steps)")
    if r["longest"]["id"]:
        _p(f"  longest session  {human_duration(r['longest']['active_s'])}  {r['longest']['title'][:60]}")
    _p("  models           " + ", ".join(f"{m} ×{n}" for m, n in r["models"][:6]))
    _p("  top tools        " + ", ".join(f"{t} ×{n}" for t, n in r["top_tools"][:8]))
    _p("  most-changed     " + ", ".join(f"{shorten_home(p)} ×{n}" for p, n in r["top_files"][:5]))
    hist = r["hour_histogram"]
    mx = max(hist) or 1
    bars = "▁▂▃▄▅▆▇█"
    _p("  by hour (0-23)   " + "".join(bars[min(7, int(h * 7 / mx))] for h in hist))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agentcast", description="asciinema for AI coding agents — replay any Claude Code / Codex session as a shareable HTML file.")
    ap.add_argument("--version", action="version", version=f"agentcast {__version__}")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--no-redact", action="store_true", help="do not scrub API keys / tokens (default: scrub)")
        p.add_argument("--keep-paths", action="store_true", help="keep your real home directory in paths (default: replace with ~)")

    p = sub.add_parser("list", help="list sessions found on this machine"); p.add_argument("-n", "--limit", type=int, default=40); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("render", help="write a self-contained HTML replay"); p.add_argument("session", help="path, session id, or id prefix"); p.add_argument("-o", "--output"); p.add_argument("--open", action="store_true"); common(p); p.set_defaults(fn=cmd_render)
    p = sub.add_parser("open", help="render to a temp file and open it in your browser"); p.add_argument("session"); common(p); p.set_defaults(fn=cmd_open)
    p = sub.add_parser("json", help="dump the normalised session as JSON"); p.add_argument("session"); p.add_argument("--compact", action="store_true"); common(p); p.set_defaults(fn=cmd_json)
    p = sub.add_parser("ui", help="browse every session in a local web UI"); p.add_argument("-p", "--port", type=int, default=8787); p.add_argument("--no-open", action="store_true"); p.add_argument("-n", "--limit", type=int); common(p); p.set_defaults(fn=cmd_ui)
    p = sub.add_parser("stats", help="totals across all sessions: hours, tokens, cost, tools, files"); p.add_argument("-n", "--limit", type=int); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_stats)

    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 0
    try:
        return a.fn(a)
    except (FileNotFoundError, ValueError) as e:
        _p(f"agentcast: {e}")
        return 2
