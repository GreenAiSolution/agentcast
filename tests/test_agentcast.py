import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from agentcast.parsers import parse_any, detect  # noqa: E402
from agentcast.render import render_html, session_payload, active_seconds  # noqa: E402
from agentcast.redact import redact  # noqa: E402
from agentcast import diff as adiff  # noqa: E402
from agentcast import cost  # noqa: E402

CC = os.path.join(HERE, "fixtures", "claude_code_min.jsonl")
CX = os.path.join(HERE, "fixtures", "codex_min.jsonl")


class Detect(unittest.TestCase):
    def test_detect(self):
        self.assertEqual(detect(CC), "claude-code")
        self.assertEqual(detect(CX), "codex")

    def test_reject_garbage(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            fh.write('{"hello": "world"}\n')
        self.assertIsNone(detect(fh.name))
        os.unlink(fh.name)


class ClaudeCode(unittest.TestCase):
    def setUp(self):
        self.s = parse_any(CC)

    def test_basics(self):
        s = self.s
        self.assertEqual(s.agent, "claude-code")
        self.assertEqual(s.title, "Fix the off-by-one in pager")
        self.assertEqual(s.cwd, "/home/dev/proj")
        self.assertEqual(s.prompts, 1)
        self.assertEqual(s.tool_calls, 4)
        self.assertEqual(s.models, ["claude-opus-5"])
        self.assertEqual([st.kind for st in s.steps],
                         ["prompt", "say", "tool", "tool", "tool", "tool", "say", "note"])

    def test_meta_and_command_records(self):
        kinds = [st.kind for st in self.s.steps]
        self.assertNotIn("<local-command-caveat>", " ".join(st.text for st in self.s.steps))
        self.assertEqual(kinds.count("note"), 1)
        self.assertEqual(self.s.steps[-1].text, "/clear")

    def test_tool_results_attached(self):
        read, edit, bash, write = [st for st in self.s.steps if st.kind == "tool"]
        self.assertEqual(read.tool, "Read")
        self.assertIn("def page", read.output)
        self.assertEqual(read.duration_ms, 500)
        self.assertTrue(bash.error)
        self.assertFalse(edit.error)

    def test_diffs(self):
        edit = self.s.steps[3]
        self.assertIn("-    return items[0:n-1]", edit.diff)
        self.assertIn("+    return items[0:n]", edit.diff)
        write = self.s.steps[5]
        self.assertTrue(write.diff.startswith("--- /dev/null"))
        self.assertIn("+# notes", write.diff)

    def test_files_and_blast_radius(self):
        files = self.s.files_touched()
        self.assertEqual(files["/home/dev/proj/pager.py"], {"read": 1, "edit": 1})
        self.assertEqual(self.s.blast_radius(), ["/home/dev/proj/NOTES.md", "/home/dev/proj/pager.py"])

    def test_usage_dedupes_by_message_id(self):
        # message m1 appears twice (text block + tool_use block) but must be counted once
        self.assertEqual(self.s.usage["input"], 10 + 5 + 5 + 5 + 5)
        self.assertEqual(self.s.usage["cache_write"], 500)
        self.assertAlmostEqual(self.s.cost_usd, cost.estimate(self.s.usage, "claude-opus-5"), places=4)
        self.assertGreater(self.s.cost_usd, 0)

    def test_active_seconds(self):
        self.assertAlmostEqual(active_seconds(self.s), 14.0, places=1)


class Codex(unittest.TestCase):
    def setUp(self):
        self.s = parse_any(CX)

    def test_basics(self):
        s = self.s
        self.assertEqual(s.agent, "codex")
        self.assertEqual(s.id, "cdx-1")
        self.assertEqual(s.models, ["gpt-5-codex"])
        self.assertEqual(s.title, "add a greet function")
        self.assertEqual(s.prompts, 1)
        self.assertEqual(s.tool_calls, 3)

    def test_patch(self):
        patch = [st for st in self.s.steps if st.tool == "apply_patch"][0]
        self.assertEqual([(f.path, f.op) for f in patch.files], [("a.py", "edit"), ("b.py", "create")])
        self.assertIn("+++ b/a.py", patch.diff)
        self.assertIn("--- /dev/null", patch.diff)
        self.assertEqual(sorted(self.s.blast_radius()), ["a.py", "b.py"])

    def test_exec_error_detection(self):
        execs = [st for st in self.s.steps if st.tool == "exec_command"]
        self.assertFalse(execs[0].error)
        self.assertTrue(execs[1].error)
        self.assertEqual(execs[0].files[0].op, "command")

    def test_usage(self):
        self.assertEqual(self.s.usage, {"input": 12216 - 9088, "output": 249, "cache_read": 9088, "cache_write": 0})
        self.assertGreater(self.s.cost_usd, 0)


class Redaction(unittest.TestCase):
    def test_patterns(self):
        cases = {
            "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789ABCDEF": "[REDACTED:anthropic-key]",
            "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef123456": "[REDACTED:github-token]",
            "AKIAIOSFODNN7EXAMPLE": "[REDACTED:aws-key-id]",
            "xoxb-1234567890-abcdefghij": "[REDACTED:slack-token]",
        }
        for raw, want in cases.items():
            self.assertEqual(redact(f"key {raw} end"), f"key {want} end", raw)

    def test_env_assignment_and_bearer(self):
        self.assertEqual(redact("export API_TOKEN=supersecretvalue123"), "export API_TOKEN=[REDACTED:env-secret]")
        self.assertEqual(redact("Authorization: Bearer abcdefghijklmnop.qrstuv"), "Authorization: Bearer [REDACTED:bearer]")
        self.assertEqual(redact("https://user:hunter22@host/x"), "https://user:[REDACTED:password]@host/x")

    def test_leaves_normal_text(self):
        t = "skip this: sk-1 short, PATH=/usr/bin, token in prose"
        self.assertEqual(redact(t), t)

    def test_render_is_redacted_by_default(self):
        html = render_html(parse_any(CC))
        self.assertNotIn("sk-ant-api03", html)
        self.assertNotIn("ghp_ABCDEF", html)
        self.assertNotIn("supersecretvalue123", html)
        self.assertIn("[REDACTED:anthropic-key]", html)
        raw = render_html(parse_any(CC), do_redact=False)
        self.assertIn("supersecretvalue123", raw)


class Render(unittest.TestCase):
    def test_html_is_self_contained(self):
        html = render_html(parse_any(CC))
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertNotIn("<script src=", html)
        self.assertNotIn("<link ", html)
        self.assertIn('id="data" type="application/json"', html)
        self.assertNotIn("</script>\n", html.split('type="application/json">')[1].split("</script>")[0])

    def test_payload_shape(self):
        d = session_payload(parse_any(CC))
        for k in ("id", "agent", "title", "steps", "usage", "cost_usd", "files", "blast_radius", "active_s", "prompts", "tool_calls"):
            self.assertIn(k, d)
        json.dumps(d)  # must be serialisable

    def test_script_close_escaped(self):
        # a session whose text contains </script> must not break the page
        p = os.path.join(tempfile.mkdtemp(), "x.jsonl")
        with open(CC) as src, open(p, "w") as dst:
            dst.write(src.read().replace("fix the off-by-one", "fix </script><b>x</b> the off-by-one"))
        html = render_html(parse_any(p))
        body = html.split('type="application/json">')[1].split("</script>")[0]
        self.assertIn("<\\/script>", body)


class Diff(unittest.TestCase):
    def test_unified_and_stats(self):
        d = adiff.unified("f.py", "a\nb\n", "a\nc\n")
        self.assertIn("-b", d)
        self.assertIn("+c", d)
        self.assertEqual(adiff.diff_stats(d), (1, 1))

    def test_truncation(self):
        d = adiff.whole_file("big.txt", "x" * 200_000)
        self.assertLess(len(d), 61_000)
        self.assertIn("truncated", d)


class Cost(unittest.TestCase):
    def test_prefix_match(self):
        self.assertEqual(cost.price_for("claude-opus-5"), cost.PRICES["claude-opus-5"])
        self.assertEqual(cost.price_for("claude-sonnet-5-20260101"), cost.PRICES["claude-sonnet-5"])
        self.assertEqual(cost.price_for("gpt-5-codex"), cost.PRICES["gpt-5-codex"])
        self.assertEqual(cost.price_for("mystery"), cost.DEFAULT)


class CLI(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "agentcast", *args], cwd=ROOT, capture_output=True, text=True)

    def test_render_and_json(self):
        out = os.path.join(tempfile.mkdtemp(), "r.html")
        r = self.run_cli("render", CC, "-o", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(out))
        r = self.run_cli("json", CX, "--compact")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["agent"], "codex")

    def test_missing_session(self):
        r = self.run_cli("render", "does-not-exist-zzz")
        self.assertEqual(r.returncode, 2)

    def test_version(self):
        r = self.run_cli("--version")
        self.assertIn("agentcast", r.stdout)


if __name__ == "__main__":
    unittest.main()
