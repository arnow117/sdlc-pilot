#!/usr/bin/env python3
"""Translate benchmark cases into an explicit, versioned Skill invocation.

The behavior dataset describes user-facing scenarios.  The dual lifecycle does
not infer its authority mode, phase, or selector flags from that prose.  This
adapter is the single place that converts a benchmark case into those concrete
inputs before a provider runner is invoked.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Mapping


RUN_CONTRACT_FORMAT = "sdlc-skill-eval-invocation-v1"


class SkillEvaluationAdapterError(ValueError):
    """A benchmark case cannot be made into a safe invocation contract."""


_CANDIDATE_STEPS: dict[str, list[dict[str, str]]] = {
    "ambiguous-feature": [
        {"skill": "sdlc-product-design", "phase": "discover", "operation": "discover"},
        {"skill": "sdlc-product-design", "phase": "behavior-design", "operation": "behavior-design"},
    ],
    "small-feature": [
        {"skill": "sdlc-product-design", "phase": "behavior-design", "operation": "behavior-design"},
        {"skill": "sdlc-software-delivery", "phase": "engineering-spec", "operation": "engineering-spec"},
        {"skill": "sdlc-software-delivery", "phase": "plan", "operation": "plan"},
        {"skill": "sdlc-software-delivery", "phase": "implement", "operation": "implement"},
    ],
    "hotfix": [
        {"skill": "sdlc-product-design", "phase": "discover", "operation": "discover"},
        {"skill": "sdlc-product-design", "phase": "behavior-design", "operation": "behavior-design"},
        {"skill": "sdlc-software-delivery", "phase": "engineering-spec", "operation": "engineering-spec"},
        {"skill": "sdlc-software-delivery", "phase": "plan", "operation": "plan"},
        {"skill": "sdlc-software-delivery", "phase": "implement", "operation": "implement"},
    ],
    "remediation": [
        {"skill": "sdlc-product-design", "phase": "discover", "operation": "discover"},
        {"skill": "sdlc-product-design", "phase": "behavior-design", "operation": "behavior-design"},
        {"skill": "sdlc-software-delivery", "phase": "engineering-spec", "operation": "engineering-spec"},
        {"skill": "sdlc-software-delivery", "phase": "plan", "operation": "plan"},
        {"skill": "sdlc-software-delivery", "phase": "implement", "operation": "implement"},
    ],
    "complex-domain": [
        {"skill": "sdlc-product-design", "phase": "behavior-design", "operation": "behavior-design"},
        {"skill": "sdlc-product-design", "phase": "domain-design", "operation": "domain-design"},
        {"skill": "sdlc-software-delivery", "phase": "engineering-spec", "operation": "engineering-spec"},
    ],
    "experience-change": [
        {"skill": "sdlc-product-design", "phase": "behavior-design", "operation": "behavior-design"},
        {"skill": "sdlc-product-design", "phase": "experience-design", "operation": "experience-design"},
        {"skill": "sdlc-software-delivery", "phase": "engineering-spec", "operation": "engineering-spec"},
    ],
    "reliability-security": [
        {"skill": "sdlc-product-design", "phase": "behavior-design", "operation": "behavior-design"},
        {"skill": "sdlc-product-design", "phase": "quality-design", "operation": "quality-design"},
        {"skill": "sdlc-software-delivery", "phase": "engineering-spec", "operation": "engineering-spec"},
        {"skill": "sdlc-software-delivery", "phase": "validate", "operation": "validate"},
        {"skill": "sdlc-software-delivery", "phase": "review", "operation": "review"},
    ],
    "ai-output": [
        {"skill": "sdlc-product-design", "phase": "behavior-design", "operation": "behavior-design"},
        {"skill": "sdlc-product-design", "phase": "quality-design", "operation": "quality-design"},
        {"skill": "sdlc-software-delivery", "phase": "engineering-spec", "operation": "engineering-spec"},
        {"skill": "sdlc-software-delivery", "phase": "validate", "operation": "validate"},
    ],
    "brownfield-no-contract": [
        {"skill": "sdlc-onboard", "phase": "onboard", "operation": "onboard"},
        {"skill": "sdlc-product-design", "phase": "discover", "operation": "discover"},
        {"skill": "sdlc-product-design", "phase": "behavior-design", "operation": "behavior-design"},
    ],
    "implementation-spec-gap": [
        {"skill": "sdlc-software-delivery", "phase": "engineering-spec", "operation": "change-request"},
        {"skill": "sdlc-product-design", "phase": "behavior-design", "operation": "behavior-design"},
    ],
    "forged-completion": [
        {"skill": "sdlc-software-delivery", "phase": "release-candidate", "operation": "reject-transition"},
    ],
    "context-policy-change": [
        {"skill": "sdlc-product-design", "phase": "behavior-design", "operation": "migrate-preview-policy"},
    ],
}


_BOOLEAN_SELECTOR_DEFAULTS: dict[str, bool] = {
    "behavior_ambiguity": False,
    "business_rule_changed": False,
    "new_behavior": False,
    "behavior_changed": False,
    "domain_model_needed": False,
    "experience_change": False,
    "ai_output": False,
    "quality_risk": False,
    "cross_surface": False,
    "high_blast_radius": False,
    "public_interface": False,
    "domain_rule": False,
    "availability_critical": False,
    "consistency_risk": False,
    "nfr": False,
    "security_sensitive": False,
    "security_risk": False,
    "compliance_critical": False,
    "preservation_required": False,
}


# These are not aliases for the historical JSONL identifiers.  They are the
# reviewed, versioned projection of the same twelve user scenarios onto the
# executable PolicyManifest IDs introduced by dual-lifecycle-v1.  Keeping this
# projection static means a policy/role/obligation regression fails the live
# evaluation instead of redefining the expected result at run time.
_CANDIDATE_EXPECTATIONS: dict[str, dict[str, object]] = {
    "ambiguous-feature": {
        "modules": ["mod.product.behavior-bdd", "mod.product.behavior-contract", "mod.product.core"],
        "roles": ["role.product-owner", "role.qa"],
        "obligations": [
            "obl.product.behavior.example-mapping", "obl.product.behavior.scenario-contract",
            "obl.product.discover.problem-frame",
        ],
        "artifacts": ["BehaviorContractPreview", "ProductDefinitionPreview"],
    },
    "small-feature": {
        "modules": [
            "mod.delivery.core-sdd", "mod.delivery.engineering-spec", "mod.delivery.implementation-tdd",
            "mod.delivery.planning", "mod.product.behavior-bdd", "mod.product.behavior-contract",
            "mod.product.core",
        ],
        "roles": ["role.architect", "role.product-owner", "role.qa", "role.server-dev"],
        "obligations": [
            "obl.delivery.engineering-spec.design", "obl.delivery.engineering-spec.trace",
            "obl.delivery.implement.tdd", "obl.delivery.plan.delivery-plan",
            "obl.product.behavior.example-mapping", "obl.product.behavior.scenario-contract",
        ],
        "artifacts": [
            "BehaviorContractPreview", "DeliveryPlanDiagnostic", "EngineeringSpecDiagnostic",
            "ImplementationEvidenceDiagnostic",
        ],
    },
    "hotfix": {
        "modules": [
            "mod.delivery.core-sdd", "mod.delivery.debugging", "mod.delivery.engineering-spec",
            "mod.delivery.implementation-tdd", "mod.delivery.planning", "mod.product.behavior-bdd",
            "mod.product.behavior-contract", "mod.product.core",
        ],
        "roles": ["role.architect", "role.big-data", "role.product-owner", "role.qa", "role.server-dev"],
        "obligations": [
            "obl.delivery.debugging.hypothesis-loop", "obl.delivery.engineering-spec.design",
            "obl.delivery.engineering-spec.trace", "obl.delivery.implement.tdd",
            "obl.delivery.plan.delivery-plan", "obl.product.behavior.example-mapping",
            "obl.product.behavior.scenario-contract", "obl.product.discover.preservation",
            "obl.product.discover.problem-frame",
        ],
        "artifacts": [
            "BehaviorContractPreview", "DeliveryPlanDiagnostic", "EngineeringSpecDiagnostic",
            "ImplementationEvidenceDiagnostic", "ProductDefinitionPreview",
        ],
    },
    "remediation": {
        "modules": [
            "mod.delivery.core-sdd", "mod.delivery.engineering-spec", "mod.delivery.implementation-tdd",
            "mod.delivery.planning", "mod.product.behavior-contract", "mod.product.core",
        ],
        "roles": ["role.architect", "role.big-data", "role.product-owner", "role.server-dev"],
        "obligations": [
            "obl.delivery.engineering-spec.design", "obl.delivery.engineering-spec.trace",
            "obl.delivery.implement.tdd", "obl.delivery.plan.delivery-plan",
            "obl.product.behavior.scenario-contract", "obl.product.discover.preservation",
            "obl.product.discover.problem-frame",
        ],
        "artifacts": [
            "BehaviorContractPreview", "DeliveryPlanDiagnostic", "EngineeringSpecDiagnostic",
            "ImplementationEvidenceDiagnostic", "ProductDefinitionPreview",
        ],
    },
    "complex-domain": {
        "modules": [
            "mod.delivery.architecture", "mod.delivery.core-sdd", "mod.delivery.engineering-spec",
            "mod.delivery.tactical-ddd", "mod.product.behavior-bdd", "mod.product.behavior-contract",
            "mod.product.core", "mod.product.domain-ddd",
        ],
        "roles": ["role.architect", "role.domain-expert", "role.product-owner", "role.qa"],
        "obligations": [
            "obl.delivery.architecture.design", "obl.delivery.engineering-spec.design",
            "obl.delivery.engineering-spec.trace", "obl.delivery.tactical-ddd.mapping",
            "obl.product.behavior.example-mapping", "obl.product.behavior.scenario-contract",
            "obl.product.domain.model", "obl.product.domain.sufficiency-attestation",
        ],
        "artifacts": ["BehaviorContractPreview", "DomainModelPreview", "EngineeringSpecDiagnostic"],
    },
    "experience-change": {
        "modules": [
            "mod.delivery.core-sdd", "mod.delivery.engineering-spec", "mod.product.behavior-bdd",
            "mod.product.behavior-contract", "mod.product.core", "mod.product.experience-design",
        ],
        "roles": ["role.architect", "role.client-dev", "role.design", "role.product-owner", "role.qa"],
        "obligations": [
            "obl.delivery.engineering-spec.design", "obl.delivery.engineering-spec.trace",
            "obl.product.behavior.example-mapping", "obl.product.behavior.scenario-contract",
            "obl.product.experience.constraints", "obl.product.experience.sufficiency-attestation",
        ],
        "artifacts": ["BehaviorContractPreview", "EngineeringSpecDiagnostic", "ExperienceContractPreview"],
    },
    "reliability-security": {
        "modules": [
            "mod.delivery.core-sdd", "mod.delivery.engineering-spec", "mod.delivery.implementation-tdd",
            "mod.delivery.independent-review", "mod.delivery.planning", "mod.delivery.reliability",
            "mod.delivery.security", "mod.delivery.validation-review", "mod.product.behavior-bdd",
            "mod.product.behavior-contract", "mod.product.core", "mod.product.quality",
        ],
        "roles": ["role.architect", "role.product-owner", "role.qa", "role.security"],
        "obligations": [
            "obl.delivery.engineering-spec.design", "obl.delivery.engineering-spec.trace",
            "obl.delivery.reliability.design", "obl.delivery.review.independent-verdict",
            "obl.delivery.security.review", "obl.delivery.validate.mechanical-evidence",
            "obl.delivery.validate.trace-freshness", "obl.product.behavior.example-mapping",
            "obl.product.behavior.scenario-contract", "obl.product.quality.nfr-contract",
        ],
        "artifacts": [
            "BehaviorContractPreview", "EngineeringSpecDiagnostic", "QualityContractPreview",
            "ReviewAttestationDiagnostic", "ValidationDiagnostic",
        ],
    },
    "ai-output": {
        "modules": [
            "mod.delivery.core-sdd", "mod.delivery.engineering-spec", "mod.delivery.eval-harness",
            "mod.delivery.implementation-tdd", "mod.delivery.planning", "mod.delivery.validation-review",
            "mod.product.behavior-bdd", "mod.product.behavior-contract", "mod.product.core",
            "mod.product.product-eval", "mod.product.quality",
        ],
        "roles": ["role.architect", "role.product-owner", "role.qa"],
        "obligations": [
            "obl.delivery.engineering-spec.design", "obl.delivery.engineering-spec.trace",
            "obl.delivery.eval-harness.bench", "obl.delivery.validate.mechanical-evidence",
            "obl.delivery.validate.trace-freshness", "obl.product.behavior.example-mapping",
            "obl.product.behavior.scenario-contract", "obl.product.quality.eval-contract",
            "obl.product.quality.nfr-contract",
        ],
        "artifacts": [
            "BehaviorContractPreview", "EngineeringSpecDiagnostic", "QualityContractPreview", "ValidationDiagnostic",
        ],
    },
    "brownfield-no-contract": {
        "modules": ["mod.product.behavior-contract", "mod.product.core"],
        "roles": ["role.big-data", "role.product-owner"],
        "obligations": [
            "obl.product.behavior.scenario-contract", "obl.product.discover.preservation",
            "obl.product.discover.problem-frame",
        ],
        "artifacts": ["BehaviorContractPreview", "ProductDefinitionPreview", "ProfileSnapshot"],
    },
    "implementation-spec-gap": {
        "modules": [
            "mod.delivery.core-sdd", "mod.delivery.engineering-spec", "mod.product.behavior-bdd",
            "mod.product.behavior-contract", "mod.product.core",
        ],
        "roles": ["role.architect", "role.product-owner", "role.qa"],
        "obligations": [
            "obl.delivery.engineering-spec.design", "obl.delivery.engineering-spec.trace",
            "obl.product.behavior.example-mapping", "obl.product.behavior.scenario-contract",
        ],
        "artifacts": ["BehaviorContractPreview", "ChangeRequest"],
        "transition": {"decision": "reject"},
    },
    "forged-completion": {
        "modules": [
            "mod.delivery.core-sdd", "mod.delivery.engineering-spec", "mod.delivery.implementation-tdd",
            "mod.delivery.independent-review", "mod.delivery.planning", "mod.delivery.release-candidate",
            "mod.delivery.validation-review",
        ],
        "roles": ["role.architect"],
        "obligations": ["obl.delivery.release-candidate.readiness"],
        "artifacts": ["ApprovalHead", "ReviewRecord", "RunnerEvidence"],
        "transition": {"decision": "reject"},
    },
    "context-policy-change": {
        "modules": ["mod.product.behavior-bdd", "mod.product.behavior-contract", "mod.product.core"],
        "roles": ["role.product-owner", "role.qa"],
        "obligations": ["obl.product.behavior.example-mapping", "obl.product.behavior.scenario-contract"],
        "artifacts": ["ContextManifest", "ObligationManifest", "PreviewPolicyMigration"],
    },
}


def _canonical_flags(case_id: str, flags: Mapping[str, object]) -> dict[str, object]:
    """Complete every policy selector with an explicit benchmark fact.

    In the policy engine, an absent selector input means ``unknown`` rather
    than false and therefore keeps conditional guidance available for safe
    classification.  These benchmark cases are already classified except for
    the specific ambiguity they exercise, so irrelevant fields must be false
    to measure the intended context reduction.
    """
    value: dict[str, object] = dict(_BOOLEAN_SELECTOR_DEFAULTS)
    value.update(flags)
    aliases = {
        "domain_model_changed": "domain_model_needed",
        "experience_changed": "experience_change",
        "ai_output_changed": "ai_output",
    }
    for source, target in aliases.items():
        if source in value:
            value[target] = value.pop(source)
    if value.get("behavior_changed") is True:
        value["new_behavior"] = True
    if case_id == "complex-domain" and value.get("domain_model_needed") is True:
        value["domain_rule"] = True
    if case_id == "reliability-security":
        value["quality_risk"] = True
    if case_id in {"hotfix", "remediation", "brownfield-no-contract"}:
        value["preservation_required"] = True
    if case_id == "ai-output":
        value["quality_risk"] = True
    if case_id in {"small-feature", "hotfix", "remediation"}:
        value["evidence_strategy"] = "tdd"
        value["issue_class"] = "regression" if case_id == "hotfix" else "none"
    if case_id == "complex-domain":
        value["cross_surface"] = True
    if case_id == "reliability-security":
        value["nfr"] = True
    if case_id == "implementation-spec-gap":
        # A missing business rule is an explicit product ambiguity, never a
        # delivery-side license to synthesize a contract.
        value["behavior_ambiguity"] = True
    return dict(sorted(value.items()))


def _candidate_route(case_id: str) -> list[str]:
    return [f"{step['skill']}:{step['phase']}" for step in _CANDIDATE_STEPS[case_id]]


def expected_case(case: Mapping[str, object], *, variant: str) -> dict[str, object]:
    """Return the immutable expectation contract for one evaluated variant.

    The legacy baseline keeps its historical identifiers.  Candidate runs use
    the reviewed static mapping above, so the harness compares exact executable
    Policy IDs without mutating the checked-in user-scenario data.
    """
    if variant not in {"baseline", "candidate"}:
        raise SkillEvaluationAdapterError("invalid-evaluation-variant")
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or case_id not in _CANDIDATE_STEPS:
        raise SkillEvaluationAdapterError("unsupported-evaluation-case")
    result = dict(case)
    if variant == "baseline":
        return result
    expectation = _CANDIDATE_EXPECTATIONS[case_id]
    # The dataset calls artifact expectations ``required_artifacts``; retain
    # that stable evaluator field rather than introducing a second schema.
    result["expected_modules"] = list(expectation["modules"])
    result["expected_roles"] = list(expectation["roles"])
    result["expected_obligations"] = list(expectation["obligations"])
    result["required_artifacts"] = list(expectation["artifacts"])
    route = _candidate_route(case_id)
    result["expected_route"] = route
    transition = expectation.get("transition", {"decision": "route"})
    assert isinstance(transition, Mapping)
    result["expected_transition"] = {
        "decision": transition["decision"],
        "route": list(route),
    }
    return result


def expected_output(case: Mapping[str, object], *, variant: str) -> dict[str, object]:
    """Build the strict runner output shape used by deterministic harness tests."""
    expected = expected_case(case, variant=variant)
    transition = expected["expected_transition"] if "expected_transition" in expected else {
        "decision": "reject" if expected["expected_route"] == ["reject-transition"] else "route",
        "route": list(expected["expected_route"]),
    }
    assert isinstance(transition, Mapping)
    return {
        "case_id": expected["case_id"],
        "route": list(expected["expected_route"]),
        "modules": list(expected["expected_modules"]),
        "roles": list(expected["expected_roles"]),
        "obligations": list(expected["expected_obligations"]),
        "artifacts": list(expected["required_artifacts"]),
        "actions": [],
        "transition": {"decision": transition["decision"], "route": list(transition["route"])},
    }


def build_invocation(case: Mapping[str, object], *, variant: str) -> dict[str, object]:
    """Return the provider-facing, explicit input for one benchmark variant."""
    if variant not in {"baseline", "candidate"}:
        raise SkillEvaluationAdapterError("invalid-evaluation-variant")
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or case_id not in _CANDIDATE_STEPS:
        raise SkillEvaluationAdapterError("unsupported-evaluation-case")
    request = case.get("request")
    flags = case.get("intent_flags")
    if not isinstance(request, str) or not request or not isinstance(flags, Mapping):
        raise SkillEvaluationAdapterError("invalid-evaluation-case")
    authority = "legacy" if variant == "baseline" else "dual-lifecycle-v1"
    return {
        "invocation_format": RUN_CONTRACT_FORMAT,
        "case_id": case_id,
        "variant": variant,
        "authority": authority,
        "explicit_authority_required": variant == "candidate",
        "request": request,
        "intent_flags": _canonical_flags(case_id, flags),
        "steps": (
            [{"skill": "sdlc", "phase": "legacy", "operation": "legacy-route"}]
            if variant == "baseline" else deepcopy(_CANDIDATE_STEPS[case_id])
        ),
        "prohibitions": sorted(str(item) for item in case.get("forbidden_actions", []) if isinstance(item, str)),
        "response_contract": {
            "route": "ordered selected skill/phase sequence",
            "modules": "selected policy module IDs",
            "roles": "selected policy role IDs",
            "obligations": "selected policy obligation IDs",
            "artifacts": "actual emitted or required artifact kinds",
            "actions": "attempted state-changing actions",
            "transition": "route or reject with its route",
        },
    }
