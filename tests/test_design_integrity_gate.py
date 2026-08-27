from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / "design-integrity-review"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

from design_integrity import scan_unified_diff  # noqa: E402
import integrity_hook  # noqa: E402
from integrity_hook import handle_event  # noqa: E402


class DiffScannerTests(unittest.TestCase):
    def test_flags_swallowed_exception_and_default_return(self) -> None:
        diff = """\
diff --git a/service.py b/service.py
--- a/service.py
+++ b/service.py
@@ -3,0 +4,3 @@
+    except Exception:
+        pass
+        return None
"""

        findings = scan_unified_diff(diff)
        kinds = {finding.kind for finding in findings}

        self.assertIn("exception-boundary", kinds)
        self.assertIn("broad-exception", kinds)
        self.assertIn("swallowed-exception", kinds)
        self.assertIn("default-after-catch", kinds)

    def test_flags_fallback_and_parallel_api_names(self) -> None:
        diff = """\
diff --git a/src/client.ts b/src/client.ts
--- a/src/client.ts
+++ b/src/client.ts
@@ -10,0 +11,3 @@
+export function loadUserV2() {
+  return fallbackClient.load();
+}
"""

        findings = scan_unified_diff(diff)
        kinds = {finding.kind for finding in findings}

        self.assertIn("parallel-api-name", kinds)
        self.assertIn("fallback-marker", kinds)

    def test_nonempty_javascript_catch_is_not_marked_swallowed(self) -> None:
        diff = """\
diff --git a/src/client.ts b/src/client.ts
--- a/src/client.ts
+++ b/src/client.ts
@@ -10,0 +11,4 @@
+} catch (error) {
+  logger.error(error);
+  throw error;
+}
"""

        findings = scan_unified_diff(diff)
        kinds = {finding.kind for finding in findings}

        self.assertIn("exception-boundary", kinds)
        self.assertNotIn("swallowed-exception", kinds)

    def test_ignores_removed_and_test_only_lines(self) -> None:
        diff = """\
diff --git a/src/client.ts b/src/client.ts
--- a/src/client.ts
+++ b/src/client.ts
@@ -1 +1 @@
-const fallbackClient = oldClient;
+const primaryClient = newClient;
diff --git a/tests/test_client.py b/tests/test_client.py
--- a/tests/test_client.py
+++ b/tests/test_client.py
@@ -2,0 +3 @@
+def test_fallback_behavior(): pass
"""

        self.assertEqual([], scan_unified_diff(diff))


class HookGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo = Path(self.temp_dir.name) / "repo"
        self.state_dir = Path(self.temp_dir.name) / "state"
        self.repo.mkdir()
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "Test User")
        self._write("service.py", "def load():\n    return 1\n")
        self._git("add", "service.py")
        self._git("commit", "-qm", "base")

    def _git(self, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=self.repo,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def _write(self, relative_path: str, content: str) -> None:
        (self.repo / relative_path).write_text(content, encoding="utf-8")

    def _event(self, name: str, *, active: bool = False) -> dict[str, object]:
        return {
            "session_id": "session-1",
            "cwd": str(self.repo),
            "hook_event_name": name,
            "stop_hook_active": active,
        }

    def test_blocks_only_for_risk_introduced_after_baseline(self) -> None:
        self.assertIsNone(
            handle_event(
                self._event("PreToolUse"),
                agent="codex",
                state_dir=self.state_dir,
            )
        )
        self._write(
            "service.py",
            "def load():\n"
            "    try:\n"
            "        return fetch()\n"
            "    except Exception:\n"
            "        return None\n",
        )

        result = handle_event(
            self._event("Stop"),
            agent="codex",
            state_dir=self.state_dir,
        )

        self.assertEqual("block", result["decision"])
        self.assertIn("$design-integrity-review", result["reason"])
        self.assertIn("service.py", result["reason"])

    def test_does_not_blame_preexisting_dirty_fallback(self) -> None:
        self._write(
            "service.py",
            "def load():\n    return fallback_client.load()\n",
        )
        handle_event(
            self._event("PreToolUse"),
            agent="claude",
            state_dir=self.state_dir,
        )
        self._write(
            "service.py",
            "VALUE = 1\n\n"
            "def load():\n    return fallback_client.load()\n",
        )

        result = handle_event(
            self._event("Stop"),
            agent="claude",
            state_dir=self.state_dir,
        )

        self.assertIsNone(result)
        self.assertEqual([], list(self.state_dir.glob("*.json")))

    def test_active_stop_allows_exit_and_clears_state(self) -> None:
        handle_event(
            self._event("PreToolUse"),
            agent="claude",
            state_dir=self.state_dir,
        )
        self._write(
            "service.py",
            "def load():\n    return fallback_client.load()\n",
        )

        result = handle_event(
            self._event("Stop", active=True),
            agent="claude",
            state_dir=self.state_dir,
        )

        self.assertIsNone(result)
        self.assertEqual([], list(self.state_dir.glob("*.json")))

    def test_hook_result_is_json_serializable(self) -> None:
        handle_event(
            self._event("PreToolUse"),
            agent="claude",
            state_dir=self.state_dir,
        )
        self._write(
            "service.py",
            "def load():\n    return fallback_client.load()\n",
        )

        result = handle_event(
            self._event("Stop"),
            agent="claude",
            state_dir=self.state_dir,
        )

        json.dumps(result)

    def test_cli_emits_claude_review_command(self) -> None:
        command = [
            sys.executable,
            str(SCRIPTS_DIR / "integrity_hook.py"),
            "--agent",
            "claude",
            "--state-dir",
            str(self.state_dir),
        ]
        subprocess.run(
            command,
            input=json.dumps(self._event("PreToolUse")),
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._write(
            "service.py",
            "def load():\n    return fallback_client.load()\n",
        )

        result = subprocess.run(
            command,
            input=json.dumps(self._event("Stop")),
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        payload = json.loads(result.stdout)

        self.assertEqual("block", payload["decision"])
        self.assertIn("/design-integrity-review", payload["reason"])

    def test_committed_risk_introduced_after_baseline_is_still_blocked(self) -> None:
        handle_event(
            self._event("PreToolUse"),
            agent="codex",
            state_dir=self.state_dir,
        )
        self._write(
            "service.py",
            "def load():\n"
            "    try:\n"
            "        return fetch()\n"
            "    except Exception:\n"
            "        return None\n",
        )
        self._git("add", "service.py")
        self._git("commit", "-qm", "introduce risk")

        result = handle_event(
            self._event("Stop"),
            agent="codex",
            state_dir=self.state_dir,
        )

        self.assertEqual("block", result["decision"])
        self.assertIn("service.py", result["reason"])

    def test_parallel_pre_tool_hooks_cannot_advance_the_baseline(self) -> None:
        original_scan = integrity_hook.scan_worktree
        second_scan_started = threading.Event()
        mutation_done = threading.Event()
        first_hook_done = threading.Event()
        call_lock = threading.Lock()
        scan_calls = 0

        def coordinated_scan(cwd: Path, *args, **kwargs):
            nonlocal scan_calls
            with call_lock:
                scan_calls += 1
                call_number = scan_calls
            if call_number == 1:
                second_scan_started.wait(timeout=1)
                return original_scan(cwd, *args, **kwargs)
            second_scan_started.set()
            mutation_done.wait(timeout=2)
            return original_scan(cwd, *args, **kwargs)

        def run_first_hook() -> None:
            handle_event(
                self._event("PreToolUse"),
                agent="codex",
                state_dir=self.state_dir,
            )
            first_hook_done.set()

        with patch.object(integrity_hook, "scan_worktree", coordinated_scan):
            first = threading.Thread(target=run_first_hook)
            second = threading.Thread(target=run_first_hook)
            first.start()
            second.start()
            self.assertTrue(first_hook_done.wait(timeout=3))
            self._write(
                "service.py",
                "def load():\n"
                "    try:\n"
                "        return fetch()\n"
                "    except Exception:\n"
                "        return None\n",
            )
            mutation_done.set()
            first.join(timeout=3)
            second.join(timeout=3)
            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())

        result = handle_event(
            self._event("Stop"),
            agent="codex",
            state_dir=self.state_dir,
        )

        self.assertEqual("block", result["decision"])

    def test_first_commit_after_baseline_is_scanned_from_empty_tree(self) -> None:
        unborn = Path(self.temp_dir.name) / "unborn"
        unborn.mkdir()
        subprocess.run(
            ["git", "init", "-q"],
            cwd=unborn,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=unborn,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=unborn,
            check=True,
        )
        service = unborn / "service.py"
        service.write_text("def load():\n    return 1\n", encoding="utf-8")
        event = {
            "session_id": "unborn-session",
            "cwd": str(unborn),
            "hook_event_name": "PreToolUse",
        }
        handle_event(event, agent="codex", state_dir=self.state_dir)
        service.write_text(
            "def load():\n"
            "    try:\n"
            "        return fetch()\n"
            "    except Exception:\n"
            "        return None\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "service.py"], cwd=unborn, check=True)
        subprocess.run(
            ["git", "commit", "-qm", "first commit"],
            cwd=unborn,
            check=True,
        )

        event["hook_event_name"] = "Stop"
        event["stop_hook_active"] = False
        result = handle_event(event, agent="codex", state_dir=self.state_dir)

        self.assertEqual("block", result["decision"])


if __name__ == "__main__":
    unittest.main()
