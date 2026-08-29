from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "reality-first-engineering"
    / "scripts"
    / "reality_prompt_hook.py"
)
sys.path.insert(0, str(SCRIPT.parent))

from reality_prompt_hook import hook_output, should_inject  # noqa: E402


class RealityPromptRoutingTests(unittest.TestCase):
    def test_explicit_request_always_routes(self) -> None:
        self.assertTrue(should_inject("请先做 reality-first-engineering"))

    def test_incomplete_domain_fact_and_action_routes(self) -> None:
        self.assertTrue(should_inject("请实现这个流程，但领域规则还未确认"))
        self.assertTrue(should_inject("请设计一个完整方案"))

    def test_high_impact_change_routes_without_magic_word_unknown(self) -> None:
        self.assertTrue(should_inject("把支付服务迁移到新的数据库并部署到生产"))
        self.assertTrue(should_inject("implement an autoresearch harness with external inputs"))

    def test_small_known_edit_does_not_route(self) -> None:
        self.assertFalse(should_inject("把 load 函数改名"))
        self.assertFalse(should_inject("修复这个 typo"))
        self.assertFalse(should_inject("更新 README 的拼写"))
        self.assertFalse(should_inject("更新接口文档的示例文字"))

    def test_hook_only_injects_for_user_prompt_event(self) -> None:
        self.assertIsNone(
            hook_output({"hook_event_name": "PreToolUse", "prompt": "部署新架构"})
        )
        result = hook_output(
            {
                "hook_event_name": "UserPromptSubmit",
                "user_prompt": "部署新架构，但权限还未确认",
            }
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(
            "UserPromptSubmit", result["hookSpecificOutput"]["hookEventName"]
        )
        self.assertIn("BLOCKED", result["hookSpecificOutput"]["additionalContext"])

    def test_cli_is_silent_for_low_risk_prompt(self) -> None:
        payload = {"hook_event_name": "UserPromptSubmit", "prompt": "修复 typo"}
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(payload),
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual("", result.stdout)


if __name__ == "__main__":
    unittest.main()
