#!/usr/bin/env python3
"""Inject a concise Reality Gate reminder for architecture-risk prompts.

The hook is intentionally advisory and cheap: it only reads the submitted prompt,
does not inspect the repository, start reviewers, write a ledger, or block a task.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any


# Keep the classifier conservative. It is driven by the combination of a
# consequential decision and an implementation action, or by an explicit
# uncertainty. A lone generic noun such as "data" or "service" is not enough.
RISK_RE = re.compile(
    r"(?:\barchitecture\b|\bsystem design\b|\brequirements?\b|"
    r"\bspecification\b|\bdomain rules?\b|\buser intent\b|"
    r"\bexternal api\b|\bexternal service\b|\bintegration\b|\bschema\b|"
    r"\bdatabase\b|\bmigration\b|\bauth(?:entication|orization)?\b|"
    r"\bpermission\b|\bsecurity\b|"
    r"\bprivacy\b|\bproduction\b|\bdeploy(?:ment)?\b|\brelease\b|"
    r"\bperformance\b|\blatency\b|\bthroughput\b|\bquota\b|"
    r"\breliability\b|\bcost\b|\bscale\b|\bdomain rule\b|"
    r"\bpolicy\b|\bacceptance\b|\beval(?:uation)?\b|"
    r"\bbenchmark\b|\bautoresearch\b|\bharness\b|\boracle\b|"
    r"\bgolden\b|\bgenerated artifact\b|"
    r"架构|系统设计|需求|规格|领域规则|用户意图|接口契约|外部接口|外部服务|集成|数据库|schema|迁移|认证|"
    r"授权|权限|安全|隐私|生产|部署|上线|发布|性能|延迟|吞吐|配额|可靠性|"
    r"成本|规模|策略|验收|评测|基准|自动研究|harness|oracle|golden|"
    r"生成产物|真实用户输入|用户可见|公共 API)",
    re.IGNORECASE,
)
UNCERTAINTY_RE = re.compile(
    r"(?:\bunknown\b|\bunverified\b|\bassumption\b|\bnot sure\b|"
    r"\bincomplete\b|\bunclear\b|\bneed to confirm\b|\bmissing facts?\b|"
    r"\bmaybe\b|\bguess(?:ed|ing)?\b|\bmeasure(?:d|ment)?\b|"
    r"\bfield test\b|\bnot available\b|\bno access\b|未知|未验证|"
    r"假设|不确定|待确认|未确认|未确定|缺信息|事实不完整|可能|猜测|测量|实测|现场|"
    r"无法访问|没有数据|尚未知道|未提供|缺少|还没确认|尚未验证)",
    re.IGNORECASE,
)
ACTION_RE = re.compile(
    r"(?:\bbuild\b|\bimplement\b|\bdesign\b|\bdevelop\b|"
    r"\bcreate\b|\bship\b|\bdeploy\b|\bfix\b|\bchange\b|"
    r"\brefactor\b|\bwrite\b|\bmake\b|实现|开发|设计|构建|编写|"
    r"部署|上线|修复|修改|重构|迁移|验证|检查|确认|做一个|加上|接入|搭建)",
    re.IGNORECASE,
)
BROAD_SCOPE_RE = re.compile(
    r"(?:\bfrom scratch\b|\bend[- ]to[- ]end\b|\bfull system\b|"
    r"\bcomplete solution\b|\bwhole project\b|完整方案|完整系统|从零|全套|"
    r"端到端|整体实现)",
    re.IGNORECASE,
)
EXPLICIT_RE = re.compile(
    r"(?:reality[ -]?first|reality[ -]?gate|\$reality-first-engineering|"
    r"现实优先|现实门|事实门)",
    re.IGNORECASE,
)
ADDITIONAL_CONTEXT = (
    "Reality-first reminder: before architecture or broad implementation, use "
    "$reality-first-engineering when an incomplete domain, external, or acceptance fact could change the "
    "direction. Separate observed, measured, inferred, and unknown; bind each "
    "architecture-critical unknown to a small falsifiable experiment with pass/fail "
    "and stop conditions. If it remains unresolved, report BLOCKED or INCOMPLETE; "
    "do not hide the uncertainty with a fallback, compatibility path, or mock-only "
    "branch. Keep the record in project-to-act's one canonical ledger."
)


def should_inject(prompt: str) -> bool:
    """Return whether a prompt warrants the lightweight reality reminder."""
    if not prompt:
        return False
    if EXPLICIT_RE.search(prompt):
        return True
    has_risk = bool(RISK_RE.search(prompt))
    has_uncertainty = bool(UNCERTAINTY_RE.search(prompt))
    has_action = bool(ACTION_RE.search(prompt))
    has_broad_scope = bool(BROAD_SCOPE_RE.search(prompt))
    # A high-impact term plus an action catches consequential plans even when the
    # user did not explicitly say "unknown"; an uncertainty plus an action catches
    # incomplete requirements in any domain.
    return has_action and (has_uncertainty or has_risk or has_broad_scope)


def hook_output(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Build the cross-harness UserPromptSubmit output, if needed."""
    if str(payload.get("hook_event_name", "")) != "UserPromptSubmit":
        return None
    prompt = payload.get("prompt")
    if not isinstance(prompt, str):
        prompt = payload.get("user_prompt") or payload.get("userPrompt")
    if not isinstance(prompt, str) or not should_inject(prompt):
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": ADDITIONAL_CONTEXT,
        }
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (OSError, TypeError, ValueError):
        # A reminder hook must fail open on malformed or non-hook input; it
        # cannot turn an unavailable context into a false gate result.
        return 0
    if not isinstance(payload, dict):
        return 0
    result = hook_output(payload)
    if result is not None:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
