#!/usr/bin/env python3
"""Read-only backlog projections for ``.sdlc-v1/state.json``.

This module never stores or changes progress. It renders the canonical
lifecycle state as a ready queue, coverage summary, tree, lint result, or HTML
board. Product and engineering context remain ordinary Markdown files.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
from typing import Mapping, Sequence


def discover_lifecycle_state_repo(start: str | Path = ".") -> Path:
    """Find the nearest enclosing repository with ``.sdlc-v1/state.json``."""
    candidate = Path(start).resolve(strict=False)
    if candidate.is_file():
        candidate = candidate.parent
    for directory in (candidate, *candidate.parents):
        state = directory / ".sdlc-v1" / "state.json"
        if state.is_symlink():
            raise RuntimeError(f"state-file-cannot-be-symlink:{state}")
        if state.is_file():
            return directory
    raise RuntimeError(f"state-not-initialized-from:{candidate}")


def load_projection(start: str | Path = ".") -> tuple[Path, dict[str, object]]:
    repo = discover_lifecycle_state_repo(start)
    try:
        from lifecycle_state import LifecycleStateError, load

        return repo, load(repo)
    except (ImportError, LifecycleStateError) as exc:
        raise RuntimeError(str(exc)) from exc


def ready_items(state: Mapping[str, object]) -> list[dict[str, object]]:
    requirements = state["requirements"]
    assert isinstance(requirements, Mapping)
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    items = [
        {
            "requirement_id": requirement["id"],
            "title": requirement["title"],
            "domain": requirement["domain"],
            "priority": requirement["priority"],
            "status": requirement["status"],
            "product_context_ref": requirement["product_context_ref"],
        }
        for requirement in requirements.values()
        if requirement["status"] == "ready" and requirement["feature_id"] is None
    ]
    items.sort(key=lambda item: (priority_order[str(item["priority"])], str(item["requirement_id"])))
    return items


def coverage_projection(state: Mapping[str, object]) -> dict[str, object]:
    requirements = state["requirements"]
    assert isinstance(requirements, Mapping)
    domains: dict[str, dict[str, object]] = {}
    total_statuses: Counter[str] = Counter()
    for requirement in requirements.values():
        domain = str(requirement["domain"])
        status_value = str(requirement["status"])
        summary = domains.setdefault(domain, {"total": 0, "by_status": {}})
        summary["total"] = int(summary["total"]) + 1
        by_status = summary["by_status"]
        assert isinstance(by_status, dict)
        by_status[status_value] = int(by_status.get(status_value, 0)) + 1
        total_statuses[status_value] += 1
    return {
        "total": len(requirements),
        "by_status": dict(sorted(total_statuses.items())),
        "domains": {key: domains[key] for key in sorted(domains)},
    }


def tree_projection(state: Mapping[str, object]) -> dict[str, object]:
    requirements = state["requirements"]
    features = state["features"]
    assert isinstance(requirements, Mapping) and isinstance(features, Mapping)
    domains: dict[str, list[dict[str, object]]] = {}
    for requirement_id, requirement in requirements.items():
        feature_id = requirement["feature_id"]
        feature = features.get(feature_id) if feature_id is not None else None
        tasks = []
        if isinstance(feature, Mapping):
            feature_tasks = feature["tasks"]
            assert isinstance(feature_tasks, Mapping)
            tasks = [dict(task) for _, task in sorted(feature_tasks.items())]
        item = {
            "requirement_id": requirement_id,
            "title": requirement["title"],
            "priority": requirement["priority"],
            "status": requirement["status"],
            "product_context_ref": requirement["product_context_ref"],
            "feature": None if not isinstance(feature, Mapping) else {
                "feature_id": feature["id"],
                "status": feature["status"],
                "branch": feature["branch"],
                "engineering_context_ref": feature["engineering_context_ref"],
                "tasks": tasks,
            },
        }
        domains.setdefault(str(requirement["domain"]), []).append(item)
    for items in domains.values():
        items.sort(key=lambda item: str(item["requirement_id"]))
    coverage = coverage_projection(state)
    return {
        "domains": [
            {"domain": domain, "requirements": domains[domain]}
            for domain in sorted(domains)
        ],
        "summary": {
            "total": coverage["total"],
            "by_status": coverage["by_status"],
            "ready_count": len(ready_items(state)),
        },
    }


def _is_git_tracked(repo: Path, relative: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--error-unmatch", "--", relative],
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.returncode == 0


def lint_projection(repo: Path, state: Mapping[str, object]) -> list[str]:
    """Check only cross-clone essentials; schema/dependencies are checked on load."""
    problems: list[str] = []
    state_ref = ".sdlc-v1/state.json"
    if not _is_git_tracked(repo, state_ref):
        problems.append(f"untracked:{state_ref}")
    requirements = state["requirements"]
    features = state["features"]
    assert isinstance(requirements, Mapping) and isinstance(features, Mapping)
    refs = [str(requirement["product_context_ref"]) for requirement in requirements.values()]
    refs.extend(str(feature["engineering_context_ref"]) for feature in features.values())
    for ref in sorted(set(refs)):
        path = repo / ref
        if path.is_symlink():
            problems.append(f"symlink-context:{ref}")
        elif not path.is_file():
            problems.append(f"missing-context:{ref}")
        elif not _is_git_tracked(repo, ref):
            problems.append(f"untracked:{ref}")
    return problems


def _emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="read-only projections of lightweight SDLC state")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("readyqueue", "coverage", "lint", "tree"):
        command = commands.add_parser(name)
        command.add_argument("--root", default=".", help="repository or any path inside it")
    board = commands.add_parser("board")
    board.add_argument("--root", default=".", help="repository or any path inside it")
    board.add_argument("--out", required=True)
    board.add_argument("--title", default="SDLC backlog")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repo, state = load_projection(args.root)
        if args.command == "readyqueue":
            _emit(ready_items(state))
        elif args.command == "coverage":
            _emit(coverage_projection(state))
        elif args.command == "tree":
            _emit(tree_projection(state))
        elif args.command == "lint":
            problems = lint_projection(repo, state)
            if problems:
                for problem in problems:
                    print(problem, file=sys.stderr)
                return 1
            print("lint: clean")
        else:
            import board

            board.write_board(repo, state, Path(args.out), title=args.title)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"backlog-error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "coverage_projection", "discover_lifecycle_state_repo", "lint_projection", "load_projection",
    "main", "ready_items", "tree_projection",
]
