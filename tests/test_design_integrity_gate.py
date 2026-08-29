from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / "design-integrity-review"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

from design_integrity import (
    acceptance_paths_from_diff,
    requires_acceptance_review,
    scan_unified_diff,
)  # noqa: E402
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
        path = self.repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_windows_lock_backend_uses_one_byte_lock(self) -> None:
        class FakeMsvcrt:
            LK_LOCK = 1
            LK_UNLCK = 2

            def __init__(self) -> None:
                self.calls: list[tuple[int, int]] = []

            def locking(self, _fd: int, mode: int, size: int) -> None:
                self.calls.append((mode, size))

        fake = FakeMsvcrt()
        state_path = self.state_dir / "windows.json"
        with patch.object(integrity_hook, "_fcntl", None), patch.object(
            integrity_hook, "_msvcrt", fake
        ):
            with integrity_hook._state_lock(state_path):
                self.assertTrue(state_path.with_suffix(".lock").exists())
            with integrity_hook._state_lock(state_path):
                self.assertEqual(1, state_path.with_suffix(".lock").stat().st_size)

        self.assertEqual(
            [
                (fake.LK_LOCK, 1),
                (fake.LK_UNLCK, 1),
                (fake.LK_LOCK, 1),
                (fake.LK_UNLCK, 1),
            ],
            fake.calls,
        )

    def _event(
        self,
        name: str,
        *,
        active: bool = False,
        turn_id: str = "turn-1",
    ) -> dict[str, object]:
        return {
            "session_id": "session-1",
            "cwd": str(self.repo),
            "hook_event_name": name,
            "stop_hook_active": active,
            "turn_id": turn_id,
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

    def test_blocks_when_existing_exception_handler_gains_default_return(self) -> None:
        self._write(
            "service.py",
            "def load():\n"
            "    try:\n"
            "        return fetch()\n"
            "    except Exception:\n"
            "        raise\n",
        )
        self._git("add", "service.py")
        self._git("commit", "-qm", "add existing handler")

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

        result = handle_event(
            self._event("Stop"),
            agent="codex",
            state_dir=self.state_dir,
        )

        self.assertEqual("block", result["decision"])
        self.assertIn("default-after-catch", result["reason"])

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

    def test_same_risk_is_not_blocked_again_after_active_stop(self) -> None:
        handle_event(
            self._event("PreToolUse"),
            agent="codex",
            state_dir=self.state_dir,
        )
        self._write(
            "service.py",
            "def load():\n    return fallback_client.load()\n",
        )

        first = handle_event(
            self._event("Stop"),
            agent="codex",
            state_dir=self.state_dir,
        )
        self.assertEqual("block", first["decision"])

        self.assertIsNone(
            handle_event(
                self._event("Stop", active=True),
                agent="codex",
                state_dir=self.state_dir,
            )
        )
        self.assertTrue(list(self.state_dir.glob("*.json")))

        second = handle_event(
            self._event("Stop"),
            agent="codex",
            state_dir=self.state_dir,
        )
        self.assertIsNone(second)

    def test_new_turn_resets_review_budget_after_acknowledged_epoch(self) -> None:
        handle_event(
            self._event("PreToolUse", turn_id="turn-1"),
            agent="codex",
            state_dir=self.state_dir,
        )
        self._write(
            "service.py",
            "def load():\n    return fallback_client.load()\n",
        )
        self.assertEqual(
            "block",
            handle_event(
                self._event("Stop", turn_id="turn-1"),
                agent="codex",
                state_dir=self.state_dir,
            )["decision"],
        )
        self.assertIsNone(
            handle_event(
                self._event("Stop", active=True, turn_id="turn-1"),
                agent="codex",
                state_dir=self.state_dir,
            )
        )

        # A real new user turn gets a new baseline and a fresh automatic budget.
        handle_event(
            self._event("PreToolUse", turn_id="turn-2"),
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
        result = handle_event(
            self._event("Stop", turn_id="turn-2"),
            agent="codex",
            state_dir=self.state_dir,
        )

        self.assertEqual("block", result["decision"])
        self.assertIn("epoch 1/", result["reason"].lower())

    def test_pending_review_is_not_dropped_on_turn_change(self) -> None:
        handle_event(
            self._event("PreToolUse", turn_id="turn-1"),
            agent="codex",
            state_dir=self.state_dir,
        )
        self._write(
            "service.py",
            "def load():\n    return fallback_client.load()\n",
        )
        first = handle_event(
            self._event("Stop", turn_id="turn-1"),
            agent="codex",
            state_dir=self.state_dir,
        )
        self.assertEqual("block", first["decision"])

        # An interrupted/newly steered turn cannot silently discard the pending gate.
        handle_event(
            self._event("PreToolUse", turn_id="turn-2"),
            agent="codex",
            state_dir=self.state_dir,
        )
        continued = handle_event(
            self._event("Stop", active=True, turn_id="turn-2"),
            agent="codex",
            state_dir=self.state_dir,
        )
        self.assertIsNone(continued)
        self.assertTrue(list(self.state_dir.glob("*.json")))

    def test_repeated_non_active_stop_does_not_acknowledge_pending_review(self) -> None:
        handle_event(
            self._event("PreToolUse"),
            agent="codex",
            state_dir=self.state_dir,
        )
        self._write("service.py", "def load():\n    return fallback_client.load()\n")

        first = handle_event(
            self._event("Stop"),
            agent="codex",
            state_dir=self.state_dir,
        )
        self.assertEqual("block", first["decision"])
        self.assertIsNone(
            handle_event(
                self._event("Stop"),
                agent="codex",
                state_dir=self.state_dir,
            )
        )

        state_path = next(self.state_dir.glob("*.json"))
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertTrue(payload["blocked_risk_signatures"])

    def test_new_risk_after_an_acknowledged_epoch_is_blocked_once(self) -> None:
        handle_event(
            self._event("PreToolUse"),
            agent="codex",
            state_dir=self.state_dir,
        )
        self._write(
            "service.py",
            "def load():\n    return fallback_client.load()\n",
        )
        self.assertEqual(
            "block",
            handle_event(
                self._event("Stop"),
                agent="codex",
                state_dir=self.state_dir,
            )["decision"],
        )
        self.assertIsNone(
            handle_event(
                self._event("Stop", active=True),
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
        self.assertIn("epoch", result["reason"].lower())

    def test_review_epoch_budget_stops_automatic_respawn(self) -> None:
        handle_event(
            self._event("PreToolUse"),
            agent="codex",
            state_dir=self.state_dir,
        )
        versions = (
            ("service.py", "def load():\n    return fallback_client.load()\n"),
            (
                "service.py",
                "def load():\n"
                "    try:\n"
                "        return fetch()\n"
                "    except Exception:\n"
                "        return None\n",
            ),
            ("src/client.ts", "export function loadUserV2() {\n  return 1;\n}\n"),
            ("other.py", "def read():\n    return fallback_client.load()\n"),
        )

        for index, (path, content) in enumerate(versions):
            self._write(path, content)
            result = handle_event(
                self._event("Stop"),
                agent="codex",
                state_dir=self.state_dir,
            )
            if index < integrity_hook.MAX_REVIEW_EPOCHS:
                self.assertEqual("block", result["decision"])
                self.assertIsNone(
                    handle_event(
                        self._event("Stop", active=True),
                        agent="codex",
                        state_dir=self.state_dir,
                    )
                )
            else:
                self.assertEqual("block", result["decision"])
                self.assertIn("budget", result["reason"].lower())

    def test_acceptance_classifier_only_returns_matching_paths(self) -> None:
        handle_event(
            self._event("PreToolUse"),
            agent="codex",
            state_dir=self.state_dir,
        )
        self._write("autoresearch/run.py", "def run():\n    return 1\n")
        self._write("service.py", "def load():\n    return 1\n")

        result = handle_event(
            self._event("Stop"),
            agent="codex",
            state_dir=self.state_dir,
        )

        self.assertIn("autoresearch/run.py", result["reason"])
        self.assertNotIn("service.py", result["reason"])

    def test_acceptance_risk_routes_through_design_integrity_skill(self) -> None:
        handle_event(
            self._event("PreToolUse"),
            agent="codex",
            state_dir=self.state_dir,
        )
        self._write("autoresearch/run.py", "def run():\n    return 1\n")

        result = handle_event(
            self._event("Stop"),
            agent="codex",
            state_dir=self.state_dir,
        )

        self.assertEqual("block", result["decision"])
        self.assertIn("$design-integrity-review", result["reason"])
        self.assertIn("acceptance-auditor", result["reason"])

    def test_ordinary_unit_test_change_does_not_trigger_acceptance_route(self) -> None:
        handle_event(
            self._event("PreToolUse"),
            agent="codex",
            state_dir=self.state_dir,
        )
        self._write("tests/test_service.py", "def test_load():\n    assert True\n")

        result = handle_event(
            self._event("Stop"),
            agent="codex",
            state_dir=self.state_dir,
        )

        self.assertIsNone(result)

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
        original_collect = integrity_hook.collect_worktree_diff
        second_scan_started = threading.Event()
        mutation_done = threading.Event()
        first_hook_done = threading.Event()
        call_lock = threading.Lock()
        scan_calls = 0

        def coordinated_collect(cwd: Path, *args, **kwargs):
            nonlocal scan_calls
            with call_lock:
                scan_calls += 1
                call_number = scan_calls
            if call_number == 1:
                second_scan_started.wait(timeout=1)
                return original_collect(cwd, *args, **kwargs)
            second_scan_started.set()
            mutation_done.wait(timeout=2)
            return original_collect(cwd, *args, **kwargs)

        def run_first_hook() -> None:
            handle_event(
                self._event("PreToolUse"),
                agent="codex",
                state_dir=self.state_dir,
            )
            first_hook_done.set()

        with patch.object(
            integrity_hook, "collect_worktree_diff", coordinated_collect
        ):
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

    def test_stale_state_files_are_collected_on_cold_pre_tool_use(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        stale_json = self.state_dir / "stale.json"
        stale_lock = self.state_dir / "stale.lock"
        fresh_json = self.state_dir / "fresh.json"
        fresh_lock = self.state_dir / "fresh.lock"
        for path in (stale_json, stale_lock, fresh_json, fresh_lock):
            path.write_text("{}", encoding="utf-8")
        stale_mtime = time.time() - 49 * 60 * 60
        os.utime(stale_json, (stale_mtime, stale_mtime))
        os.utime(stale_lock, (stale_mtime, stale_mtime))

        result = handle_event(
            self._event("PreToolUse"),
            agent="codex",
            state_dir=self.state_dir,
        )

        self.assertIsNone(result)
        self.assertFalse(stale_json.exists())
        self.assertFalse(stale_lock.exists())
        self.assertTrue(fresh_json.exists())
        self.assertTrue(fresh_lock.exists())
        baseline = [
            path for path in self.state_dir.glob("*.json") if path.name != "fresh.json"
        ]
        self.assertEqual(1, len(baseline))
        payload = json.loads(baseline[0].read_text(encoding="utf-8"))
        self.assertIn("findings", payload)
        self.assertIn("base_revision", payload)

    def test_held_lock_is_not_collected_on_long_lived_session_cold_start(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        lock_path = integrity_hook._state_path(
            self.state_dir, "session-1", self.repo
        ).with_suffix(".lock")
        lock_path.write_text("", encoding="utf-8")
        stale_mtime = time.time() - 49 * 60 * 60
        os.utime(lock_path, (stale_mtime, stale_mtime))

        result = handle_event(
            self._event("PreToolUse"),
            agent="codex",
            state_dir=self.state_dir,
        )

        self.assertIsNone(result)
        self.assertTrue(lock_path.exists())
        state_path = lock_path.with_suffix(".json")
        self.assertTrue(state_path.exists())
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertIn("findings", payload)
        self.assertIn("base_revision", payload)


class ScannerPrecisionTests(unittest.TestCase):
    def _diff(self, path: str, *added: str) -> str:
        return "\n".join(
            [
                f"diff --git a/{path} b/{path}",
                f"--- a/{path}",
                f"+++ b/{path}",
                f"@@ -1,0 +1,{len(added)} @@",
                *(f"+{line}" for line in added),
            ]
        )

    def test_comments_and_strings_are_not_flagged(self) -> None:
        diff = "\n".join(
            [
                self._diff("src/guard.ts", "// catch this early; no fallback needed"),
                self._diff("cache.py", "# we fall back to cache here"),
                self._diff("src/log.ts", 'logger.info("no fallback needed")'),
            ]
        )

        self.assertEqual([], scan_unified_diff(diff))

    def test_catch_prefix_identifiers_are_not_exception_boundaries(self) -> None:
        diff = self._diff(
            "src/names.ts",
            "const catchyName = 1;",
            "catchError(x);",
        )

        kinds = {finding.kind for finding in scan_unified_diff(diff)}
        self.assertNotIn("exception-boundary", kinds)

    def test_real_exception_boundaries_are_flagged(self) -> None:
        cases = (
            ("src/client.ts", "} catch (err) {"),
            ("src/promise.ts", "promise.catch(handleError)"),
            ("src/Handler.swift", "catch let error {"),
            ("src/Handler.cs", "catch (Exception e)"),
            ("service.py", "except ValueError:"),
            ("groups.py", "except* ValueError:"),
            ("loader.rb", "rescue => e"),
            ("loader.rb", "data = JSON.parse(raw) rescue {}"),
        )
        for path, line in cases:
            with self.subTest(path=path, line=line):
                kinds = {finding.kind for finding in scan_unified_diff(self._diff(path, line))}
                self.assertIn("exception-boundary", kinds)

    def test_existing_exception_boundary_with_new_default_return_is_flagged(self) -> None:
        diff = "\n".join(
            [
                "diff --git a/service.py b/service.py",
                "--- a/service.py",
                "+++ b/service.py",
                "@@ -1,5 +1,5 @@",
                " def load():",
                "     try:",
                "         return fetch()",
                "     except Exception:",
                "-        raise",
                "+        return None",
            ]
        )

        kinds = {finding.kind for finding in scan_unified_diff(diff)}
        self.assertIn("default-after-catch", kinds)

    def test_promise_catch_call_does_not_capture_following_default_return(self) -> None:
        diff = self._diff(
            "src/promise.ts",
            "promise.catch(handleError);",
            "return null;",
        )

        kinds = {finding.kind for finding in scan_unified_diff(diff)}
        self.assertIn("exception-boundary", kinds)
        self.assertNotIn("default-after-catch", kinds)

    def test_existing_exception_boundary_with_new_pass_is_flagged(self) -> None:
        diff = "\n".join(
            [
                "diff --git a/service.py b/service.py",
                "--- a/service.py",
                "+++ b/service.py",
                "@@ -1,5 +1,5 @@",
                " def load():",
                "     try:",
                "         return fetch()",
                "     except Exception:",
                "-        raise",
                "+        pass",
            ]
        )

        kinds = {finding.kind for finding in scan_unified_diff(diff)}
        self.assertIn("swallowed-exception", kinds)

    def test_existing_braced_exception_boundary_does_not_capture_code_after_close(self) -> None:
        diff = "\n".join(
            [
                "diff --git a/src/service.ts b/src/service.ts",
                "--- a/src/service.ts",
                "+++ b/src/service.ts",
                "@@ -1,7 +1,8 @@",
                " function load() {",
                "   try {",
                "     return fetch();",
                "   } catch (error) {",
                "     throw error;",
                "   }",
                "+  return null;",
                " }",
            ]
        )

        kinds = {finding.kind for finding in scan_unified_diff(diff)}
        self.assertNotIn("default-after-catch", kinds)
        self.assertNotIn("swallowed-exception", kinds)

    def test_existing_indented_exception_boundary_does_not_capture_code_after_dedent(self) -> None:
        diff = "\n".join(
            [
                "diff --git a/service.py b/service.py",
                "--- a/service.py",
                "+++ b/service.py",
                "@@ -1,7 +1,8 @@",
                " def load():",
                "     try:",
                "         return fetch()",
                "     except Exception:",
                "         raise",
                "+    return None",
                "",
                " def other():",
            ]
        )

        kinds = {finding.kind for finding in scan_unified_diff(diff)}
        self.assertNotIn("default-after-catch", kinds)
        self.assertNotIn("swallowed-exception", kinds)

    def test_ruby_rescue_in_plain_string_is_not_flagged(self) -> None:
        diff = self._diff("loader.rb", 'text = " value rescue later"')

        kinds = {finding.kind for finding in scan_unified_diff(diff)}
        self.assertNotIn("exception-boundary", kinds)

    def test_real_fallback_code_forms_are_flagged(self) -> None:
        cases = (
            ("client.py", "fallback_client = make()"),
            ("src/load.ts", "return fallbackClient.load()"),
            ("flags.py", "load(fallback=True)"),
            ("src/read.ts", "return client.fallback"),
        )
        for path, line in cases:
            with self.subTest(path=path, line=line):
                kinds = {finding.kind for finding in scan_unified_diff(self._diff(path, line))}
                self.assertIn("fallback-marker", kinds)

    def test_value_position_fallback_is_deliberately_not_flagged(self) -> None:
        # Explicit contract: value-position recall yields to prose false-positive suppression; semantic review covers the rest.
        diff = "\n".join(
            [
                self._diff("src/nullish.ts", "return cached ?? fallbackValue;"),
                self._diff("src/arg.ts", "use(fallbackClient)"),
                self._diff("src/key.ts", "{ fallback: loadBackup }"),
            ]
        )

        kinds = {finding.kind for finding in scan_unified_diff(diff)}
        self.assertNotIn("fallback-marker", kinds)

    def test_parallel_api_covers_fn_and_fun(self) -> None:
        cases = (
            ("src/load.rs", "fn load_v2() {"),
            ("src/User.kt", "fun loadUserV2() {"),
        )
        for path, line in cases:
            with self.subTest(path=path, line=line):
                kinds = {finding.kind for finding in scan_unified_diff(self._diff(path, line))}
                self.assertIn("parallel-api-name", kinds)

    def test_acceptance_surface_classifier_is_narrow(self) -> None:
        acceptance = self._diff("autoresearch/run.py", "def run(): pass")
        filename_acceptance = self._diff(
            "tests/test_autoresearch.py", "def test_run(): pass"
        )
        ordinary = self._diff("src/service.py", "def run(): pass")

        self.assertTrue(requires_acceptance_review(acceptance))
        self.assertEqual(["autoresearch/run.py"], acceptance_paths_from_diff(acceptance))
        self.assertTrue(requires_acceptance_review(filename_acceptance))
        self.assertEqual(
            ["tests/test_autoresearch.py"],
            acceptance_paths_from_diff(filename_acceptance),
        )
        self.assertFalse(requires_acceptance_review(ordinary))
        self.assertEqual([], acceptance_paths_from_diff(ordinary))


if __name__ == "__main__":
    unittest.main()
