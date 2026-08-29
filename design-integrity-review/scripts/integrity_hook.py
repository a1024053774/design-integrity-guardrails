#!/usr/bin/env python3
"""Lifecycle hook that requests fresh review for newly introduced risk markers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

try:  # POSIX (macOS/Linux)
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - exercised on Windows
    _fcntl = None

try:  # Windows
    import msvcrt as _msvcrt
except ImportError:  # pragma: no cover - exercised on POSIX
    _msvcrt = None

from design_integrity import (
    Finding,
    acceptance_paths_from_diff,
    collect_worktree_diff,
    introduced_findings,
    resolve_base_revision,
    scan_unified_diff,
)


DEFAULT_STATE_DIR = Path(tempfile.gettempdir()) / "design-integrity-review"
STATE_TTL_SECONDS = 48 * 60 * 60
# One initial review plus at most one targeted re-review.
MAX_REVIEW_EPOCHS = 2


@dataclass
class HookState:
    root: Path
    base_revision: str
    turn_id: str
    baseline_findings: list[Finding]
    baseline_acceptance_paths: list[str]
    blocked_risk_signatures: list[tuple[str, str, str]]
    blocked_acceptance_paths: list[str]
    review_epochs: int


def _state_path(state_dir: Path, session_id: str, cwd: Path) -> Path:
    identity = f"{session_id}\0{cwd.resolve()}".encode("utf-8", errors="replace")
    return state_dir / f"{hashlib.sha256(identity).hexdigest()}.json"


def _write_state(
    path: Path,
    *,
    root: Path,
    base_revision: str,
    turn_id: str = "",
    findings: list[Finding],
    baseline_acceptance_paths: list[str] | None = None,
    blocked_risk_signatures: list[tuple[str, str, str]] | None = None,
    blocked_acceptance_paths: list[str] | None = None,
    review_epochs: int = 0,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "root": str(root),
        "base_revision": base_revision,
        "turn_id": turn_id,
        "findings": [finding.to_dict() for finding in findings],
        "baseline_acceptance_paths": sorted(set(baseline_acceptance_paths or [])),
        "blocked_risk_signatures": [
            list(signature) for signature in (blocked_risk_signatures or [])
        ],
        "blocked_acceptance_paths": sorted(set(blocked_acceptance_paths or [])),
        "review_epochs": review_epochs,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _read_state(path: Path) -> HookState | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        blocked_signatures = []
        raw_signatures = payload.get("blocked_risk_signatures")
        if raw_signatures is None:
            # Read states written by the previous epoch implementation.
            raw_signatures = payload.get("blocked_risk_keys", [])
        for item in raw_signatures:
            if isinstance(item, list) and len(item) == 3:
                blocked_signatures.append(
                    (str(item[0]), str(item[1]), str(item[2]))
                )
            elif isinstance(item, list) and len(item) == 2:
                blocked_signatures.append((str(item[0]), str(item[1]), ""))
        return HookState(
            root=Path(payload["root"]),
            base_revision=str(payload["base_revision"]),
            turn_id=str(payload.get("turn_id", "")),
            baseline_findings=[
                Finding.from_dict(item) for item in payload["findings"]
            ],
            baseline_acceptance_paths=[
                str(item) for item in payload.get("baseline_acceptance_paths", [])
            ],
            blocked_risk_signatures=blocked_signatures,
            blocked_acceptance_paths=[
                str(item) for item in payload.get("blocked_acceptance_paths", [])
            ],
            review_epochs=int(payload.get("review_epochs", 0)),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _remove_state(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _risk_signatures(findings: list[Finding]) -> list[tuple[str, str, str]]:
    return sorted({finding.signature for finding in findings})


def _has_pending_review(state: HookState) -> bool:
    return bool(state.blocked_risk_signatures or state.blocked_acceptance_paths)


def _scan_current(
    cwd: Path,
    base_revision: str,
) -> tuple[Path | None, list[Finding], list[str]]:
    """Collect one diff and derive both review routes from it."""
    root, diff = collect_worktree_diff(cwd, base_revision)
    return root, scan_unified_diff(diff), acceptance_paths_from_diff(diff)


def _collect_garbage(state_dir: Path) -> None:
    """Delete state files whose mtime is older than STATE_TTL_SECONDS.

    The normal Stop path does not unlink the sibling .lock: unlinking a file
    another process may already be waiting on would create two inodes and two
    lock domains, breaking mutual exclusion. Collecting after 48h is safe
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
        if _fcntl is not None:
            _fcntl.flock(lock_file.fileno(), _fcntl.LOCK_EX)

            def unlock() -> None:
                _fcntl.flock(lock_file.fileno(), _fcntl.LOCK_UN)

        elif _msvcrt is not None:
            # msvcrt.locking locks one byte at the current file position. Keep
            # the byte present and always seek back to make lock/unlock target
            # the same range on Windows. LK_LOCK waits in bounded one-second
            # intervals, which fits the hook's ten-second command timeout.
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            _msvcrt.locking(lock_file.fileno(), _msvcrt.LK_LOCK, 1)

            def unlock() -> None:
                lock_file.seek(0)
                _msvcrt.locking(lock_file.fileno(), _msvcrt.LK_UNLCK, 1)

        else:  # pragma: no cover - every supported platform has one backend
            raise RuntimeError("no supported file-lock backend")

        os.utime(lock_path)
        try:
            yield
        finally:
            unlock()


def _is_true(value: object) -> bool:
    return value is True or (isinstance(value, str) and value.lower() == "true")


def _review_reason(
    agent: str,
    findings: list[Finding],
    *,
    acceptance_paths: list[str],
    review_epoch: int,
) -> str:
    invocation = (
        "$design-integrity-review"
        if agent == "codex"
        else "/design-integrity-review"
    )
    shown = findings[:8]
    if findings:
        lines = [
            "Design-integrity gate found code-risk markers introduced after this turn's baseline:",
            *(
                f"- {finding.path}:{finding.line} [{finding.kind}] {finding.text}"
                for finding in shown
            ),
        ]
    else:
        lines = ["Acceptance-integrity gate found an evaluation surface changed this turn:"]
    if acceptance_paths:
        lines.append("- acceptance paths: " + ", ".join(acceptance_paths[:8]))
        if len(acceptance_paths) > 8:
            lines.append(f"- ... and {len(acceptance_paths) - 8} more paths")
    if len(findings) > len(shown):
        lines.append(f"- ... and {len(findings) - len(shown)} more")
    lines.extend(
        [
            "",
            f"Review epoch {review_epoch}/{MAX_REVIEW_EPOCHS}. Before finishing, invoke {invocation} exactly once.",
            "The skill routes acceptance-risk changes to the read-only acceptance-auditor; do not start",
            "a second reviewer. Freeze the candidate while reviewing. If the correct fix exceeds scope,",
            "report INCOMPLETE instead of adding a catch, fallback, compatibility path, or parallel API.",
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
    raw_turn_id = payload.get("turn_id")
    turn_id = raw_turn_id if isinstance(raw_turn_id, str) else ""
    cwd_value = payload.get("cwd")
    if not session_id or not isinstance(cwd_value, str):
        return None

    cwd = Path(cwd_value)
    state_path = _state_path(state_dir, session_id, cwd)

    if event == "PreToolUse":
        with _state_lock(state_path):
            if state_path.exists():
                state = _read_state(state_path)
                if state is None:
                    _remove_state(state_path)
                elif (
                    turn_id
                    and turn_id != state.turn_id
                    and not _has_pending_review(state)
                ):
                    # A completed epoch must not spend the next user's review
                    # budget. Capture a fresh baseline before the new tool runs.
                    root, base_revision = resolve_base_revision(cwd)
                    if root is not None and base_revision is not None:
                        _, findings, acceptance_paths = _scan_current(cwd, base_revision)
                        _write_state(
                            state_path,
                            root=root,
                            base_revision=base_revision,
                            turn_id=turn_id,
                            findings=findings,
                            baseline_acceptance_paths=acceptance_paths,
                        )
                    else:
                        _remove_state(state_path)
                else:
                    # Keep an unresolved review across a turn change; dropping
                    # it here would let an interrupted candidate bypass the gate.
                    return None
            if not state_path.exists():
                _collect_garbage(state_dir)
                root, base_revision = resolve_base_revision(cwd)
                if root is not None and base_revision is not None:
                    _, findings, acceptance_paths = _scan_current(cwd, base_revision)
                    _write_state(
                        state_path,
                        root=root,
                        base_revision=base_revision,
                        turn_id=turn_id,
                        findings=findings,
                        baseline_acceptance_paths=acceptance_paths,
                    )
        return None

    if event != "Stop":
        return None

    with _state_lock(state_path):
        state = _read_state(state_path)
        if state is None:
            _remove_state(state_path)
            return None

        active = _is_true(payload.get("stop_hook_active"))
        if (
            turn_id
            and turn_id != state.turn_id
            and not _has_pending_review(state)
            and not active
        ):
            # Normally PreToolUse has already reset the baseline. This fallback
            # handles a turn that had no matching tool event without discarding
            # edits made since the previously acknowledged candidate.
            state = HookState(
                root=state.root,
                base_revision=state.base_revision,
                turn_id=turn_id,
                baseline_findings=state.baseline_findings,
                baseline_acceptance_paths=state.baseline_acceptance_paths,
                blocked_risk_signatures=[],
                blocked_acceptance_paths=[],
                review_epochs=0,
            )
            _write_state(
                state_path,
                root=state.root,
                base_revision=state.base_revision,
                turn_id=turn_id,
                findings=state.baseline_findings,
                baseline_acceptance_paths=state.baseline_acceptance_paths,
                review_epochs=0,
            )

        current_root, current_findings, current_acceptance_paths = _scan_current(
            cwd, state.base_revision
        )
        if current_root is None or current_root != state.root:
            _remove_state(state_path)
            return None

        introduced = introduced_findings(state.baseline_findings, current_findings)
        new_acceptance_paths = sorted(
            set(current_acceptance_paths) - set(state.baseline_acceptance_paths)
        )
        if not introduced and not new_acceptance_paths:
            _remove_state(state_path)
            return None

        current_risk_signatures = set(_risk_signatures(introduced))
        blocked_risk_signatures = set(state.blocked_risk_signatures)
        blocked_acceptance_paths = set(state.blocked_acceptance_paths)
        has_pending_epoch = bool(
            blocked_risk_signatures or blocked_acceptance_paths
        )
        new_risk_signatures = current_risk_signatures - blocked_risk_signatures
        new_acceptance_scope = set(new_acceptance_paths) - blocked_acceptance_paths

        # A Stop continuation for the same risk scope acknowledges that epoch.
        # Advance the baseline so later edits in the same turn can be compared
        # against the latest acknowledged version instead of replaying old risks.
        if (
            has_pending_epoch
            and not new_risk_signatures
            and not new_acceptance_scope
        ):
            if active:
                _write_state(
                    state_path,
                    root=state.root,
                    base_revision=state.base_revision,
                    turn_id=turn_id or state.turn_id,
                    findings=current_findings,
                    baseline_acceptance_paths=current_acceptance_paths,
                    review_epochs=state.review_epochs,
                )
            return None

        # Preserve the old safety behavior for an unexpected active continuation
        # without a recorded block (for example, a state file from an older hook).
        if active and not has_pending_epoch:
            _remove_state(state_path)
            return None

        if state.review_epochs >= MAX_REVIEW_EPOCHS:
            _write_state(
                state_path,
                root=state.root,
                base_revision=state.base_revision,
                turn_id=turn_id or state.turn_id,
                findings=state.baseline_findings,
                baseline_acceptance_paths=state.baseline_acceptance_paths,
                blocked_risk_signatures=_risk_signatures(introduced),
                blocked_acceptance_paths=new_acceptance_paths,
                review_epochs=state.review_epochs,
            )
            return {
                "decision": "block",
                "reason": (
                    f"Automatic review budget exhausted after {MAX_REVIEW_EPOCHS} epochs. "
                    "Report INCOMPLETE or request an explicit additional review; do not "
                    "spawn another reviewer automatically."
                ),
            }

        review_epoch = state.review_epochs + 1
        _write_state(
            state_path,
            root=state.root,
            base_revision=state.base_revision,
            turn_id=turn_id or state.turn_id,
            findings=state.baseline_findings,
            baseline_acceptance_paths=state.baseline_acceptance_paths,
            blocked_risk_signatures=_risk_signatures(introduced),
            blocked_acceptance_paths=new_acceptance_paths,
            review_epochs=review_epoch,
        )
        return {
            "decision": "block",
            "reason": _review_reason(
                agent,
                introduced,
                acceptance_paths=new_acceptance_paths,
                review_epoch=review_epoch,
            ),
        }


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
