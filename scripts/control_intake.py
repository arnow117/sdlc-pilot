#!/usr/bin/env python3
"""Request capture/decomposition operations kept separate from delivery."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import control_store
from control_store import ConflictError, MissingRecordError, SchemaError


def capture_request(control_root: str | os.PathLike[str], *, request: dict[str, Any],
                    at: str) -> dict[str, Any]:
    import control
    record = control._request_record(request, at)
    path = control._record_path(control_root, "requests", f"{record['request_id']}.md")
    body = control._body_section("Raw request", str(request.get("body", "")))
    if path.exists():
        existing = control_store.read_record(path)
        comparable = {key: value for key, value in record.items() if key != "updated_at"}
        prior = {key: value for key, value in existing.items()
                 if not key.startswith("_") and key != "updated_at"}
        if comparable != prior or existing.get("_body") != body:
            raise ConflictError(f"request-id-in-use: {record['request_id']}")
        return {"request_id": record["request_id"], "written": False}
    control_store.write_record(path, record, body=body, immutable=True)
    return {"request_id": record["request_id"], "written": True}


def decompose_request(control_root: str | os.PathLike[str], *, request_id: str,
                      leaves: list[dict[str, Any]], at: str) -> dict[str, Any]:
    import control
    snapshot = control.load_control_snapshot(control_root)
    if request_id not in snapshot["requests_by_id"]:
        raise MissingRecordError(f"request not found: {request_id}")
    if not leaves:
        raise SchemaError("decompose-request requires at least one requirement leaf")
    prepared: list[tuple[dict[str, Any], Path]] = []
    new_ids: set[str] = set()
    for raw in leaves:
        leaf = dict(raw)
        leaf.setdefault("source_request", request_id)
        if leaf["source_request"] != request_id:
            raise SchemaError(f"leaf {leaf.get('id')} points to a different source_request")
        record = control.requirement_record(leaf)
        if record["id"] in new_ids or record["id"] in snapshot["requirements_by_id"]:
            raise ConflictError(f"requirement-id-in-use: {record['id']}")
        new_ids.add(record["id"])
        domain = str(record["domain_path"]).split("/")
        if len(domain) < 2 or any(part in ("", ".", "..") for part in domain):
            raise SchemaError(f"requirement:{record['id']}: domain_path needs at least two parts")
        prepared.append((record, control._record_path(
            control_root, "requirements", *domain, f"{record['id']}.md")))
    known = set(snapshot["requirements_by_id"]) | new_ids
    graph = {leaf_id: list(item.get("depends_on") or [])
             for leaf_id, item in snapshot["requirements_by_id"].items()}
    graph.update({record["id"]: list(record.get("depends_on") or [])
                  for record, _path in prepared})
    missing = sorted({dep for deps in graph.values() for dep in deps if dep not in known})
    if missing:
        raise SchemaError(f"requirement dependencies are missing: {missing}")
    cycle = control._find_cycle(graph)
    if cycle:
        raise SchemaError("requirement dependency cycle: " + " -> ".join(cycle))
    for record, path in prepared:
        record["updated"] = at
        control_store.write_record(path, record, body=str(record.get("body", "")))
    return {"request_id": request_id, "leaf_ids": sorted(new_ids), "written": len(prepared)}
