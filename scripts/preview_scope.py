#!/usr/bin/env python3
"""Fail-closed detection for Phase 1 preview-only artifacts.

The legacy control ledger cannot infer provenance after callers strip it.  This
module therefore rejects every explicit preview marker at the input boundary;
it deliberately has no control-store dependency so both API and CLI adapters
can use the same check.
"""
from __future__ import annotations

from collections.abc import Mapping
import os
import re


PREVIEW_SCOPE = "preview"
SHADOW_PLAN_FORMAT = "shadow-delivery-plan-v1"
_PREVIEW_PATH_RE = re.compile(r"(?:^|/)\.sdlc/preview(?:/|$|[?#])")
_PREVIEW_SCOPE_RE = re.compile(
    r"(?:^|[?&#,{\s])scope\s*(?:=|:)\s*(?:[\"']preview[\"']|preview)(?=$|[\s,}&])",
    re.IGNORECASE,
)


class PreviewScopeError(ValueError):
    """A preview-only artifact was offered to a legacy authority boundary."""


def preview_reason(value: object) -> str | None:
    """Return a stable reason when ``value`` explicitly identifies preview data."""
    if isinstance(value, (list, tuple, set, frozenset)):
        return next((reason for item in value if (reason := preview_reason(item))), None)
    if isinstance(value, Mapping):
        scope = value.get("scope")
        if isinstance(scope, str) and scope.strip().lower() == PREVIEW_SCOPE:
            return "preview-scope"
        for field in ("plan_format", "format", "schema"):
            if value.get(field) == SHADOW_PLAN_FORMAT:
                return "shadow-delivery-plan"
        return next((reason for item in value.values() if (reason := preview_reason(item))), None)
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    if not isinstance(value, str):
        return None
    normalized = value.replace("\\", "/")
    if _PREVIEW_PATH_RE.search(normalized):
        return "preview-path"
    if _PREVIEW_SCOPE_RE.search(value):
        return "preview-scope"
    if SHADOW_PLAN_FORMAT in value:
        return "shadow-delivery-plan"
    return None


def is_preview(value: object) -> bool:
    """Whether a value carries an explicit Phase 1 preview marker."""
    return preview_reason(value) is not None


def reject_preview(value: object, *, field: str,
                   error_cls: type[Exception] = PreviewScopeError) -> None:
    """Raise the caller's domain error when a preview-only input is supplied."""
    reason = preview_reason(value)
    if reason:
        raise error_cls(f"{field} cannot reference Phase 1 preview data: {reason}")
