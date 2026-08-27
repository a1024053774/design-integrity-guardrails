#!/usr/bin/env python3
"""Find newly added code constructs that require design-integrity review."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".m",
    ".mm",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
}
TEST_PARTS = {"__tests__", "fixture", "fixtures", "spec", "specs", "test", "tests"}
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
EXCEPTION_RE = re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{?|^\s*except(?:\s|:)")
BROAD_EXCEPTION_RE = re.compile(
    r"^\s*except\s*(?::|(?:Exception|BaseException)(?:\s+as\s+\w+)?\s*:)",
)
FALLBACK_RE = re.compile(r"\bfall[\s_-]?back\b|\bfallback\w*", re.IGNORECASE)
PARALLEL_API_RE = re.compile(
    r"\b(?:def|function|class|func)\s+"
    r"[A-Za-z_]\w*(?:_v\d+|_new|_safe|_fallback|_or_default|_compat|_legacy|"
    r"V\d+|New|Safe|WithFallback|OrDefault|Compat|Legacy)\b",
)
INLINE_SWALLOW_RE = re.compile(
    r"(?:catch\s*(?:\([^)]*\))?\s*\{\s*\}|except[^:]*:\s*pass\b)",
)
DEFAULT_RETURN_RE = re.compile(
    r"^return\s+(?:None|null|nil|false|true|0|[\"']{2}|\[\]|\{\})\s*;?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AddedLine:
    path: str
    line: int
    text: str


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    text: str

    @property
    def signature(self) -> tuple[str, str, str]:
        return (self.path, self.kind, " ".join(self.text.split()))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "Finding":
        return cls(
            path=str(value["path"]),
            line=int(value["line"]),
            kind=str(value["kind"]),
            text=str(value["text"]),
        )


def parse_unified_diff(diff: str) -> list[AddedLine]:
    added: list[AddedLine] = []
    current_path: str | None = None
    new_line: int | None = None

    for raw_line in diff.splitlines():
        if raw_line.startswith("+++ "):
            path = raw_line[4:]
            if path == "/dev/null":
                current_path = None
            else:
                current_path = path[2:] if path.startswith("b/") else path
            new_line = None
            continue

        hunk_match = HUNK_RE.match(raw_line)
        if hunk_match:
            new_line = int(hunk_match.group(1))
            continue

        if current_path is None or new_line is None:
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            added.append(AddedLine(current_path, new_line, raw_line[1:]))
            new_line += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            continue
        elif raw_line.startswith("\\ No newline"):
            continue
        else:
            new_line += 1

    return added


def is_reviewable_source(path: str) -> bool:
    posix_path = PurePosixPath(path)
    lowered_parts = {part.lower() for part in posix_path.parts}
    name = posix_path.name.lower()

    if lowered_parts & TEST_PARTS:
        return False
    if name.startswith("test_") or name.endswith("_test.py") or name.endswith("_test.go"):
        return False
    if ".test." in name or ".spec." in name:
        return False
    return posix_path.suffix.lower() in SOURCE_SUFFIXES


def scan_added_lines(lines: Iterable[AddedLine]) -> list[Finding]:
    source_lines = [line for line in lines if is_reviewable_source(line.path)]
    findings: list[Finding] = []
    seen: set[tuple[str, int, str]] = set()

    def add(line: AddedLine, kind: str, text: str | None = None) -> None:
        key = (line.path, line.line, kind)
        if key in seen:
            return
        seen.add(key)
        findings.append(Finding(line.path, line.line, kind, text or line.text.strip()))

    exception_lines: list[AddedLine] = []
    for line in source_lines:
        stripped = line.text.strip()
        if EXCEPTION_RE.search(line.text):
            exception_lines.append(line)
            add(line, "exception-boundary")
        if BROAD_EXCEPTION_RE.search(line.text):
            add(line, "broad-exception")
        if INLINE_SWALLOW_RE.search(line.text):
            add(line, "swallowed-exception")
        if FALLBACK_RE.search(line.text):
            add(line, "fallback-marker")
        if PARALLEL_API_RE.search(line.text):
            add(line, "parallel-api-name")

    by_path: dict[str, list[AddedLine]] = {}
    for line in source_lines:
        by_path.setdefault(line.path, []).append(line)
    for path_lines in by_path.values():
        path_lines.sort(key=lambda item: item.line)

    for boundary in exception_lines:
        saw_substantive_statement = False
        for candidate in by_path[boundary.path]:
            if candidate.line <= boundary.line:
                continue
            if candidate.line > boundary.line + 5:
                break
            stripped = candidate.text.strip()
            if not stripped:
                continue
            if stripped == "}":
                if not saw_substantive_statement:
                    add(candidate, "swallowed-exception")
                break
            if stripped == "pass":
                add(candidate, "swallowed-exception")
            if DEFAULT_RETURN_RE.match(stripped):
                add(candidate, "default-after-catch")
            if not stripped.startswith(("#", "//", "/*", "*")):
                saw_substantive_statement = True

    return sorted(findings, key=lambda finding: (finding.path, finding.line, finding.kind))


def scan_unified_diff(diff: str) -> list[Finding]:
    return scan_added_lines(parse_unified_diff(diff))


def introduced_findings(
    baseline: Iterable[Finding],
    current: Iterable[Finding],
) -> list[Finding]:
    remaining = Counter(finding.signature for finding in baseline)
    introduced: list[Finding] = []
    for finding in current:
        if remaining[finding.signature] > 0:
            remaining[finding.signature] -= 1
        else:
            introduced.append(finding)
    return introduced


def _run_git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=root,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _git_root(cwd: Path) -> Path | None:
    result = _run_git(cwd, "rev-parse", "--show-toplevel", check=False)
    if result.returncode != 0:
        return None
    return Path(result.stdout.decode("utf-8", errors="replace").strip())


def _base_revision(root: Path) -> str:
    head = _run_git(root, "rev-parse", "--verify", "HEAD", check=False)
    if head.returncode == 0:
        return head.stdout.decode("utf-8", errors="replace").strip()

    empty_tree = subprocess.run(
        ["git", "mktree"],
        cwd=root,
        check=True,
        input=b"",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return empty_tree.stdout.decode("utf-8", errors="replace").strip()


def resolve_base_revision(cwd: Path) -> tuple[Path | None, str | None]:
    root = _git_root(cwd)
    if root is None:
        return None, None
    return root, _base_revision(root)


def _synthetic_untracked_diff(root: Path, paths: Iterable[str]) -> str:
    chunks: list[str] = []
    for relative_path in paths:
        path = root / relative_path
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if len(data) > 1_000_000 or b"\x00" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        chunks.extend(
            [
                f"diff --git a/{relative_path} b/{relative_path}",
                "--- /dev/null",
                f"+++ b/{relative_path}",
                f"@@ -0,0 +1,{len(lines)} @@",
                *(f"+{line}" for line in lines),
            ]
        )
    return "\n".join(chunks)


def collect_worktree_diff(
    cwd: Path,
    base_revision: str | None = None,
) -> tuple[Path | None, str]:
    root = _git_root(cwd)
    if root is None:
        return None, ""

    comparison_base = base_revision or _base_revision(root)
    tracked = _run_git(
        root,
        "diff",
        "--no-ext-diff",
        "--no-color",
        "--unified=0",
        comparison_base,
        "--",
    ).stdout.decode("utf-8", errors="replace")
    untracked_bytes = _run_git(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    ).stdout

    untracked = [
        value.decode("utf-8", errors="replace")
        for value in untracked_bytes.split(b"\0")
        if value
    ]
    synthetic = _synthetic_untracked_diff(root, untracked)
    return root, "\n".join(part for part in (tracked.rstrip(), synthetic) if part)


def scan_worktree(
    cwd: Path,
    base_revision: str | None = None,
) -> tuple[Path | None, list[Finding]]:
    root, diff = collect_worktree_diff(cwd, base_revision)
    return root, scan_unified_diff(diff)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args()

    root, findings = scan_worktree(args.cwd)
    if args.format == "json":
        print(
            json.dumps(
                {
                    "root": str(root) if root else None,
                    "findings": [finding.to_dict() for finding in findings],
                },
                ensure_ascii=False,
            )
        )
    else:
        for finding in findings:
            print(f"{finding.path}:{finding.line}: {finding.kind}: {finding.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
