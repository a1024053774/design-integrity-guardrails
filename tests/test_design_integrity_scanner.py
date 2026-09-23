from __future__ import annotations

import sys
import unittest
from pathlib import Path


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

    def test_identifiers_are_not_treated_as_structural_risk(self) -> None:
        diff = """\
diff --git a/src/client.ts b/src/client.ts
--- a/src/client.ts
+++ b/src/client.ts
@@ -10,0 +11,4 @@
+export function loadUserV2() {
+  return fallbackClient.load();
+}
+const pattern = "promise.catch(x)";
"""

        findings = scan_unified_diff(diff)
        self.assertEqual([], findings)

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

    def test_multiline_comments_and_escaped_strings_are_not_scanned(self) -> None:
        diff = self._diff(
            "src/log.ts",
            "/*",
            "  catch (error) { return null; }",
            "*/",
            r'const pattern = "escaped \".catch(x)";',
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

    def test_fallback_identifiers_are_not_behavior_evidence(self) -> None:
        cases = (
            ("client.py", "fallback_client = make()"),
            ("src/load.ts", "return fallbackClient.load()"),
            ("flags.py", "load(fallback=True)"),
            ("src/read.ts", "return client.fallback"),
        )
        for path, line in cases:
            with self.subTest(path=path, line=line):
                kinds = {finding.kind for finding in scan_unified_diff(self._diff(path, line))}
                self.assertNotIn("fallback-marker", kinds)

    def test_fallback_in_value_positions_is_not_behavior_evidence(self) -> None:
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

    def test_versioned_api_names_are_not_parallel_api_evidence(self) -> None:
        cases = (
            ("src/load.rs", "fn load_v2() {"),
            ("src/User.kt", "fun loadUserV2() {"),
        )
        for path, line in cases:
            with self.subTest(path=path, line=line):
                kinds = {finding.kind for finding in scan_unified_diff(self._diff(path, line))}
                self.assertNotIn("parallel-api-name", kinds)

    def test_acceptance_surface_classifier_is_narrow(self) -> None:
        acceptance = self._diff("autoresearch/run.py", "def run(): pass")
        filename_only = self._diff("src/model_acceptance.py", "def helper(): pass")
        ordinary = self._diff("src/service.py", "def run(): pass")

        self.assertTrue(requires_acceptance_review(acceptance))
        self.assertEqual(["autoresearch/run.py"], acceptance_paths_from_diff(acceptance))
        self.assertFalse(requires_acceptance_review(filename_only))
        self.assertEqual([], acceptance_paths_from_diff(filename_only))
        self.assertFalse(requires_acceptance_review(ordinary))
        self.assertEqual([], acceptance_paths_from_diff(ordinary))

    def test_renaming_from_acceptance_surface_keeps_review_route(self) -> None:
        diff = "\n".join(
            [
                "diff --git a/autoresearch/run.py b/src/run.py",
                "similarity index 100%",
                "rename from autoresearch/run.py",
                "rename to src/run.py",
            ]
        )

        self.assertTrue(requires_acceptance_review(diff))
        self.assertEqual(
            ["autoresearch/run.py"],
            acceptance_paths_from_diff(diff),
        )


if __name__ == "__main__":
    unittest.main()
