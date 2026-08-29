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
ACCEPTANCE_PARTS = {
    "acceptance",
    "autoresearch",
    "benchmark",
    "benchmarks",
    "eval",
    "evals",
    "golden",
    "grader",
    "graders",
    "harness",
    "oracle",
}
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
DIFF_PATH_RE = re.compile(r"^diff --git a/(.+) b/(.+)$")
EXCEPTION_RE = re.compile(
    r"(?:^|[;}])\s*catch\b[^{;]*\{"                # catch 子句（含 } catch、单行 try{..}catch、Swift catch let e {），要求同行出现 {
    r"|^\s*(?:\}\s*)?catch\s*(?:\([^)]*\))?\s*$"   # Allman 风格：catch(...) 或 catch 独占一行，{ 在下一行
    r"|\.catch\s*\("                               # promise/方法链 .catch(
    r"|^\s*except\*?(?:\s+[^:]+)?\s*:"             # Python except / except*（3.11 exception groups）
    r"|^\s*rescue(?:\s+.*)?$"                     # Ruby rescue 子句（独占一行，含 rescue => e / rescue SomeError）
    r"|^[^#]*\brescue\s+(?:nil|false|true|\{\}|\[\]|[A-Za-z_]\w*(?:\s*\([^)]*\))?)\s*;?(?:\s*#.*)?$"  # Ruby 后缀 rescue：expr rescue nil / {} / fallback
)
EXCEPTION_BODY_RE = re.compile(
    r"(?:^|[;}])\s*catch\b[^{;]*\{"                # 带花括号的 catch 子句
    r"|^\s*(?:\}\s*)?catch\s*(?:\([^)]*\))?\s*$"   # Allman 风格 catch，花括号在下一行
    r"|^\s*except\*?(?:\s+[^:]+)?\s*:"             # Python except / except*
    r"|^\s*rescue(?:\s+.*)?$"                     # Ruby 独占一行的 rescue 子句
)
BROAD_EXCEPTION_RE = re.compile(
    r"^\s*except\*?\s*(?::|(?:Exception|BaseException)(?:\s+as\s+\w+)?\s*:)",
)
FALLBACK_RE = re.compile(
    r"\b\w*fall_?back\w*\s*(?:\(|\.|\[|=(?!=))"   # 调用/属性链/下标/赋值/kwarg：fallback(、fallbackClient.、fallback_client =、fallback=True
    r"|\.\w*fall_?back\w*\b",                     # 属性读取：client.fallback
    re.IGNORECASE,
)
PARALLEL_API_RE = re.compile(
    r"\b(?:def|function|class|func|fn|fun)\s+"
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
class DiffLine:
    path: str
    line: int
    text: str
    added: bool


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


def _parse_diff_lines(diff: str) -> list[DiffLine]:
    parsed: list[DiffLine] = []
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
            parsed.append(DiffLine(current_path, new_line, raw_line[1:], True))
            new_line += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            continue
        elif raw_line.startswith("\\ No newline"):
            continue
        else:
            text = raw_line[1:] if raw_line.startswith(" ") else raw_line
            parsed.append(DiffLine(current_path, new_line, text, False))
            new_line += 1

    return parsed


def parse_unified_diff(diff: str) -> list[AddedLine]:
    return [
        AddedLine(line.path, line.line, line.text)
        for line in _parse_diff_lines(diff)
        if line.added
    ]


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


def changed_paths_from_diff(diff: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for raw_line in diff.splitlines():
        if raw_line.startswith("+++ b/"):
            path = raw_line[6:]
        else:
            match = DIFF_PATH_RE.match(raw_line)
            if not match:
                continue
            path = match.group(2)
        if path == "/dev/null" or path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def _is_acceptance_path(path: str) -> bool:
    parts = {part.lower() for part in PurePosixPath(path).parts}
    if parts & ACCEPTANCE_PARTS:
        return True
    name = PurePosixPath(path).name.lower()
    return any(
        token in name
        for token in (
            "_acceptance",
            "_autoresearch",
            "_benchmark",
            "_eval",
            "_golden",
            "_grader",
            "_harness",
            "_oracle",
        )
    )


def acceptance_paths_from_diff(diff: str) -> list[str]:
    return [path for path in changed_paths_from_diff(diff) if _is_acceptance_path(path)]


def requires_acceptance_review(diff: str) -> bool:
    """Return whether a diff belongs to a high-risk acceptance surface.

    This deliberately routes only explicit evaluation surfaces. Ordinary unit-test
    edits remain covered by evidence-first testing without starting a model review;
    callers can invoke the acceptance skill explicitly for other behavioral work.
    """
    return bool(acceptance_paths_from_diff(diff))


def _is_comment_line(text: str) -> bool:
    # C `*ptr = ...` dereference assignments are skipped, matching swallow-scan's `*` prefix rule.
    stripped = text.strip()
    return stripped.startswith(("#", "//", "/*", "*"))


def _indentation(text: str) -> int:
    return len(text) - len(text.lstrip())


def scan_added_lines(lines: Iterable[AddedLine]) -> list[Finding]:
    return _scan_diff_lines(
        DiffLine(line.path, line.line, line.text, True) for line in lines
    )


def _scan_diff_lines(lines: Iterable[DiffLine]) -> list[Finding]:
    source_lines = [line for line in lines if is_reviewable_source(line.path)]
    added_lines = [
        line
        for line in source_lines
        if line.added and not _is_comment_line(line.text)
    ]
    context_lines = [
        line
        for line in source_lines
        if not line.added and not _is_comment_line(line.text)
    ]
    findings: list[Finding] = []
    seen: set[tuple[str, int, str]] = set()

    def add(line: DiffLine, kind: str, text: str | None = None) -> None:
        if not line.added:
            return
        key = (line.path, line.line, kind)
        if key in seen:
            return
        seen.add(key)
        findings.append(Finding(line.path, line.line, kind, text or line.text.strip()))

    exception_lines: list[DiffLine] = []
    for line in added_lines:
        if EXCEPTION_RE.search(line.text):
            add(line, "exception-boundary")
        if EXCEPTION_BODY_RE.search(line.text):
            exception_lines.append(line)
        if BROAD_EXCEPTION_RE.search(line.text):
            add(line, "broad-exception")
        if INLINE_SWALLOW_RE.search(line.text):
            add(line, "swallowed-exception")
        if FALLBACK_RE.search(line.text):
            add(line, "fallback-marker")
        if PARALLEL_API_RE.search(line.text):
            add(line, "parallel-api-name")

    # Context lines are used only to locate an existing exception boundary around
    # newly added handling code; they never become findings themselves.
    for line in context_lines:
        if EXCEPTION_BODY_RE.search(line.text):
            exception_lines.append(line)

    by_path: dict[str, list[DiffLine]] = {}
    for line in source_lines:
        by_path.setdefault(line.path, []).append(line)
    for path_lines in by_path.values():
        path_lines.sort(key=lambda item: item.line)

    for boundary in exception_lines:
        saw_substantive_statement = False
        indentation_block = boundary.path.lower().endswith((".py", ".rb"))
        boundary_indent = _indentation(boundary.text)
        for candidate in by_path[boundary.path]:
            if candidate.line <= boundary.line:
                continue
            if candidate.line > boundary.line + 5:
                break
            stripped = candidate.text.strip()
            if not stripped:
                continue
            if stripped == "}":
                if candidate.added and not saw_substantive_statement:
                    add(candidate, "swallowed-exception")
                break
            if not candidate.added:
                if (
                    indentation_block
                    and _indentation(candidate.text) <= boundary_indent
                ):
                    break
                continue
            if indentation_block and _indentation(candidate.text) <= boundary_indent:
                break
            if stripped == "pass":
                add(candidate, "swallowed-exception")
            if DEFAULT_RETURN_RE.match(stripped):
                add(candidate, "default-after-catch")
            if not stripped.startswith(("#", "//", "/*", "*")):
                saw_substantive_statement = True

    return sorted(findings, key=lambda finding: (finding.path, finding.line, finding.kind))


def scan_unified_diff(diff: str) -> list[Finding]:
    return _scan_diff_lines(_parse_diff_lines(diff))


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
        "--unified=5",
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
