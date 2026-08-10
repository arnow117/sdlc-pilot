#!/usr/bin/env python3
"""Static HTML board for the lightweight SDLC state."""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Mapping


_CSS = """
:root{color-scheme:light dark;--bg:#f5f6f8;--panel:#fff;--ink:#18202b;--muted:#677386;
--line:#dfe3e8;--accent:#356ae6;--done:#25855a;--warn:#b76b00}
@media(prefers-color-scheme:dark){:root{--bg:#11151b;--panel:#1a2029;--ink:#edf1f7;
--muted:#a8b2c1;--line:#303846;--accent:#7da2ff;--done:#66c99a;--warn:#f0b35c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:1180px;margin:auto;padding:32px 22px 64px}h1{font-size:28px;margin:0 0 6px}
.source{color:var(--muted);word-break:break-all}.summary{display:flex;gap:8px;flex-wrap:wrap;margin:22px 0}
.chip,.badge{border:1px solid var(--line);border-radius:999px;padding:4px 9px;background:var(--panel)}
.domains{display:grid;gap:24px}.domain h2{font-size:19px;margin:0 0 10px}.cards{display:grid;
grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:12px}.card{background:var(--panel);
border:1px solid var(--line);border-radius:10px;padding:15px;min-width:0}.card-head{display:flex;
align-items:flex-start;justify-content:space-between;gap:8px}.id{font-weight:700;color:var(--accent)}
.title{font-size:16px;font-weight:650;margin:7px 0 12px}.meta{display:grid;grid-template-columns:88px 1fr;
gap:5px 9px;color:var(--muted)}.meta b{color:var(--ink);font-weight:600}.path{font-family:ui-monospace,
SFMono-Regular,Menlo,monospace;font-size:12px;word-break:break-all}.feature{border-top:1px solid var(--line);
margin-top:13px;padding-top:12px}.tasks{margin:9px 0 0;padding-left:20px}.tasks li{margin:3px 0}
.status-released,.status-done{color:var(--done)}.status-blocked{color:var(--warn)}
.empty{padding:30px;background:var(--panel);border:1px dashed var(--line);border-radius:10px;color:var(--muted)}
"""


def _status_class(status: object) -> str:
    value = str(status).replace("_", "-")
    safe = "".join(character for character in value if character.isalnum() or character == "-")
    return f"status-{safe}"


def render_board(tree: Mapping[str, object], *, title: str, source: str) -> str:
    summary = tree["summary"]
    domains = tree["domains"]
    assert isinstance(summary, Mapping) and isinstance(domains, list)
    by_status = summary["by_status"]
    assert isinstance(by_status, Mapping)
    chips = [f'<span class="chip">total {int(summary["total"])}</span>']
    chips.extend(
        f'<span class="chip {escape(_status_class(status))}">{escape(str(status))} {int(count)}</span>'
        for status, count in sorted(by_status.items())
    )
    chips.append(f'<span class="chip">ready {int(summary["ready_count"])}</span>')

    domain_sections: list[str] = []
    for domain in domains:
        assert isinstance(domain, Mapping)
        cards: list[str] = []
        requirements = domain["requirements"]
        assert isinstance(requirements, list)
        for requirement in requirements:
            assert isinstance(requirement, Mapping)
            feature = requirement["feature"]
            feature_html = ""
            if isinstance(feature, Mapping):
                tasks = feature["tasks"]
                assert isinstance(tasks, list)
                task_items = "".join(
                    '<li><span class="path">{}</span> — <span class="{}">{}</span>: {}</li>'.format(
                        escape(str(task["id"])),
                        escape(_status_class(task["status"])),
                        escape(str(task["status"])),
                        escape(str(task["title"])),
                    )
                    for task in tasks
                    if isinstance(task, Mapping)
                )
                tasks_html = f'<ul class="tasks">{task_items}</ul>' if task_items else '<div class="source">No tasks yet</div>'
                feature_html = (
                    '<div class="feature">'
                    '<div class="card-head"><span class="id">{feature_id}</span>'
                    '<span class="badge {feature_class}">{feature_status}</span></div>'
                    '<div class="meta"><b>branch</b><span class="path">{branch}</span>'
                    '<b>engineering</b><span class="path">{engineering}</span></div>{tasks}</div>'
                ).format(
                    feature_id=escape(str(feature["feature_id"])),
                    feature_class=escape(_status_class(feature["status"])),
                    feature_status=escape(str(feature["status"])),
                    branch=escape(str(feature["branch"])),
                    engineering=escape(str(feature["engineering_context_ref"])),
                    tasks=tasks_html,
                )
            cards.append(
                (
                    '<article class="card"><div class="card-head"><span class="id">{requirement_id}</span>'
                    '<span class="badge {requirement_class}">{status}</span></div>'
                    '<div class="title">{title}</div><div class="meta">'
                    '<b>priority</b><span>{priority}</span>'
                    '<b>product</b><span class="path">{product}</span></div>{feature}</article>'
                ).format(
                    requirement_id=escape(str(requirement["requirement_id"])),
                    requirement_class=escape(_status_class(requirement["status"])),
                    status=escape(str(requirement["status"])),
                    title=escape(str(requirement["title"])),
                    priority=escape(str(requirement["priority"])),
                    product=escape(str(requirement["product_context_ref"])),
                    feature=feature_html,
                )
            )
        domain_sections.append(
            f'<section class="domain"><h2>{escape(str(domain["domain"]))}</h2>'
            f'<div class="cards">{"".join(cards)}</div></section>'
        )
    content = '<div class="domains">' + "".join(domain_sections) + "</div>" if domain_sections else (
        '<div class="empty">No requirements captured.</div>'
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{escape(title)}</title><style>{_CSS}</style></head><body><main>'
        f'<h1>{escape(title)}</h1><div class="source">Source: {escape(source)}/.sdlc-v1/state.json</div>'
        f'<div class="summary">{"".join(chips)}</div>{content}</main></body></html>\n'
    )


def write_board(repo: Path, state: Mapping[str, object], output: Path, *, title: str = "SDLC backlog") -> Path:
    from backlog import tree_projection

    destination = output.expanduser().resolve(strict=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        render_board(tree_projection(state), title=title, source=str(repo)), encoding="utf-8",
    )
    return destination


__all__ = ["render_board", "write_board"]
