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
REVIEW_FILE = "REVIEW.md"
ACCEPTANCE_HEADING_RE = re.compile(r"^#{1,6}\s+acceptance surfaces\s*$", re.IGNORECASE)
HEADING_RE = re.compile(r"^#{1,6}\s")
GLOB_ITEM_RE = re.compile(r"^\s*[-*+]\s+(?:`([^`]+)`|(\S+))")
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
            for path in match.groups():
                if path != "/dev/null" and path not in seen:
                    seen.add(path)
                    paths.append(path)
            continue
        if path == "/dev/null" or path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def parse_acceptance_globs(review_text: str) -> list[str] | None:
    """Return the globs listed under the ``Acceptance surfaces`` heading of REVIEW.md.

    ``None`` means the file has no such section, so the directory convention applies.
    An empty list means the owner declared that the repository has no acceptance
    surface. Only list items whose first token is in backticks or looks like a path
    (contains ``/``, ``*``, or ``.``) count; a prose bullet is not a glob.
    """
    globs: list[str] | None = None
    for raw_line in review_text.splitlines():
        if ACCEPTANCE_HEADING_RE.match(raw_line.strip()):
            globs = []
            continue
        if globs is None:
            continue
        if HEADING_RE.match(raw_line):
            break
        match = GLOB_ITEM_RE.match(raw_line)
        if not match:
            continue
        token = match.group(1) or match.group(2)
        if match.group(1) or any(mark in token for mark in "/*."):
            globs.append(token.strip())
    return globs


def load_acceptance_globs(root: Path) -> list[str] | None:
    review = root / REVIEW_FILE
    if not review.is_file():
        return None
    return parse_acceptance_globs(review.read_text(encoding="utf-8"))


def _glob_regex(glob: str) -> re.Pattern[str]:
    """Translate a REVIEW.md glob: ``**`` crosses directories, ``*`` and ``?`` do not.

    A glob without a wildcard names a file or a directory, so it also matches
    everything below it; a trailing ``/`` means the same.
    """
    pattern = glob[2:] if glob.startswith("./") else glob
    pattern = pattern.lstrip("/")
    if pattern.endswith("/"):
        pattern = pattern.rstrip("/")
        has_wildcard = False
    else:
        has_wildcard = any(mark in pattern for mark in "*?")
    out: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif pattern[index] == "*":
            out.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            out.append("[^/]")
            index += 1
        else:
            out.append(re.escape(pattern[index]))
            index += 1
    suffix = r"\Z" if has_wildcard else r"(?:/.*)?\Z"
    return re.compile("".join(out) + suffix)


def _is_acceptance_path(path: str, globs: list[str] | None = None) -> bool:
    # REVIEW.md declares what is frozen, so editing it is itself a requirement change;
    # otherwise an agent could drop a glob and then edit the test it protected.
    if path == REVIEW_FILE:
        return True
    if globs is not None:
        return any(_glob_regex(glob).match(path) for glob in globs)
    parts = {part.lower() for part in PurePosixPath(path).parts}
    # A conventional directory is an explicit repository routing policy. A
    # filename such as ``model_acceptance.py`` is not enough to establish that
    # the file is an evaluation surface.
    return bool(parts & ACCEPTANCE_PARTS)


def acceptance_paths_from_diff(diff: str, globs: list[str] | None = None) -> list[str]:
    """Changed paths that are acceptance surfaces.

    ``globs`` comes from REVIEW.md and replaces the directory convention when given.
    """
    return [path for path in changed_paths_from_diff(diff) if _is_acceptance_path(path, globs)]


def requires_acceptance_review(diff: str, globs: list[str] | None = None) -> bool:
    """Return whether a diff touches an acceptance surface.

    Without REVIEW.md, automatic routing is limited to conventional
    evaluation-directory components. Ordinary unit-test edits remain covered by
    evidence-first testing without starting a model review.
    """
    return bool(acceptance_paths_from_diff(diff, globs))


def _indentation(text: str) -> int:
    return len(text) - len(text.lstrip())


@dataclass
class _LexicalState:
    """State needed to ignore literals and block comments across diff lines."""

    quote: str | None = None
    block_comment: str | None = None
    escaped: bool = False


def _mask_non_code(text: str, state: _LexicalState, suffix: str) -> str:
    """Replace literals/comments with spaces while preserving positions.

    The scanner is a diff router, not a language parser. It still must avoid treating
    prose, log messages, or fixture values as executable structure. This small lexer
    handles the string/comment forms shared by the supported source languages and
    carries block state across adjacent diff lines.
    """

    c_like = suffix.lower() in {
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
        ".rs",
        ".scala",
        ".swift",
        ".ts",
        ".tsx",
    }
    hash_comments = suffix.lower() in {".py", ".rb", ".sh"}
    quote = state.quote
    block_comment = state.block_comment
    result: list[str] = []
    index = 0

    while index < len(text):
        if block_comment:
            end = text.find(block_comment, index)
            if end < 0:
                result.extend(" " for _ in text[index:])
                return "".join(result)
            result.extend(" " for _ in text[index : end + len(block_comment)])
            index = end + len(block_comment)
            block_comment = None
            state.block_comment = None
            continue

        if quote:
            delimiter = quote
            while index < len(text):
                if state.escaped:
                    result.append(" ")
                    state.escaped = False
                    index += 1
                elif text[index] == "\\":
                    result.append(" ")
                    state.escaped = True
                    index += 1
                elif text.startswith(delimiter, index):
                    result.extend(" " for _ in delimiter)
                    index += len(delimiter)
                    quote = None
                    state.quote = None
                    break
                else:
                    result.append(" ")
                    index += 1
            if quote:
                return "".join(result)
            continue

        if c_like and text.startswith("/*", index):
            block_comment = "*/"
            state.block_comment = block_comment
            result.extend("  ")
            index += 2
            continue
        if c_like and text.startswith("//", index):
            result.extend(" " for _ in text[index:])
            break
        if hash_comments and text[index] == "#":
            result.extend(" " for _ in text[index:])
            break

        delimiter: str | None = None
        if text.startswith("'''", index) or text.startswith('"""', index):
            delimiter = text[index : index + 3]
        elif text[index] in {"'", '"'} or (c_like and text[index] == "`"):
            delimiter = text[index]
        if delimiter:
            quote = delimiter
            state.quote = delimiter
            result.extend(" " for _ in delimiter)
            index += len(delimiter)
            continue

        result.append(text[index])
        index += 1

    return "".join(result)


def scan_added_lines(lines: Iterable[AddedLine]) -> list[Finding]:
    return _scan_diff_lines(
        DiffLine(line.path, line.line, line.text, True) for line in lines
    )


def _scan_diff_lines(lines: Iterable[DiffLine]) -> list[Finding]:
    source_lines = [line for line in lines if is_reviewable_source(line.path)]
    by_path: dict[str, list[DiffLine]] = {}
    for line in source_lines:
        by_path.setdefault(line.path, []).append(line)
    for path_lines in by_path.values():
        path_lines.sort(key=lambda item: item.line)

    code_text: dict[int, str] = {}
    for path, path_lines in by_path.items():
        state = _LexicalState()
        previous_line: int | None = None
        suffix = PurePosixPath(path).suffix
        for line in path_lines:
            if previous_line is not None and line.line > previous_line + 1:
                # A diff hunk omits the lines between these entries; do not carry a
                # quote/comment state through unknown source.
                state = _LexicalState()
            code_text[id(line)] = _mask_non_code(line.text, state, suffix)
            previous_line = line.line

    added_lines = [
        line
        for line in source_lines
        if line.added and code_text[id(line)].strip()
    ]
    context_lines = [
        line
        for line in source_lines
        if not line.added and code_text[id(line)].strip()
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
        code = code_text[id(line)]
        if EXCEPTION_RE.search(code):
            add(line, "exception-boundary")
        if EXCEPTION_BODY_RE.search(code):
            exception_lines.append(line)
        if BROAD_EXCEPTION_RE.search(code):
            add(line, "broad-exception")
        if INLINE_SWALLOW_RE.search(code):
            add(line, "swallowed-exception")

    # Context lines are used only to locate an existing exception boundary around
    # newly added handling code; they never become findings themselves.
    for line in context_lines:
        if EXCEPTION_BODY_RE.search(code_text[id(line)]):
            exception_lines.append(line)

    for boundary in exception_lines:
        saw_substantive_statement = False
        indentation_block = boundary.path.lower().endswith((".py", ".rb"))
        boundary_indent = _indentation(boundary.text)
        for candidate in by_path[boundary.path]:
            if candidate.line <= boundary.line:
                continue
            if candidate.line > boundary.line + 5:
                break
            stripped = code_text[id(candidate)].strip()
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
    parser.add_argument(
        "--base",
        help="revision to compare the working tree with, such as the commit the session "
        "started from (default: HEAD, which cannot see changes already committed)",
    )
    args = parser.parse_args()

    root, diff = collect_worktree_diff(args.cwd, args.base)
    findings = scan_unified_diff(diff)
    globs = load_acceptance_globs(root) if root else None
    acceptance = acceptance_paths_from_diff(diff, globs)
    source = REVIEW_FILE if globs is not None else "directory convention"
    if args.format == "json":
        print(
            json.dumps(
                {
                    "root": str(root) if root else None,
                    "base": args.base or "HEAD",
                    "findings": [finding.to_dict() for finding in findings],
                    "acceptance_changes": acceptance,
                    "acceptance_source": source,
                },
                ensure_ascii=False,
            )
        )
    else:
        for finding in findings:
            print(f"{finding.path}:{finding.line}: {finding.kind}: {finding.text}")
        for path in acceptance:
            print(f"{path}: acceptance-surface ({source})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
