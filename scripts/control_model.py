#!/usr/bin/env python3
"""Pure helpers and compatibility API for SDLC control records."""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Any, Iterable, Mapping

import control_store
from control_store import SchemaError


def find_cycle(nodes: dict[str, list[str]]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        if node in visiting:
            return stack[stack.index(node):] + [node]
        if node in visited:
            return None
        visiting.add(node)
        stack.append(node)
        for dependency in nodes.get(node, []):
            if dependency in nodes:
                cycle = visit(dependency)
                if cycle:
                    return cycle
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for node in nodes:
        cycle = visit(node)
        if cycle:
            return cycle
    return None


def render_control_record(fields: dict[str, Any], body: str = "",
                          field_order: list[str] | None = None) -> str:
    return control_store.render_record(fields, body=body, field_order=field_order)


def atomic_write_record(path: str | os.PathLike[str], fields: dict[str, Any],
                        body: str = "", create_only: bool = False) -> bool:
    return control_store.write_record(path, fields, body=body, immutable=create_only)


def load_control_snapshot_from_files(
        files: Mapping[str, str] | Iterable[tuple[str, str]]) -> dict[str, Any]:
    """Load an in-memory path/text collection through the normal strict loader."""
    entries = files.items() if isinstance(files, Mapping) else files
    with tempfile.TemporaryDirectory(prefix="sdlc-control-files-") as tmp:
        root = Path(tmp) / control_store.CONTROL_DIR
        for raw_path, text in entries:
            parts = PurePosixPath(str(raw_path)).parts
            if parts and parts[0] == control_store.CONTROL_DIR:
                parts = parts[1:]
            target = control_store.safe_record_path(root, *parts)
            control_store.write_text_atomic(target, text)
        return control_store.load_control_snapshot(root, mode="local-serial")


_TASK_HEADING = re.compile(r"^### Task\s+[^:]+:", re.MULTILINE)
_TASK_FIELD = re.compile(r"^- \*\*([a-z_]+)\*\*:\s*(.*)$", re.MULTILINE)
_REQUIRED_TASK_FIELDS = {
    "id", "requirements", "depends_on_tasks", "write_set", "interface_owner",
    "interfaces_fixed", "runtime_isolated", "read_first", "action", "acceptance_criteria",
}


def _parse_value(value: str) -> Any:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [item.strip().strip("`") for item in inner.split(",") if item.strip()]
    if value in {"true", "false"}:
        return value == "true"
    return value.strip("`")


def parse_plan_tasks(plan_text: str) -> list[dict[str, Any]]:
    """Parse strict Task field blocks from an approved Markdown plan."""
    matches = list(_TASK_HEADING.finditer(plan_text))
    tasks: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(plan_text)
        block = plan_text[match.end():end]
        fields = {key: _parse_value(value) for key, value in _TASK_FIELD.findall(block)}
        missing = sorted(_REQUIRED_TASK_FIELDS - fields.keys())
        if missing:
            raise SchemaError(f"plan task missing fields: {missing}")
        fields["task_id"] = fields.pop("id")
        tasks.append(fields)
    if not tasks:
        raise SchemaError("plan contains no Task blocks")
    ids = [str(task["task_id"]) for task in tasks]
    if len(ids) != len(set(ids)):
        raise SchemaError("plan contains duplicate task ids")
    graph = {str(task["task_id"]): list(task["depends_on_tasks"]) for task in tasks}
    unknown = sorted({dep for deps in graph.values() for dep in deps if dep not in graph})
    if unknown:
        raise SchemaError(f"plan task dependencies are missing: {unknown}")
    cycle = find_cycle(graph)
    if cycle:
        raise SchemaError("plan task dependency cycle: " + " -> ".join(cycle))
    return tasks


def derive_task_readiness(snapshot: dict[str, Any], feature_id: str) -> dict[str, str]:
    tasks = {str(task["task_id"]): task
             for task in snapshot.get("tasks_by_feature", {}).get(feature_id, [])}
    return {
        task_id: ("ready" if all(tasks.get(dep, {}).get("status") == "verified"
                                  for dep in task.get("depends_on_tasks", [])) else "waiting")
        if task.get("status") in {"waiting", "ready"} else str(task.get("status"))
        for task_id, task in tasks.items()
    }
