#!/usr/bin/env python3
"""Strict, config-derived authority for the dual-lifecycle canonical ledger.

``authority.json`` is the only source of a principal and authorization policy.
Callers may provide the approval subject and decision intent, but cannot inject
identity or policy material through the adapter APIs in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Sequence

import approval


AUTHORITY_FORMAT = "dual-lifecycle-authority-v1"
CHANGE_REQUEST_ACTIONS = frozenset({"accept", "reject", "cancel"})

_TOP_LEVEL_FIELDS = frozenset(
    {
        "authority_format",
        "authority_mode",
        "principal",
        "policies",
        "change_request_policy",
    }
)
_PRINCIPAL_FIELDS = frozenset(
    {
        "authority_mode",
        "principal_ref",
        "roles",
        "authn_method",
        "authn_assurance",
    }
)
_POLICY_FIELDS = frozenset(
    {
        "policy_id",
        "allowed_roles",
        "min_authn_assurance",
        "subject_type",
        "scope",
    }
)
_CHANGE_REQUEST_POLICY_FIELDS = frozenset(
    {"allowed_roles", "min_authn_assurance"}
)
_CALLER_AUTHORITY_FIELDS = frozenset(
    {
        "authority_format",
        "authority_mode",
        "principal",
        "principal_ref",
        "principal_role",
        "roles",
        "authn_method",
        "authn_assurance",
        "policy",
        "policies",
        "policy_id",
        "authorization_policy",
        "authorization_policy_ref",
        "allowed_roles",
        "min_authn_assurance",
        "change_request_policy",
    }
)
_CHANGE_REQUEST_SUBJECT = {
    "subject_type": "change_request",
    "scope": "change_request",
    "subject_id": "configured-change-request-authority",
    "subject_ref": "configured-change-request-authority",
    "subject_revision": "configured-change-request-authority",
    "subject_sha256": "0" * 64,
}


class AuthorityConfigError(ValueError):
    """The canonical authority configuration or authority use is invalid."""


@dataclass(frozen=True)
class ConfiguredPrincipal:
    """The static ``principal`` object from ``authority.json``."""

    authority_mode: str
    principal_ref: str
    roles: tuple[str, ...]
    authn_method: str
    authn_assurance: str

    def as_approval_config(self) -> dict[str, object]:
        """Return a fresh config object with the exact ``approval`` schema."""
        return {
            "authority_mode": self.authority_mode,
            "principal_ref": self.principal_ref,
            "roles": list(self.roles),
            "authn_method": self.authn_method,
            "authn_assurance": self.authn_assurance,
        }


@dataclass(frozen=True)
class ChangeRequestPolicy:
    """Static role and assurance rule applied to accept/reject/cancel actions."""

    allowed_roles: tuple[str, ...]
    min_authn_assurance: str

    def as_authorization_policy(self) -> approval.AuthorizationPolicy:
        """Adapt the fixed CR rule to the shared approval authorization API."""
        return approval.AuthorizationPolicy(
            policy_id="change-request-transition-policy-v1",
            allowed_roles=self.allowed_roles,
            min_authn_assurance=self.min_authn_assurance,
        )


@dataclass(frozen=True)
class AuthorityConfig:
    """Validated immutable representation of canonical ``authority.json``."""

    authority_mode: str
    principal: ConfiguredPrincipal
    policies: tuple[approval.AuthorizationPolicy, ...]
    change_request_policy: ChangeRequestPolicy


def parse_config_bytes(payload: bytes) -> AuthorityConfig:
    """Parse a UTF-8 JSON ``authority.json`` with duplicate/unknown fields rejected."""
    if not isinstance(payload, bytes):
        raise AuthorityConfigError("authority-config-must-be-bytes")
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuthorityConfigError("authority-config-not-utf8") from exc
    try:
        raw = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_json_fields,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, AuthorityConfigError) as exc:
        if isinstance(exc, AuthorityConfigError):
            raise
        raise AuthorityConfigError("invalid-authority-config-json") from exc
    return _parse_config(raw)


def load_config(path: str | Path) -> AuthorityConfig:
    """Read and parse a canonical authority configuration file."""
    try:
        payload = Path(path).read_bytes()
    except (OSError, TypeError) as exc:
        raise AuthorityConfigError("cannot-read-authority-config") from exc
    return parse_config_bytes(payload)


def resolve_configured_principal(
    config: AuthorityConfig, *, caller_payload: Mapping[str, object] | None = None
) -> approval.Principal:
    """Resolve identity exclusively from the static principal configuration."""
    _require_config(config)
    _reject_caller_authority_fields(caller_payload)
    try:
        return approval.resolve_principal(
            authority_mode=config.authority_mode,
            authority_config=config.principal.as_approval_config(),
        )
    except approval.ApprovalError as exc:
        raise AuthorityConfigError(str(exc)) from exc


def select_policy(
    config: AuthorityConfig,
    *,
    subject_type: str,
    scope: str,
    caller_payload: Mapping[str, object] | None = None,
) -> approval.AuthorizationPolicy:
    """Return the one configured policy exactly matching a subject type and scope."""
    _require_config(config)
    _reject_caller_authority_fields(caller_payload)
    normalized_subject_type = _nonempty_text(subject_type, "subject-type")
    normalized_scope = _nonempty_text(scope, "scope")
    matches = tuple(
        policy
        for policy in config.policies
        if policy.subject_type == normalized_subject_type and policy.scope == normalized_scope
    )
    if len(matches) != 1:
        label = "missing" if not matches else "ambiguous"
        raise AuthorityConfigError(
            f"{label}-authorization-policy:{normalized_subject_type}:{normalized_scope}"
        )
    return matches[0]


def build_configured_approval(
    config: AuthorityConfig,
    *,
    subject: Mapping[str, object],
    decision: str,
    previous_approval_ref: str | None,
    decision_intent_ref: str,
    decided_at: str,
    resolves_change_requests: Sequence[str] = (),
    caller_payload: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build an approval using only the configured principal and matching policy."""
    _require_config(config)
    _reject_caller_authority_fields(caller_payload)
    if not isinstance(subject, Mapping):
        raise AuthorityConfigError("invalid-approval-subject")
    policy = select_policy(
        config,
        subject_type=subject.get("subject_type"),
        scope=subject.get("scope"),
    )
    principal = resolve_configured_principal(config)
    try:
        return approval.build_approval(
            subject=subject,
            decision=decision,
            previous_approval_ref=previous_approval_ref,
            authorization_policy=policy,
            principal=principal,
            decision_intent_ref=decision_intent_ref,
            decided_at=decided_at,
            resolves_change_requests=resolves_change_requests,
        )
    except approval.ApprovalError as exc:
        raise AuthorityConfigError(str(exc)) from exc


def authorize_change_request(
    config: AuthorityConfig,
    *,
    action: str,
    caller_payload: Mapping[str, object] | None = None,
) -> str:
    """Verify the configured principal may accept, reject, or cancel a CR.

    The returned value is the configured principal role that authorized the
    requested action.  The single static CR policy intentionally governs all
    three actions; callers cannot provide a replacement role or policy.
    """
    _require_config(config)
    _reject_caller_authority_fields(caller_payload)
    if not isinstance(action, str) or action not in CHANGE_REQUEST_ACTIONS:
        raise AuthorityConfigError("invalid-change-request-action")
    principal = resolve_configured_principal(config)
    try:
        return approval.authorize(
            _CHANGE_REQUEST_SUBJECT,
            principal,
            config.change_request_policy.as_authorization_policy(),
        )
    except approval.ApprovalError as exc:
        raise AuthorityConfigError(str(exc)) from exc


def _parse_config(value: object) -> AuthorityConfig:
    source = _strict_object(value, "authority-config", _TOP_LEVEL_FIELDS)
    authority_format = _nonempty_text(source["authority_format"], "authority-format")
    if authority_format != AUTHORITY_FORMAT:
        raise AuthorityConfigError("unsupported-authority-format")
    authority_mode = _nonempty_text(source["authority_mode"], "authority-mode")
    principal = _parse_principal(source["principal"], authority_mode)
    policies = _parse_policies(source["policies"])
    change_request_policy = _parse_change_request_policy(source["change_request_policy"])
    return AuthorityConfig(
        authority_mode=authority_mode,
        principal=principal,
        policies=policies,
        change_request_policy=change_request_policy,
    )


def _parse_principal(value: object, authority_mode: str) -> ConfiguredPrincipal:
    source = _strict_object(value, "principal", _PRINCIPAL_FIELDS)
    nested_mode = _nonempty_text(source["authority_mode"], "principal-authority-mode")
    if nested_mode != authority_mode:
        raise AuthorityConfigError("authority-mode-principal-mismatch")
    _nonempty_text(source["principal_ref"], "principal-ref")
    _nonempty_string_list(source["roles"], "principal-roles")
    _nonempty_text(source["authn_method"], "authn-method")
    _nonempty_text(source["authn_assurance"], "authn-assurance")
    try:
        resolved = approval.resolve_principal(
            authority_mode=authority_mode,
            authority_config=dict(source),
        )
    except approval.ApprovalError as exc:
        raise AuthorityConfigError(str(exc)) from exc
    return ConfiguredPrincipal(
        authority_mode=authority_mode,
        principal_ref=resolved.principal_ref,
        roles=resolved.roles,
        authn_method=resolved.authn_method,
        authn_assurance=resolved.authn_assurance,
    )


def _parse_policies(value: object) -> tuple[approval.AuthorizationPolicy, ...]:
    if not isinstance(value, list) or not value:
        raise AuthorityConfigError("invalid-policies")
    policies: list[approval.AuthorizationPolicy] = []
    policy_ids: set[str] = set()
    targets: set[tuple[str, str]] = set()
    for index, raw_policy in enumerate(value):
        source = _strict_object(raw_policy, f"policy-{index}", _POLICY_FIELDS)
        _nonempty_text(source["policy_id"], f"policy-{index}-id")
        _nonempty_string_list(source["allowed_roles"], f"policy-{index}-allowed-roles")
        _nonempty_text(source["min_authn_assurance"], f"policy-{index}-assurance")
        subject_type = _nonempty_text(source["subject_type"], f"policy-{index}-subject-type")
        scope = _nonempty_text(source["scope"], f"policy-{index}-scope")
        try:
            policy = approval.parse_authorization_policy(dict(source))
        except approval.ApprovalError as exc:
            raise AuthorityConfigError(str(exc)) from exc
        if policy.policy_id in policy_ids:
            raise AuthorityConfigError(f"duplicate-policy-id:{policy.policy_id}")
        target = (subject_type, scope)
        if target in targets:
            raise AuthorityConfigError(
                f"duplicate-policy-subject-scope:{subject_type}:{scope}"
            )
        policy_ids.add(policy.policy_id)
        targets.add(target)
        policies.append(policy)
    return tuple(policies)


def _parse_change_request_policy(value: object) -> ChangeRequestPolicy:
    source = _strict_object(
        value, "change-request-policy", _CHANGE_REQUEST_POLICY_FIELDS
    )
    _nonempty_string_list(source["allowed_roles"], "change-request-allowed-roles")
    _nonempty_text(source["min_authn_assurance"], "change-request-assurance")
    try:
        parsed = approval.parse_authorization_policy(
            {
                "policy_id": "change-request-transition-policy-v1",
                "allowed_roles": source["allowed_roles"],
                "min_authn_assurance": source["min_authn_assurance"],
            }
        )
    except approval.ApprovalError as exc:
        raise AuthorityConfigError(str(exc)) from exc
    return ChangeRequestPolicy(
        allowed_roles=parsed.allowed_roles,
        min_authn_assurance=parsed.min_authn_assurance,
    )


def _strict_object(
    value: object, label: str, expected_fields: frozenset[str]
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise AuthorityConfigError(f"invalid-{label}")
    fields = set(value)
    if fields != expected_fields:
        unknown = sorted(fields - expected_fields)
        missing = sorted(expected_fields - fields)
        detail = ",".join([*(f"unknown:{item}" for item in unknown), *(f"missing:{item}" for item in missing)])
        raise AuthorityConfigError(f"invalid-{label}-fields:{detail}")
    return value


def _nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthorityConfigError(f"empty-or-invalid-{label}")
    return value


def _nonempty_string_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise AuthorityConfigError(f"invalid-{label}")
    result = tuple(_nonempty_text(item, f"{label}-item") for item in value)
    if len(set(result)) != len(result):
        raise AuthorityConfigError(f"duplicate-{label}")
    return result


def _reject_duplicate_json_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AuthorityConfigError(f"duplicate-json-field:{key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise AuthorityConfigError(f"invalid-json-constant:{value}")


def _reject_caller_authority_fields(
    caller_payload: Mapping[str, object] | None,
) -> None:
    if caller_payload is None:
        return
    if not isinstance(caller_payload, Mapping) or any(
        not isinstance(key, str) for key in caller_payload
    ):
        raise AuthorityConfigError("invalid-caller-payload")
    supplied = sorted(_CALLER_AUTHORITY_FIELDS & set(caller_payload))
    if supplied:
        raise AuthorityConfigError(
            "caller-cannot-supply-authority:" + ",".join(supplied)
        )


def _require_config(value: object) -> AuthorityConfig:
    if not isinstance(value, AuthorityConfig):
        raise AuthorityConfigError("invalid-authority-config")
    return value


__all__ = [
    "AUTHORITY_FORMAT",
    "CHANGE_REQUEST_ACTIONS",
    "AuthorityConfig",
    "AuthorityConfigError",
    "ChangeRequestPolicy",
    "ConfiguredPrincipal",
    "authorize_change_request",
    "build_configured_approval",
    "load_config",
    "parse_config_bytes",
    "resolve_configured_principal",
    "select_policy",
]
