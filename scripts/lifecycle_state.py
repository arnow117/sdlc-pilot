#!/usr/bin/env python3
"""Small Git-tracked state store for the default SDLC lifecycle.

``.sdlc-v1/state.json`` is the only progress source. Product and engineering
context remains ordinary Markdown under ``.sdlc-v1/context/`` and is referenced
by path. Git provides history and cross-clone transport; there is no event
ledger, hash chain, journal, compatibility runtime, or automatic Git action.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
from typing import Callable, Iterator, Mapping, Sequence


STATE_DIRECTORY = ".sdlc-v1"
STATE_FILENAME = "state.json"
STATE_FORMAT = "sdlc-lightweight-state-v1"
STATE_VERSION = 3

_STATE_FIELDS = frozenset({"state_format", "state_version", "requirements", "features"})
_REQUIREMENT_FIELDS = frozenset({
    "id", "title", "description", "domain", "priority", "status", "depends_on", "feature_id",
    "product_context_ref", "created_at", "updated_at",
})
_FEATURE_FIELDS = frozenset({
    "id", "requirement_id", "branch", "status", "tasks", "validation", "review", "release",
    "engineering_context_ref", "created_at", "updated_at",
})
_REQUIREMENT_FIELDS_WITH_ACCEPTANCE = _REQUIREMENT_FIELDS | {"acceptance"}
_FEATURE_FIELDS_WITH_ACCEPTANCE = _FEATURE_FIELDS | {"acceptance"}
_TASK_FIELDS = frozenset({"id", "title", "status", "depends_on", "updated_at"})
_VALIDATION_FIELDS = frozenset({"result", "command", "commit", "at"})
_REVIEW_FIELDS = frozenset({"decision", "by", "at"})
_RELEASE_FIELDS = frozenset({"status", "commit", "at"})
_SNAPSHOT_FIELDS = frozenset({"algorithm", "normalization", "at", "documents"})
_SNAPSHOT_ALGORITHM = "sha256"
_SNAPSHOT_NORMALIZATION = "context-v1"
_REQUIREMENT_ACCEPTANCE_POINTS = frozenset({"spec_ready"})
_FEATURE_ACCEPTANCE_POINTS = frozenset({"plan", "validation", "review"})
_ACCEPTANCE_POINT_ORDER = ("spec_ready", "plan", "validation", "review")
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_FRONTMATTER_METADATA_KEYS = ("updated_at", "status", "document_status")
_DOCUMENT_STATUS_PREFIXES = ("- 文档状态：", "**状态**：", "**上次确认**：")

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,127}$")
_REQUIREMENT_STATUSES = frozenset({"captured", "ready", "in_delivery", "validated", "released", "cancelled"})
_FEATURE_STATUSES = frozenset({"planned", "in_progress", "validated", "reviewed", "released", "cancelled"})
_TASK_STATUSES = frozenset({"todo", "in_progress", "done", "blocked", "cancelled"})
_PRIORITIES = frozenset({"P0", "P1", "P2", "P3"})
_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
_TASK_TRANSITIONS = {
    "todo": frozenset({"in_progress", "blocked", "cancelled"}),
    "in_progress": frozenset({"todo", "done", "blocked", "cancelled"}),
    "blocked": frozenset({"todo", "in_progress", "cancelled"}),
    "done": frozenset({"todo"}),
    "cancelled": frozenset(),
}
_GIT_LOCAL_ENVIRONMENT_VARIABLES = frozenset({
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CONFIG",
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_PARAMETERS",
    "GIT_DIR",
    "GIT_GRAFT_FILE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_NAMESPACE",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_OBJECT_DIRECTORY",
    "GIT_PREFIX",
    "GIT_REPLACE_REF_BASE",
    "GIT_SHALLOW_FILE",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
})
_GIT_CONFIG_ENVIRONMENT_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")


class LifecycleStateError(RuntimeError):
    """The lightweight lifecycle state is missing, invalid, or inconsistent."""

    def __init__(self, code: str, *, details: Mapping[str, object] | None = None) -> None:
        super().__init__(code)
        self.details = None if details is None else dict(details)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise LifecycleStateError(f"duplicate-json-field:{key}")
        result[key] = value
    return result


def _repo_root(repo: str | os.PathLike[str]) -> Path:
    path = Path(repo)
    try:
        root = path.resolve(strict=True)
    except OSError as exc:
        raise LifecycleStateError("repository-root-not-found") from exc
    if not root.is_dir():
        raise LifecycleStateError("repository-root-not-directory")
    return root


def _state_directory(root: Path, *, create: bool) -> Path:
    directory = root / STATE_DIRECTORY
    if directory.is_symlink():
        raise LifecycleStateError("state-directory-cannot-be-symlink")
    if not directory.exists():
        if not create:
            return directory
        directory.mkdir(mode=0o755)
    if not directory.is_dir():
        raise LifecycleStateError("state-directory-not-directory")
    return directory


def state_path(repo: str | os.PathLike[str] = ".") -> Path:
    root = _repo_root(repo)
    return _state_directory(root, create=False) / STATE_FILENAME


def _state_file(root: Path, *, require_exists: bool) -> Path:
    """Return the canonical state path without inspecting historical runtimes."""
    path = _state_directory(root, create=False) / STATE_FILENAME
    if path.is_symlink():
        raise LifecycleStateError("state-file-cannot-be-symlink")
    if path.exists() and not path.is_file():
        raise LifecycleStateError("state-file-not-regular")
    if require_exists and not path.exists():
        raise LifecycleStateError("state-not-initialized")
    return path


def _id(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise LifecycleStateError(f"invalid-{label}")
    return value


def _text(value: object, *, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or "\x00" in value or (not allow_empty and not value.strip()):
        raise LifecycleStateError(f"invalid-{label}")
    return value


def _optional_text(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label=label)


def _context_ref(value: object, *, label: str) -> str:
    raw = _text(value, label=label)
    if "\\" in raw:
        raise LifecycleStateError(f"invalid-{label}")
    path = PurePosixPath(raw)
    parts = path.parts
    if (
        path.is_absolute()
        or path.as_posix() != raw
        or any(part in {"", ".", ".."} for part in raw.split("/"))
        or len(parts) < 3
        or parts[:2] != (STATE_DIRECTORY, "context")
        or path.suffix.lower() != ".md"
    ):
        raise LifecycleStateError(f"invalid-{label}")
    return raw


def _require_context_file(root: Path, ref: str, *, label: str) -> None:
    current = root
    for part in PurePosixPath(ref).parts:
        current = current / part
        if current.is_symlink():
            raise LifecycleStateError(f"{label}-cannot-be-symlink:{ref}")
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except FileNotFoundError as exc:
        raise LifecycleStateError(f"{label}-not-found:{ref}") from exc
    except ValueError as exc:
        raise LifecycleStateError(f"{label}-not-found:{ref}") from exc
    except OSError as exc:
        # Existence cannot be confirmed (for example EACCES); report that
        # distinctly instead of claiming the file is missing.
        raise LifecycleStateError(f"{label}-cannot-confirm:{ref}") from exc
    if not resolved.is_file():
        raise LifecycleStateError(f"{label}-not-regular:{ref}")


def _context_file_path(root: Path, ref: str) -> Path:
    path = root
    for part in PurePosixPath(ref).parts:
        path = path / part
    return path


def _read_context_bytes(root: Path, ref: str) -> bytes:
    """Read one context file strictly: inside the repo, no symlinks, must exist."""
    _require_context_file(root, ref, label="context")
    try:
        return _context_file_path(root, ref).read_bytes()
    except OSError as exc:
        raise LifecycleStateError(f"cannot-read-context:{ref}") from exc


def _read_verification_context_bytes(root: Path, ref: str) -> bytes | None:
    """Read one context file for a query; a vanished bound file is drift, not an error."""
    current = root
    for part in PurePosixPath(ref).parts:
        current = current / part
        if current.is_symlink():
            raise LifecycleStateError(f"context-cannot-be-symlink:{ref}")
    path = current
    try:
        info = os.stat(path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        # Existence cannot be confirmed (for example a permission error);
        # that is an explicit error, not a three-state result.
        raise LifecycleStateError(f"cannot-confirm-context:{ref}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise LifecycleStateError(f"context-not-regular:{ref}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise LifecycleStateError(f"cannot-read-context:{ref}") from exc


def _split_physical_lines(text: str) -> list[str]:
    """Split only on ``\\n`` so other Unicode separators stay byte-faithful content."""
    lines: list[str] = []
    start = 0
    for index, character in enumerate(text):
        if character == "\n":
            lines.append(text[start:index + 1])
            start = index + 1
    if start < len(text):
        lines.append(text[start:])
    return lines


def _line_content(line: str) -> str:
    if line.endswith("\r\n"):
        return line[:-2]
    if line.endswith("\n") or line.endswith("\r"):
        return line[:-1]
    return line


def _frontmatter_close_index(lines: list[str]) -> int | None:
    """Return the closing marker index of a complete opening frontmatter block."""
    if not lines or _line_content(lines[0]) != "---":
        return None
    open_quote: str | None = None
    flow_stack: list[str] = []
    flow_quote: str | None = None
    for index in range(1, len(lines)):
        content = _line_content(lines[index])
        if content == "---":
            if open_quote is not None or flow_stack:
                return None
            return index
        if flow_stack:
            flow_quote = _advance_flow_context(content, flow_stack, flow_quote)
        elif open_quote is not None:
            if _line_closes_open_quote(content, open_quote):
                open_quote = None
        else:
            open_quote = _unterminated_quoted_value(content)
            if open_quote is None:
                flow_quote = _advance_flow_context(content, flow_stack, flow_quote)
    return None


_FRONTMATTER_METADATA_KEY_PATTERN = re.compile(r"(updated_at|status|document_status):[ \t]+(\S.*)")
_QUOTE_CHARACTERS = {"\"", "'"}


def _metadata_scalar_value(content: str) -> str | None:
    """Return the value part when the line names a documented top-level key."""
    match = _FRONTMATTER_METADATA_KEY_PATTERN.fullmatch(content)
    if match is None:
        return None
    return match.group(2)


def _quoted_scalar_closing_index(value: str, quote: str) -> int | None:
    """Index of the unescaped closing quote, or None while the scalar stays open."""
    index = 1  # skip the opening quote
    while index < len(value):
        character = value[index]
        if quote == '"' and character == "\\":
            index += 2
            continue
        if character == quote:
            if quote == "'" and value[index + 1:index + 2] == "'":
                index += 2
                continue
            return index
        index += 1
    return None


def _line_closes_open_quote(content: str, quote: str) -> bool:
    """Whether an open quoted scalar closes somewhere within this line."""
    index = 0
    while index < len(content):
        character = content[index]
        if quote == '"' and character == "\\":
            index += 2
            continue
        if character == quote:
            if quote == "'" and content[index + 1:index + 2] == "'":
                index += 2
                continue
            return True
        index += 1
    return False


def _unterminated_quoted_value(content: str) -> str | None:
    """Quote character when a ``key: "value`` line leaves its scalar open."""
    value = content.lstrip(" \t")
    if not value or value[0] not in _QUOTE_CHARACTERS:
        colon = content.find(":")
        if colon < 0 or colon + 1 >= len(content) or content[colon + 1] not in " \t":
            return None
        value = content[colon + 1:].lstrip(" \t")
    value = re.sub(r"^(?:[&!][^ \t]+[ \t]+)+", "", value)
    if not value or value[0] not in _QUOTE_CHARACTERS:
        return None
    if _quoted_scalar_closing_index(value, value[0]) is not None:
        return None
    return value[0]


def _is_complete_metadata_scalar(value: str, following: str | None) -> bool:
    """Confirm one complete single-line scalar for a documented top-level key.

    An indented following line may continue the value as a nested block or a
    multi-line scalar, which stays byte-sensitive. Quoted values must close on
    the same line; flow collections, block scalars, and anchored values are not
    confirmable plain scalars. Without full YAML parsing, anything unconfirmed
    is conservatively kept.
    """
    if following is not None and _line_content(following)[:1] in {" ", "\t"}:
        return False
    if value[0] in _QUOTE_CHARACTERS:
        closing = _quoted_scalar_closing_index(value, value[0])
        if closing is None:
            return False
        if value[0] == '"':
            quoted = value[1:closing]
            valid_escape = r'\\(?:[0abtnvfre "\\/N_LP]|x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8})'
            if re.search(r'\\', re.sub(valid_escape, "", quoted)):
                return False
        return value[closing + 1:].strip(" \t") == ""
    if value[0] in {"[", "{", "|", ">", "&", "*", "!", "%", "@", "`", "#", ",", "]", "}"}:
        return False
    if re.match(r"[-?:](?:[ \t]|$)", value):
        return False
    if re.search(r":(?:[ \t]|$)|[ \t]#|[\x00-\x08\x0b-\x1f\x7f]", value):
        return False
    return True


def _next_significant_frontmatter_line(lines: list[str], start: int, end: int) -> str | None:
    """Skip blank and comment lines, which cannot establish scalar closure."""
    for line in lines[start:end]:
        content = _line_content(line)
        if not content.strip(" \t") or content.lstrip(" \t").startswith("#"):
            continue
        return line
    return None


def _advance_flow_context(
    content: str, stack: list[str], quote: str | None,
) -> str | None:
    """Track flow collections and quoted strings without interpreting their values.

    Unclosed or mismatched collections remain open so ambiguous later lines are
    retained. Outside a collection, only a value beginning with a flow opener is
    recognized; quoted block values are handled separately by the caller.
    """
    index = 0
    if not stack:
        index = len(content) - len(content.lstrip(" \t"))
        value = content[index:]
        if not value or value[0] not in "[{":
            if value and value[0] in _QUOTE_CHARACTERS:
                closing = _quoted_scalar_closing_index(value, value[0])
                if closing is None:
                    return None
                separator = re.match(r"[ \t]*:[ \t]+", value[closing + 1:])
                if separator is None:
                    return None
                index += closing + 1 + separator.end()
                value = content[index:]
            else:
                match = re.match(r"[ \t]*(?:[^:#]+:[ \t]+|-[ \t]+)(.*)", content)
                if match is None:
                    return None
                value = match.group(1)
                index = match.start(1)
        prefix = re.match(r"(?:[&!][^ \t]+[ \t]+)*", value)
        index += prefix.end()
        value = content[index:]
        if not value or value[0] not in "[{":
            return None

    while index < len(content):
        character = content[index]
        if quote is not None:
            if quote == '"' and character == "\\":
                index += 2
                continue
            if character == quote:
                if quote == "'" and content[index + 1:index + 2] == "'":
                    index += 2
                    continue
                quote = None
        elif character == "#" and (index == 0 or content[index - 1] in " \t"):
            break
        elif character in _QUOTE_CHARACTERS and (
            index == 0 or content[index - 1] in " \t,:[{?"
        ):
            quote = character
        elif character in "[{":
            stack.append(character)
        elif character in "]}":
            if not stack or stack[-1] != {']': '[', '}': '{'}[character]:
                # An invalid collection is uncertain: keep all remaining lines.
                stack.append("?")
                return quote
            stack.pop()
            if not stack:
                return None
        index += 1
    return quote


def _drop_frontmatter_metadata_lines(lines: list[str]) -> list[str]:
    close_index = _frontmatter_close_index(lines)
    if close_index is None:
        # No complete frontmatter block: nothing is excluded, conservatively.
        return lines
    kept = []
    open_quote: str | None = None
    flow_stack: list[str] = []
    flow_quote: str | None = None
    for index, line in enumerate(lines):
        if not 0 < index < close_index:
            kept.append(line)
            continue
        content = _line_content(line)
        following = _next_significant_frontmatter_line(lines, index + 1, close_index)
        if flow_stack:
            flow_quote = _advance_flow_context(content, flow_stack, flow_quote)
            kept.append(line)
            continue
        if open_quote is not None:
            # Conservatively keep every line inside a cross-line quoted value;
            # a metadata-like line there is content, not a top-level key.
            if _line_closes_open_quote(content, open_quote):
                open_quote = None
            kept.append(line)
            continue
        value = _metadata_scalar_value(content)
        if value is not None and _is_complete_metadata_scalar(value, following):
            continue
        opened = _unterminated_quoted_value(content)
        if opened is not None:
            open_quote = opened
        else:
            flow_quote = _advance_flow_context(content, flow_stack, flow_quote)
        kept.append(line)
    return kept


def _heading_level(content: str) -> int | None:
    match = re.match(r"(#{1,6})(\s|$)", content)
    if match is None:
        return None
    return len(match.group(1))


_CODE_FENCE_PATTERN = re.compile(r" {0,3}(`{3,}|~{3,})")


def _code_fence_marker(content: str) -> tuple[str, int] | None:
    """Return the fence character and length for an opening fence-shaped line."""
    match = _CODE_FENCE_PATTERN.match(content)
    if match is None:
        return None
    marker = match.group(1)
    return marker[0], len(marker)


def _closes_code_fence(content: str, character: str, length: int) -> bool:
    """Whether this line is a bare fence closing the given opening fence."""
    indent = len(content) - len(content.lstrip(" "))
    if indent > 3:
        return False
    stripped = content[indent:]
    if len(stripped) < length or any(part != character for part in stripped[:length]):
        return False
    return stripped[length:].strip(" \t") == ""


def _fenced_code_line_flags(lines: list[str], start: int) -> list[bool]:
    """Per-line flags: True when the line belongs to a fenced code block.

    A fence opens with three or more backticks or tildes (up to three leading
    spaces, optional info string) and closes with a bare fence of the same
    character at least as long. An unterminated fence conservatively keeps the
    rest of the document inside the block.
    """
    flags = []
    in_fence = False
    fence_character = ""
    fence_length = 0
    for line in lines[start:]:
        content = _line_content(line)
        marker = _code_fence_marker(content)
        if marker is not None:
            character, length = marker
            if (
                in_fence
                and character == fence_character
                and length >= fence_length
                and _closes_code_fence(content, character, length)
            ):
                in_fence = False
                flags.append(True)
                continue
            if not in_fence:
                match = _CODE_FENCE_PATTERN.match(content)
                if character == "`" and "`" in content[match.end():]:
                    flags.append(False)
                    continue
                fence_character = character
                fence_length = length
                in_fence = True
            flags.append(True)
            continue
        flags.append(in_fence)
    return flags


def _drop_document_status_lines(lines: list[str]) -> list[str]:
    opens_frontmatter = bool(lines) and _line_content(lines[0]) == "---"
    close_index = _frontmatter_close_index(lines)
    if opens_frontmatter and close_index is None:
        # Incomplete frontmatter: nothing is excluded, conservatively.
        return lines
    body_start = 0 if close_index is None else close_index + 1
    fenced = _fenced_code_line_flags(lines, body_start)
    first_heading = None
    for offset, line in enumerate(lines[body_start:]):
        if fenced[offset]:
            continue
        if _heading_level(_line_content(line)) is not None:
            first_heading = body_start + offset
            break
    if first_heading is None:
        return lines
    drop = set()
    for offset in range(first_heading + 1 - body_start, len(fenced)):
        if fenced[offset]:
            continue
        content = _line_content(lines[body_start + offset])
        if _heading_level(content) == 2:
            break
        if any(content.startswith(prefix) for prefix in _DOCUMENT_STATUS_PREFIXES):
            drop.add(body_start + offset)
    return [line for index, line in enumerate(lines) if index not in drop]


def _normalize_context_v1(text: str) -> str:
    """Drop only the documented lifecycle metadata lines; keep every other byte."""
    lines = _split_physical_lines(text)
    lines = _drop_frontmatter_metadata_lines(lines)
    lines = _drop_document_status_lines(lines)
    return "".join(lines)


def _context_digest(raw: bytes, *, ref: str) -> str:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LifecycleStateError(f"context-not-valid-utf8:{ref}") from exc
    return hashlib.sha256(_normalize_context_v1(text).encode("utf-8")).hexdigest()


def _timestamp(value: object, *, label: str) -> str:
    raw = _text(value, label=label)
    parseable = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    # Python 3.9 rejects ISO 8601 basic timezone offsets (for example,
    # ``+0800``) that later supported Python versions accept. Normalize only a
    # terminal basic offset for parsing; state continues to retain the original
    # timestamp spelling.
    parseable = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", parseable)
    try:
        parsed = datetime.fromisoformat(parseable)
    except ValueError as exc:
        raise LifecycleStateError(f"invalid-{label}") from exc
    if parsed.tzinfo is None:
        raise LifecycleStateError(f"invalid-{label}")
    return raw


def _id_list(value: object, *, label: str) -> list[str]:
    if not isinstance(value, list):
        raise LifecycleStateError(f"invalid-{label}")
    result = [_id(item, label=f"{label}-item") for item in value]
    if len(set(result)) != len(result):
        raise LifecycleStateError(f"duplicate-{label}")
    return result


def _cycle(nodes: Mapping[str, list[str]]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(node: str, trail: list[str]) -> list[str] | None:
        if node in visiting:
            return trail[trail.index(node):] + [node]
        if node in visited:
            return None
        visiting.add(node)
        for dependency in nodes[node]:
            found = walk(dependency, [*trail, node])
            if found:
                return found
        visiting.remove(node)
        visited.add(node)
        return None

    for node in sorted(nodes):
        found = walk(node, [])
        if found:
            return found
    return None


def _validate_validation(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _VALIDATION_FIELDS:
        raise LifecycleStateError("invalid-feature-validation-fields")
    result = dict(value)
    if result.get("result") not in {"pending", "pass", "fail"}:
        raise LifecycleStateError("invalid-feature-validation-result")
    result["command"] = _optional_text(result.get("command"), label="feature-validation-command")
    result["commit"] = _optional_text(result.get("commit"), label="feature-validation-commit")
    at = result.get("at")
    result["at"] = None if at is None else _timestamp(at, label="feature-validation-at")
    if result["result"] == "pending" and any(result[field] is not None for field in ("command", "commit", "at")):
        raise LifecycleStateError("pending-feature-validation-cannot-have-record")
    if result["result"] != "pending" and (
        result["commit"] is None or result["at"] is None
    ):
        raise LifecycleStateError("completed-feature-validation-requires-commit-and-at")
    return result


def _validate_review(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _REVIEW_FIELDS:
        raise LifecycleStateError("invalid-feature-review-fields")
    result = dict(value)
    if result.get("decision") not in {"pending", "approved", "changes_requested"}:
        raise LifecycleStateError("invalid-feature-review-decision")
    result["by"] = _optional_text(result.get("by"), label="feature-review-by")
    at = result.get("at")
    result["at"] = None if at is None else _timestamp(at, label="feature-review-at")
    if result["decision"] == "pending" and (result["by"] is not None or result["at"] is not None):
        raise LifecycleStateError("pending-feature-review-cannot-have-record")
    if result["decision"] != "pending" and result["at"] is None:
        raise LifecycleStateError("completed-feature-review-requires-at")
    return result


def _validate_release(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _RELEASE_FIELDS:
        raise LifecycleStateError("invalid-feature-release-fields")
    result = dict(value)
    if result.get("status") not in {"pending", "released"}:
        raise LifecycleStateError("invalid-feature-release-status")
    result["commit"] = _optional_text(result.get("commit"), label="feature-release-commit")
    at = result.get("at")
    result["at"] = None if at is None else _timestamp(at, label="feature-release-at")
    if result["status"] == "pending" and (result["commit"] is not None or result["at"] is not None):
        raise LifecycleStateError("pending-feature-release-cannot-have-record")
    if result["status"] == "released" and (
        result["commit"] is None or result["at"] is None
    ):
        raise LifecycleStateError("released-feature-requires-commit-and-at")
    return result


def _validate_snapshot(value: object, *, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _SNAPSHOT_FIELDS:
        raise LifecycleStateError(f"invalid-{label}-fields")
    result = dict(value)
    if result.get("algorithm") != _SNAPSHOT_ALGORITHM:
        raise LifecycleStateError(f"invalid-{label}-algorithm")
    if result.get("normalization") != _SNAPSHOT_NORMALIZATION:
        raise LifecycleStateError(f"invalid-{label}-normalization")
    result["at"] = _timestamp(result.get("at"), label=f"{label}-at")
    documents = result.get("documents")
    if not isinstance(documents, Mapping) or not documents:
        raise LifecycleStateError(f"invalid-{label}-documents")
    checked_documents: dict[str, object] = {}
    for ref, digest in documents.items():
        checked_documents[_context_ref(ref, label=f"{label}-document-ref")] = digest
        if not isinstance(digest, str) or _DIGEST_PATTERN.fullmatch(digest) is None:
            raise LifecycleStateError(f"invalid-{label}-digest:{ref}")
    result["documents"] = checked_documents
    return result


def _validate_acceptance(value: object, *, label: str, allowed_points: frozenset[str]) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise LifecycleStateError(f"invalid-{label}-fields")
    unknown_points = sorted(set(value) - allowed_points)
    if unknown_points:
        raise LifecycleStateError(f"invalid-{label}-fields:" + ",".join(unknown_points))
    result: dict[str, object] = {}
    for point in _ACCEPTANCE_POINT_ORDER:
        if point in value:
            result[point] = _validate_snapshot(value[point], label="acceptance-snapshot")
    return result


def _validate_state(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _STATE_FIELDS:
        raise LifecycleStateError("invalid-state-fields")
    state = deepcopy(dict(value))
    if state.get("state_format") != STATE_FORMAT or state.get("state_version") != STATE_VERSION:
        raise LifecycleStateError("unsupported-state-format")
    requirements = state.get("requirements")
    features = state.get("features")
    if not isinstance(requirements, Mapping) or not isinstance(features, Mapping):
        raise LifecycleStateError("invalid-state-collections")
    requirement_records: dict[str, dict[str, object]] = {}
    for key, raw in requirements.items():
        requirement_id = _id(key, label="requirement-key")
        if not isinstance(raw, Mapping) or set(raw) not in (
            _REQUIREMENT_FIELDS, _REQUIREMENT_FIELDS_WITH_ACCEPTANCE,
        ):
            raise LifecycleStateError(f"invalid-requirement-fields:{requirement_id}")
        record = deepcopy(dict(raw))
        if _id(record.get("id"), label="requirement-id") != requirement_id:
            raise LifecycleStateError(f"requirement-key-id-mismatch:{requirement_id}")
        record["title"] = _text(record.get("title"), label="requirement-title")
        record["description"] = _text(record.get("description"), label="requirement-description", allow_empty=True)
        record["domain"] = _text(record.get("domain"), label="requirement-domain")
        record["product_context_ref"] = _context_ref(
            record.get("product_context_ref"), label="requirement-product-context-ref",
        )
        if record.get("priority") not in _PRIORITIES:
            raise LifecycleStateError(f"invalid-requirement-priority:{requirement_id}")
        if record.get("status") not in _REQUIREMENT_STATUSES:
            raise LifecycleStateError(f"invalid-requirement-status:{requirement_id}")
        record["depends_on"] = _id_list(record.get("depends_on"), label=f"requirement-depends-on:{requirement_id}")
        feature_id = record.get("feature_id")
        record["feature_id"] = None if feature_id is None else _id(feature_id, label="requirement-feature-id")
        record["created_at"] = _timestamp(record.get("created_at"), label="requirement-created-at")
        record["updated_at"] = _timestamp(record.get("updated_at"), label="requirement-updated-at")
        if "acceptance" in record:
            record["acceptance"] = _validate_acceptance(
                record["acceptance"],
                label="requirement-acceptance",
                allowed_points=_REQUIREMENT_ACCEPTANCE_POINTS,
            )
        requirement_records[requirement_id] = record
    missing_requirements = sorted({dependency for record in requirement_records.values()
                                   for dependency in record["depends_on"] if dependency not in requirement_records})
    if missing_requirements:
        raise LifecycleStateError("unknown-requirement-dependency:" + ",".join(missing_requirements))
    requirement_cycle = _cycle({key: list(record["depends_on"]) for key, record in requirement_records.items()})
    if requirement_cycle:
        raise LifecycleStateError("requirement-dependency-cycle:" + "->".join(requirement_cycle))

    feature_records: dict[str, dict[str, object]] = {}
    for key, raw in features.items():
        feature_id = _id(key, label="feature-key")
        if not isinstance(raw, Mapping) or set(raw) not in (
            _FEATURE_FIELDS, _FEATURE_FIELDS_WITH_ACCEPTANCE,
        ):
            raise LifecycleStateError(f"invalid-feature-fields:{feature_id}")
        record = deepcopy(dict(raw))
        if _id(record.get("id"), label="feature-id") != feature_id:
            raise LifecycleStateError(f"feature-key-id-mismatch:{feature_id}")
        requirement_id = _id(record.get("requirement_id"), label="feature-requirement-id")
        if requirement_id not in requirement_records:
            raise LifecycleStateError(f"unknown-feature-requirement:{feature_id}")
        record["requirement_id"] = requirement_id
        record["branch"] = _text(record.get("branch"), label="feature-branch")
        record["engineering_context_ref"] = _context_ref(
            record.get("engineering_context_ref"), label="feature-engineering-context-ref",
        )
        if record.get("status") not in _FEATURE_STATUSES:
            raise LifecycleStateError(f"invalid-feature-status:{feature_id}")
        record["created_at"] = _timestamp(record.get("created_at"), label="feature-created-at")
        record["updated_at"] = _timestamp(record.get("updated_at"), label="feature-updated-at")
        tasks = record.get("tasks")
        if not isinstance(tasks, Mapping):
            raise LifecycleStateError(f"invalid-feature-tasks:{feature_id}")
        task_records: dict[str, dict[str, object]] = {}
        for task_key, task_raw in tasks.items():
            task_id = _id(task_key, label="task-key")
            if not isinstance(task_raw, Mapping) or set(task_raw) != _TASK_FIELDS:
                raise LifecycleStateError(f"invalid-task-fields:{feature_id}/{task_id}")
            task = deepcopy(dict(task_raw))
            if _id(task.get("id"), label="task-id") != task_id:
                raise LifecycleStateError(f"task-key-id-mismatch:{feature_id}/{task_id}")
            task["title"] = _text(task.get("title"), label="task-title")
            if task.get("status") not in _TASK_STATUSES:
                raise LifecycleStateError(f"invalid-task-status:{feature_id}/{task_id}")
            task["depends_on"] = _id_list(task.get("depends_on"), label=f"task-depends-on:{feature_id}/{task_id}")
            task["updated_at"] = _timestamp(task.get("updated_at"), label="task-updated-at")
            task_records[task_id] = task
        unknown_tasks = sorted({dependency for task in task_records.values()
                                for dependency in task["depends_on"] if dependency not in task_records})
        if unknown_tasks:
            raise LifecycleStateError(f"unknown-task-dependency:{feature_id}/" + ",".join(unknown_tasks))
        task_cycle = _cycle({task_id: list(task["depends_on"]) for task_id, task in task_records.items()})
        if task_cycle:
            raise LifecycleStateError(f"task-dependency-cycle:{feature_id}/" + "->".join(task_cycle))
        record["tasks"] = task_records
        record["validation"] = _validate_validation(record.get("validation"))
        record["review"] = _validate_review(record.get("review"))
        record["release"] = _validate_release(record.get("release"))
        if "acceptance" in record:
            record["acceptance"] = _validate_acceptance(
                record["acceptance"],
                label="feature-acceptance",
                allowed_points=_FEATURE_ACCEPTANCE_POINTS,
            )
        feature_records[feature_id] = record

    for requirement_id, requirement in requirement_records.items():
        linked_feature = requirement["feature_id"]
        if linked_feature is None:
            if requirement["status"] not in {"captured", "ready", "cancelled"}:
                raise LifecycleStateError(f"unlinked-requirement-has-delivery-status:{requirement_id}")
            continue
        feature = feature_records.get(linked_feature)
        if feature is None or feature["requirement_id"] != requirement_id:
            raise LifecycleStateError(f"requirement-feature-link-mismatch:{requirement_id}")
        expected_status = {
            "planned": "in_delivery", "in_progress": "in_delivery", "validated": "validated",
            "reviewed": "validated", "released": "released", "cancelled": "cancelled",
        }[str(feature["status"])]
        if requirement["status"] != expected_status:
            raise LifecycleStateError(f"requirement-feature-status-mismatch:{requirement_id}")
    for feature_id, feature in feature_records.items():
        requirement = requirement_records[str(feature["requirement_id"])]
        if requirement["feature_id"] != feature_id:
            raise LifecycleStateError(f"feature-requirement-link-mismatch:{feature_id}")
        validation = feature["validation"]
        review = feature["review"]
        release = feature["release"]
        status = str(feature["status"])
        if status in {"validated", "reviewed", "released"} and validation["result"] != "pass":
            raise LifecycleStateError(f"feature-status-requires-passing-validation:{feature_id}")
        if status in {"reviewed", "released"} and review["decision"] != "approved":
            raise LifecycleStateError(f"feature-status-requires-approved-review:{feature_id}")
        if status == "released" and release["status"] != "released":
            raise LifecycleStateError(f"feature-status-requires-release-record:{feature_id}")
        if status != "released" and release["status"] == "released":
            raise LifecycleStateError(f"release-record-status-mismatch:{feature_id}")
    return {
        "state_format": STATE_FORMAT,
        "state_version": STATE_VERSION,
        "requirements": requirement_records,
        "features": feature_records,
    }


def _empty_state() -> dict[str, object]:
    return {
        "state_format": STATE_FORMAT,
        "state_version": STATE_VERSION,
        "requirements": {},
        "features": {},
    }


def _decode_state(raw: bytes) -> dict[str, object]:
    try:
        source = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except LifecycleStateError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LifecycleStateError("invalid-state-json") from exc
    return _validate_state(source)


def _read_state(root: Path) -> dict[str, object]:
    path = _state_file(root, require_exists=True)
    try:
        return _decode_state(path.read_bytes())
    except LifecycleStateError:
        raise
    except OSError as exc:
        raise LifecycleStateError("cannot-read-state") from exc


def _state_identity(path: Path) -> tuple[int, int, int, int]:
    try:
        info = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise LifecycleStateError("cannot-stat-state") from exc
    if not stat.S_ISREG(info.st_mode):
        raise LifecycleStateError("state-file-not-regular")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _read_descriptor(descriptor: int) -> bytes:
    with os.fdopen(os.dup(descriptor), "rb", closefd=True) as handle:
        return handle.read()


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LifecycleStateError("git-is-required-for-lightweight-state") from exc


def _reject_git_local_environment_for_branch_migration() -> None:
    """Keep one migration's Git identity bound to its supplied checkout.

    The explicit names come from ``git rev-parse --local-env-vars`` in the
    supported Git version. ``GIT_NAMESPACE`` and numbered config entries also
    change ref or config resolution, so the migration rejects them as well.
    Other lifecycle commands retain their existing environment behavior.
    """
    redirected = [
        name
        for name in os.environ
        if name in _GIT_LOCAL_ENVIRONMENT_VARIABLES
        or name.startswith(_GIT_CONFIG_ENVIRONMENT_PREFIXES)
    ]
    if redirected:
        raise LifecycleStateError(
            "branch-migration-rejects-git-local-environment:" + ",".join(sorted(redirected)),
        )


def _require_explicit_local_branch(root: Path, branch: str) -> str:
    """Return a validated local branch name without accepting Git shorthand."""
    if branch in {"@", "HEAD"} or branch.startswith("refs/"):
        raise LifecycleStateError("invalid-feature-branch")
    result = _git(root, "check-ref-format", "--branch", branch)
    if result.returncode != 0 or result.stdout.strip() != branch:
        raise LifecycleStateError("invalid-feature-branch")
    return f"refs/heads/{branch}"


def _current_branch_migration_identity(
    root: Path, *, branch: str, expected_head: str,
) -> dict[str, str]:
    """Read the current attached checkout identity for a branch migration."""
    actual_root = _git(root, "rev-parse", "--show-toplevel")
    if actual_root.returncode != 0 or not actual_root.stdout.strip():
        raise LifecycleStateError("branch-migration-requires-git-worktree")
    canonical_root = Path(actual_root.stdout.strip()).resolve()
    if canonical_root != root:
        raise LifecycleStateError("branch-migration-repository-root-mismatch")

    expected_ref = _require_explicit_local_branch(root, branch)
    symbolic_head = _git(root, "symbolic-ref", "--quiet", "HEAD")
    if symbolic_head.returncode != 0 or not symbolic_head.stdout.strip():
        raise LifecycleStateError("branch-migration-requires-attached-local-branch")
    if symbolic_head.stdout.strip() != expected_ref:
        raise LifecycleStateError("branch-migration-branch-not-current-checkout")

    head = _git(root, "rev-parse", "--verify", "HEAD^{commit}")
    if head.returncode != 0 or not head.stdout.strip():
        raise LifecycleStateError("branch-migration-requires-head-commit")
    actual_head = head.stdout.strip()
    if actual_head != expected_head:
        raise LifecycleStateError("branch-migration-head-mismatch")
    return {"head": actual_head, "repo_root": str(canonical_root)}


def _require_git_repository(root: Path) -> None:
    result = _git(root, "rev-parse", "--is-inside-work-tree")
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise LifecycleStateError("git-repository-required")


def _ensure_state_can_be_tracked(root: Path) -> None:
    """Fail early when a repository ignore rule would defeat cross-clone sync."""
    _require_git_repository(root)
    relative = f"{STATE_DIRECTORY}/{STATE_FILENAME}"
    ignored = _git(root, "check-ignore", "-q", "--", relative)
    if ignored.returncode == 0:
        raise LifecycleStateError("state-path-is-gitignored")
    if ignored.returncode != 1:
        raise LifecycleStateError("cannot-check-state-git-ignore")


def _state_git_status(root: Path) -> dict[str, bool]:
    relative = f"{STATE_DIRECTORY}/{STATE_FILENAME}"
    tracked_result = _git(root, "ls-files", "--error-unmatch", "--", relative)
    if tracked_result.returncode not in {0, 1}:
        raise LifecycleStateError("cannot-check-state-tracking")
    unmerged_result = _git(root, "ls-files", "-u", "--", relative)
    if unmerged_result.returncode != 0:
        raise LifecycleStateError("cannot-check-state-conflicts")
    staged_result = _git(root, "diff", "--cached", "--quiet", "--", relative)
    if staged_result.returncode not in {0, 1}:
        raise LifecycleStateError("cannot-check-staged-state")
    return {
        "tracked": tracked_result.returncode == 0,
        "unmerged": bool(unmerged_result.stdout.strip()),
        "staged": staged_result.returncode == 1,
    }


def _require_tracked_state(root: Path) -> None:
    state_git = _state_git_status(root)
    if state_git["unmerged"]:
        raise LifecycleStateError("state-has-unmerged-index-entries")
    if not state_git["tracked"]:
        raise LifecycleStateError("state-must-be-git-tracked-before-validation")


def _require_tracked_feature_contexts(
    root: Path, state: Mapping[str, object], feature: Mapping[str, object],
) -> None:
    requirements = state["requirements"]
    assert isinstance(requirements, Mapping)
    requirement = requirements[str(feature["requirement_id"])]
    assert isinstance(requirement, Mapping)
    refs = (
        (str(requirement["product_context_ref"]), "product-context"),
        (str(feature["engineering_context_ref"]), "engineering-context"),
    )
    for ref, label in refs:
        _require_context_file(root, ref, label=label)
        tracked = _git(root, "ls-files", "--error-unmatch", "--", ref)
        if tracked.returncode != 0:
            raise LifecycleStateError(f"context-must-be-git-tracked-before-validation:{ref}")
        unmerged = _git(root, "ls-files", "-u", "--", ref)
        if unmerged.returncode != 0:
            raise LifecycleStateError(f"cannot-check-context-conflicts:{ref}")
        if unmerged.stdout.strip():
            raise LifecycleStateError(f"context-has-unmerged-index-entries:{ref}")


def _reject_staged_state(root: Path) -> None:
    """Do not overwrite the index after a caller has started a handoff commit."""
    state_git = _state_git_status(root)
    if state_git["unmerged"]:
        raise LifecycleStateError("state-has-unmerged-index-entries")
    if state_git["staged"]:
        raise LifecycleStateError("state-is-staged-commit-or-unstage-before-update")


def _reject_installed_legacy_hooks(root: Path) -> None:
    """Refuse initialization while copied hooks from the removed runtime remain active."""
    hooks_result = _git(root, "rev-parse", "--git-path", "hooks")
    if hooks_result.returncode != 0 or not hooks_result.stdout.strip():
        raise LifecycleStateError("cannot-locate-git-hooks-directory")
    hooks_directory = Path(hooks_result.stdout.strip())
    if not hooks_directory.is_absolute():
        hooks_directory = root / hooks_directory
    markers = ("sdlc-pilot", "sdlc-guard", ".sdlc/STATE.md", ".sdlc-control/")
    installed: list[str] = []
    for name in ("pre-commit", "pre-push", "post-checkout", "sdlc-guard"):
        candidate = hooks_directory / name
        if not candidate.is_file():
            continue
        try:
            source = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise LifecycleStateError(f"cannot-read-git-hook:{name}") from exc
        if name == "sdlc-guard" or any(marker in source for marker in markers):
            installed.append(name)
    if installed:
        names = ",".join(installed)
        raise LifecycleStateError(
            f"unsupported-sdlc-hooks-installed:{names};remove-manually-from:{hooks_directory}",
        )


def _code_head(
    root: Path, state: Mapping[str, object], feature: Mapping[str, object],
) -> str:
    """Return HEAD when code is clean and lifecycle handoff files are tracked.

    ``.sdlc-v1`` is excluded from code cleanliness so validation evidence and
    progress can be committed after the implementation without invalidating
    the tested code tree.
    """
    _require_git_repository(root)
    _require_tracked_state(root)
    _require_tracked_feature_contexts(root, state, feature)
    dirty = _git(
        root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        ".",
        f":(glob,exclude){STATE_DIRECTORY}/**",
    )
    if dirty.returncode != 0:
        raise LifecycleStateError("cannot-check-worktree-status")
    if dirty.stdout:
        raise LifecycleStateError("validation-and-release-require-clean-worktree")
    head = _git(root, "rev-parse", "--verify", "HEAD")
    if head.returncode != 0:
        raise LifecycleStateError("validation-and-release-require-head-commit")
    return head.stdout.strip()


def _implementation_unchanged(root: Path, validated_commit: str, current_head: str) -> bool:
    result = _git(
        root,
        "diff",
        "--quiet",
        validated_commit,
        current_head,
        "--",
        ".",
        f":(glob,exclude){STATE_DIRECTORY}/**",
    )
    if result.returncode not in {0, 1}:
        raise LifecycleStateError("cannot-compare-validation-implementation")
    return result.returncode == 0


@contextmanager
def _locked_state(root: Path) -> Iterator[tuple[dict[str, object], Path, tuple[int, int, int, int]]]:
    """Lock the current state inode; retry if another writer replaced it first."""
    path = _state_file(root, require_exists=True)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    for _ in range(4):
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise LifecycleStateError("cannot-open-state") from exc
        locked = False
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise LifecycleStateError("state-file-not-regular")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            locked = True
            identity = _state_identity(path)
            if (info.st_dev, info.st_ino) != identity[:2]:
                continue
            state = _decode_state(_read_descriptor(descriptor))
            yield state, path, identity
            return
        finally:
            if locked:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
    raise LifecycleStateError("state-changed-during-lock-acquisition")


def _sync_directory(directory: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(directory, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise LifecycleStateError("cannot-sync-state-directory") from exc


def _write_replacement(
    root: Path, path: Path, state: Mapping[str, object], *, expected_identity: tuple[int, int, int, int],
) -> None:
    """Atomically replace an unchanged state file while holding its advisory lock."""
    checked = _validate_state(state)
    if _state_identity(path) != expected_identity:
        raise LifecycleStateError("state-changed-before-write")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".state-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(checked, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if _state_identity(path) != expected_identity:
            raise LifecycleStateError("state-changed-before-replace")
        os.replace(temporary_name, path)
        _sync_directory(path.parent)
    except OSError as exc:
        raise LifecycleStateError("cannot-write-state") from exc
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _create_state(path: Path, state: Mapping[str, object]) -> None:
    checked = _validate_state(state)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o644)
    except FileExistsError as exc:
        raise LifecycleStateError("state-already-initialized") from exc
    except OSError as exc:
        raise LifecycleStateError("cannot-create-state") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(checked, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise LifecycleStateError("cannot-write-state") from exc
    _sync_directory(path.parent)


def initialize(repo: str | os.PathLike[str] = ".", *, at: str | None = None) -> dict[str, object]:
    root = _repo_root(repo)
    _ensure_state_can_be_tracked(root)
    _reject_installed_legacy_hooks(root)
    path = _state_file(root, require_exists=False)
    if path.exists():
        raise LifecycleStateError("state-already-initialized")
    path = _state_directory(root, create=True) / STATE_FILENAME
    if at is not None:
        _timestamp(at, label="state-initialized-at")
    state = _empty_state()
    _create_state(path, state)
    return status(root)


def load(repo: str | os.PathLike[str] = ".") -> dict[str, object]:
    return deepcopy(_read_state(_repo_root(repo)))


def _mutate(
    repo: str | os.PathLike[str], operation: Callable[[dict[str, object], str], dict[str, object]], *, at: str | None,
) -> dict[str, object]:
    root = _repo_root(repo)
    _ensure_state_can_be_tracked(root)
    with _locked_state(root) as (state, path, identity):
        _reject_staged_state(root)
        timestamp = _timestamp(at, label="operation-at") if at is not None else _now()
        result = operation(state, timestamp)
        _write_replacement(root, path, state, expected_identity=identity)
        return result


def _requirement(state: Mapping[str, object], requirement_id: str) -> dict[str, object]:
    requirements = state["requirements"]
    assert isinstance(requirements, dict)
    record = requirements.get(requirement_id)
    if not isinstance(record, dict):
        raise LifecycleStateError(f"requirement-not-found:{requirement_id}")
    return record


def _feature(state: Mapping[str, object], feature_id: str) -> dict[str, object]:
    features = state["features"]
    assert isinstance(features, dict)
    record = features.get(feature_id)
    if not isinstance(record, dict):
        raise LifecycleStateError(f"feature-not-found:{feature_id}")
    return record


def _set_acceptance_snapshot(record: dict[str, object], point: str, snapshot: Mapping[str, object]) -> None:
    acceptance = record.get("acceptance")
    if not isinstance(acceptance, dict):
        acceptance = {}
        record["acceptance"] = acceptance
    acceptance[point] = deepcopy(dict(snapshot))


def _clear_acceptance_snapshot(record: dict[str, object], *points: str) -> None:
    acceptance = record.get("acceptance")
    if not isinstance(acceptance, dict):
        return
    for point in points:
        acceptance.pop(point, None)


def _context_file_identity(root: Path, ref: str) -> tuple[int, int, int, int]:
    """Read-time identity of one context file, recorded for the later re-check."""
    path = _context_file_path(root, ref)
    try:
        info = os.stat(path, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise LifecycleStateError(f"context-not-found:{ref}") from exc
    except OSError as exc:
        raise LifecycleStateError(f"cannot-confirm-context:{ref}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise LifecycleStateError(f"context-cannot-be-symlink:{ref}")
    if not stat.S_ISREG(info.st_mode):
        raise LifecycleStateError(f"context-not-regular:{ref}")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _build_acceptance_snapshot(
    root: Path, refs: Sequence[str], *, at: str,
) -> tuple[dict[str, object], dict[str, str], dict[str, tuple[int, int, int, int]]]:
    ordered_refs = sorted(set(refs))
    if not ordered_refs:
        raise LifecycleStateError("acceptance-references-empty")
    documents: dict[str, object] = {}
    raw_digests: dict[str, str] = {}
    identities: dict[str, tuple[int, int, int, int]] = {}
    for ref in ordered_refs:
        identities[ref] = _context_file_identity(root, ref)
        raw = _read_context_bytes(root, ref)
        raw_digests[ref] = hashlib.sha256(raw).hexdigest()
        documents[ref] = _context_digest(raw, ref=ref)
    snapshot = {
        "algorithm": _SNAPSHOT_ALGORITHM,
        "normalization": _SNAPSHOT_NORMALIZATION,
        "at": at,
        "documents": documents,
    }
    return snapshot, raw_digests, identities


def _verify_snapshot_identity(
    root: Path,
    raw_digests: Mapping[str, str],
    identities: Mapping[str, tuple[int, int, int, int]],
) -> None:
    """Re-read every bound file once more before the caller replaces the state."""
    for ref, expected_raw_digest in raw_digests.items():
        raw = _read_context_bytes(root, ref)
        if hashlib.sha256(raw).hexdigest() != expected_raw_digest:
            raise LifecycleStateError(f"context-changed-during-snapshot:{ref}")
        if _context_file_identity(root, ref) != identities[ref]:
            raise LifecycleStateError(f"context-changed-during-snapshot:{ref}")


def capture_requirement(
    *, repo: str | os.PathLike[str] = ".", requirement_id: str, title: str,
    description: str = "", domain: str = "general", priority: str = "P2",
    product_context_ref: str, depends_on: Sequence[str] = (), at: str | None = None,
) -> dict[str, object]:
    root = _repo_root(repo)
    requirement_id = _id(requirement_id, label="requirement-id")
    title = _text(title, label="requirement-title")
    description = _text(description, label="requirement-description", allow_empty=True)
    domain = _text(domain, label="requirement-domain")
    product_context_ref = _context_ref(
        product_context_ref, label="requirement-product-context-ref",
    )
    _require_context_file(root, product_context_ref, label="product-context")
    if priority not in _PRIORITIES:
        raise LifecycleStateError("invalid-requirement-priority")
    dependencies = [_id(item, label="requirement-depends-on-item") for item in depends_on]
    if len(set(dependencies)) != len(dependencies) or requirement_id in dependencies:
        raise LifecycleStateError("invalid-requirement-depends-on")

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        requirements = state["requirements"]
        assert isinstance(requirements, dict)
        if requirement_id in requirements:
            raise LifecycleStateError(f"requirement-already-exists:{requirement_id}")
        missing = [item for item in dependencies if item not in requirements]
        if missing:
            raise LifecycleStateError("unknown-requirement-dependency:" + ",".join(sorted(missing)))
        record = {
            "id": requirement_id, "title": title, "description": description, "domain": domain,
            "priority": priority, "status": "captured", "depends_on": list(dependencies), "feature_id": None,
            "product_context_ref": product_context_ref,
            "created_at": timestamp, "updated_at": timestamp,
        }
        requirements[requirement_id] = record
        return {"operation": "capture-requirement", "requirement": deepcopy(record)}

    return _mutate(root, operation, at=at)


def revise_requirement(
    *, repo: str | os.PathLike[str] = ".", requirement_id: str,
    title: str | None = None, description: str | None = None, domain: str | None = None,
    priority: str | None = None, product_context_ref: str | None = None,
    depends_on: Sequence[str] | None = None, at: str | None = None,
) -> dict[str, object]:
    """Revise an unbound captured requirement without rewriting state by hand."""
    root = _repo_root(repo)
    requirement_id = _id(requirement_id, label="requirement-id")
    if all(value is None for value in (
        title, description, domain, priority, product_context_ref, depends_on,
    )):
        raise LifecycleStateError("requirement-revision-has-no-changes")
    if title is not None:
        title = _text(title, label="requirement-title")
    if description is not None:
        description = _text(description, label="requirement-description", allow_empty=True)
    if domain is not None:
        domain = _text(domain, label="requirement-domain")
    if priority is not None and priority not in _PRIORITIES:
        raise LifecycleStateError("invalid-requirement-priority")
    if product_context_ref is not None:
        product_context_ref = _context_ref(
            product_context_ref, label="requirement-product-context-ref",
        )
        _require_context_file(root, product_context_ref, label="product-context")
    dependencies = None
    if depends_on is not None:
        dependencies = [_id(item, label="requirement-depends-on-item") for item in depends_on]
        if len(set(dependencies)) != len(dependencies) or requirement_id in dependencies:
            raise LifecycleStateError("invalid-requirement-depends-on")

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        requirement = _requirement(state, requirement_id)
        if requirement["status"] != "captured" or requirement["feature_id"] is not None:
            raise LifecycleStateError(f"requirement-not-revisable:{requirement_id}")
        if dependencies is not None:
            requirements = state["requirements"]
            assert isinstance(requirements, dict)
            missing = [item for item in dependencies if item not in requirements]
            if missing:
                raise LifecycleStateError(
                    "unknown-requirement-dependency:" + ",".join(sorted(missing))
                )
            requirement["depends_on"] = list(dependencies)
        for field, value in (
            ("title", title), ("description", description), ("domain", domain),
            ("priority", priority), ("product_context_ref", product_context_ref),
        ):
            if value is not None:
                requirement[field] = value
        requirement["updated_at"] = timestamp
        return {"operation": "revise-requirement", "requirement": deepcopy(requirement)}

    return _mutate(root, operation, at=at)


def cancel_requirement(
    *, repo: str | os.PathLike[str] = ".", requirement_id: str, reason: str,
    at: str | None = None,
) -> dict[str, object]:
    """Cancel an unbound backlog item while retaining its history and context."""
    requirement_id = _id(requirement_id, label="requirement-id")
    reason = _text(reason, label="requirement-cancellation-reason")

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        requirement = _requirement(state, requirement_id)
        if requirement["status"] not in {"captured", "ready"} or requirement["feature_id"] is not None:
            raise LifecycleStateError(f"requirement-not-cancellable:{requirement_id}")
        requirements = state["requirements"]
        assert isinstance(requirements, dict)
        dependents = sorted(
            item_id for item_id, item in requirements.items()
            if item_id != requirement_id
            and isinstance(item, dict)
            and item["status"] != "cancelled"
            and requirement_id in item["depends_on"]
        )
        if dependents:
            raise LifecycleStateError(
                "requirement-has-active-dependents:" + ",".join(dependents)
            )
        requirement["status"] = "cancelled"
        requirement["updated_at"] = timestamp
        return {
            "operation": "cancel-requirement", "reason": reason,
            "requirement": deepcopy(requirement),
        }

    return _mutate(repo, operation, at=at)


def mark_requirement_ready(
    *, repo: str | os.PathLike[str] = ".", requirement_id: str, at: str | None = None,
    refresh_acceptance: bool = False,
) -> dict[str, object]:
    root = _repo_root(repo)
    requirement_id = _id(requirement_id, label="requirement-id")

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        requirement = _requirement(state, requirement_id)
        if refresh_acceptance:
            if requirement["status"] in {"released", "cancelled"}:
                raise LifecycleStateError(f"requirement-not-open-for-refresh:{requirement_id}")
            acceptance = requirement.get("acceptance")
            if not isinstance(acceptance, dict) or "spec_ready" not in acceptance:
                raise LifecycleStateError(f"acceptance-snapshot-missing:{requirement_id}/spec_ready")
        else:
            if requirement["status"] != "captured":
                raise LifecycleStateError(f"requirement-not-captured:{requirement_id}")
            unmet = [item for item in requirement["depends_on"] if _requirement(state, item)["status"] != "released"]
            if unmet:
                raise LifecycleStateError("requirement-dependencies-not-released:" + ",".join(sorted(unmet)))
        snapshot, raw_digests, identities = _build_acceptance_snapshot(
            root, [str(requirement["product_context_ref"])], at=timestamp,
        )
        if not refresh_acceptance:
            requirement["status"] = "ready"
        requirement["updated_at"] = timestamp
        _set_acceptance_snapshot(requirement, "spec_ready", snapshot)
        _verify_snapshot_identity(root, raw_digests, identities)
        return {"operation": "mark-requirement-ready", "requirement": deepcopy(requirement)}

    return _mutate(root, operation, at=at)


def start_feature(
    *, repo: str | os.PathLike[str] = ".", requirement_id: str, feature_id: str, branch: str,
    engineering_context_ref: str, at: str | None = None, refresh_acceptance: bool = False,
) -> dict[str, object]:
    root = _repo_root(repo)
    requirement_id = _id(requirement_id, label="requirement-id")
    feature_id = _id(feature_id, label="feature-id")
    branch = _text(branch, label="feature-branch")
    engineering_context_ref = _context_ref(
        engineering_context_ref, label="feature-engineering-context-ref",
    )
    _require_context_file(root, engineering_context_ref, label="engineering-context")

    def feature_identity_matches(feature: Mapping[str, object]) -> bool:
        return (
            feature["requirement_id"] == requirement_id
            and feature["branch"] == branch
            and feature["engineering_context_ref"] == engineering_context_ref
        )

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        requirement = _requirement(state, requirement_id)
        features = state["features"]
        assert isinstance(features, dict)
        if refresh_acceptance:
            existing = features.get(feature_id)
            if not isinstance(existing, dict):
                raise LifecycleStateError(f"feature-not-found:{feature_id}")
            if existing["status"] in {"released", "cancelled"}:
                raise LifecycleStateError(f"feature-not-open-for-refresh:{feature_id}")
            if (
                not feature_identity_matches(existing)
                or requirement["feature_id"] != feature_id
            ):
                raise LifecycleStateError(f"feature-identity-mismatch:{feature_id}")
            acceptance = existing.get("acceptance")
            if not isinstance(acceptance, dict) or "plan" not in acceptance:
                raise LifecycleStateError(f"acceptance-snapshot-missing:{feature_id}/plan")
            feature = existing
            snapshot, raw_digests, identities = _build_acceptance_snapshot(
                root,
                sorted({str(requirement["product_context_ref"]), engineering_context_ref}),
                at=timestamp,
            )
            feature["updated_at"] = timestamp
            _set_acceptance_snapshot(feature, "plan", snapshot)
            _verify_snapshot_identity(root, raw_digests, identities)
            return {"operation": "start-feature", "feature": deepcopy(feature), "requirement": deepcopy(requirement)}
        if requirement["status"] != "ready" or requirement["feature_id"] is not None:
            raise LifecycleStateError(f"requirement-not-ready-for-feature:{requirement_id}")
        if feature_id in features:
            raise LifecycleStateError(f"feature-already-exists:{feature_id}")
        snapshot, raw_digests, identities = _build_acceptance_snapshot(
            root,
            sorted({str(requirement["product_context_ref"]), engineering_context_ref}),
            at=timestamp,
        )
        record = {
            "id": feature_id, "requirement_id": requirement_id, "branch": branch, "status": "planned", "tasks": {},
            "engineering_context_ref": engineering_context_ref,
            "validation": {"result": "pending", "command": None, "commit": None, "at": None},
            "review": {"decision": "pending", "by": None, "at": None},
            "release": {"status": "pending", "commit": None, "at": None},
            "created_at": timestamp, "updated_at": timestamp,
        }
        _set_acceptance_snapshot(record, "plan", snapshot)
        _verify_snapshot_identity(root, raw_digests, identities)
        features[feature_id] = record
        requirement["feature_id"] = feature_id
        requirement["status"] = "in_delivery"
        requirement["updated_at"] = timestamp
        return {"operation": "start-feature", "feature": deepcopy(record), "requirement": deepcopy(requirement)}

    return _mutate(root, operation, at=at)


def migrate_feature_branch(
    *,
    repo: str | os.PathLike[str] = ".",
    feature_id: str,
    expected_branch: str,
    branch: str,
    expected_head: str,
    reason: str,
    at: str | None = None,
) -> dict[str, object]:
    """Move one open Feature's branch registration to its current checkout.

    This does not checkout code, change delivery progress, or write engineering
    context. The caller records intent and recovery evidence in that context.
    """
    _reject_git_local_environment_for_branch_migration()
    root = _repo_root(repo)
    feature_id = _id(feature_id, label="feature-id")
    expected_branch = _text(expected_branch, label="expected-feature-branch")
    branch = _text(branch, label="feature-branch")
    expected_head = _text(expected_head, label="expected-feature-head")
    reason = _text(reason, label="feature-branch-migration-reason")
    _require_explicit_local_branch(root, branch)
    _current_branch_migration_identity(root, branch=branch, expected_head=expected_head)

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        feature = _feature(state, feature_id)
        if feature["status"] in {"released", "cancelled"}:
            raise LifecycleStateError(f"feature-not-open-for-branch-migration:{feature_id}")
        old_branch = str(feature["branch"])
        if old_branch != expected_branch:
            raise LifecycleStateError(f"feature-branch-does-not-match-expected:{feature_id}")
        if branch == old_branch:
            raise LifecycleStateError("feature-branch-migration-requires-new-branch")

        engineering_context_ref = _context_ref(
            str(feature["engineering_context_ref"]), label="feature-engineering-context-ref",
        )
        _require_context_file(root, engineering_context_ref, label="engineering-context")
        identity = _current_branch_migration_identity(
            root, branch=branch, expected_head=expected_head,
        )
        feature["branch"] = branch
        feature["updated_at"] = timestamp
        final_identity = _current_branch_migration_identity(
            root, branch=branch, expected_head=expected_head,
        )
        if final_identity != identity:
            raise LifecycleStateError("branch-migration-identity-changed-during-operation")
        return {
            "operation": "migrate-feature-branch",
            "feature_id": feature_id,
            "feature": deepcopy(feature),
            "old_branch": old_branch,
            "new_branch": branch,
            "reason": reason,
            "head": final_identity["head"],
            "repo_root": final_identity["repo_root"],
            "at": timestamp,
            "engineering_context_ref": engineering_context_ref,
        }

    return _mutate(root, operation, at=at)


def add_task(
    *, repo: str | os.PathLike[str] = ".", feature_id: str, task_id: str, title: str,
    depends_on: Sequence[str] = (), at: str | None = None,
) -> dict[str, object]:
    feature_id = _id(feature_id, label="feature-id")
    task_id = _id(task_id, label="task-id")
    title = _text(title, label="task-title")
    dependencies = [_id(item, label="task-depends-on-item") for item in depends_on]
    if len(set(dependencies)) != len(dependencies) or task_id in dependencies:
        raise LifecycleStateError("invalid-task-depends-on")

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        feature = _feature(state, feature_id)
        if feature["status"] not in {"planned", "in_progress"}:
            raise LifecycleStateError(f"feature-not-open-for-task:{feature_id}")
        tasks = feature["tasks"]
        assert isinstance(tasks, dict)
        if task_id in tasks:
            raise LifecycleStateError(f"task-already-exists:{feature_id}/{task_id}")
        missing = [item for item in dependencies if item not in tasks]
        if missing:
            raise LifecycleStateError("unknown-task-dependency:" + feature_id + "/" + ",".join(sorted(missing)))
        record = {"id": task_id, "title": title, "status": "todo", "depends_on": list(dependencies), "updated_at": timestamp}
        tasks[task_id] = record
        feature["updated_at"] = timestamp
        return {"operation": "add-task", "task": deepcopy(record), "feature_id": feature_id}

    return _mutate(repo, operation, at=at)


def _reset_delivery_checks(feature: dict[str, object]) -> None:
    feature["validation"] = {"result": "pending", "command": None, "commit": None, "at": None}
    feature["review"] = {"decision": "pending", "by": None, "at": None}
    feature["release"] = {"status": "pending", "commit": None, "at": None}
    # The pass records these snapshots attest are revoked with the checks.
    _clear_acceptance_snapshot(feature, "validation", "review")


def _unmet_task_dependencies(task: Mapping[str, object], tasks: Mapping[str, object]) -> list[str]:
    dependencies = task["depends_on"]
    assert isinstance(dependencies, list)
    unmet: list[str] = []
    for dependency in dependencies:
        dependency_task = tasks[str(dependency)]
        assert isinstance(dependency_task, Mapping)
        if dependency_task["status"] != "done":
            unmet.append(str(dependency))
    return sorted(unmet)


def _available_task_transitions(
    feature: Mapping[str, object], task: Mapping[str, object], tasks: Mapping[str, object],
) -> list[str]:
    if feature["status"] in {"released", "cancelled"}:
        return []

    current_status = str(task["status"])
    available = set(_TASK_TRANSITIONS[current_status])
    if _unmet_task_dependencies(task, tasks):
        available.difference_update({"in_progress", "done"})
    return sorted(available)


def _task_status_rejection(
    code: str,
    *,
    feature_id: str,
    task_id: str,
    current_status: str | None,
    requested_status: str,
    allowed_next: list[str],
    message: str,
    hint: str,
    effect: str,
    feature_status: str | None = None,
    unmet_dependencies: list[str] | None = None,
) -> LifecycleStateError:
    details: dict[str, object] = {
        "message": message,
        "hint": hint,
        "effect": effect,
        "operation": "set-task-status",
        "feature_id": feature_id,
        "task_id": task_id,
        "current_status": current_status,
        "requested_status": requested_status,
        "allowed_next": allowed_next,
        "state_changed": False,
    }
    if feature_status is not None:
        details["feature_status"] = feature_status
    if unmet_dependencies:
        details["unmet_dependencies"] = unmet_dependencies
    return LifecycleStateError(code, details=details)


def _unknown_task_status_details(
    *, feature_id: str, task_id: str, requested_status: str,
) -> dict[str, object]:
    return {
        "message": "无法确认 Task 状态写入是否完成。",
        "hint": "先运行 feature-projection 和 next 只读查询当前状态，再决定是否继续操作。",
        "effect": "本次操作的写入结果未知；不要根据退出码或错误名称推断状态未变化。",
        "operation": "set-task-status",
        "feature_id": feature_id,
        "task_id": task_id,
        "current_status": None,
        "requested_status": requested_status,
        "allowed_next": None,
        "state_changed": "unknown",
    }


def set_task_status(
    *, repo: str | os.PathLike[str] = ".", feature_id: str, task_id: str, status: str,
    at: str | None = None,
) -> dict[str, object]:
    feature_id = _id(feature_id, label="feature-id")
    task_id = _id(task_id, label="task-id")
    if status not in _TASK_STATUSES:
        raise LifecycleStateError("invalid-task-status")

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        feature = _feature(state, feature_id)
        tasks = feature["tasks"]
        assert isinstance(tasks, dict)
        task = tasks.get(task_id)
        current_status = str(task["status"]) if isinstance(task, dict) else None
        if feature["status"] in {"released", "cancelled"}:
            raise _task_status_rejection(
                f"feature-not-open-for-task:{feature_id}",
                feature_id=feature_id,
                task_id=task_id,
                current_status=current_status,
                requested_status=status,
                allowed_next=[],
                message="Feature 已关闭，不能修改其中的 Task。",
                hint="先运行 feature-projection 和 next 只读确认历史状态与后续工作。",
                effect="本次拒绝未写入状态，对现有状态和交付检查无影响。",
                feature_status=str(feature["status"]),
            )
        if not isinstance(task, dict):
            raise LifecycleStateError(f"task-not-found:{feature_id}/{task_id}")
        old_status = str(task["status"])
        if status == old_status:
            return {"operation": "set-task-status", "idempotent": True, "task": deepcopy(task), "feature_id": feature_id}
        if status not in _TASK_TRANSITIONS[old_status]:
            reopens_completed_task = old_status == "done" and status == "in_progress"
            hint = "请从 allowed_next 选择下一状态；必要时先读取 feature-projection 和 next。"
            effect = "本次拒绝未写入状态，对现有状态和交付检查无影响。"
            if reopens_completed_task:
                hint = "请先将 Task 从 done 转为 todo，读取 next 并确认依赖完成后，才能转为 in_progress。"
                effect = (
                    "本次拒绝未写入状态。若改为 done → todo，会清除该 Feature 的 validation、review "
                    "和 release 记录，之后需重新完成交付检查。"
                )
            raise _task_status_rejection(
                f"invalid-task-transition:{old_status}->{status}",
                feature_id=feature_id,
                task_id=task_id,
                current_status=old_status,
                requested_status=status,
                allowed_next=_available_task_transitions(feature, task, tasks),
                message="任务状态转换不被允许。",
                hint=hint,
                effect=effect,
                feature_status=str(feature["status"]),
            )
        if status in {"in_progress", "done"}:
            unmet = _unmet_task_dependencies(task, tasks)
            if unmet:
                raise _task_status_rejection(
                    "task-dependencies-not-done:" + feature_id + "/" + ",".join(unmet),
                    feature_id=feature_id,
                    task_id=task_id,
                    current_status=old_status,
                    requested_status=status,
                    allowed_next=_available_task_transitions(feature, task, tasks),
                    message="任务依赖尚未完成。",
                    hint="先完成 unmet_dependencies 中的 Task，读取 next 后再启动或完成当前 Task。",
                    effect="本次拒绝未写入状态，对现有状态和交付检查无影响。",
                    feature_status=str(feature["status"]),
                    unmet_dependencies=unmet,
                )
        task["status"] = status
        task["updated_at"] = timestamp
        if status != "done" or old_status == "done":
            _reset_delivery_checks(feature)
        feature["status"] = "in_progress"
        feature["updated_at"] = timestamp
        requirement = _requirement(state, str(feature["requirement_id"]))
        requirement["status"] = "in_delivery"
        requirement["updated_at"] = timestamp
        return {"operation": "set-task-status", "idempotent": False, "task": deepcopy(task), "feature_id": feature_id}

    return _mutate(repo, operation, at=at)


def record_validation(
    *, repo: str | os.PathLike[str] = ".", feature_id: str, result: str, command: str | None = None,
    commit: str | None = None, at: str | None = None,
) -> dict[str, object]:
    feature_id = _id(feature_id, label="feature-id")
    if result not in {"pass", "fail"}:
        raise LifecycleStateError("invalid-feature-validation-result")
    command = None if command is None else _text(command, label="feature-validation-command")
    supplied_commit = None if commit is None else _text(commit, label="feature-validation-commit")
    root = _repo_root(repo)

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        feature = _feature(state, feature_id)
        head = _code_head(root, state, feature)
        if supplied_commit is not None and supplied_commit != head:
            raise LifecycleStateError("validation-commit-does-not-match-head")
        if feature["status"] in {"released", "cancelled"}:
            raise LifecycleStateError(f"feature-not-open-for-validation:{feature_id}")
        tasks = feature["tasks"]
        assert isinstance(tasks, dict)
        active_tasks = [task for task in tasks.values() if task["status"] != "cancelled"]
        if result == "pass" and (
            not active_tasks or any(task["status"] != "done" for task in active_tasks)
        ):
            raise LifecycleStateError(f"feature-has-incomplete-active-tasks:{feature_id}")
        requirement = _requirement(state, str(feature["requirement_id"]))
        validation_snapshot: dict[str, object] | None = None
        raw_digests: dict[str, str] | None = None
        snapshot_identities: dict[str, tuple[int, int, int, int]] | None = None
        if result == "pass":
            validation_snapshot, raw_digests, snapshot_identities = _build_acceptance_snapshot(
                root,
                sorted({str(requirement["product_context_ref"]), str(feature["engineering_context_ref"])}),
                at=timestamp,
            )
        feature["validation"] = {"result": result, "command": command, "commit": head, "at": timestamp}
        feature["review"] = {"decision": "pending", "by": None, "at": None}
        feature["release"] = {"status": "pending", "commit": None, "at": None}
        if result == "pass":
            _set_acceptance_snapshot(feature, "validation", validation_snapshot)
        else:
            # A failed validation cannot keep a passing fingerprint.
            _clear_acceptance_snapshot(feature, "validation")
        # The previous approval is revoked together with the review record.
        _clear_acceptance_snapshot(feature, "review")
        feature["status"] = "validated" if result == "pass" else "in_progress"
        feature["updated_at"] = timestamp
        requirement["status"] = "validated" if result == "pass" else "in_delivery"
        requirement["updated_at"] = timestamp
        if raw_digests is not None and snapshot_identities is not None:
            _verify_snapshot_identity(root, raw_digests, snapshot_identities)
        return {"operation": "record-validation", "feature": deepcopy(feature)}

    return _mutate(root, operation, at=at)


def record_review(
    *, repo: str | os.PathLike[str] = ".", feature_id: str, decision: str, by: str | None = None,
    at: str | None = None,
) -> dict[str, object]:
    feature_id = _id(feature_id, label="feature-id")
    if decision not in {"approved", "changes_requested"}:
        raise LifecycleStateError("invalid-feature-review-decision")
    by = None if by is None else _text(by, label="feature-review-by")
    root = _repo_root(repo)

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        feature = _feature(state, feature_id)
        head = _code_head(root, state, feature)
        if feature["status"] not in {"validated", "reviewed"}:
            raise LifecycleStateError(f"feature-not-ready-for-review:{feature_id}")
        validation = feature["validation"]
        validated_commit = str(validation["commit"])
        if not _implementation_unchanged(root, validated_commit, head):
            raise LifecycleStateError("review-commit-does-not-match-validation")
        requirement = _requirement(state, str(feature["requirement_id"]))
        review_snapshot: dict[str, object] | None = None
        raw_digests: dict[str, str] | None = None
        snapshot_identities: dict[str, tuple[int, int, int, int]] | None = None
        if decision == "approved":
            review_snapshot, raw_digests, snapshot_identities = _build_acceptance_snapshot(
                root,
                sorted({str(requirement["product_context_ref"]), str(feature["engineering_context_ref"])}),
                at=timestamp,
            )
        feature["review"] = {"decision": decision, "by": by, "at": timestamp}
        feature["release"] = {"status": "pending", "commit": None, "at": None}
        if decision == "approved":
            _set_acceptance_snapshot(feature, "review", review_snapshot)
        else:
            _clear_acceptance_snapshot(feature, "review")
        feature["status"] = "reviewed" if decision == "approved" else "in_progress"
        feature["updated_at"] = timestamp
        requirement["status"] = "validated" if decision == "approved" else "in_delivery"
        requirement["updated_at"] = timestamp
        if raw_digests is not None and snapshot_identities is not None:
            _verify_snapshot_identity(root, raw_digests, snapshot_identities)
        return {
            "operation": "record-review", "feature": deepcopy(feature),
            "requirement": deepcopy(requirement),
        }

    return _mutate(root, operation, at=at)


def record_release(
    *, repo: str | os.PathLike[str] = ".", feature_id: str, commit: str | None = None,
    at: str | None = None,
) -> dict[str, object]:
    feature_id = _id(feature_id, label="feature-id")
    supplied_commit = None if commit is None else _text(commit, label="feature-release-commit")
    root = _repo_root(repo)

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        feature = _feature(state, feature_id)
        head = _code_head(root, state, feature)
        if feature["status"] != "reviewed":
            raise LifecycleStateError(f"feature-not-ready-for-release:{feature_id}")
        validation = feature["validation"]
        validated_commit = str(validation["commit"])
        if supplied_commit is not None and supplied_commit != validated_commit:
            raise LifecycleStateError("release-commit-does-not-match-validation")
        if not _implementation_unchanged(root, validated_commit, head):
            raise LifecycleStateError("release-commit-does-not-match-validation")
        feature["release"] = {
            "status": "released", "commit": validated_commit, "at": timestamp,
        }
        feature["status"] = "released"
        feature["updated_at"] = timestamp
        requirement = _requirement(state, str(feature["requirement_id"]))
        requirement["status"] = "released"
        requirement["updated_at"] = timestamp
        return {"operation": "record-release", "feature": deepcopy(feature), "requirement": deepcopy(requirement)}

    return _mutate(root, operation, at=at)


def retract_release(
    *, repo: str | os.PathLike[str] = ".", feature_id: str, reason: str,
    at: str | None = None,
) -> dict[str, object]:
    """Correct a release record that did not represent a completed deployment.

    Git retains the prior record and the corrective commit. Long-form incident
    evidence belongs in the Feature engineering context; ``reason`` is required
    so CLI/audit output can state why the correction was made without expanding
    the lightweight state schema.
    """
    feature_id = _id(feature_id, label="feature-id")
    reason = _text(reason, label="release-retraction-reason")
    root = _repo_root(repo)

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        feature = _feature(state, feature_id)
        if feature["status"] != "released" or feature["release"]["status"] != "released":
            raise LifecycleStateError(f"feature-not-released:{feature_id}")
        _code_head(root, state, feature)
        feature["release"] = {"status": "pending", "commit": None, "at": None}
        feature["status"] = "reviewed"
        feature["updated_at"] = timestamp
        requirement = _requirement(state, str(feature["requirement_id"]))
        requirement["status"] = "validated"
        requirement["updated_at"] = timestamp
        return {
            "operation": "retract-release",
            "reason": reason,
            "feature": deepcopy(feature),
            "requirement": deepcopy(requirement),
        }

    return _mutate(root, operation, at=at)


def readyqueue(repo: str | os.PathLike[str] = ".") -> list[dict[str, object]]:
    state = load(repo)
    requirements = state["requirements"]
    assert isinstance(requirements, dict)
    result = [{
        "requirement_id": requirement_id,
        "title": record["title"],
        "priority": record["priority"],
        "domain": record["domain"],
        "status": record["status"],
        "product_context_ref": record["product_context_ref"],
    } for requirement_id, record in requirements.items()
              if record["status"] == "ready" and record["feature_id"] is None]
    result.sort(key=lambda item: (_PRIORITY_ORDER[str(item["priority"])], str(item["requirement_id"])))
    return result


def product_projection(*, repo: str | os.PathLike[str] = ".", requirement_id: str) -> dict[str, object]:
    state = load(repo)
    requirement = _requirement(state, _id(requirement_id, label="requirement-id"))
    feature_id = requirement["feature_id"]
    feature = None if feature_id is None else _feature(state, str(feature_id))
    return {"requirement": deepcopy(requirement), "feature": deepcopy(feature)}


def feature_projection(*, repo: str | os.PathLike[str] = ".", feature_id: str) -> dict[str, object]:
    state = load(repo)
    feature = _feature(state, _id(feature_id, label="feature-id"))
    requirement = _requirement(state, str(feature["requirement_id"]))
    return {"feature": deepcopy(feature), "requirement": deepcopy(requirement)}


def _compare_snapshot_with_current(
    root: Path, snapshot: Mapping[str, object], refs: Sequence[str],
) -> tuple[bool, list[dict[str, object]]]:
    expected_documents = snapshot["documents"]
    assert isinstance(expected_documents, Mapping)
    current_refs = set(refs)
    files: list[dict[str, object]] = []
    is_stale = False
    for ref in sorted(set(expected_documents) | current_refs):
        expected = expected_documents.get(ref)
        current_digest: str | None = None
        if ref in current_refs:
            raw = _read_verification_context_bytes(root, ref)
            if raw is not None:
                confirmation = _read_verification_context_bytes(root, ref)
                if confirmation is None or hashlib.sha256(confirmation).hexdigest() != hashlib.sha256(raw).hexdigest():
                    raise LifecycleStateError(f"context-changed-during-verification:{ref}")
                current_digest = _context_digest(raw, ref=ref)
        if ref not in expected_documents:
            reason = "ref-added"
            is_stale = True
        elif ref not in current_refs:
            reason = "ref-removed"
            is_stale = True
        elif current_digest is None:
            reason = "missing-file"
            is_stale = True
        elif current_digest != expected:
            reason = "content-drift"
            is_stale = True
        else:
            reason = "match"
        files.append({
            "path": ref,
            "expected_digest": expected,
            "current_digest": current_digest,
            "reason": reason,
        })
    return is_stale, files


def verify_acceptance(
    *, repo: str | os.PathLike[str] = ".", requirement_id: str | None = None,
    feature_id: str | None = None, point: str | None = None,
) -> dict[str, object]:
    """Read-only acceptance fingerprint comparison; this writes nothing."""
    if (requirement_id is None) == (feature_id is None):
        raise LifecycleStateError("invalid-acceptance-target")
    if point is not None and point not in _ACCEPTANCE_POINT_ORDER:
        raise LifecycleStateError(f"invalid-acceptance-point:{point}")
    root = _repo_root(repo)
    state = _read_state(root)
    if requirement_id is not None:
        if point is not None and point != "spec_ready":
            raise LifecycleStateError(f"invalid-acceptance-point:{point}")
        requirement = _requirement(state, _id(requirement_id, label="requirement-id"))
        target_type = "requirement"
        target_id = str(requirement["id"])
        product_ref = str(requirement["product_context_ref"])
        engineering_ref = None
        sources = [("spec_ready", requirement)]
    else:
        feature = _feature(state, _id(feature_id, label="feature-id"))
        requirement = _requirement(state, str(feature["requirement_id"]))
        target_type = "feature"
        target_id = str(feature["id"])
        product_ref = str(requirement["product_context_ref"])
        engineering_ref = str(feature["engineering_context_ref"])
        if point is None:
            sources = [
                ("spec_ready", requirement), ("plan", feature),
                ("validation", feature), ("review", feature),
            ]
        elif point == "spec_ready":
            sources = [("spec_ready", requirement)]
        else:
            sources = [(point, feature)]
    points: list[dict[str, object]] = []
    for point_name, record in sources:
        if point_name == "spec_ready":
            refs = [product_ref]
        else:
            assert engineering_ref is not None
            refs = sorted({product_ref, engineering_ref})
        acceptance = record.get("acceptance")
        snapshot = acceptance.get(point_name) if isinstance(acceptance, Mapping) else None
        if snapshot is None:
            points.append({"point": point_name, "result": "missing", "files": []})
            continue
        is_stale, files = _compare_snapshot_with_current(root, snapshot, refs)
        points.append({"point": point_name, "result": "stale" if is_stale else "match", "files": files})
    results = {item["result"] for item in points}
    overall = "stale" if "stale" in results else ("missing" if "missing" in results else "match")
    return {"target_type": target_type, "target_id": target_id, "result": overall, "points": points}


def _feature_next_stage(feature: Mapping[str, object]) -> tuple[str, str]:
    status_value = str(feature["status"])
    tasks = feature["tasks"]
    review = feature["review"]
    assert isinstance(tasks, Mapping) and isinstance(review, Mapping)
    if status_value == "planned":
        if not tasks:
            return "plan", "feature-needs-task-plan"
        return "build", "planned-tasks-are-ready"
    if status_value == "in_progress":
        if review["decision"] == "changes_requested":
            return "build", "review-requested-changes"
        if any(task["status"] == "blocked" for task in tasks.values()):
            return "build", "blocked-tasks-require-work"
        active_tasks = [task for task in tasks.values() if task["status"] != "cancelled"]
        if active_tasks and all(task["status"] == "done" for task in active_tasks):
            return "validate", "all-active-tasks-are-complete"
        return "build", "feature-has-incomplete-tasks"
    if status_value == "validated":
        return "review", "validation-passed"
    if status_value == "reviewed":
        return "ship", "review-approved"
    raise LifecycleStateError(f"feature-has-no-next-stage:{feature['id']}")


def next_action(repo: str | os.PathLike[str] = ".") -> dict[str, object]:
    """Return one deterministic stage, or explicit candidates when selection is needed."""
    state = load(repo)
    requirements = state["requirements"]
    features = state["features"]
    assert isinstance(requirements, dict) and isinstance(features, dict)

    active_features = [
        feature for feature in features.values()
        if feature["status"] not in {"released", "cancelled"}
    ]
    active_features.sort(key=lambda feature: (
        _PRIORITY_ORDER[str(requirements[str(feature["requirement_id"])]["priority"])],
        str(feature["requirement_id"]),
        str(feature["id"]),
    ))
    if len(active_features) > 1:
        candidates = []
        for feature in active_features:
            stage, _ = _feature_next_stage(feature)
            candidates.append({
                "requirement_id": feature["requirement_id"],
                "feature_id": feature["id"],
                "stage": stage,
            })
        return {
            "stage": "needs_selection", "requirement_id": None, "feature_id": None,
            "reason": "multiple-active-features", "candidates": candidates,
        }
    if active_features:
        feature = active_features[0]
        stage, reason = _feature_next_stage(feature)
        return {
            "stage": stage, "requirement_id": feature["requirement_id"], "feature_id": feature["id"],
            "reason": reason, "candidates": [],
        }

    def pending(status_value: str) -> list[dict[str, object]]:
        records = [
            requirement for requirement in requirements.values()
            if requirement["status"] == status_value and requirement["feature_id"] is None
        ]
        records.sort(key=lambda requirement: (
            _PRIORITY_ORDER[str(requirement["priority"])], str(requirement["id"]),
        ))
        return records

    for requirement_status, stage, reason in (
        ("ready", "plan", "requirement-ready-for-engineering"),
        ("captured", "spec", "requirement-needs-product-definition"),
    ):
        records = pending(requirement_status)
        if len(records) > 1:
            return {
                "stage": "needs_selection", "requirement_id": None, "feature_id": None,
                "reason": f"multiple-{requirement_status}-requirements",
                "candidates": [
                    {"requirement_id": requirement["id"], "feature_id": None, "stage": stage}
                    for requirement in records
                ],
            }
        if records:
            return {
                "stage": stage, "requirement_id": records[0]["id"], "feature_id": None,
                "reason": reason, "candidates": [],
            }

    if requirements:
        return {
            "stage": "done", "requirement_id": None, "feature_id": None,
            "reason": "all-requirements-are-terminal", "candidates": [],
        }
    return {
        "stage": "intake", "requirement_id": None, "feature_id": None,
        "reason": "no-requirements-captured", "candidates": [],
    }


def status(repo: str | os.PathLike[str] = ".") -> dict[str, object]:
    root = _repo_root(repo)
    state = _read_state(root)
    requirements = state["requirements"]
    features = state["features"]
    assert isinstance(requirements, dict) and isinstance(features, dict)
    git_status = _state_git_status(root)
    return {
        "state_format": STATE_FORMAT,
        "state_version": STATE_VERSION,
        "state_path": str(_state_directory(root, create=False) / STATE_FILENAME),
        "git": git_status,
        "requirements": len(requirements),
        "features": len(features),
        "ready_requirements": len(readyqueue(root)),
    }


def _split_ids(value: str) -> list[str]:
    if not value:
        return []
    result = [item.strip() for item in value.split(",") if item.strip()]
    if len(set(result)) != len(result):
        raise LifecycleStateError("duplicate-id-list-item")
    return result


def _emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _emit_error_details(details: Mapping[str, object]) -> None:
    rendered = json.dumps(details, ensure_ascii=False, sort_keys=True)
    print(f"error-details: {rendered}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Git-tracked lightweight SDLC lifecycle state")
    parser.add_argument("--repo", default=".", help="target repository root")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="create .sdlc-v1/state.json")
    init.add_argument("--at")
    commands.add_parser("status", help="show state summary")
    capture = commands.add_parser("capture-requirement", help="capture a product requirement")
    capture.add_argument("--id", required=True)
    capture.add_argument("--title", required=True)
    capture.add_argument("--description", default="")
    capture.add_argument("--domain", default="general")
    capture.add_argument("--priority", default="P2", choices=sorted(_PRIORITIES))
    capture.add_argument("--product-context-ref", required=True)
    capture.add_argument("--depends-on", default="", help="comma-separated requirement IDs")
    capture.add_argument("--at")
    revise = commands.add_parser("revise-requirement", help="revise an unbound captured requirement")
    revise.add_argument("--requirement-id", required=True)
    revise.add_argument("--title")
    revise.add_argument("--description")
    revise.add_argument("--domain")
    revise.add_argument("--priority", choices=sorted(_PRIORITIES))
    revise.add_argument("--product-context-ref")
    revise.add_argument(
        "--depends-on", default=None,
        help="comma-separated requirement IDs; pass an empty value to clear dependencies",
    )
    revise.add_argument("--at")
    cancel = commands.add_parser("cancel-requirement", help="cancel an unbound backlog requirement")
    cancel.add_argument("--requirement-id", required=True)
    cancel.add_argument("--reason", required=True)
    cancel.add_argument("--at")
    ready = commands.add_parser("mark-requirement-ready", help="mark a captured requirement ready for delivery")
    ready.add_argument("--requirement-id", required=True)
    ready.add_argument(
        "--refresh-acceptance", action="store_true",
        help="re-record the existing spec_ready fingerprint after renewed approval; changes no progress",
    )
    ready.add_argument("--at")
    start = commands.add_parser("start-feature", help="link a ready requirement to one feature branch")
    start.add_argument("--requirement-id", required=True)
    start.add_argument("--feature-id", required=True)
    start.add_argument("--branch", required=True)
    start.add_argument("--engineering-context-ref", required=True)
    start.add_argument(
        "--refresh-acceptance", action="store_true",
        help="re-record the existing plan fingerprint after renewed approval; creates no feature",
    )
    start.add_argument("--at")
    add = commands.add_parser("add-task", help="add a delivery task")
    add.add_argument("--feature-id", required=True)
    add.add_argument("--task-id", required=True)
    add.add_argument("--title", required=True)
    add.add_argument("--depends-on", default="", help="comma-separated task IDs")
    add.add_argument("--at")
    task = commands.add_parser("set-task-status", help="update one task")
    task.add_argument("--feature-id", required=True)
    task.add_argument("--task-id", required=True)
    task.add_argument("--status", required=True, choices=sorted(_TASK_STATUSES))
    task.add_argument("--at")
    validation = commands.add_parser("record-validation", help="record the feature test result")
    validation.add_argument("--feature-id", required=True)
    validation.add_argument("--result", required=True, choices=("pass", "fail"))
    validation.add_argument("--test-command")
    validation.add_argument("--commit")
    validation.add_argument("--at")
    review = commands.add_parser("record-review", help="record the feature review result")
    review.add_argument("--feature-id", required=True)
    review.add_argument("--decision", required=True, choices=("approved", "changes_requested"))
    review.add_argument("--by")
    review.add_argument("--at")
    release = commands.add_parser("record-release", help="record a completed release")
    release.add_argument("--feature-id", required=True)
    release.add_argument("--commit")
    release.add_argument("--at")
    retract = commands.add_parser("retract-release", help="correct a release record without a completed deployment")
    retract.add_argument("--feature-id", required=True)
    retract.add_argument("--reason", required=True)
    retract.add_argument("--at")
    migrate_branch = commands.add_parser(
        "migrate-feature-branch",
        help="update an open Feature registration for its current checkout branch",
        description=(
            "Update only an open Feature's stored branch registration. This command does not "
            "checkout code, accept delivery work, or edit engineering context."
        ),
    )
    migrate_branch.add_argument(
        "--feature-id",
        required=True,
        help="open Feature whose registration changes",
    )
    migrate_branch.add_argument(
        "--expected-branch",
        required=True,
        help="exact branch value currently stored for that Feature",
    )
    migrate_branch.add_argument(
        "--branch",
        required=True,
        help="explicit local branch already checked out in this worktree",
    )
    migrate_branch.add_argument(
        "--expected-head",
        required=True,
        help="full current commit ID expected in this worktree",
    )
    migrate_branch.add_argument(
        "--reason",
        required=True,
        help="pre-recorded migration decision in the Feature engineering context",
    )
    migrate_branch.add_argument("--at", help="optional operation timestamp")
    commands.add_parser("readyqueue", help="list requirements ready for delivery")
    commands.add_parser("next", help="show the next lifecycle stage")
    product = commands.add_parser("product-projection", help="show one requirement and its feature")
    product.add_argument("--requirement-id", required=True)
    feature = commands.add_parser("feature-projection", help="show one feature and its requirement")
    feature.add_argument("--feature-id", required=True)
    verify = commands.add_parser(
        "verify-acceptance",
        help="compare recorded acceptance fingerprints with current context content",
        description=(
            "Read-only check of the content fingerprints recorded at acceptance time. "
            "This command writes nothing and exits 1 when a checked point is stale."
        ),
    )
    verify_target = verify.add_mutually_exclusive_group(required=True)
    verify_target.add_argument(
        "--requirement-id", help="check this requirement's spec_ready acceptance point",
    )
    verify_target.add_argument(
        "--feature-id",
        help="check this feature's acceptance points; spec_ready uses the linked requirement",
    )
    verify.add_argument(
        "--point", choices=_ACCEPTANCE_POINT_ORDER,
        help="check a single acceptance point instead of the default set",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            result = initialize(args.repo, at=args.at)
        elif args.command == "status":
            result = status(args.repo)
        elif args.command == "capture-requirement":
            result = capture_requirement(
                repo=args.repo, requirement_id=args.id, title=args.title, description=args.description,
                domain=args.domain, priority=args.priority, product_context_ref=args.product_context_ref,
                depends_on=_split_ids(args.depends_on), at=args.at,
            )
        elif args.command == "revise-requirement":
            result = revise_requirement(
                repo=args.repo, requirement_id=args.requirement_id, title=args.title,
                description=args.description, domain=args.domain, priority=args.priority,
                product_context_ref=args.product_context_ref,
                depends_on=None if args.depends_on is None else _split_ids(args.depends_on),
                at=args.at,
            )
        elif args.command == "cancel-requirement":
            result = cancel_requirement(
                repo=args.repo, requirement_id=args.requirement_id, reason=args.reason, at=args.at,
            )
        elif args.command == "mark-requirement-ready":
            result = mark_requirement_ready(
                repo=args.repo, requirement_id=args.requirement_id,
                at=args.at, refresh_acceptance=args.refresh_acceptance,
            )
        elif args.command == "start-feature":
            result = start_feature(
                repo=args.repo, requirement_id=args.requirement_id, feature_id=args.feature_id,
                branch=args.branch, engineering_context_ref=args.engineering_context_ref,
                at=args.at, refresh_acceptance=args.refresh_acceptance,
            )
        elif args.command == "add-task":
            result = add_task(
                repo=args.repo, feature_id=args.feature_id, task_id=args.task_id, title=args.title,
                depends_on=_split_ids(args.depends_on), at=args.at,
            )
        elif args.command == "set-task-status":
            result = set_task_status(
                repo=args.repo, feature_id=args.feature_id, task_id=args.task_id, status=args.status, at=args.at,
            )
        elif args.command == "record-validation":
            result = record_validation(
                repo=args.repo, feature_id=args.feature_id, result=args.result, command=args.test_command,
                commit=args.commit, at=args.at,
            )
        elif args.command == "record-review":
            result = record_review(
                repo=args.repo, feature_id=args.feature_id, decision=args.decision, by=args.by, at=args.at,
            )
        elif args.command == "record-release":
            result = record_release(repo=args.repo, feature_id=args.feature_id, commit=args.commit, at=args.at)
        elif args.command == "retract-release":
            result = retract_release(
                repo=args.repo, feature_id=args.feature_id, reason=args.reason, at=args.at,
            )
        elif args.command == "migrate-feature-branch":
            result = migrate_feature_branch(
                repo=args.repo,
                feature_id=args.feature_id,
                expected_branch=args.expected_branch,
                branch=args.branch,
                expected_head=args.expected_head,
                reason=args.reason,
                at=args.at,
            )
        elif args.command == "readyqueue":
            result = readyqueue(args.repo)
        elif args.command == "next":
            result = next_action(args.repo)
        elif args.command == "product-projection":
            result = product_projection(repo=args.repo, requirement_id=args.requirement_id)
        elif args.command == "verify-acceptance":
            result = verify_acceptance(
                repo=args.repo, requirement_id=args.requirement_id,
                feature_id=args.feature_id, point=args.point,
            )
        else:
            result = feature_projection(repo=args.repo, feature_id=args.feature_id)
    except LifecycleStateError as exc:
        print(f"lifecycle-state-error: {exc}", file=sys.stderr)
        if args.command == "set-task-status":
            details = exc.details or _unknown_task_status_details(
                feature_id=args.feature_id,
                task_id=args.task_id,
                requested_status=args.status,
            )
            _emit_error_details(details)
        return 2
    _emit(result)
    if args.command == "verify-acceptance":
        return 1 if result["result"] == "stale" else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "LifecycleStateError", "STATE_DIRECTORY", "STATE_FILENAME", "STATE_FORMAT", "STATE_VERSION",
    "add_task", "cancel_requirement", "capture_requirement", "feature_projection", "initialize", "load", "main",
    "mark_requirement_ready", "migrate_feature_branch", "next_action", "product_projection", "readyqueue",
    "record_release", "retract_release",
    "record_review", "record_validation", "revise_requirement", "set_task_status", "start_feature", "state_path", "status",
    "verify_acceptance",
]
