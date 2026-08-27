#!/usr/bin/env python3
"""Lifecycle hook that requests fresh review for newly introduced risk markers."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from design_integrity import (
    Finding,
    introduced_findings,
    resolve_base_revision,
    scan_worktree,
)


DEFAULT_STATE_DIR = Path(tempfile.gettempdir()) / "design-integrity-review"
STATE_TTL_SECONDS = 48 * 60 * 60


def _state_path(state_dir: Path, session_id: str, cwd: Path) -> Path:
    identity = f"{session_id}\0{cwd.resolve()}".encode("utf-8", errors="replace")
    return state_dir / f"{hashlib.sha256(identity).hexdigest()}.json"


def _write_state(
    path: Path,
    *,
    root: Path,
    base_revision: str,
    findings: list[Finding],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "root": str(root),
        "base_revision": base_revision,
        "findings": [finding.to_dict() for finding in findings],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _read_state(path: Path) -> tuple[Path, str, list[Finding]] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return (
            Path(payload["root"]),
            str(payload["base_revision"]),
            [Finding.from_dict(item) for item in payload["findings"]],
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _remove_state(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _collect_garbage(state_dir: Path) -> None:
    """Delete state files whose mtime is older than STATE_TTL_SECONDS.

    The normal Stop path does not unlink the sibling .lock: unlinking a file
    another process may already be flock-waiting on would create two inodes and
    two lock domains, breaking mutual exclusion. Collecting after 48h is safe
    because every successful lock acquisition refreshes the lock file mtime, so
    an mtime older than the TTL means no process acquired that lock within 48
    hours (the hook timeout is 10 seconds); there is neither an active holder
    nor a waiter.
    """
    cutoff = time.time() - STATE_TTL_SECONDS
    for path in (*state_dir.glob("*.json"), *state_dir.glob("*.lock")):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


@contextmanager
def _state_lock(state_path: Path):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_suffix(".lock")
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        os.utime(lock_path)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _is_true(value: object) -> bool:
    return value is True or (isinstance(value, str) and value.lower() == "true")


def _review_reason(agent: str, findings: list[Finding]) -> str:
    invocation = (
        "$design-integrity-review"
        if agent == "codex"
        else "/design-integrity-review"
    )
    shown = findings[:8]
    lines = [
        "Design-integrity gate found code-risk markers introduced after this turn's baseline:",
        *(
            f"- {finding.path}:{finding.line} [{finding.kind}] {finding.text}"
            for finding in shown
        ),
    ]
    if len(findings) > len(shown):
        lines.append(f"- ... and {len(findings) - len(shown)} more")
    lines.extend(
        [
            "",
            f"Before finishing, invoke {invocation}. The review must run in a fresh, read-only context,",
            "inspect the task, current diff, relevant callers/tests, and active instructions, and must not",
            "inherit the implementation rationale. Address confirmed findings; if the only correct fix",
            "exceeds current scope or authorization, stop and report the required change instead of adding",
            "a catch, fallback, compatibility path, or parallel API.",
        ]
    )
    return "\n".join(lines)


def handle_event(
    payload: dict[str, object],
    *,
    agent: str,
    state_dir: Path = DEFAULT_STATE_DIR,
) -> dict[str, str] | None:
    event = str(payload.get("hook_event_name", ""))
    session_id = str(payload.get("session_id", ""))
    cwd_value = payload.get("cwd")
    if not session_id or not isinstance(cwd_value, str):
        return None

    cwd = Path(cwd_value)
    state_path = _state_path(state_dir, session_id, cwd)

    if event == "PreToolUse":
        with _state_lock(state_path):
            if state_path.exists():
                return None
            _collect_garbage(state_dir)
            root, base_revision = resolve_base_revision(cwd)
            if root is not None and base_revision is not None:
                _, findings = scan_worktree(cwd, base_revision)
                _write_state(
                    state_path,
                    root=root,
                    base_revision=base_revision,
                    findings=findings,
                )
        return None

    if event != "Stop":
        return None

    state = _read_state(state_path)
    if state is None:
        _remove_state(state_path)
        return None
    if _is_true(payload.get("stop_hook_active")):
        _remove_state(state_path)
        return None

    baseline_root, base_revision, baseline_findings = state
    current_root, current_findings = scan_worktree(cwd, base_revision)
    if current_root is None or current_root != baseline_root:
        _remove_state(state_path)
        return None

    introduced = introduced_findings(baseline_findings, current_findings)
    if not introduced:
        _remove_state(state_path)
        return None

    return {"decision": "block", "reason": _review_reason(agent, introduced)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=("codex", "claude"), required=True)
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path(os.environ.get("DESIGN_INTEGRITY_STATE_DIR", DEFAULT_STATE_DIR)),
    )
    args = parser.parse_args()

    try:
        payload = json.load(sys.stdin)
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0

    result = handle_event(payload, agent=args.agent, state_dir=args.state_dir)
    if result is not None:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
