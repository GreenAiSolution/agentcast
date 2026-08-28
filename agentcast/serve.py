"""`agentcast ui` — a local browser for every session on this machine.
Binds to 127.0.0.1 only. Nothing is uploaded anywhere."""
from __future__ import annotations

import html
import json
import os
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .discover import find_sessions
from .parsers import parse_any
from .render import render_html, active_seconds
from .util import human_duration, human_int, shorten_home
from . import __version__

INDEX_CSS = """
:root{--bg:#0b0d10;--bg2:#12151a;--bg3:#1a1e25;--line:#262b34;--fg:#e6e8eb;--dim:#8b93a1;--mute:#5c6470;--acc:#5ee3a1;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
@media (prefers-color-scheme: light){:root{--bg:#f7f8fa;--bg2:#fff;--bg3:#eef1f5;--line:#dde2ea;--fg:#14171c;--dim:#5b6472;--mute:#8a93a2;--acc:#118a55}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,BlinkMacSystemFont,Inter,Segoe UI,Roboto,sans-serif}
header{padding:18px 24px;border-bottom:1px solid var(--line);background:var(--bg2);display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}
h1{margin:0;font-size:18px}h1 span{color:var(--acc)}.sub{color:var(--dim);font-size:13px}
input{margin-left:auto;background:var(--bg);border:1px solid var(--line);color:var(--fg);border-radius:6px;padding:7px 10px;font:13px inherit;min-width:260px}
table{width:100%;border-collapse:collapse}td,th{padding:9px 24px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font:600 11px var(--mono);color:var(--mute);text-transform:uppercase;letter-spacing:.06em}
tr:hover td{background:var(--bg3)}a{color:inherit;text-decoration:none}a:hover{text-decoration:underline}
.b{font:600 11px var(--mono);padding:3px 6px;border-radius:5px;border:1px solid var(--line);color:var(--dim)}.b.claude-code{color:var(--acc);border-color:var(--acc)}.b.codex{color:#7cc4ff;border-color:#7cc4ff}
.m{font:12px var(--mono);color:var(--mute)}.t{font-weight:600}
"""


def _index(found, q: str = "") -> str:
    rows = []
    for f in found:
        try:
            s = parse_any(f.path)
        except Exception as e:  # noqa: BLE001
            continue
        if q and q.lower() not in (s.title + " " + s.cwd + " " + s.id).lower():
            continue
        sid = os.path.basename(f.path)
        rows.append(
            f"<tr><td><span class='b {s.agent}'>{s.agent}</span></td>"
            f"<td><a class='t' href='/s/{urllib.parse.quote(f.path)}'>{html.escape(s.title or '(untitled)')}</a>"
            f"<div class='m'>{html.escape(shorten_home(s.cwd))} · {html.escape(sid[:12])}</div></td>"
            f"<td class='m'>{html.escape(s.started[:16].replace('T', ' '))}</td>"
            f"<td class='m'>{human_duration(active_seconds(s))}</td>"
            f"<td class='m'>{s.prompts} / {s.tool_calls}</td>"
            f"<td class='m'>{len(s.blast_radius())}</td>"
            f"<td class='m'>{human_int(sum(s.usage.values()))}</td>"
            f"<td class='m'>{'$%.2f' % s.cost_usd if s.cost_usd is not None else '—'}</td></tr>"
        )
    return (f"<!doctype html><meta charset=utf-8><title>agentcast</title><style>{INDEX_CSS}</style>"
            f"<header><h1><span>agentcast</span> · {len(rows)} sessions</h1><span class='sub'>local only · 127.0.0.1 · v{__version__}</span>"
            f"<form><input name=q placeholder='filter by title / folder' value='{html.escape(q)}' autofocus></form></header>"
            f"<table><tr><th>agent</th><th>session</th><th>started</th><th>active</th><th>prompts / tools</th><th>files changed</th><th>tokens</th><th>est. cost</th></tr>"
            + "".join(rows) + "</table>")


class Handler(BaseHTTPRequestHandler):
    found = []
    opts = {"redact": True, "anon": True}

    def log_message(self, *a):  # quiet
        pass

    def _send(self, body: str, code: int = 200):
        b = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/":
            q = urllib.parse.parse_qs(u.query).get("q", [""])[0]
            return self._send(_index(self.found, q))
        if u.path.startswith("/s/"):
            p = urllib.parse.unquote(u.path[3:])
            allowed = {f.path for f in self.found}
            if p not in allowed:
                return self._send("not found", 404)
            s = parse_any(p)
            return self._send(render_html(s, self.opts["redact"], self.opts["anon"]))
        return self._send("not found", 404)


def serve(port: int = 8787, open_browser: bool = True, redact: bool = True, anon: bool = True, limit: int | None = None):
    Handler.found = find_sessions()[: limit or None]
    Handler.opts = {"redact": redact, "anon": anon}
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"agentcast ui → {url}   ({len(Handler.found)} sessions, local only; Ctrl-C to stop)")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
