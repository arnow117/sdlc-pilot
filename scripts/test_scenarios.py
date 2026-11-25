#!/usr/bin/env python3
"""Reusable local fixtures and deterministic oracles, not independent Agent runs."""
from __future__ import annotations

import copy
import io
import json
import os
import shlex
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import lifecycle_state as lifecycle
import test_support

HERE = Path(__file__).resolve().parent
REQ = "REQ-scenario"
FEATURE = "FEAT-scenario"
PROBE_CODE = (
    "from pathlib import Path; import sys; p=Path('required-environment-probe'); "
    "print('present' if p.exists() else 'missing'); sys.exit(0 if p.exists() else 2)"
)
TASKS = {
    "TASK-one": ("Implement parser", []),
    "TASK-two": ("Handle invalid input", ["TASK-one"]),
    "TASK-three": ("Verify output", ["TASK-two"]),
}
REQUESTS = {
    "B01": "Implement a CLI that doubles an integer; invalid input must fail. Complete the delivery.",
    "B02": "Continue. The product choice between decimal and integer output remains open; no choice was delegated.",
    "B03": "Revalidate; the required local environment probe is missing. Preserve implementation and stop before review or ship.",
    "B04A": "Assess existing evidence applicability only; clarify its prose. Do not execute new validation or implementation.",
    "B04B": "Assess existing evidence applicability only. A new invalid-input verification obligation lacks evidence; do not execute validation or implementation. Stop before review or ship.",
    "B05": "Resume interrupted preparation and register all tasks from the accepted plan; stop before Build.",
}
BUSINESS_TEST = '''import subprocess
import sys
import unittest


class DoubleIntegerTest(unittest.TestCase):
    def test_positive_and_negative(self):
        for value, expected in (("3", "6"), ("-4", "-8")):
            result = subprocess.run([sys.executable, "cli.py", value], capture_output=True, text=True)
            self.assertEqual((result.returncode, result.stdout.strip()), (0, expected))

    def test_invalid_input(self):
        result = subprocess.run([sys.executable, "cli.py", "bad"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
'''
INITIAL_CLI = 'print("fixture baseline")\n'
SOLUTION = '''import sys


def main():
    if len(sys.argv) != 2:
        print("expected integer", file=sys.stderr)
        return 2
    try:
        value = int(sys.argv[1])
    except ValueError:
        print("expected integer", file=sys.stderr)
        return 2
    print(value * 2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

# On-demand human acceptance, approval re-record, and release registration.
# The fixtures below exercise the existing CLI's observable behavior only; they
# do not model Agent decisions and never run a real deployment.
HUMAN_FEATURE = "FEAT-human"
HUMAN_TASK = "TASK-human"
HUMAN_OTHER_FEATURE = "FEAT-other"
HUMAN_OTHER_REQUIREMENT = "REQ-other"
HUMAN_OTHER_TASK = "TASK-other"
HUMAN_PRODUCT = (
    "# Product\n\n"
    "Double integer input; invalid input fails. Scope confirmed.\n"
    "One acceptance item needs a person to operate the CLI.\n"
)
HUMAN_ENGINEERING = (
    "# Engineering plan\n\n"
    "- TASK-human: Deliver the doubling CLI and hand the candidate to a person.\n"
)
HUMAN_OTHER_PRODUCT = (
    "# Product\n\n"
    "Double integer input for the second feature. Scope confirmed.\n"
)
HUMAN_OTHER_ENGINEERING = (
    "# Engineering plan\n\n"
    "- TASK-other: Deliver the second feature on the same candidate.\n"
)
# A pure evidence append that keeps the product condition unchanged.
HUMAN_EVIDENCE_APPEND = "\nPrior scripted verification covered the invalid input path.\n"
# A substantive product condition that changes the promised behavior.
HUMAN_SUBSTANTIVE_INSERT = (
    "\nOutput must be a decimal number rather than an integer.\n"
)
# Integration items are ordinary tracked files, so a missing item is a missing
# file rather than a claim about prose.
INTEGRATION_MANIFEST = "integration/required.json"
INTEGRATION_OBSERVATION = ".sdlc-v1/fixture-evidence/observation.json"
INTEGRATION_ITEM_A = "int-a"
INTEGRATION_ITEM_B = "int-b"
# The observation is explicitly a scripted fixture record. It never claims to
# be a human observation, so it cannot stand in for one.
OBSERVATION_KIND = "synthetic"


def integration_manifest() -> str:
    return json.dumps(
        {
            "required": {
                HUMAN_FEATURE: [INTEGRATION_ITEM_A],
                HUMAN_OTHER_FEATURE: [INTEGRATION_ITEM_B],
            }
        },
        indent=2, sort_keys=True,
    ) + "\n"


def integration_evidence(item: str, *, candidate: str, command: str, exit_code: int,
                          stdout: str) -> str:
    """Bind one integration item to the command that actually produced it."""
    return json.dumps(
        {
            "item": item,
            "candidate": candidate,
            "command": command,
            "exit": exit_code,
            "stdout": stdout,
            "evidence": f"the recorded command exited {exit_code} with output {stdout!r}",
        },
        indent=2, sort_keys=True,
    ) + "\n"


def integration_observation(candidate: str, *, conditions: dict) -> str:
    """Build the shared observation that both features can locate."""
    return json.dumps(
        {
            "kind": OBSERVATION_KIND,
            "synthetic": True,
            "disclaimer": "Scripted fixture record. It is not a human observation.",
            "candidate": candidate,
            "observer": "scripted fixture observer",
            "observer_kind": OBSERVATION_KIND,
            "conditions": conditions,
        },
        indent=2, sort_keys=True,
    ) + "\n"


def committed_file(repo: Path, candidate: str, path: str):
    """Read a path as it exists in one candidate commit, or None when absent."""
    result = subprocess.run(
        ["git", "-C", str(repo), "show", f"{candidate}:{path}"], capture_output=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    """Whether one commit is an ancestor of (or equal to) another."""
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True,
    )
    return result.returncode == 0


def fixture_inputs_match(repo: Path, checked: str, candidate: str) -> bool:
    """Compare the business, test, and acceptance inputs of this fixture."""
    result = subprocess.run(
        ["git", "-C", str(repo), "diff", "--quiet", checked, candidate, "--",
         "cli.py", "test_cli.py", INTEGRATION_MANIFEST,
         ".sdlc-v1/context/product.md", ".sdlc-v1/context/engineering.md",
         ".sdlc-v1/context/product-other.md", ".sdlc-v1/context/engineering-other.md"],
        capture_output=True,
    )
    return result.returncode == 0


def integration_evidence_errors(repo: Path, feature_id: str, item: str, *,
                                candidate: str, expected: dict) -> list:
    """Reasons the shared observation cannot serve as evidence for one condition.

    An empty list means the record carries a candidate, an observer, this
    feature's own condition, and a passing result whose source exists in the
    candidate commit and matches the command that actually ran.
    """
    errors = []
    path = repo / INTEGRATION_OBSERVATION
    if not path.exists():
        return [f"{INTEGRATION_OBSERVATION}: the shared observation is missing"]
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        return [f"{INTEGRATION_OBSERVATION}: unreadable observation ({error})"]
    if not isinstance(record, dict) or not record:
        return [f"{INTEGRATION_OBSERVATION}: the observation is an empty object"]
    if record.get("kind") != OBSERVATION_KIND or record.get("synthetic") is not True:
        errors.append(f"{INTEGRATION_OBSERVATION}: the record is not marked as a synthetic observation")
    if record.get("observer_kind") != OBSERVATION_KIND:
        errors.append(f"{INTEGRATION_OBSERVATION}: the observer is not marked as a synthetic observer")
    if not record.get("observer"):
        errors.append(f"{INTEGRATION_OBSERVATION}: no observer is recorded")
    observed = record.get("candidate")
    if observed != candidate:
        # The record is committed after it is written, so the revision it
        # observed may be an ancestor with the same relevant inputs.
        if not observed or not is_ancestor(repo, observed, candidate):
            errors.append(
                f"{INTEGRATION_OBSERVATION}: recorded candidate {observed!r} "
                f"is not the observed candidate {candidate!r} nor one of its ancestors"
            )
        elif not fixture_inputs_match(repo, observed, candidate):
            errors.append(f"{INTEGRATION_OBSERVATION}: inputs changed after the observation")
    conditions = record.get("conditions")
    if not isinstance(conditions, dict):
        errors.append(f"{INTEGRATION_OBSERVATION}: no conditions are recorded")
        return errors
    if feature_id not in conditions:
        errors.append(f"{INTEGRATION_OBSERVATION}: no condition for {feature_id}")
        return errors
    condition = conditions[feature_id]
    if not isinstance(condition, dict) or not condition:
        errors.append(f"{INTEGRATION_OBSERVATION}: the condition for {feature_id} is empty")
        return errors
    required = condition.get("required")
    if not isinstance(required, list) or item not in required:
        errors.append(f"{INTEGRATION_OBSERVATION}: {feature_id} does not require {item}")
        return errors
    results = condition.get("results")
    if not isinstance(results, dict):
        errors.append(f"{INTEGRATION_OBSERVATION}: {feature_id} has no results")
        return errors
    result = results.get(item)
    if not isinstance(result, dict) or not result:
        errors.append(f"{INTEGRATION_OBSERVATION}: {feature_id} has no result for {item}")
        return errors
    if result.get("result") != "pass":
        errors.append(
            f"{INTEGRATION_OBSERVATION}: {item} has result {result.get('result')!r}, not 'pass'"
        )
    if not result.get("evidence"):
        errors.append(f"{INTEGRATION_OBSERVATION}: {item} has no evidence text")
    source = result.get("source")
    if not source:
        errors.append(f"{INTEGRATION_OBSERVATION}: {item} has no source reference")
        return errors
    # The source must exist in the candidate commit, not only in the worktree.
    committed = committed_file(repo, candidate, source)
    if committed is None:
        errors.append(
            f"{INTEGRATION_OBSERVATION}: the source {source} is not in candidate {candidate}"
        )
        return errors
    try:
        source_record = json.loads(committed.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        errors.append(f"{INTEGRATION_OBSERVATION}: the source {source} is not a readable record")
        return errors
    if not isinstance(source_record, dict) or not source_record:
        errors.append(f"{INTEGRATION_OBSERVATION}: the source {source} is an empty object")
        return errors
    if source_record.get("item") != item:
        errors.append(
            f"{INTEGRATION_OBSERVATION}: the source {source} records item "
            f"{source_record.get('item')!r}, not {item!r}"
        )
    if source_record.get("exit") != 0 or expected.get("exit") != 0:
        errors.append(f"{INTEGRATION_OBSERVATION}: a passing check must actually exit 0")
    # The source records the revision the command actually ran against, which
    # must be the observed candidate or one of its ancestors.
    source_candidate = source_record.get("candidate")
    if not source_candidate or not is_ancestor(repo, source_candidate, candidate):
        errors.append(
            f"{INTEGRATION_OBSERVATION}: the source {source} records candidate "
            f"{source_candidate!r}, which is not the observed candidate {candidate!r} "
            f"nor one of its ancestors"
        )
    elif not fixture_inputs_match(repo, source_candidate, candidate):
        errors.append(f"{INTEGRATION_OBSERVATION}: inputs changed after the source check")
    for key in ("command", "exit", "stdout"):
        if key not in source_record:
            errors.append(f"{INTEGRATION_OBSERVATION}: the source {source} records no {key}")
        elif source_record.get(key) != expected.get(key):
            errors.append(
                f"{INTEGRATION_OBSERVATION}: the source {source} records {key} "
                f"{source_record.get(key)!r}, but the actual run produced {expected.get(key)!r}"
            )
    return errors


def human_state(repo: Path) -> dict:
    return lifecycle.load(repo)["features"][HUMAN_FEATURE]


def human_feature_state(repo: Path, feature_id: str) -> dict:
    return lifecycle.load(repo)["features"][feature_id]


def human_verify(repo: Path, *args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(HERE / "lifecycle_state.py"), "--repo", str(repo),
         "verify-acceptance", *args],
        capture_output=True, text=True,
    )
    assert result.returncode in {0, 1}, (result.returncode, result.stderr)
    return json.loads(result.stdout)


def human_cli(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HERE / "lifecycle_state.py"), "--repo", str(repo), *args],
        capture_output=True, text=True,
    )


def context_digest(raw: bytes, ref: str) -> str:
    """The existing context-v1 normalization used by the lifecycle snapshots."""
    return lifecycle._context_digest(raw, ref=ref)


def tracked_bytes(repo: Path, commit: str, path: str) -> bytes:
    """Read one path as it was recorded in a commit."""
    result = subprocess.run(
        ["git", "-C", str(repo), "show", f"{commit}:{path}"], capture_output=True,
    )
    assert result.returncode == 0, (commit, path, result.stderr)
    return result.stdout


def last_commit_for(repo: Path, path: str) -> str:
    result = test_support.git(repo, "log", "-1", "--format=%H", "--", path)
    return result.stdout.strip()


def approved_mapping(repo: Path, feature_id: str, point: str) -> dict:
    """The path -> context-v1 digest mapping the CLI reports for one point."""
    result = human_verify(repo, "--feature-id", feature_id, "--point", point)
    return {item["path"]: item["current_digest"] for item in result["points"][0]["files"]}


def recorded_mapping(repo: Path, feature_id: str, point: str) -> dict:
    """The path -> context-v1 digest mapping recorded in state for one point."""
    snapshot = human_feature_state(repo, feature_id)["acceptance"][point]
    return dict(snapshot["documents"])


def run_integration_check(repo: Path, item: str, candidate: str) -> dict:
    """Run the business check and write the evidence it actually produced.

    The record binds the item to the exact command, exit code and output, so a
    checker can compare it against a later real run instead of trusting prose.
    """
    command = [sys.executable, "-B", "-m", "unittest", "-q", "test_cli"]
    result = subprocess.run(command, cwd=repo, capture_output=True, text=True)
    stdout = result.stdout.strip()
    evidence = integration_evidence(
        item, candidate=candidate,
        command=" ".join(["python3", "-B", "-m", "unittest", "-q", "test_cli"]),
        exit_code=result.returncode, stdout=stdout,
    )
    path = repo / "integration" / f"{item}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(evidence, encoding="utf-8")
    return {
        "command": "python3 -B -m unittest -q test_cli",
        "exit": result.returncode,
        "stdout": stdout,
        "path": f"integration/{item}.json",
    }


def prepare_human(repo: Path, *, with_cli: bool = False, second_feature: bool = False,
                  integration_items: tuple = (), release_evidence_ref: str | None = None,
                  human_required: bool = True) -> dict:
    """Create a tracked repository with registered features, tasks and contexts."""
    test_support.initialize_git_repo(repo, readme="# Integer doubling CLI\n")
    lifecycle.initialize(repo)
    if with_cli:
        (repo / "cli.py").write_text(SOLUTION, encoding="utf-8")
        (repo / "test_cli.py").write_text(BUSINESS_TEST, encoding="utf-8")
    integration = repo / INTEGRATION_MANIFEST
    integration.parent.mkdir(parents=True, exist_ok=True)
    integration.write_text(integration_manifest(), encoding="utf-8")
    product_text = HUMAN_PRODUCT if human_required else HUMAN_PRODUCT.replace(
        "One acceptance item needs a person to operate the CLI.\n", "",
    )
    product = context(repo, "product", product_text)
    engineering_text = HUMAN_ENGINEERING if human_required else HUMAN_ENGINEERING.replace(
        " and hand the candidate to a person", "",
    )
    if release_evidence_ref is not None:
        engineering_text += f"\nRelease evidence: {release_evidence_ref}\n"
    engineering_text += f"\nShared observation: {INTEGRATION_OBSERVATION}\n"
    engineering = context(repo, "engineering", engineering_text)
    branch = test_support.git(repo, "symbolic-ref", "--short", "HEAD").stdout.strip()
    lifecycle.capture_requirement(
        repo=repo, requirement_id=REQ, title="Double integers", product_context_ref=product,
    )
    lifecycle.mark_requirement_ready(repo=repo, requirement_id=REQ)
    lifecycle.start_feature(
        repo=repo, requirement_id=REQ, feature_id=HUMAN_FEATURE, branch=branch,
        engineering_context_ref=engineering,
    )
    lifecycle.add_task(
        repo=repo, feature_id=HUMAN_FEATURE, task_id=HUMAN_TASK, title="Deliver the doubling CLI",
    )
    if second_feature:
        other_product = context(repo, "product-other", HUMAN_OTHER_PRODUCT)
        other_engineering = context(
            repo, "engineering-other",
            HUMAN_OTHER_ENGINEERING + f"\nShared observation: {INTEGRATION_OBSERVATION}\n",
        )
        lifecycle.capture_requirement(
            repo=repo, requirement_id=HUMAN_OTHER_REQUIREMENT, title="Double integers again",
            product_context_ref=other_product,
        )
        lifecycle.mark_requirement_ready(repo=repo, requirement_id=HUMAN_OTHER_REQUIREMENT)
        lifecycle.start_feature(
            repo=repo, requirement_id=HUMAN_OTHER_REQUIREMENT, feature_id=HUMAN_OTHER_FEATURE,
            branch=branch, engineering_context_ref=other_engineering,
        )
        lifecycle.add_task(
            repo=repo, feature_id=HUMAN_OTHER_FEATURE, task_id=HUMAN_OTHER_TASK,
            title="Deliver the second feature",
        )
    commit(repo, "initial human acceptance fixture")
    return {
        "state": copy.deepcopy(lifecycle.load(repo)),
        "product": (repo / product).read_bytes(),
        "engineering": (repo / engineering).read_bytes(),
        "branch": branch,
        "product_ref": product,
        "engineering_ref": engineering,
    }


def human_complete_task(repo: Path, feature_id: str = HUMAN_FEATURE,
                        task_id: str = HUMAN_TASK) -> None:
    cli(repo, "set-task-status", "--feature-id", feature_id, "--task-id", task_id,
        "--status", "in_progress")
    cli(repo, "set-task-status", "--feature-id", feature_id, "--task-id", task_id,
        "--status", "done")
    commit(repo, "task complete")


def human_pass_and_review(repo: Path, *, commit_result: bool = True,
                          feature_id: str = HUMAN_FEATURE,
                          task_id: str = HUMAN_TASK) -> str:
    """Record a passing validation and an approval; return the validated commit."""
    cli(repo, "record-validation", "--feature-id", feature_id, "--result", "pass",
        "--test-command", "python3 -m unittest -q test_cli")
    cli(repo, "record-review", "--feature-id", feature_id, "--decision", "approved",
        "--by", "scripted reference")
    if commit_result:
        commit(repo, "validation and review")
    return human_feature_state(repo, feature_id)["validation"]["commit"]


def human_checkpoint_path(repo: Path, feature_id: str) -> Path:
    return repo / ".sdlc-v1" / "checkpoints" / f"{feature_id}.md"


# The checkpoint records the acceptance point, the bound paths and their
# pre-approved digests, the tested commit, and the original review facts. The
# mapping lines are machine-readable so a recovery can parse the approved
# mapping from disk instead of trusting an in-memory value.
CHECKPOINT_POINT_PREFIX = "- 核准验收点："
CHECKPOINT_COMMIT_PREFIX = "- 被测 commit："
CHECKPOINT_REVIEW_PREFIX = "- 原 Review："
CHECKPOINT_MAPPING_PREFIX = "  - 绑定路径 "
# A candidate that never received a review records this marker instead of
# reviewer facts, so the check does not demand an original record for it.
NO_REVIEW_MARKER = "尚无原 Review"


def write_human_checkpoint(repo: Path, feature_id: str, *, location: str, point: str,
                           approved: dict, tested_commit: str, review: str,
                           pending: str, next_step: str, references: list) -> Path:
    """Write a five-section checkpoint holding the approved mapping and open items."""
    path = human_checkpoint_path(repo, feature_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# 恢复检查点：{feature_id}", "", "## 定位", "", f"- {location}", "",
             f"- Task ID：{HUMAN_TASK}", "", "## 已确认", "",
             f"{CHECKPOINT_POINT_PREFIX}{point}",
             f"{CHECKPOINT_COMMIT_PREFIX}{tested_commit}",
             f"{CHECKPOINT_REVIEW_PREFIX}{review}",
             "- 预核准绑定路径与 context-v1 摘要："]
    lines += [f"{CHECKPOINT_MAPPING_PREFIX}{ref} = {digest}"
              for ref, digest in sorted(approved.items())]
    lines += ["", "## 未完成", "", f"- {pending}", "", "## 下一步", "", f"- {next_step}",
              "", "## 必要引用", ""]
    lines += [f"- {reference}" for reference in references]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def checkpoint_sections(path: Path) -> list:
    return [
        line for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("## ")
    ]


def parse_checkpoint_mapping(path: Path) -> dict:
    """Read the pre-approved path -> digest mapping back from the checkpoint file."""
    mapping = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith(CHECKPOINT_MAPPING_PREFIX.strip()):
            continue
        ref, _, digest = stripped[len(CHECKPOINT_MAPPING_PREFIX.strip()):].partition("=")
        mapping[ref.strip()] = digest.strip()
    return mapping


def parse_checkpoint_field(path: Path, prefix: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()
    return ""


def parse_checkpoint_references(path: Path) -> list:
    """Read the Git references recorded in the checkpoint's reference section.

    A reference is a ``<commit>:<path>`` pair. The descriptive label before
    the commit may end in any separator, including the full-width colon used
    by the Chinese checkpoint text, so the whole reference line is searched.
    """
    import re
    references = []
    pattern = re.compile(r"([0-9a-f]{40}):([^\s]+)")
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        for match in pattern.finditer(stripped[2:]):
            references.append(match.group(0))
    return references


def checkpoint_recovery_mismatches(repo: Path, path: Path, feature_id: str, point: str,
                                  *, recorded: bool = True, require_prior_review: bool = True) -> list:
    """Verify a persisted checkpoint against the CLI and the original record.

    The check reads the acceptance point, the complete path set, the pre-approved
    digests, the tested commit, the original reviewer/decision and the Git
    reference from the checkpoint file on disk. It compares them with the CLI's
    reported digests and with the original committed state, for the same
    Feature. It writes nothing.

    With ``recorded`` false the check runs before the re-record call, so only
    the current digests are compared; afterwards the recorded digests are
    compared as well.

    When an old Review is to be recovered, its facts and Git record are required
    independently of what the checkpoint claims. Only a caller that is not
    recovering a Review may explicitly set ``require_prior_review`` to false.
    Returns one entry per gap. An empty list means the checkpoint is consistent
    with the CLI and the required original record.
    """
    differences = []
    if not path.exists():
        return ["the checkpoint file is missing"]
    approved = parse_checkpoint_mapping(path)
    recorded_point = parse_checkpoint_field(path, CHECKPOINT_POINT_PREFIX)
    tested_commit = parse_checkpoint_field(path, CHECKPOINT_COMMIT_PREFIX)
    review_facts = parse_checkpoint_field(path, CHECKPOINT_REVIEW_PREFIX)
    references = parse_checkpoint_references(path)
    # The acceptance point must be recorded and must be the one requested.
    if not recorded_point:
        differences.append("the checkpoint records no acceptance point")
    elif recorded_point != point:
        differences.append(
            f"checkpoint acceptance point {recorded_point!r} differs from the requested {point!r}"
        )
    # The mapping must be present and complete.
    if not approved:
        differences.append("the checkpoint records no pre-approved path mapping")
    result = human_verify(repo, "--feature-id", feature_id, "--point", point)
    reported = result["points"][0]["files"]
    if not reported:
        differences.append(f"the CLI reports no bound path for the {point!r} point")
    reported_paths = {item["path"] for item in reported}
    for item in reported:
        ref = item["path"]
        if ref not in approved:
            differences.append(f"{ref}: missing from the checkpoint mapping")
            continue
        if recorded and approved[ref] != item["expected_digest"]:
            differences.append(f"{ref}: approved {approved[ref]} != expected {item['expected_digest']}")
        if approved[ref] != item["current_digest"]:
            differences.append(f"{ref}: approved {approved[ref]} != current {item['current_digest']}")
    for ref in sorted(approved):
        if ref not in reported_paths:
            differences.append(f"{ref}: not reported by the CLI for this point")
    # The tested commit and the original review facts must match the original
    # committed record that the checkpoint's Git reference points at. A
    # checkpoint for a candidate without an original review records neither,
    # so it is not required to carry them.
    if not tested_commit:
        differences.append("the checkpoint records no tested commit")
    if require_prior_review and (not review_facts or review_facts.startswith(NO_REVIEW_MARKER)):
        differences.append("the original review facts required for recovery are missing")
    if require_prior_review and not references:
        differences.append("the original review record required for recovery is missing")
    if review_facts and not review_facts.startswith(NO_REVIEW_MARKER):
        if not references:
            differences.append(
                "the checkpoint records original review facts but no Git reference"
            )
    elif references:
        differences.append(
            "the checkpoint records a Git reference but no original review facts"
        )
    original = None
    for reference in references:
        revision, _, referenced_path = reference.partition(":")
        if not revision or not referenced_path:
            differences.append(f"the Git reference {reference!r} is malformed")
            continue
        resolved = committed_file(repo, revision, referenced_path)
        if resolved is None:
            differences.append(f"the Git reference {reference!r} does not resolve in Git")
            continue
        try:
            referenced_state = json.loads(resolved.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            differences.append(f"the Git reference {reference!r} is not readable")
            continue
        features = referenced_state.get("features", {})
        if feature_id not in features:
            differences.append(
                f"the Git reference {reference!r} has no feature {feature_id}"
            )
            continue
        record = features[feature_id]
        original_validation = record.get("validation", {})
        original_review = record.get("review", {})
        if require_prior_review and original_review.get("decision") not in {"approved", "changes_requested"}:
            differences.append(
                f"the Git reference {reference!r} has no completed review decision"
            )
        if original is None:
            original = record
        else:
            if original.get("review") != original_review:
                differences.append(
                    f"the Git reference {reference!r} records a different review than "
                    f"the other references"
                )
        # The tested commit must be the validation commit of the same Feature.
        if tested_commit and original_validation.get("commit") != tested_commit:
            differences.append(
                f"the tested commit {tested_commit} is not the validation commit "
                f"{original_validation.get('commit')!r} of {feature_id} in the original record"
            )
        # The recorded reviewer and decision must match the original record.
        expected_review = f"{original_review.get('decision')} by {original_review.get('by')}"
        if review_facts and review_facts != expected_review:
            differences.append(
                f"the recorded original review {review_facts!r} differs from the "
                f"original record {expected_review!r}"
            )
    return differences


def unpack_archive(repo: Path, commit: str, destination: Path) -> tuple[Path, str]:
    """Unpack one archive and return its root and that same archive's source identity."""
    archive = subprocess.run(
        ["git", "-C", str(repo), "archive", "--format=tar", commit], capture_output=True,
    )
    assert archive.returncode == 0, (commit, archive.stderr)
    destination.mkdir(parents=True, exist_ok=True)
    import tarfile
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        source_commit = tar.pax_headers.get("comment", "").strip()
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            assert target.is_relative_to(destination.resolve()), member.name
            assert member.isfile() or member.isdir(), member.name
        # Git produced this archive from our disposable fixture. Restrict its
        # members explicitly so this also works on supported Python 3.9 builds,
        # where tarfile's filter argument is unavailable.
        tar.extractall(destination)
    return destination, source_commit


def simulate_deploy(target: Path, operation: dict) -> dict:
    """Apply one operation to a disposable local target and write its receipt."""
    target.mkdir(parents=True, exist_ok=True)
    receipt = {
        "operation": operation["operation"],
        "version": operation["expected_version"],
        "applied_from": operation["original_version"],
    }
    (target / "version").write_text(operation["expected_version"] + "\n", encoding="utf-8")
    with (target / "applications.log").open("a", encoding="utf-8") as stream:
        stream.write(f"{operation['operation']} {operation['expected_version']}\n")
    (target / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True),
                                         encoding="utf-8")
    return receipt


def read_deploy_receipt(target: Path) -> dict:
    """Re-read the receipt from the persistent target, not from a caller's memory."""
    return json.loads((target / "receipt.json").read_text(encoding="utf-8"))


def deploy_applications(target: Path) -> int:
    """Count how many times an operation was applied to this target."""
    log = target / "applications.log"
    if not log.exists():
        return 0
    return log.read_text(encoding="utf-8").count("\n")


def stage_operation_record(root: Path, environment: str, operation: dict) -> Path:
    """Persist one stage's operation record before the action is attempted."""
    directory = root / "operations"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{environment}.json"
    path.write_text(json.dumps(operation, indent=2, sort_keys=True), encoding="utf-8")
    return path


def read_operation_record(root: Path, environment: str) -> dict:
    """Re-read one stage's operation record from disk."""
    path = root / "operations" / f"{environment}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def archive_smoke(repo: Path, commit: str, destination: Path, evidence_path: Path) -> dict:
    """Unpack a fixed revision outside the repository and really run its CLI.

    The result is written to ``evidence_path`` so the caller reads it back from
    disk instead of trusting a value it could have fabricated.
    """
    unpacked, source = unpack_archive(repo, commit, destination)
    result = subprocess.run(
        [sys.executable, "-B", "cli.py", "3"], cwd=unpacked, capture_output=True, text=True,
    )
    evidence = {
        "source_commit": source,
        "command": "python3 -B cli.py 3",
        "exit": result.returncode,
        "stdout": result.stdout.strip(),
        "unpacked": str(unpacked),
    }
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    return evidence


def read_smoke_evidence(evidence_path: Path) -> dict:
    """Re-read a persisted smoke result from disk."""
    return json.loads(evidence_path.read_text(encoding="utf-8"))


def verify_smoke_evidence(evidence_path: Path) -> list:
    """Re-run the recorded smoke and report where the persisted record differs."""
    evidence = read_smoke_evidence(evidence_path)
    unpacked = Path(evidence["unpacked"])
    if not (unpacked / "cli.py").exists():
        return ["the recorded smoke has no unpacked cli.py to re-run"]
    result = subprocess.run(
        [sys.executable, "-B", "cli.py", "3"], cwd=unpacked, capture_output=True, text=True,
    )
    differences = []
    if result.returncode != evidence["exit"]:
        differences.append(
            f"the recorded exit {evidence['exit']} differs from the re-run {result.returncode}"
        )
    if result.stdout.strip() != evidence["stdout"]:
        differences.append(
            f"the recorded stdout {evidence['stdout']!r} differs from the re-run "
            f"{result.stdout.strip()!r}"
        )
    return differences


def stage_preconditions_errors(root: Path, environment: str, version: str) -> list:
    """Check the synthetic stage authorization and prior local evidence."""
    errors = []
    try:
        authorization = json.loads((root / "stage-authorization.json").read_text(encoding="utf-8"))
        operation = read_operation_record(root, environment)
        granted = authorization["operations"].get(environment)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return ["missing stage authorization or operation record"]
    if (authorization.get("synthetic") is not True or authorization.get("version") != version
            or not granted or granted != operation.get("operation")
            or operation.get("expected_version") != version
            or operation.get("environment") != environment):
        errors.append("the stage is not authorized for this operation and version")
    previous = {"staging": None, "canary": "staging", "full": "canary"}.get(environment)
    if environment not in {"staging", "canary", "full"}:
        return errors + ["unknown stage"]
    prior_operation = {}
    if previous:
        try:
            prior_operation = read_operation_record(root, previous)
            prior_receipt = read_deploy_receipt(root / "targets" / previous)
            prior_smoke = read_smoke_evidence(root / "evidence" / f"{previous}-smoke.json")
            actual_version = (root / "targets" / previous / "version").read_text(encoding="utf-8").strip()
            if (authorization["operations"].get(previous) != prior_operation.get("operation")
                    or prior_operation.get("environment") != previous
                    or prior_operation.get("expected_version") != version
                    or prior_receipt.get("operation") != prior_operation.get("operation")
                    or prior_receipt.get("version") != version or actual_version != version
                    or prior_smoke.get("source_commit") != version
                    or prior_smoke.get("exit") != 0 or prior_smoke.get("stdout") != "6"):
                errors.append("previous stage receipt or smoke does not match")
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            errors.append("previous stage receipt or smoke is missing")
    if environment == "full":
        try:
            observation = json.loads((root / "evidence" / "canary-observation.json").read_text(encoding="utf-8"))
            if (observation.get("synthetic") is not True or observation.get("version") != version
                    or observation.get("operation") != prior_operation.get("operation")
                    or observation.get("failures") != 0):
                errors.append("canary observation does not meet the agreed condition")
        except (OSError, ValueError, TypeError, AttributeError):
            errors.append("canary observation is missing")
    return errors


def cli(repo: Path, *args: str) -> None:
    subprocess.run(
        [sys.executable, str(HERE / "lifecycle_state.py"), "--repo", str(repo), *args],
        check=True, capture_output=True, text=True,
    )


def commit(repo: Path, message: str) -> str:
    test_support.git(repo, "add", ".")
    test_support.git(repo, "commit", "-m", message)
    return test_support.git(repo, "rev-parse", "HEAD").stdout.strip()


def context(repo: Path, name: str, content: str) -> str:
    relative = ".sdlc-v1/context/" + name + ".md"
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return relative


def business_files(repo: Path) -> dict:
    return {
        str(path.relative_to(repo)): path.read_bytes()
        for path in repo.rglob("*")
        if path.is_file() and path.relative_to(repo).parts[0] not in {".git", ".sdlc-v1"}
    }


def run_check(repo: Path, arguments: list) -> tuple:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(arguments, cwd=repo, capture_output=True, text=True, env=env)
    return result, shlex.join(arguments)


def coverage_commands(python: Path, artifact_dir: Path) -> tuple:
    data = artifact_dir / ".coverage"
    base = [str(python), "-m", "coverage"]
    commands = []
    for index, arguments in enumerate((["3"], ["-4"], ["bad"], [])):
        command = base + ["run", "--branch", "--source=cli", f"--data-file={data}"]
        if index:
            command.append("--append")
        commands.append(command + ["cli.py", *arguments])
    report = base + ["report", f"--data-file={data}", "--show-missing"]
    json_report = base + ["json", f"--data-file={data}", "-o", str(artifact_dir / "coverage.json")]
    return commands, report, json_report


def run_coverage(repo: Path, python: Path, artifact_dir: Path) -> str:
    commands, report, json_report = coverage_commands(python, artifact_dir)
    evidence = []
    for index, command in enumerate(commands):
        result, actual = run_check(repo, command)
        expected_status = 0 if index < 2 else 2
        assert result.returncode == expected_status, (actual, result.stderr)
        evidence.append(f"{actual}: exit {result.returncode}")
    result, actual = run_check(repo, report)
    assert result.returncode == 0, (actual, result.stderr)
    evidence.append(f"{actual}: exit 0\n{result.stdout}")
    result, actual = run_check(repo, json_report)
    assert result.returncode == 0, (actual, result.stderr)
    summary = json.loads((artifact_dir / "coverage.json").read_text(encoding="utf-8"))["totals"]
    evidence.append(
        f"{actual}: exit 0; lines {summary['covered_lines']}/{summary['num_statements']}; "
        f"branches {summary['covered_branches']}/{summary['num_branches']}"
    )
    assert summary["num_statements"] and summary["num_branches"]
    assert summary["covered_lines"] / summary["num_statements"] >= 0.80
    assert summary["covered_branches"] / summary["num_branches"] >= 0.70
    return "\n".join(evidence)


def prepare(repo: Path, scenario: str, *, coverage_python: Path | None = None) -> dict:
    """Create an initial repository and retain an independent pre-operation snapshot."""
    if scenario not in REQUESTS:
        raise ValueError(scenario)
    output = (
        "The output number format remains open (integer or decimal)."
        if scenario == "B02"
        else "For example, `python3 cli.py 3` prints `6`."
    )
    readme = (
        "# Integer doubling CLI\n\n"
        "A user supplies one integer as a command-line argument to `cli.py` and "
        "receives its doubled value on standard output. " + output + "\n\n"
        "Run `python3 cli.py <integer>`. Missing or invalid input is an error and "
        "returns a nonzero exit status. The CLI may be under implementation; "
        "run `python3 -m unittest -q test_cli` to check its behavior.\n"
    )
    test_support.initialize_git_repo(repo, readme=readme)
    scope = "cli.py and .sdlc-v1/**" if scenario == "B01" else ".sdlc-v1/**"
    (repo / "request.md").write_text(
        REQUESTS[scenario] + "\n\nWrite scope: " + scope + " only.\n", encoding="utf-8",
    )
    (repo / "test_cli.py").write_text(BUSINESS_TEST, encoding="utf-8")
    if scenario != "B01":
        code = SOLUTION if scenario in {"B03", "B04A", "B04B"} else INITIAL_CLI
        (repo / "cli.py").write_text(code, encoding="utf-8")
    lifecycle.initialize(repo)
    branch = test_support.git(repo, "symbolic-ref", "--short", "HEAD").stdout.strip()
    entry_status = "planned; not present yet" if scenario == "B01" else "present"
    artifact_dir = repo.absolute().parent / f"{repo.name}-coverage"
    if coverage_python is not None:
        coverage_python = Path(coverage_python).absolute()
        artifact_dir.mkdir()
        coverage_runs, coverage_report, coverage_json = coverage_commands(coverage_python, artifact_dir)
        coverage_command = shlex.join(coverage_report)
        coverage_note = (
            "\n## Coverage\n\n"
            f"Artifacts are outside the repository at `{artifact_dir}`. "
            "The applicable minimum is 80% line coverage and 70% branch coverage for `cli.py`. "
            "Run the following commands from the repository root; invalid and missing input "
            "are expected to exit nonzero. Inspect the JSON line and branch counts against "
            "both thresholds.\n\n```bash\n"
            + "\n".join(shlex.join(command) for command in [*coverage_runs, coverage_report, coverage_json])
            + "\n```\n"
        )
    else:
        coverage_command = "none"
        coverage_note = "\nThis fixture does not require numeric coverage. No coverage tool is configured.\n"
    project = f"""# Project context: local Python CLI

This repository contains a single-module Python standard-library CLI. The checked-out
branch is `{branch}`. `test_cli.py` contains the local business assertions. The
`cli.py` entry is {entry_status}.
The fixture uses Python's standard library and has no external service or dependencies.

## Commands

```yaml
commands:
  unit: "PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -q test_cli"
  coverage: {json.dumps(coverage_command)}
  e2e: none
  typecheck: none
  lint: none
  build: none
```

The command and test asset are available; the current implementation's result must
be observed when run. There is no CI or repository artifact archive.

## Surface map

```yaml
surfaces:
  - name: python-cli
    globs: ["cli.py", "test_cli.py"]
    roles: [qa]
    modes: [correctness]
```

## Conventions and scope

Use the local files and `request.md` for the task and permitted write scope. No
credentials, configuration files, long-lived project guidance, or external services
are present. Release target and deployment configuration: none; this exercise ends
at review. Other verification resources and context sources: none.
"""
    project += coverage_note
    if scenario == "B03":
        probe_command = shlex.join(["python3", "-c", PROBE_CODE])
        project += (
            "\n## Required revalidation environment probe\n\n"
            "The local file `required-environment-probe` must exist for the necessary "
            "revalidation environment to be available. Check from the repository root: "
            f"`{probe_command}`. It prints `present` and exits 0 when available, "
            "or prints `missing` and exits 2 when absent.\n"
        )
    (repo / ".sdlc-v1/project.md").write_text(project, encoding="utf-8")
    product = context(repo, "product", "# Product\n" + (
        "Output format: OPEN (integer or decimal).\n" if scenario == "B02"
        else "Double integer input; invalid input fails. Scope confirmed.\n"
    ))
    lifecycle.capture_requirement(
        repo=repo, requirement_id=REQ, title="Double integers", product_context_ref=product,
    )
    if scenario != "B02":
        lifecycle.mark_requirement_ready(repo=repo, requirement_id=REQ)
        planned_tasks = TASKS if scenario == "B05" else {"TASK-one": TASKS["TASK-one"]}
        plan = "# Engineering plan\n" + "".join(
            f"- {task_id}: {title}; depends on {', '.join(deps) or 'none'}\n"
            for task_id, (title, deps) in planned_tasks.items()
        )
        if scenario == "B04B":
            plan += (
                "The confirmed product scope includes invalid-input failure. "
                "Its historical verification evidence is missing. Assess the existing "
                "evidence only; do not run an additional check during this exercise.\n"
            )
        engineering = context(repo, "engineering", plan)
        lifecycle.start_feature(
            repo=repo, requirement_id=REQ, feature_id=FEATURE, branch=branch,
            engineering_context_ref=engineering,
        )
        lifecycle.add_task(repo=repo, feature_id=FEATURE, task_id="TASK-one", title=TASKS["TASK-one"][0])
        if scenario in {"B03", "B04A", "B04B"}:
            for status in ("in_progress", "done"):
                lifecycle.set_task_status(repo=repo, feature_id=FEATURE, task_id="TASK-one", status=status)
    commit(repo, "initial scenario")
    if scenario in {"B03", "B04A", "B04B"}:
        arguments = [sys.executable, "cli.py", "3"] if scenario == "B04B" else [sys.executable, "-m", "unittest", "-q", "test_cli"]
        result, command = run_check(repo, arguments)
        assert result.returncode == 0
        if scenario == "B04B":
            assert result.stdout.strip() == "6"
        evidence = (
            "Prior scripted verification executed: " + command + " (exit 0).\n"
            + ("Only normal input was checked.\n" if scenario == "B04B" else "Includes invalid input.\n")
        )
        if scenario in {"B03", "B04A"} and coverage_python is not None:
            evidence += "Prior coverage evidence:\n" + run_coverage(repo, coverage_python, artifact_dir) + "\n"
        else:
            evidence += "Prior coverage: NOT_RUN.\n"
        with (repo / ".sdlc-v1/context/engineering.md").open("a", encoding="utf-8") as stream:
            stream.write(evidence)
        lifecycle.record_validation(repo=repo, feature_id=FEATURE, result="pass", command=command)
        lifecycle.record_review(repo=repo, feature_id=FEATURE, decision="approved", by="prior reviewer")
        commit(repo, "prior validation and review")
    return {
        "state": copy.deepcopy(lifecycle.load(repo)),
        "business": business_files(repo),
        "code": (repo / "cli.py").read_bytes() if (repo / "cli.py").exists() else None,
        "product": (repo / product).read_bytes(),
        "plan": (repo / ".sdlc-v1/context/engineering.md").read_bytes() if scenario != "B02" else None,
    }


def reference(repo: Path, scenario: str) -> None:
    """Scripted lifecycle transitions are not independent Agent validation/review."""
    if scenario == "B01":
        project = (repo / ".sdlc-v1/project.md").read_text(encoding="utf-8")
        if "## Coverage" in project.splitlines():
            raise ValueError("B01 scripted reference requires a fixture without a coverage threshold")
        (repo / "cli.py").write_text(SOLUTION, encoding="utf-8")
        result, command = run_check(repo, [sys.executable, "-m", "unittest", "-q", "test_cli"])
        assert result.returncode == 0
        cli(repo, "set-task-status", "--feature-id", FEATURE, "--task-id", "TASK-one", "--status", "in_progress")
        cli(repo, "set-task-status", "--feature-id", FEATURE, "--task-id", "TASK-one", "--status", "done")
        commit(repo, "implement CLI")
        with (repo / ".sdlc-v1/context/engineering.md").open("a", encoding="utf-8") as stream:
            stream.write(
                "Scripted reference transitions only; independent validation, independent review, "
                "and coverage measurement are NOT_RUN.\n"
            )
        cli(repo, "record-validation", "--feature-id", FEATURE, "--result", "pass", "--test-command", command)
        cli(repo, "record-review", "--feature-id", FEATURE, "--decision", "approved", "--by", "scripted reference")
    elif scenario == "B02":
        with (repo / ".sdlc-v1/context/product.md").open("a", encoding="utf-8") as stream:
            stream.write("Clarification needed: integer or decimal? Choice remains open.\n")
    elif scenario in {"B03", "B04B"}:
        if scenario == "B03":
            probe = [
                sys.executable, "-c", PROBE_CODE,
            ]
            result, command = run_check(repo, probe)
            assert result.returncode == 2 and result.stdout.strip() == "missing"
            note = "ENV_BLOCKED: required-environment-probe is absent; revalidation inconclusive.\n"
        else:
            note = "INCONCLUSIVE: new invalid-input verification obligation has no evidence; NOT_RUN.\n"
        with (repo / ".sdlc-v1/context/engineering.md").open("a", encoding="utf-8") as stream:
            stream.write(note)
        validation = ["record-validation", "--feature-id", FEATURE, "--result", "fail"]
        if scenario == "B03":
            validation.extend(["--test-command", command])
        cli(repo, *validation)
    elif scenario == "B04A":
        with (repo / ".sdlc-v1/context/engineering.md").open("a", encoding="utf-8") as stream:
            stream.write("Clarification: prior check covers the unchanged obligation.\n")
    elif scenario == "B05":
        for task_id in ("TASK-two", "TASK-three"):
            title, dependencies = TASKS[task_id]
            lifecycle.add_task(repo=repo, feature_id=FEATURE, task_id=task_id, title=title, depends_on=dependencies)


def assert_result(test: unittest.TestCase, repo: Path, scenario: str, initial: dict) -> None:
    """Assert observable artifacts and state; semantic and identity checks remain manual."""
    state = lifecycle.load(repo)
    expected_files = dict(initial["business"])
    actual_files = business_files(repo)
    if scenario == "B01":
        actual_files.pop("cli.py", None)
    test.assertEqual(actual_files, expected_files)
    if scenario == "B02":
        test.assertEqual(state, initial["state"])
        test.assertEqual((repo / "cli.py").read_bytes(), initial["code"])
        return
    test.assertEqual((repo / ".sdlc-v1/context/product.md").read_bytes(), initial["product"])
    feature = state["features"][FEATURE]
    engineering = (repo / ".sdlc-v1/context/engineering.md").read_bytes()
    test.assertTrue(engineering.startswith(initial["plan"]))
    test.assertEqual(feature["branch"], test_support.git(repo, "symbolic-ref", "--short", "HEAD").stdout.strip())
    if scenario == "B01":
        for value, expected in (("0", "0"), ("7", "14"), ("-5", "-10")):
            result = subprocess.run([sys.executable, str(repo / "cli.py"), value], capture_output=True, text=True)
            test.assertEqual((result.returncode, result.stdout.strip()), (0, expected))
        result = subprocess.run([sys.executable, str(repo / "cli.py"), "bad"], capture_output=True, text=True)
        test.assertNotEqual(result.returncode, 0)
        test.assertEqual(feature["status"], "reviewed")
        test.assertEqual(feature["validation"]["result"], "pass")
        test.assertEqual(feature["review"]["decision"], "approved")
        head = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
        difference = subprocess.run(
            ["git", "-C", str(repo), "diff", "--quiet", feature["validation"]["commit"], head,
             "--", ".", ":(exclude).sdlc-v1/**"],
            capture_output=True,
        )
        test.assertEqual(difference.returncode, 0)
        test.assertEqual(test_support.git(repo, "status", "--porcelain", "--", "cli.py").stdout, "")
        test.assertEqual(set(feature["tasks"]), {"TASK-one"})
        return
    test.assertEqual((repo / "cli.py").read_bytes(), initial["code"])
    test.assertEqual(
        test_support.git(repo, "diff", "--name-only", "HEAD", "--", ".", ":(exclude).sdlc-v1/**").stdout,
        "",
    )
    if scenario in {"B03", "B04B"}:
        test.assertEqual(set(feature["tasks"]), {"TASK-one"})
        test.assertEqual(feature["validation"]["result"], "fail")
        test.assertEqual(feature["review"]["decision"], "pending")
        test.assertEqual(feature["release"]["status"], "pending")
        test.assertEqual(feature["status"], "in_progress")
        note = "ENV_BLOCKED" if scenario == "B03" else "INCONCLUSIVE"
        test.assertIn(note, (repo / ".sdlc-v1/context/engineering.md").read_text(encoding="utf-8"))
        if scenario == "B04B":
            test.assertIsNone(feature["validation"]["command"])
        if scenario == "B03":
            test.assertIsNotNone(feature["validation"]["command"])
            test.assertFalse((repo / "required-environment-probe").exists())
    elif scenario == "B04A":
        test.assertEqual(set(feature["tasks"]), {"TASK-one"})
        test.assertEqual(state, initial["state"])
        test.assertIn("Clarification:", (repo / ".sdlc-v1/context/engineering.md").read_text(encoding="utf-8"))
        test.assertEqual(feature["validation"], initial["state"]["features"][FEATURE]["validation"])
        test.assertEqual(feature["review"], initial["state"]["features"][FEATURE]["review"])
        test.assertEqual(feature["status"], "reviewed")
    elif scenario == "B05":
        test.assertEqual((repo / ".sdlc-v1/context/engineering.md").read_bytes(), initial["plan"])
        test.assertEqual(set(feature["tasks"]), set(TASKS))
        test.assertEqual(feature["tasks"]["TASK-one"], initial["state"]["features"][FEATURE]["tasks"]["TASK-one"])
        for task_id, (title, dependencies) in TASKS.items():
            task = feature["tasks"][task_id]
            test.assertEqual((task["title"], task["depends_on"], task["status"]), (title, dependencies, "todo"))
        test.assertEqual(feature["status"], "planned")
        test.assertEqual(feature["validation"]["result"], "pending")
        test.assertEqual(feature["review"]["decision"], "pending")
        test.assertEqual(lifecycle.next_action(repo)["stage"], "build")


def assert_human_wait(test: unittest.TestCase, repo: Path, *, feature_id: str = FEATURE,
                      task_id: str = "TASK-one") -> str:
    """Check a real fixture's pending state, not an Agent's judgment or dialogue."""
    feature = lifecycle.load(repo)["features"][feature_id]
    test.assertEqual(feature["status"], "in_progress")
    test.assertEqual(feature["tasks"][task_id]["status"], "done")
    test.assertEqual(feature["validation"]["result"], "pending")
    test.assertIsNone(feature["validation"]["at"])
    test.assertIsNone(feature["validation"]["commit"])
    test.assertEqual(feature["review"]["decision"], "pending")
    test.assertEqual(feature["release"]["status"], "pending")
    test.assertEqual(lifecycle.next_action(repo)["stage"], "validate")
    head = test_support.git(repo, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip()
    test.assertEqual(test_support.git(repo, "status", "--porcelain=v1", "--untracked-files=all",
                                      "--", ".", ":(glob,exclude).sdlc-v1/**").stdout, "")
    return head


T3_CONTRACT_PATHS = {
    "adapter": HERE.parent / "skills/sdlc/references/runtime-adapters/t3-code.md",
    "protocol": HERE.parent / "skills/sdlc/references/stage-agent-protocol.md",
    "template": HERE.parent / "skills/sdlc/references/templates/TASK.md",
    "readme": HERE.parent / "README.md",
    "testing_guide": HERE.parent / "docs/testing.md",
    "router": HERE.parent / "skills/sdlc/SKILL.md",
    "codex": HERE.parent / "skills/sdlc/references/runtime-adapters/codex.md",
}
T3_REQUIRED_TOKENS = {
    "adapter": ("delegate_task", "task_cancel", "host `next`"),
    "protocol": ("runtime-adapters/t3-code.md", "host `next`"),
    "template": (),
    "testing_guide": (
        "[SCN-t3-stage-dispatch](../.sdlc-v1/context/REQ-t3-stage-dispatch.product.md)",
        "[SCN-t3-nested-delegation](../.sdlc-v1/context/REQ-t3-nested-delegation.product.md)",
    ),
    "router": (),
    "codex": (),
}
T3_OLD_PATH = "Launch idle via `t3_thread_launch`"
T3_HEADING = "### T3 layer boundary"
T3_LINKS = {
    "adapter": "../stage-agent-protocol.md#t3-layer-boundary",
    "template": "../stage-agent-protocol.md#t3-layer-boundary",
    "readme": "skills/sdlc/references/stage-agent-protocol.md#t3-layer-boundary",
    "router": "references/stage-agent-protocol.md#t3-layer-boundary",
    "codex": "../stage-agent-protocol.md#t3-layer-boundary",
}
T3_OBSOLETE_BANS = {
    "adapter": "terminal executor: explicitly prohibit nested executors",
    "protocol": "A T3 child is a terminal executor",
    "template": "T3 child 为终端执行者",
    "readme": "T3 child 是终端执行者，不再嵌套派工",
    "router": "受托执行者不得嵌套派工",
    "codex": "its children must not delegate further",
}


def t3_child_contract_errors(
    adapter: Path, protocol: Path, template: Path, readme: Path, router: Path, codex: Path,
    testing_guide: Path,
) -> list:
    """Check document contract shape; this does not establish live host behavior."""
    paths = {
        "adapter": adapter,
        "protocol": protocol,
        "template": template,
        "readme": readme,
        "testing_guide": testing_guide,
        "router": router,
        "codex": codex,
    }
    texts = {name: path.read_text(encoding="utf-8") for name, path in paths.items()}
    errors = []
    for name, tokens in T3_REQUIRED_TOKENS.items():
        for token in tokens:
            if token not in texts[name]:
                errors.append(f"{name}: missing {token}")
    if T3_HEADING not in texts["protocol"].splitlines():
        errors.append("protocol: missing T3 layer boundary heading")
    for name, link in T3_LINKS.items():
        if f"{link})" not in texts[name]:
            errors.append(f"{name}: missing T3 layer boundary link")
    for name, phrase in T3_OBSOLETE_BANS.items():
        inspected = texts[name]
        if name == "codex":
            inspected = inspected.split("## Interface map\n", 1)[0]
        if phrase in " ".join(inspected.split()):
            errors.append(f"{name}: obsolete unconditional T3 ban")
    if T3_OLD_PATH in texts["adapter"]:
        errors.append("adapter: obsolete affirmative top-level stage path")
    return errors


class T3ChildContractTest(unittest.TestCase):
    def test_real_repository_contract(self) -> None:
        self.assertEqual(t3_child_contract_errors(**T3_CONTRACT_PATHS), [])

    def test_temporary_copies_and_each_missing_token(self) -> None:
        originals = {name: path.read_bytes() for name, path in T3_CONTRACT_PATHS.items()}
        cases = [(None, None)] + [
            (name, token)
            for name, tokens in T3_REQUIRED_TOKENS.items()
            for token in tokens
        ]
        for name, token in cases:
            with self.subTest(document=name, token=token), tempfile.TemporaryDirectory() as temporary:
                copies = {key: Path(temporary) / key for key in originals}
                for key, path in copies.items():
                    path.write_bytes(originals[key])
                expected = []
                if name is not None:
                    content = copies[name].read_text(encoding="utf-8")
                    self.assertIn(token, content)
                    copies[name].write_text(content.replace(token, ""), encoding="utf-8")
                    expected = [f"{name}: missing {token}"]
                self.assertEqual(t3_child_contract_errors(**copies), expected)
                self.assertEqual(
                    {key: path.read_bytes() for key, path in T3_CONTRACT_PATHS.items()}, originals
                )

    def test_boundary_references_and_obsolete_bans(self) -> None:
        originals = {name: path.read_bytes() for name, path in T3_CONTRACT_PATHS.items()}
        cases = [("protocol", T3_HEADING, "missing T3 layer boundary heading")]
        cases += [(name, link, "missing T3 layer boundary link") for name, link in T3_LINKS.items()]
        for name, original, error in cases:
            for replacement in ("", original + "-wrong"):
                with self.subTest(document=name, replacement=replacement), tempfile.TemporaryDirectory() as temporary:
                    copies = {key: Path(temporary) / key for key in originals}
                    for key, path in copies.items():
                        path.write_bytes(originals[key])
                    content = copies[name].read_text(encoding="utf-8")
                    self.assertIn(original, content)
                    copies[name].write_text(content.replace(original, replacement), encoding="utf-8")
                    self.assertIn(f"{name}: {error}", t3_child_contract_errors(**copies))
        for name, phrase in T3_OBSOLETE_BANS.items():
            with self.subTest(document=name, ban=True), tempfile.TemporaryDirectory() as temporary:
                copies = {key: Path(temporary) / key for key in originals}
                for key, path in copies.items():
                    path.write_bytes(originals[key])
                content = copies[name].read_text(encoding="utf-8")
                if name == "codex":
                    content = content.replace("## Interface map\n", phrase + "\n\n## Interface map\n")
                else:
                    content += "\n" + phrase + "\n"
                copies[name].write_text(content, encoding="utf-8")
                self.assertIn(f"{name}: obsolete unconditional T3 ban", t3_child_contract_errors(**copies))
        self.assertEqual({key: path.read_bytes() for key, path in T3_CONTRACT_PATHS.items()}, originals)

    def test_scoped_desktop_prohibition_and_unknown_capability_are_allowed(self) -> None:
        originals = {name: path.read_bytes() for name, path in T3_CONTRACT_PATHS.items()}
        with tempfile.TemporaryDirectory() as temporary:
            copies = {key: Path(temporary) / key for key in originals}
            for key, path in copies.items():
                path.write_bytes(originals[key])
            with copies["adapter"].open("a", encoding="utf-8") as stream:
                stream.write(
                    "\nDesktop children must not fan out under its native default. "
                    "The capability of `spawn_agent` or `delegate_task` is unknown.\n"
                )
            self.assertEqual(t3_child_contract_errors(**copies), [])
        self.assertEqual({key: path.read_bytes() for key, path in T3_CONTRACT_PATHS.items()}, originals)

    def test_missing_document_surfaces_read_error(self) -> None:
        originals = {name: path.read_bytes() for name, path in T3_CONTRACT_PATHS.items()}
        with tempfile.TemporaryDirectory() as temporary:
            copies = {key: Path(temporary) / key for key in originals}
            for key, path in copies.items():
                if key != "router":
                    path.write_bytes(originals[key])
            with self.assertRaises(FileNotFoundError):
                t3_child_contract_errors(**copies)
        self.assertEqual({key: path.read_bytes() for key, path in T3_CONTRACT_PATHS.items()}, originals)

    def test_old_affirmative_path_is_rejected_in_new_copy(self) -> None:
        originals = {name: path.read_bytes() for name, path in T3_CONTRACT_PATHS.items()}
        with tempfile.TemporaryDirectory() as temporary:
            copies = {key: Path(temporary) / key for key in originals}
            for key, path in copies.items():
                path.write_bytes(originals[key])
            with copies["adapter"].open("a", encoding="utf-8") as stream:
                stream.write(
                    "\nNever use `t3_thread_launch` for a child; native `spawn_agent` "
                    "belongs to another adapter.\n"
                )
            self.assertEqual(t3_child_contract_errors(**copies), [])
            with copies["adapter"].open("a", encoding="utf-8") as stream:
                stream.write("\n" + T3_OLD_PATH + "\n")
            self.assertEqual(
                t3_child_contract_errors(**copies),
                ["adapter: obsolete affirmative top-level stage path"],
            )
            self.assertEqual(
                {key: path.read_bytes() for key, path in T3_CONTRACT_PATHS.items()}, originals
            )


class ScenarioTest(unittest.TestCase):
    def test_reference_and_wrong_results(self) -> None:
        for scenario in REQUESTS:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                repo = Path(temporary) / "repo"
                initial = prepare(repo, scenario)
                reference(repo, scenario)
                assert_result(self, repo, scenario, initial)
                if scenario == "B01":
                    (repo / "cli.py").write_text('print("incorrect")\n', encoding="utf-8")
                elif scenario == "B02":
                    lifecycle.mark_requirement_ready(repo=repo, requirement_id=REQ)
                elif scenario == "B04A":
                    cli(repo, "record-validation", "--feature-id", FEATURE, "--result", "fail")
                else:
                    path = repo / ".sdlc-v1/state.json"
                    state = lifecycle.load(repo)
                    feature = state["features"][FEATURE]
                    if scenario in {"B03", "B04B"}:
                        state = copy.deepcopy(initial["state"])
                    elif scenario == "B05":
                        del feature["tasks"]["TASK-three"]
                    path.write_text(json.dumps(state), encoding="utf-8")
                    if scenario == "B05":
                        self.assertEqual(lifecycle.next_action(repo)["stage"], "build")
                with self.assertRaises(AssertionError):
                    assert_result(self, repo, scenario, initial)


    def test_b03_failure_record_and_independent_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "failed-validation"
            initial = prepare(repo, "B03")
            # The old pass must not satisfy the result oracle before revalidation.
            with self.assertRaises(AssertionError):
                assert_result(self, repo, "B03", initial)
            reference(repo, "B03")
            assert_result(self, repo, "B03", initial)
            feature = lifecycle.load(repo)["features"][FEATURE]
            self.assertEqual(feature["validation"]["result"], "fail")
            self.assertEqual(feature["review"]["decision"], "pending")

            independent = root / "independent"
            other_initial = prepare(independent, "B05")
            reference(independent, "B05")
            assert_result(self, independent, "B05", other_initial)
            assert_result(self, repo, "B03", initial)

    def test_b03_rejected_fail_preserves_old_state_and_business(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            initial = prepare(repo, "B03")
            state_path = repo / ".sdlc-v1/state.json"
            before_state = state_path.read_bytes()
            business_path = repo / "cli.py"
            business_path.write_text(SOLUTION + "\n# uncommitted change\n", encoding="utf-8")
            before_business = business_files(repo)
            probe, command = run_check(repo, [sys.executable, "-c", PROBE_CODE])
            self.assertEqual((probe.returncode, probe.stdout.strip()), (2, "missing"))
            result, _ = run_check(repo, [
                sys.executable, str(HERE / "lifecycle_state.py"), "--repo", str(repo),
                "record-validation", "--feature-id", FEATURE, "--result", "fail",
                "--test-command", command,
            ])
            self.assertEqual(result.returncode, 2)
            self.assertIn("validation-and-release-require-clean-worktree", result.stderr + result.stdout)
            self.assertEqual(state_path.read_bytes(), before_state)
            self.assertEqual(lifecycle.load(repo), initial["state"])
            self.assertEqual(business_files(repo), before_business)
            # Rejection is not a successful fail record and must fail the normal oracle.
            with self.assertRaises(AssertionError):
                assert_result(self, repo, "B03", initial)

    def test_b01_accepts_state_only_handoff_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            initial = prepare(repo, "B01")
            reference(repo, "B01")
            with (repo / ".sdlc-v1/context/engineering.md").open("a", encoding="utf-8") as stream:
                stream.write("Evidence handoff.\n")
            test_support.git(repo, "add", ".sdlc-v1")
            test_support.git(repo, "commit", "-m", "handoff")
            assert_result(self, repo, "B01", initial)

    def test_b01_scripted_reference_rejects_required_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            initial = prepare(repo, "B01", coverage_python=Path(sys.executable))

            with self.assertRaisesRegex(ValueError, "B01 scripted reference requires a fixture without a coverage threshold"):
                reference(repo, "B01")

            self.assertEqual(lifecycle.load(repo), initial["state"])
            self.assertFalse((repo / "cli.py").exists())

    def test_business_write_boundary_rejects_added_file(self) -> None:
        for scenario in REQUESTS:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                repo = Path(temporary) / "repo"
                initial = prepare(repo, scenario)
                reference(repo, scenario)
                (repo / "unexpected.py").write_text("unexpected = True\n", encoding="utf-8")
                with self.assertRaises(AssertionError):
                    assert_result(self, repo, scenario, initial)

    def test_nested_reserved_names_are_business_files(self) -> None:
        for directory in (".git", ".sdlc-v1"):
            with self.subTest(directory=directory), tempfile.TemporaryDirectory() as temporary:
                repo = Path(temporary) / "repo"
                initial = prepare(repo, "B02")
                reference(repo, "B02")
                assert_result(self, repo, "B02", initial)
                unexpected = repo / "business" / directory / "unexpected.py"
                unexpected.parent.mkdir(parents=True)
                unexpected.write_text("unexpected = True\n", encoding="utf-8")
                with self.assertRaises(AssertionError):
                    assert_result(self, repo, "B02", initial)

    def test_initial_project_context_and_environment_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare(repo, "B03")
            project_path = repo / ".sdlc-v1/project.md"
            project = project_path.read_text(encoding="utf-8")
            branch = test_support.git(repo, "symbolic-ref", "--short", "HEAD").stdout.strip()
            self.assertIn(f"`{branch}`", project)
            self.assertIn("PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -q test_cli", project)
            self.assertIn(shlex.join(["python3", "-c", PROBE_CODE]), project)
            result, _ = run_check(repo, ["python3", "-c", PROBE_CODE])
            self.assertEqual((result.returncode, result.stdout.strip()), (2, "missing"))
            test_support.git(repo, "ls-files", "--error-unmatch", ".sdlc-v1/project.md")


class HumanAcceptanceTest(unittest.TestCase):
    """Observable CLI behavior for on-demand human acceptance and re-records.

    These assertions cover state transitions, fingerprint comparisons, Git
    facts and real command results only. They do not prove that an Agent asked,
    waited, handed off, obtained writer exclusivity, or completed a release.
    """

    # ------------------------------------------------------------------
    # 1. First human wait, validation history, and reopens
    # ------------------------------------------------------------------

    def test_first_human_wait_keeps_pending_and_rejects_generic_continue(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            feature = human_state(repo)
            # No formal validation result exists yet, so the first wait is pending.
            self.assertEqual(feature["validation"]["result"], "pending")
            self.assertEqual(feature["review"]["decision"], "pending")
            self.assertEqual(feature["release"]["status"], "pending")
            self.assertEqual(lifecycle.next_action(repo)["stage"], "validate")
            # A generic continue is not a CLI operation; it must not write state.
            before = (repo / ".sdlc-v1/state.json").read_bytes()
            self.assertEqual(lifecycle.next_action(repo)["stage"], "validate")
            self.assertEqual((repo / ".sdlc-v1/state.json").read_bytes(), before)
            # The acceptance points that were never recorded stay unbound.
            points = human_verify(repo, "--feature-id", HUMAN_FEATURE)
            self.assertEqual(points["result"], "missing")

    def test_pending_human_wait_checkpoint_states_candidate_and_open_item(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo, with_cli=True)
            human_complete_task(repo)
            head = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            feature = human_state(repo)
            # The candidate is identifiable and the open item is real.
            self.assertEqual(feature["validation"]["result"], "pending")
            self.assertEqual(feature["validation"]["commit"], None)
            self.assertEqual(feature["validation"]["command"], None)
            self.assertEqual(feature["review"]["decision"], "pending")
            self.assertEqual(feature["release"]["status"], "pending")
            self.assertEqual(feature["status"], "in_progress")
            self.assertEqual(feature["tasks"][HUMAN_TASK]["status"], "done")
            # Nothing recorded a pass or a fail for the waiting candidate.
            self.assertEqual(lifecycle.next_action(repo)["stage"], "validate")
            state = lifecycle.load(repo)
            self.assertEqual(state["features"][HUMAN_FEATURE]["validation"]["result"], "pending")
            self.assertEqual(state["features"][HUMAN_FEATURE]["review"]["decision"], "pending")
            self.assertEqual(state["features"][HUMAN_FEATURE]["release"]["status"], "pending")
            self.assertIsNone(state["features"][HUMAN_FEATURE]["validation"]["at"])
            self.assertIsNone(state["features"][HUMAN_FEATURE]["review"]["at"])
            self.assertIsNone(state["features"][HUMAN_FEATURE]["release"]["at"])
            # The candidate that a person would receive is a real commit.
            self.assertEqual(len(head), 40)
            self.assertEqual(
                test_support.git(repo, "cat-file", "-t", head).stdout.strip(), "commit",
            )
            # The pending checkpoint records the candidate, the open item and the
            # continuation action in the fixed five sections.
            path = write_human_checkpoint(
                repo, HUMAN_FEATURE,
                location=f"Feature / branch / HEAD / workspace：{HUMAN_FEATURE} / "
                         f"{human_state(repo)['branch']} / {head} / clean",
                point="plan",
                approved=approved_mapping(repo, HUMAN_FEATURE, "plan"),
                tested_commit=head,
                review=f"{NO_REVIEW_MARKER}；本次候选尚未记录任何评审结论",
                pending="待验项：真人操作 CLI；候选身份见「定位」",
                next_step="等待约定的人操作并答复；在此之前保持 pending",
                references=[f"候选 commit：{head}"],
            )
            text = path.read_text(encoding="utf-8")
            self.assertEqual(
                checkpoint_sections(path),
                ["## 定位", "## 已确认", "## 未完成", "## 下一步", "## 必要引用"],
            )
            self.assertLessEqual(len(text.splitlines()), 60)
            self.assertIn(head, text)
            # The checkpoint records no pass and no fail for this candidate.
            self.assertNotIn("pass", text)
            self.assertNotIn("fail", text)
            # The mapping is readable from disk and agrees with the CLI.
            self.assertEqual(parse_checkpoint_mapping(path),
                             approved_mapping(repo, HUMAN_FEATURE, "plan"))
            self.assertEqual(checkpoint_recovery_mismatches(
                repo, path, HUMAN_FEATURE, "plan", require_prior_review=False), [])

    def test_human_wait_oracle_rejects_recorded_pass_and_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo, with_cli=True)
            human_complete_task(repo)
            self.assertEqual(assert_human_wait(self, repo, feature_id=HUMAN_FEATURE,
                                               task_id=HUMAN_TASK),
                             test_support.git(repo, "rev-parse", "HEAD").stdout.strip())
            cli(repo, "record-validation", "--feature-id", HUMAN_FEATURE, "--result", "fail")
            with self.assertRaises(AssertionError):
                assert_human_wait(self, repo, feature_id=HUMAN_FEATURE, task_id=HUMAN_TASK)
            cli(repo, "record-validation", "--feature-id", HUMAN_FEATURE, "--result", "pass")
            with self.assertRaises(AssertionError):
                assert_human_wait(self, repo, feature_id=HUMAN_FEATURE, task_id=HUMAN_TASK)

    def test_known_failure_reopen_keeps_the_accessible_receipt_and_the_new_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo, with_cli=True)
            human_complete_task(repo)
            (repo / "cli.py").write_text('print("incorrect result")\n', encoding="utf-8")
            failed_candidate = commit(repo, "failed CLI candidate")
            failure = subprocess.run([sys.executable, "-B", "-m", "unittest", "-q", "test_cli"],
                                     cwd=repo, capture_output=True, text=True)
            self.assertNotEqual(failure.returncode, 0)
            cli(repo, "record-validation", "--feature-id", HUMAN_FEATURE, "--result", "fail",
                "--test-command", "python3 -m unittest -q test_cli")
            failed_commit = commit(repo, "recorded failure")
            # The original failure is retrieved and parsed for this feature.
            failed_state = json.loads(test_support.git(
                repo, "show", f"{failed_commit}:.sdlc-v1/state.json",
            ).stdout)
            failed_feature = failed_state["features"][HUMAN_FEATURE]
            self.assertEqual(failed_feature["validation"]["result"], "fail")
            self.assertEqual(failed_feature["validation"]["command"],
                             "python3 -m unittest -q test_cli")
            # The recorded failure points at the candidate that actually failed.
            self.assertEqual(failed_feature["validation"]["commit"], failed_candidate)
            self.assertEqual(failed_feature["review"]["decision"], "pending")
            # Reopen walks done -> todo -> in_progress -> done.
            cli(repo, "set-task-status", "--feature-id", HUMAN_FEATURE, "--task-id", HUMAN_TASK,
                "--status", "todo")
            cli(repo, "set-task-status", "--feature-id", HUMAN_FEATURE, "--task-id", HUMAN_TASK,
                "--status", "in_progress")
            (repo / "cli.py").write_text(SOLUTION, encoding="utf-8")
            repaired = subprocess.run([sys.executable, "-B", "-m", "unittest", "-q", "test_cli"],
                                      cwd=repo, capture_output=True, text=True)
            self.assertEqual(repaired.returncode, 0, repaired.stderr)
            cli(repo, "set-task-status", "--feature-id", HUMAN_FEATURE, "--task-id", HUMAN_TASK,
                "--status", "done")
            # The repaired candidate is committed separately from the failed one.
            repaired_commit = commit(repo, "repaired candidate")
            feature = human_state(repo)
            # The reopened candidate is pending and needs its own validation.
            self.assertEqual(feature["validation"]["result"], "pending")
            self.assertEqual(feature["validation"]["commit"], None)
            self.assertEqual(feature["review"]["decision"], "pending")
            self.assertEqual(feature["release"]["status"], "pending")
            self.assertEqual(feature["status"], "in_progress")
            self.assertEqual(feature["tasks"][HUMAN_TASK]["status"], "done")
            validation_point = human_verify(repo, "--feature-id", HUMAN_FEATURE, "--point", "validation")
            self.assertEqual(validation_point["result"], "missing")
            # The repaired candidate is a different commit than the failed one.
            self.assertNotEqual(repaired_commit, failed_commit)
            self.assertNotEqual(failed_candidate, repaired_commit)
            self.assertNotEqual(tracked_bytes(repo, failed_candidate, "cli.py"),
                                tracked_bytes(repo, repaired_commit, "cli.py"))
            # The current candidate is the repaired one, and it passed its check.
            self.assertEqual(feature["validation"]["commit"], None)
            self.assertEqual(feature["validation"]["result"], "pending")
            # The failure stays readable as history and is not the current result.
            history = (repo / ".sdlc-v1/context/engineering.md").read_text(encoding="utf-8")
            self.assertIn("TASK-human", history)
            self.assertNotEqual(feature["validation"]["result"], "fail")
            # The reopened candidate is not the failed one, so the recorded
            # failure cannot be mistaken for the current result.
            self.assertNotEqual(feature["validation"]["commit"], failed_feature["validation"]["commit"])

    def test_reopened_candidate_does_not_restore_a_previous_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            human_pass_and_review(repo)
            cli(repo, "set-task-status", "--feature-id", HUMAN_FEATURE, "--task-id", HUMAN_TASK,
                "--status", "todo")
            feature = human_state(repo)
            # The current pass is not recovered from history; it needs re-validation.
            self.assertEqual(feature["validation"]["result"], "pending")
            self.assertEqual(feature["validation"]["commit"], None)
            self.assertEqual(feature["review"]["decision"], "pending")
            self.assertEqual(feature["release"]["status"], "pending")
            validation_point = human_verify(repo, "--feature-id", HUMAN_FEATURE, "--point", "validation")
            self.assertEqual(validation_point["result"], "missing")

    def test_uncommitted_pass_leaves_history_incomplete_and_needs_revalidation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            # Record a pass and an approval, and keep both uncommitted, so Git
            # and the projection cannot both show the earlier formal result.
            cli(repo, "record-validation", "--feature-id", HUMAN_FEATURE, "--result", "pass",
                "--test-command", "python3 -m unittest -q test_cli")
            cli(repo, "record-review", "--feature-id", HUMAN_FEATURE, "--decision", "approved",
                "--by", "scripted reference")
            uncommitted = human_state(repo)
            self.assertEqual(uncommitted["validation"]["result"], "pass")
            self.assertEqual(uncommitted["review"]["decision"], "approved")
            self.assertEqual(
                test_support.git(repo, "status", "--porcelain", "--", ".sdlc-v1/state.json").stdout,
                " M .sdlc-v1/state.json\n",
            )
            cli(repo, "set-task-status", "--feature-id", HUMAN_FEATURE, "--task-id", HUMAN_TASK,
                "--status", "todo")
            cli(repo, "set-task-status", "--feature-id", HUMAN_FEATURE, "--task-id", HUMAN_TASK,
                "--status", "in_progress")
            cli(repo, "set-task-status", "--feature-id", HUMAN_FEATURE, "--task-id", HUMAN_TASK,
                "--status", "done")
            feature = human_state(repo)
            self.assertEqual(feature["validation"]["result"], "pending")
            # Neither the current projection nor HEAD holds that pass or approval.
            projection = lifecycle.load(repo)["features"][HUMAN_FEATURE]
            self.assertEqual(projection["validation"]["result"], "pending")
            self.assertEqual(projection["review"]["decision"], "pending")
            committed = json.loads(test_support.git(
                repo, "show", "HEAD:.sdlc-v1/state.json",
            ).stdout)["features"][HUMAN_FEATURE]
            self.assertEqual(committed["validation"]["result"], "pending")
            self.assertEqual(committed["review"]["decision"], "pending")
            # The snapshots are unbound in both the projection and HEAD.
            validation_point = human_verify(repo, "--feature-id", HUMAN_FEATURE, "--point", "validation")
            self.assertEqual(validation_point["result"], "missing")
            review_point = human_verify(repo, "--feature-id", HUMAN_FEATURE, "--point", "review")
            self.assertEqual(review_point["result"], "missing")
            self.assertNotIn("validation", committed.get("acceptance", {}))
            self.assertNotIn("review", committed.get("acceptance", {}))
            # There is no recoverable receipt of that pass anywhere in Git.
            history = test_support.git(repo, "log", "--format=%H", "--", ".sdlc-v1/state.json").stdout
            recoverable = []
            for revision in history.split():
                state = json.loads(test_support.git(
                    repo, "show", f"{revision}:.sdlc-v1/state.json",
                ).stdout)["features"][HUMAN_FEATURE]
                if state["validation"]["result"] == "pass":
                    recoverable.append(revision)
            self.assertEqual(recoverable, [])
            # Even a completed reopened task cannot prove this is the first wait.
            self.assertEqual(feature["status"], "in_progress")
            self.assertEqual(feature["tasks"][HUMAN_TASK]["status"], "done")
            self.assertEqual(lifecycle.next_action(repo)["stage"], "validate")

    def test_old_pass_must_be_revoked_before_new_evidence_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            human_pass_and_review(repo)
            # A new obligation without evidence is not satisfied by the old pass.
            cli(repo, "record-validation", "--feature-id", HUMAN_FEATURE, "--result", "fail")
            feature = human_state(repo)
            self.assertEqual(feature["validation"]["result"], "fail")
            self.assertEqual(feature["review"]["decision"], "pending")
            self.assertEqual(feature["release"]["status"], "pending")
            self.assertEqual(feature["status"], "in_progress")
            for point in ("validation", "review"):
                result = human_verify(repo, "--feature-id", HUMAN_FEATURE, "--point", point)
                self.assertEqual(result["result"], "missing")

    def test_rejected_failure_record_preserves_state_and_blocks_downstream(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            human_pass_and_review(repo)
            state_path = repo / ".sdlc-v1/state.json"
            before = state_path.read_bytes()
            # A dirty business worktree makes the failure record impossible.
            (repo / "cli.py").write_text(SOLUTION + "\n# uncommitted change\n", encoding="utf-8")
            dirty = business_files(repo)
            result = human_cli(repo, "record-validation", "--feature-id", HUMAN_FEATURE,
                               "--result", "fail")
            self.assertEqual(result.returncode, 2)
            self.assertIn("validation-and-release-require-clean-worktree", result.stderr)
            self.assertEqual(state_path.read_bytes(), before)
            self.assertEqual(business_files(repo), dirty)
            # The old approval still exists but must not be used to continue.
            self.assertEqual(human_state(repo)["review"]["decision"], "approved")

    # ------------------------------------------------------------------
    # 2. Approval re-record: pre-approved mapping, read-back, checkpoints
    # ------------------------------------------------------------------

    def test_approved_original_text_digests_are_proven_from_tracked_git(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            approved_commit = last_commit_for(repo, ".sdlc-v1/context/product.md")
            recorded = recorded_mapping(repo, HUMAN_FEATURE, "plan")
            for ref, expected in recorded.items():
                original = tracked_bytes(repo, approved_commit, ref)
                # The existing context-v1 function reproduces the recorded digest
                # from the real tracked bytes of the accepted revision.
                self.assertEqual(context_digest(original, ref), expected)

    def test_pure_append_control_rebinds_exactly_the_preapproved_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            validated = human_pass_and_review(repo)
            original_commit = last_commit_for(repo, ".sdlc-v1/context/engineering.md")
            # The original bound text is recoverable and matches what was recorded.
            plan_recorded = recorded_mapping(repo, HUMAN_FEATURE, "plan")
            for ref, expected in plan_recorded.items():
                self.assertEqual(
                    context_digest(tracked_bytes(repo, original_commit, ref), ref), expected,
                )
            # A pure evidence append only changes the engineering context.
            engineering = repo / ".sdlc-v1/context/engineering.md"
            with engineering.open("a", encoding="utf-8") as stream:
                stream.write(HUMAN_EVIDENCE_APPEND)
            commit(repo, "append evidence")
            # Fix the pre-approved mapping for BOTH bound paths before re-recording.
            preapproved = {
                ".sdlc-v1/context/engineering.md": context_digest(
                    (repo / ".sdlc-v1/context/engineering.md").read_bytes(),
                    ".sdlc-v1/context/engineering.md",
                ),
                ".sdlc-v1/context/product.md": context_digest(
                    (repo / ".sdlc-v1/context/product.md").read_bytes(),
                    ".sdlc-v1/context/product.md",
                ),
            }
            self.assertEqual(preapproved[".sdlc-v1/context/product.md"],
                             plan_recorded[".sdlc-v1/context/product.md"])
            result = human_cli(
                repo, "start-feature", "--requirement-id", REQ, "--feature-id", HUMAN_FEATURE,
                "--branch", human_state(repo)["branch"],
                "--engineering-context-ref", ".sdlc-v1/context/engineering.md",
                "--refresh-acceptance",
            )
            self.assertEqual(result.returncode, 0)
            # Read back and compare every bound path against the pre-approved map.
            readback = human_verify(repo, "--feature-id", HUMAN_FEATURE, "--point", "plan")
            self.assertEqual(readback["result"], "match")
            for item in readback["points"][0]["files"]:
                ref = item["path"]
                self.assertIn(ref, preapproved)
                self.assertEqual(item["expected_digest"], preapproved[ref])
                self.assertEqual(item["current_digest"], preapproved[ref])
            # The original test commit is preserved; only the plan point moved.
            self.assertEqual(human_state(repo)["validation"]["commit"], validated)
            self.assertEqual(human_state(repo)["review"]["decision"], "approved")

    def test_approved_mapping_mismatch_is_detected_even_when_the_cli_reports_match(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            preapproved = approved_mapping(repo, HUMAN_FEATURE, "plan")
            product_path = repo / ".sdlc-v1/context/product.md"
            # Insert a substantive product condition immediately before the call.
            with product_path.open("a", encoding="utf-8") as stream:
                stream.write(HUMAN_SUBSTANTIVE_INSERT)
            result = human_cli(
                repo, "start-feature", "--requirement-id", REQ, "--feature-id", HUMAN_FEATURE,
                "--branch", human_state(repo)["branch"],
                "--engineering-context-ref", ".sdlc-v1/context/engineering.md",
                "--refresh-acceptance",
            )
            self.assertEqual(result.returncode, 0)
            # The CLI reports match against the newly recorded fingerprint ...
            after = human_verify(repo, "--feature-id", HUMAN_FEATURE, "--point", "plan")
            self.assertEqual(after["result"], "match")
            # ... but the pre-approved mapping differs for the changed path, so the
            # comparison against the pre-approved value detects the deviation.
            for item in after["points"][0]["files"]:
                ref = item["path"]
                self.assertIn(ref, preapproved)
                if ref.endswith("product.md"):
                    self.assertNotEqual(item["current_digest"], preapproved[ref])
                    self.assertEqual(item["expected_digest"], item["current_digest"])
                else:
                    self.assertEqual(item["current_digest"], preapproved[ref])

    def test_checkpoint_records_the_validation_point_and_its_preapproved_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            validated = human_pass_and_review(repo)
            original_record_commit = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            review = human_state(repo)["review"]
            # The checkpoint records the acceptance point that is actually being
            # re-recorded, not the plan point.
            point = "validation"
            approved = approved_mapping(repo, HUMAN_FEATURE, point)
            self.assertEqual(set(approved), {
                ".sdlc-v1/context/product.md", ".sdlc-v1/context/engineering.md",
            })
            path = write_human_checkpoint(
                repo, HUMAN_FEATURE,
                location=f"Feature / branch / HEAD / workspace：{HUMAN_FEATURE} / "
                         f"{human_state(repo)['branch']} / {validated} / clean",
                point=point,
                approved=approved,
                tested_commit=validated,
                review=f"{review['decision']} by {review['by']}",
                pending="保留既有未完成事项：核对旧 Review 的决定、reviewer 与证据",
                next_step="执行 record-validation 并逐项比较读回摘要",
                references=[f"原 state：{original_record_commit}:.sdlc-v1/state.json"],
            )
            text = path.read_text(encoding="utf-8")
            # The fixed five sections and their order are preserved.
            self.assertEqual(
                checkpoint_sections(path),
                ["## 定位", "## 已确认", "## 未完成", "## 下一步", "## 必要引用"],
            )
            self.assertLessEqual(len(text.splitlines()), 60)
            # The recorded point, tested commit and original review are on disk.
            self.assertEqual(parse_checkpoint_field(path, CHECKPOINT_POINT_PREFIX), point)
            self.assertEqual(parse_checkpoint_field(path, CHECKPOINT_COMMIT_PREFIX), validated)
            self.assertIn(review["by"], parse_checkpoint_field(path, CHECKPOINT_REVIEW_PREFIX))
            self.assertIn(review["decision"], parse_checkpoint_field(path, CHECKPOINT_REVIEW_PREFIX))
            # The pre-approved mapping is persisted with the real digests and is
            # recoverable from disk without any in-memory help.
            self.assertEqual(parse_checkpoint_mapping(path), approved)
            for ref, digest in approved.items():
                self.assertIn(digest, text)
            # The existing open item is preserved rather than overwritten.
            self.assertIn("保留既有未完成事项", text)
            # The on-disk mapping agrees with every path the CLI reports.
            self.assertEqual(checkpoint_recovery_mismatches(repo, path, HUMAN_FEATURE, point), [])

    def test_checkpoint_recovery_rejects_tampered_identity_and_missing_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            validated = human_pass_and_review(repo)
            original_record_commit = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            point = "validation"
            approved = approved_mapping(repo, HUMAN_FEATURE, point)
            path = write_human_checkpoint(
                repo, HUMAN_FEATURE,
                location="Feature / branch / HEAD / workspace：FEAT-human / main / HEAD / clean",
                point=point,
                approved=approved,
                tested_commit=validated,
                review="approved by scripted reference",
                pending="保留既有未完成事项：核对旧 Review 的决定、reviewer 与证据",
                next_step="执行 record-validation 并逐项比较读回摘要",
                references=[f"原 state：{original_record_commit}:.sdlc-v1/state.json"],
            )
            original_text = path.read_text(encoding="utf-8")
            state_path = repo / ".sdlc-v1/state.json"
            state_before = state_path.read_bytes()

            def expect_gap(label: str, replacement: tuple) -> None:
                with self.subTest(tampered=label):
                    text = original_text.replace(*replacement)
                    self.assertNotEqual(text, original_text)
                    path.write_text(text, encoding="utf-8")
                    differences = checkpoint_recovery_mismatches(repo, path, HUMAN_FEATURE, point)
                    self.assertNotEqual(differences, [], label)
                    # The check itself writes nothing.
                    self.assertEqual(state_path.read_bytes(), state_before)
                    path.write_text(original_text, encoding="utf-8")

            # A different reviewer.
            expect_gap("reviewer", ("approved by scripted reference", "approved by someone else"))
            # A different decision.
            expect_gap("decision", ("approved by scripted reference", "changes_requested by scripted reference"))
            # A different tested commit.
            expect_gap("commit", (f"{CHECKPOINT_COMMIT_PREFIX}{validated}",
                                  f"{CHECKPOINT_COMMIT_PREFIX}{'0' * 40}"))
            # A Git reference that does not resolve.
            expect_gap("git reference", (f"{original_record_commit}:.sdlc-v1/state.json",
                                         f"{'0' * 40}:.sdlc-v1/state.json"))
            # Each bound path digest.
            for ref in sorted(approved):
                expect_gap(f"digest {ref}", (approved[ref], "0" * 64))
            # An emptied mapping.
            emptied = "\n".join(
                line for line in original_text.splitlines()
                if not line.strip().startswith(CHECKPOINT_MAPPING_PREFIX.strip())
            ) + "\n"
            path.write_text(emptied, encoding="utf-8")
            differences = checkpoint_recovery_mismatches(repo, path, HUMAN_FEATURE, point)
            self.assertNotEqual(differences, [])
            self.assertTrue(any("no pre-approved path mapping" in difference
                                for difference in differences), differences)
            self.assertEqual(state_path.read_bytes(), state_before)
            path.write_text(original_text, encoding="utf-8")
            # A missing checkpoint file.
            path.unlink()
            missing = checkpoint_recovery_mismatches(repo, path, HUMAN_FEATURE, point)
            self.assertNotEqual(missing, [])
            self.assertTrue(any("missing" in difference for difference in missing), missing)
            self.assertEqual(state_path.read_bytes(), state_before)
            # A missing original record: the referenced commit does not exist.
            path.write_text(original_text.replace(
                original_record_commit, "0" * 40,
            ), encoding="utf-8")
            unresolved = checkpoint_recovery_mismatches(repo, path, HUMAN_FEATURE, point)
            self.assertNotEqual(unresolved, [])
            self.assertEqual(state_path.read_bytes(), state_before)
            path.write_text(original_text, encoding="utf-8")
            # The restored checkpoint compares clean again.
            self.assertEqual(checkpoint_recovery_mismatches(repo, path, HUMAN_FEATURE, point), [])

    def test_checkpoint_recovery_comparison_detects_a_tampered_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            validated = human_pass_and_review(repo)
            original_record_commit = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            point = "validation"
            approved = approved_mapping(repo, HUMAN_FEATURE, point)
            path = write_human_checkpoint(
                repo, HUMAN_FEATURE,
                location="Feature / branch / HEAD / workspace：FEAT-human / main / HEAD / clean",
                point=point,
                approved=approved,
                tested_commit=validated,
                review="approved by scripted reference",
                pending="保留既有未完成事项：核对旧 Review 的决定、reviewer 与证据",
                next_step="执行 record-validation 并逐项比较读回摘要",
                references=[f"原 state：{original_record_commit}:.sdlc-v1/state.json"],
            )
            self.assertEqual(checkpoint_recovery_mismatches(repo, path, HUMAN_FEATURE, point), [])
            # Tampering any single bound path on disk must break the comparison.
            for ref in sorted(approved):
                with self.subTest(tampered=ref):
                    original = path.read_text(encoding="utf-8")
                    tampered = original.replace(approved[ref], "0" * 64)
                    self.assertNotEqual(tampered, original)
                    path.write_text(tampered, encoding="utf-8")
                    differences = checkpoint_recovery_mismatches(repo, path, HUMAN_FEATURE, point)
                    self.assertNotEqual(differences, [])
                    self.assertTrue(any(ref in difference for difference in differences), differences)
                    path.write_text(original, encoding="utf-8")
            # The restored file compares clean again.
            self.assertEqual(checkpoint_recovery_mismatches(repo, path, HUMAN_FEATURE, point), [])

    def test_review_recovery_rejects_removed_or_denied_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            validated = human_pass_and_review(repo)
            original_ref = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            approved = approved_mapping(repo, HUMAN_FEATURE, "validation")
            path = write_human_checkpoint(
                repo, HUMAN_FEATURE, location="selected Feature and workspace",
                point="validation", approved=approved, tested_commit=validated,
                review="approved by scripted reference", pending="restore old Review",
                next_step="read back validation", references=[f"原 state：{original_ref}:.sdlc-v1/state.json"],
            )
            original = path.read_text(encoding="utf-8")
            cli(repo, "record-validation", "--feature-id", HUMAN_FEATURE, "--result", "pass")
            self.assertEqual(human_state(repo)["review"]["decision"], "pending")
            state_path = repo / ".sdlc-v1/state.json"
            before = state_path.read_bytes()
            for label, replacement in (("missing", ""),
                                       ("false no-review marker", f"{CHECKPOINT_REVIEW_PREFIX}{NO_REVIEW_MARKER}")):
                with self.subTest(case=label):
                    text = original.replace(f"{CHECKPOINT_REVIEW_PREFIX}approved by scripted reference", replacement)
                    text = text.replace(f"- 原 state：{original_ref}:.sdlc-v1/state.json\n", "")
                    path.write_text(text, encoding="utf-8")
                    self.assertNotEqual(checkpoint_recovery_mismatches(
                        repo, path, HUMAN_FEATURE, "validation"), [])
                    self.assertEqual(state_path.read_bytes(), before)
                    self.assertEqual(human_state(repo)["review"]["decision"], "pending")

    def test_review_recovery_rejects_pending_as_a_prior_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            cli(repo, "record-validation", "--feature-id", HUMAN_FEATURE, "--result", "pass")
            validated = human_state(repo)["validation"]["commit"]
            original_ref = commit(repo, "validation without review")
            approved = approved_mapping(repo, HUMAN_FEATURE, "validation")
            path = write_human_checkpoint(
                repo, HUMAN_FEATURE, location="selected Feature and workspace",
                point="validation", approved=approved, tested_commit=validated,
                review="pending by None", pending="restore old Review",
                next_step="read back validation", references=[f"原 state：{original_ref}:.sdlc-v1/state.json"],
            )
            before = (repo / ".sdlc-v1/state.json").read_bytes()
            self.assertNotEqual(checkpoint_recovery_mismatches(repo, path, HUMAN_FEATURE, "validation"), [])
            self.assertEqual((repo / ".sdlc-v1/state.json").read_bytes(), before)

    def test_interrupted_re_record_states_are_distinguishable_by_actual_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            validated = human_pass_and_review(repo)
            original_record_commit = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            # (a) Not yet written: no checkpoint exists at all.
            self.assertFalse(human_checkpoint_path(repo, HUMAN_FEATURE).exists())
            recorded_before = recorded_mapping(repo, HUMAN_FEATURE, "validation")
            # The approved body gains one pure evidence append.
            engineering = repo / ".sdlc-v1/context/engineering.md"
            with engineering.open("a", encoding="utf-8") as stream:
                stream.write(HUMAN_EVIDENCE_APPEND)
            commit(repo, "append evidence")
            # The main Agent fixes the mapping it approves for both bound paths.
            approved = approved_mapping(repo, HUMAN_FEATURE, "validation")
            self.assertNotEqual(approved[".sdlc-v1/context/engineering.md"],
                                recorded_before[".sdlc-v1/context/engineering.md"])
            # (b) Written but not called: the checkpoint holds the pre-approved map
            #     while the recorded validation snapshot still shows the older digests.
            path = write_human_checkpoint(
                repo, HUMAN_FEATURE,
                location="Feature / branch / HEAD / workspace：FEAT-human / main / HEAD / clean",
                point="validation",
                approved=approved,
                tested_commit=validated,
                review="approved by scripted reference",
                pending="保留既有未完成事项：核对旧 Review 的决定、reviewer 与证据",
                next_step="执行 record-validation 并逐项比较读回摘要",
                references=[f"原 state：{original_record_commit}:.sdlc-v1/state.json"],
            )
            self.assertTrue(path.exists())
            self.assertEqual(recorded_mapping(repo, HUMAN_FEATURE, "validation"), recorded_before)
            # The comparison is made against the mapping parsed from disk.
            self.assertEqual(parse_checkpoint_mapping(path), approved)
            differences = checkpoint_recovery_mismatches(repo, path, HUMAN_FEATURE, "validation")
            self.assertNotEqual(differences, [])
            self.assertTrue(any("expected" in difference for difference in differences), differences)
            # (c) Called but not read back: the validation point moved to the approved
            #     digest while the plan snapshot still carries the older one.
            cli(repo, "record-validation", "--feature-id", HUMAN_FEATURE, "--result", "pass",
                "--test-command", "python3 -m unittest -q test_cli")
            validation_after = recorded_mapping(repo, HUMAN_FEATURE, "validation")
            plan_snapshot = recorded_mapping(repo, HUMAN_FEATURE, "plan")
            self.assertNotEqual(validation_after[".sdlc-v1/context/engineering.md"],
                                plan_snapshot[".sdlc-v1/context/engineering.md"])
            # The read-back comparison against the saved mapping now agrees.
            self.assertEqual(validation_after, approved)
            self.assertEqual(checkpoint_recovery_mismatches(repo, path, HUMAN_FEATURE, "validation"), [])

    def test_re_record_after_validation_clears_the_old_review_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            human_pass_and_review(repo)
            self.assertEqual(human_state(repo)["review"]["decision"], "approved")
            self.assertIn("review", human_feature_state(repo, HUMAN_FEATURE)["acceptance"])
            # Re-recording validation clears the old review record and its snapshot.
            cli(repo, "record-validation", "--feature-id", HUMAN_FEATURE, "--result", "pass",
                "--test-command", "python3 -m unittest -q test_cli")
            feature = human_state(repo)
            self.assertEqual(feature["review"]["decision"], "pending")
            self.assertEqual(feature["release"]["status"], "pending")
            self.assertNotIn("review", feature["acceptance"])
            self.assertIn("validation", feature["acceptance"])

    def test_validation_written_but_not_read_back_leaves_the_pending_review_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            original_tested_commit = human_pass_and_review(repo)
            original_record_commit = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            original_review = copy.deepcopy(human_state(repo)["review"])
            # The engineering body changes, so a re-record is required.
            engineering = repo / ".sdlc-v1/context/engineering.md"
            with engineering.open("a", encoding="utf-8") as stream:
                stream.write(HUMAN_EVIDENCE_APPEND)
            commit(repo, "append evidence")
            approved = approved_mapping(repo, HUMAN_FEATURE, "validation")
            path = write_human_checkpoint(
                repo, HUMAN_FEATURE,
                location="Feature / branch / HEAD / workspace：FEAT-human / main / HEAD / clean",
                point="validation",
                approved=approved,
                tested_commit=original_tested_commit,
                review=f"{original_review['decision']} by {original_review['by']}",
                pending="保留既有未完成事项：核对旧 Review 的决定、reviewer 与证据",
                next_step="按 validation → review 顺序恢复，并逐项比较读回摘要",
                references=[f"原评审：{original_record_commit}:.sdlc-v1/state.json"],
            )
            # The validation re-record is written, but the read-back has not
            # happened yet, so the old review record is already cleared.
            cli(repo, "record-validation", "--feature-id", HUMAN_FEATURE, "--result", "pass",
                "--test-command", "python3 -m unittest -q test_cli")
            feature = human_state(repo)
            self.assertEqual(feature["validation"]["result"], "pass")
            self.assertEqual(feature["review"]["decision"], "pending")
            self.assertEqual(feature["release"]["status"], "pending")
            self.assertNotIn("review", feature["acceptance"])
            # The validation snapshot now matches the approved body, so the
            # read-back comparison against the saved mapping is what confirms it.
            self.assertEqual(checkpoint_recovery_mismatches(repo, path, HUMAN_FEATURE, "validation"), [])
            # The old review conclusion is no longer in state; it can only be
            # located in the original committed record.
            original_ref = parse_checkpoint_field(path, "- 原评审：")
            self.assertEqual(original_ref, f"{original_record_commit}:.sdlc-v1/state.json")
            self.assertEqual(parse_checkpoint_field(path, CHECKPOINT_COMMIT_PREFIX), original_tested_commit)
            original = json.loads(test_support.git(repo, "show", original_ref).stdout)
            saved = original["features"][HUMAN_FEATURE]
            self.assertEqual(saved["review"], original_review)
            self.assertEqual(parse_checkpoint_field(path, CHECKPOINT_REVIEW_PREFIX),
                             f"{saved['review']['decision']} by {saved['review']['by']}")
            self.assertEqual(saved["validation"]["commit"], original_tested_commit)

    def test_new_clone_without_the_checkpoint_cannot_reuse_the_local_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            validated = human_pass_and_review(repo)
            original_record_commit = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            # The engineering body changes, so a re-record is required.
            engineering = repo / ".sdlc-v1/context/engineering.md"
            with engineering.open("a", encoding="utf-8") as stream:
                stream.write(HUMAN_EVIDENCE_APPEND)
            commit(repo, "append evidence")
            # The checkpoint is written and verified BEFORE the re-record call.
            approved = approved_mapping(repo, HUMAN_FEATURE, "validation")
            path = write_human_checkpoint(
                repo, HUMAN_FEATURE,
                location="Feature / branch / HEAD / workspace：FEAT-human / main / HEAD / clean",
                point="validation",
                approved=approved,
                tested_commit=validated,
                review="approved by scripted reference",
                pending="保留既有未完成事项：核对旧 Review 的决定、reviewer 与证据",
                next_step="执行 record-validation 并逐项比较读回摘要",
                references=[f"原 state：{original_record_commit}:.sdlc-v1/state.json"],
            )
            self.assertEqual(checkpoint_recovery_mismatches(repo, path, HUMAN_FEATURE, "validation",
                                                            recorded=False), [])
            # Now the re-record happens and clears the old review.
            cli(repo, "record-validation", "--feature-id", HUMAN_FEATURE, "--result", "pass",
                "--test-command", "python3 -m unittest -q test_cli")
            self.assertEqual(human_state(repo)["review"]["decision"], "pending")
            # The checkpoint is deliberately not committed; only the re-recorded
            # state and the necessary context are synchronized into Git.
            test_support.git(repo, "add", ".sdlc-v1/state.json", ".sdlc-v1/context")
            test_support.git(repo, "commit", "-m", "sync re-recorded state")
            self.assertTrue(path.exists())
            self.assertNotIn(
                ".sdlc-v1/checkpoints",
                test_support.git(repo, "ls-files", "--", ".sdlc-v1").stdout,
            )
            clone = root / "clone"
            test_support.git(repo, "clone", str(repo), str(clone))
            # The clone has the new snapshot ...
            cloned = human_feature_state(clone, HUMAN_FEATURE)
            self.assertEqual(cloned["acceptance"]["validation"]["documents"],
                             recorded_mapping(repo, HUMAN_FEATURE, "validation"))
            self.assertEqual(cloned["validation"]["result"], "pass")
            # ... but no usable pre-approval checkpoint, because it was never
            # committed. A plain match is not the original pre-approval evidence.
            self.assertFalse(human_checkpoint_path(clone, HUMAN_FEATURE).exists())
            clone_point = human_verify(clone, "--feature-id", HUMAN_FEATURE, "--point", "validation")
            self.assertEqual(clone_point["result"], "match")
            # The clone cannot run the recovery check, because the approved
            # mapping was never synchronized to it.
            self.assertNotEqual(
                checkpoint_recovery_mismatches(clone, human_checkpoint_path(clone, HUMAN_FEATURE),
                                              HUMAN_FEATURE, "validation"),
                [],
            )
            # The old Review was not restored in the clone.
            self.assertEqual(cloned["review"]["decision"], "pending")
            self.assertIsNone(cloned["review"]["by"])
            self.assertNotIn("review", cloned["acceptance"])

    # ------------------------------------------------------------------
    # 3. Refusal path
    # ------------------------------------------------------------------

    def test_refusal_path_succeeds_while_the_validation_fingerprint_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            human_pass_and_review(repo)
            feature_before = human_state(repo)
            validation_record_before = copy.deepcopy(feature_before["validation"])
            validation_snapshot_before = copy.deepcopy(feature_before["acceptance"]["validation"])
            engineering_path = repo / ".sdlc-v1/context/engineering.md"
            with engineering_path.open("a", encoding="utf-8") as stream:
                stream.write("\nFinding: a must-fix defect was found.\n")
            stale = human_verify(repo, "--feature-id", HUMAN_FEATURE, "--point", "validation")
            self.assertEqual(stale["result"], "stale")
            result = human_cli(repo, "record-review", "--feature-id", HUMAN_FEATURE,
                               "--decision", "changes_requested", "--by", "scripted reference")
            self.assertEqual(result.returncode, 0)
            feature = human_state(repo)
            self.assertEqual(feature["review"]["decision"], "changes_requested")
            self.assertEqual(feature["release"]["status"], "pending")
            self.assertEqual(feature["status"], "in_progress")
            # The refusal does not clear the passing validation record or snapshot.
            self.assertEqual(feature["validation"], validation_record_before)
            self.assertEqual(feature["validation"]["result"], "pass")
            self.assertEqual(feature["acceptance"]["validation"], validation_snapshot_before)
            review_point = human_verify(repo, "--feature-id", HUMAN_FEATURE, "--point", "review")
            self.assertEqual(review_point["result"], "missing")

    def test_refusal_path_is_rejected_on_a_dirty_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            human_pass_and_review(repo)
            (repo / "cli.py").write_text(SOLUTION + "\n# uncommitted change\n", encoding="utf-8")
            state_path = repo / ".sdlc-v1/state.json"
            before = state_path.read_bytes()
            result = human_cli(repo, "record-review", "--feature-id", HUMAN_FEATURE,
                               "--decision", "changes_requested", "--by", "scripted reference")
            self.assertEqual(result.returncode, 2)
            self.assertIn("validation-and-release-require-clean-worktree", result.stderr)
            self.assertEqual(state_path.read_bytes(), before)
            self.assertEqual(human_state(repo)["review"]["decision"], "approved")

    # ------------------------------------------------------------------
    # 4. Two features on one candidate
    # ------------------------------------------------------------------

    def test_shared_observation_evidence_gates_each_feature_independently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo, with_cli=True, second_feature=True, human_required=False)
            human_complete_task(repo)
            human_complete_task(repo, HUMAN_OTHER_FEATURE, HUMAN_OTHER_TASK)
            candidate = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            # The business check actually runs and its output is recorded.
            run = run_integration_check(repo, INTEGRATION_ITEM_A, candidate)
            self.assertEqual(run["exit"], 0)
            test_support.git(repo, "add", "integration")
            test_support.git(repo, "commit", "-m", "record integration evidence")
            candidate = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            # The shared observation records the candidate, the observer and the
            # acceptance condition of each participating feature.
            conditions = {
                HUMAN_FEATURE: {
                    "required": [INTEGRATION_ITEM_A],
                    "results": {
                        INTEGRATION_ITEM_A: {
                            "result": "pass",
                            "evidence": "the recorded business check exited 0 on the shared candidate",
                            "source": run["path"],
                        },
                    },
                },
                HUMAN_OTHER_FEATURE: {
                    "required": [INTEGRATION_ITEM_B],
                    "results": {},
                },
            }
            observation = repo / INTEGRATION_OBSERVATION
            observation.parent.mkdir(parents=True, exist_ok=True)
            observation.write_text(integration_observation(candidate, conditions=conditions),
                                   encoding="utf-8")
            test_support.git(repo, "add", INTEGRATION_OBSERVATION)
            test_support.git(repo, "commit", "-m", "record shared observation")
            candidate = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            # Both features' tracked engineering contexts locate the same record.
            for ref in (".sdlc-v1/context/engineering.md",
                        ".sdlc-v1/context/engineering-other.md"):
                self.assertIn(INTEGRATION_OBSERVATION, (repo / ref).read_text(encoding="utf-8"))
            expected = {"command": run["command"], "exit": run["exit"], "stdout": run["stdout"]}
            # A's necessary integration result has verifiable content and source.
            self.assertEqual(
                integration_evidence_errors(repo, HUMAN_FEATURE, INTEGRATION_ITEM_A,
                                            candidate=candidate, expected=expected),
                [],
            )
            # B's own item is still missing and stays pending.
            errors = integration_evidence_errors(repo, HUMAN_OTHER_FEATURE, INTEGRATION_ITEM_B,
                                                candidate=candidate, expected=expected)
            self.assertNotEqual(errors, [])
            self.assertTrue(any(INTEGRATION_ITEM_B in error for error in errors), errors)
            # The observation is explicitly synthetic and never claims a person.
            record = json.loads(observation.read_text(encoding="utf-8"))
            self.assertEqual(record["kind"], OBSERVATION_KIND)
            self.assertTrue(record["synthetic"])
            self.assertEqual(record["observer_kind"], OBSERVATION_KIND)
            # This is a self-verifiable A, not a claim of human acceptance.
            # The fixture may record A while B's own condition remains missing.
            human_pass_and_review(repo, commit_result=False)
            self.assertEqual(human_state(repo)["validation"]["result"], "pass")
            self.assertEqual(human_state(repo)["validation"]["commit"], candidate)
            # B's own state is untouched by A's evidence.
            other = human_feature_state(repo, HUMAN_OTHER_FEATURE)
            self.assertEqual(other["validation"]["result"], "pending")
            self.assertEqual(other["release"]["status"], "pending")

    def test_shared_observation_rejects_empty_and_incomplete_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo, with_cli=True, second_feature=True, human_required=False)
            human_complete_task(repo)
            candidate = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            run = run_integration_check(repo, INTEGRATION_ITEM_A, candidate)
            self.assertEqual(run["exit"], 0)
            test_support.git(repo, "add", "integration")
            test_support.git(repo, "commit", "-m", "record integration evidence")
            candidate = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            observation = repo / INTEGRATION_OBSERVATION
            observation.parent.mkdir(parents=True, exist_ok=True)
            expected = {"command": run["command"], "exit": run["exit"], "stdout": run["stdout"]}

            def write_observation(results: dict, conditions: dict = None) -> None:
                if conditions is None:
                    conditions = {
                        HUMAN_FEATURE: {
                            "required": [INTEGRATION_ITEM_A],
                            "results": results,
                        },
                    }
                observation.write_text(
                    integration_observation(candidate, conditions=conditions), encoding="utf-8",
                )

            good_result = {
                "result": "pass",
                "evidence": "the recorded business check exited 0 on the shared candidate",
                "source": run["path"],
            }
            write_observation({INTEGRATION_ITEM_A: good_result})
            self.assertEqual(
                integration_evidence_errors(repo, HUMAN_FEATURE, INTEGRATION_ITEM_A,
                                            candidate=candidate, expected=expected),
                [],
            )
            # A failing result is not a passing integration result.
            write_observation({INTEGRATION_ITEM_A: dict(good_result, result="fail")})
            failed = integration_evidence_errors(repo, HUMAN_FEATURE, INTEGRATION_ITEM_A,
                                                candidate=candidate, expected=expected)
            self.assertNotEqual(failed, [])
            self.assertTrue(any("not 'pass'" in error for error in failed), failed)
            # A source that does not exist in the candidate commit is rejected.
            write_observation({INTEGRATION_ITEM_A: dict(good_result, source="integration/absent.json")})
            absent = integration_evidence_errors(repo, HUMAN_FEATURE, INTEGRATION_ITEM_A,
                                                 candidate=candidate, expected=expected)
            self.assertNotEqual(absent, [])
            self.assertTrue(any("not in candidate" in error for error in absent), absent)
            # A source that exists only in the worktree is rejected too.
            (repo / "integration" / "local-only.json").write_text(
                json.dumps({"item": INTEGRATION_ITEM_A, "candidate": candidate,
                            "command": run["command"], "exit": run["exit"],
                            "stdout": run["stdout"]}) + "\n",
                encoding="utf-8",
            )
            write_observation({INTEGRATION_ITEM_A: dict(good_result,
                                                        source="integration/local-only.json")})
            untracked = integration_evidence_errors(repo, HUMAN_FEATURE, INTEGRATION_ITEM_A,
                                                    candidate=candidate, expected=expected)
            self.assertNotEqual(untracked, [])
            self.assertTrue(any("not in candidate" in error for error in untracked), untracked)
            # A source whose content is unrelated to the actual run is rejected.
            write_observation({INTEGRATION_ITEM_A: good_result})
            source_path = repo / "integration" / f"{INTEGRATION_ITEM_A}.json"
            original_source = source_path.read_bytes()
            source_path.write_text(json.dumps({
                "item": INTEGRATION_ITEM_A, "candidate": candidate,
                "command": "some other command", "exit": 3, "stdout": "unrelated",
            }) + "\n", encoding="utf-8")
            test_support.git(repo, "add", "integration")
            test_support.git(repo, "commit", "-m", "change the evidence content")
            changed = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            mismatched = integration_evidence_errors(repo, HUMAN_FEATURE, INTEGRATION_ITEM_A,
                                                     candidate=changed, expected=expected)
            self.assertNotEqual(mismatched, [])
            self.assertTrue(any("actual run produced" in error for error in mismatched), mismatched)
            source_path.write_bytes(original_source)
            test_support.git(repo, "add", "integration")
            test_support.git(repo, "commit", "-m", "restore the evidence content")
            # An observation that covers only one feature cannot serve the other.
            write_observation({INTEGRATION_ITEM_A: good_result})
            other = integration_evidence_errors(repo, HUMAN_OTHER_FEATURE, INTEGRATION_ITEM_B,
                                                candidate=candidate, expected=expected)
            self.assertNotEqual(other, [])
            self.assertTrue(any(HUMAN_OTHER_FEATURE in error for error in other), other)
            # A record that claims to be a human observation is not accepted.
            forged = json.loads(observation.read_text(encoding="utf-8"))
            forged["kind"] = "human"
            forged["synthetic"] = False
            forged["observer"] = "a product owner"
            observation.write_text(json.dumps(forged, indent=2, sort_keys=True) + "\n",
                                   encoding="utf-8")
            human_claim = integration_evidence_errors(repo, HUMAN_FEATURE, INTEGRATION_ITEM_A,
                                                      candidate=candidate, expected=expected)
            self.assertNotEqual(human_claim, [])
            self.assertTrue(any("synthetic" in error for error in human_claim), human_claim)
            # A candidate that does not match the observed one is rejected.
            forged = json.loads(observation.read_text(encoding="utf-8"))
            forged["kind"] = OBSERVATION_KIND
            forged["synthetic"] = True
            forged["observer_kind"] = OBSERVATION_KIND
            forged["candidate"] = "0" * 40
            observation.write_text(json.dumps(forged, indent=2, sort_keys=True) + "\n",
                                   encoding="utf-8")
            wrong_candidate = integration_evidence_errors(repo, HUMAN_FEATURE, INTEGRATION_ITEM_A,
                                                         candidate=candidate, expected=expected)
            self.assertNotEqual(wrong_candidate, [])
            self.assertTrue(any("not the observed candidate" in error
                                for error in wrong_candidate), wrong_candidate)

    def test_shared_candidate_records_a_while_b_keeps_its_own_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            # A has no human obligation, so its own checks can satisfy it.
            prepare_human(repo, with_cli=True, second_feature=True, human_required=False)
            self.assertNotIn("person", (repo / ".sdlc-v1/context/product.md").read_text())
            self.assertNotIn("person", (repo / ".sdlc-v1/context/engineering.md").read_text())
            human_complete_task(repo)
            human_complete_task(repo, HUMAN_OTHER_FEATURE, HUMAN_OTHER_TASK)
            candidate = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            # A's integration item is produced by a real run on the shared candidate.
            run = run_integration_check(repo, INTEGRATION_ITEM_A, candidate)
            self.assertEqual(run["exit"], 0)
            test_support.git(repo, "add", "integration")
            test_support.git(repo, "commit", "-m", "record integration evidence")
            candidate = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            manifest = json.loads((repo / INTEGRATION_MANIFEST).read_text(encoding="utf-8"))
            # A has every required integration item; B is still missing its own.
            self.assertEqual(manifest["required"][HUMAN_FEATURE], [INTEGRATION_ITEM_A])
            self.assertTrue((repo / "integration" / f"{INTEGRATION_ITEM_A}.json").exists())
            self.assertEqual(manifest["required"][HUMAN_OTHER_FEATURE], [INTEGRATION_ITEM_B])
            self.assertFalse((repo / "integration" / f"{INTEGRATION_ITEM_B}.json").exists())
            # The shared observation binds A's result to the real run.
            conditions = {
                HUMAN_FEATURE: {
                    "required": [INTEGRATION_ITEM_A],
                    "results": {
                        INTEGRATION_ITEM_A: {
                            "result": "pass",
                            "evidence": "the recorded business check exited 0 on the shared candidate",
                            "source": run["path"],
                        },
                    },
                },
                HUMAN_OTHER_FEATURE: {"required": [INTEGRATION_ITEM_B], "results": {}},
            }
            observation = repo / INTEGRATION_OBSERVATION
            observation.parent.mkdir(parents=True, exist_ok=True)
            observation.write_text(integration_observation(candidate, conditions=conditions),
                                   encoding="utf-8")
            test_support.git(repo, "add", INTEGRATION_OBSERVATION)
            test_support.git(repo, "commit", "-m", "record shared observation")
            candidate = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            expected = {"command": run["command"], "exit": run["exit"], "stdout": run["stdout"]}
            self.assertEqual(
                integration_evidence_errors(repo, HUMAN_FEATURE, INTEGRATION_ITEM_A,
                                            candidate=candidate, expected=expected),
                [],
            )
            # A can be recorded on the shared candidate.
            human_pass_and_review(repo)
            # B keeps its own pending result: A's evidence does not cover B.
            other = human_feature_state(repo, HUMAN_OTHER_FEATURE)
            self.assertEqual(human_state(repo)["validation"]["result"], "pass")
            self.assertEqual(other["validation"]["result"], "pending")
            self.assertEqual(other["review"]["decision"], "pending")
            self.assertEqual(other["release"]["status"], "pending")
            self.assertEqual(other["status"], "in_progress")
            self.assertEqual(other["tasks"][HUMAN_OTHER_TASK]["status"], "done")
            # The two features are bound to their own contexts.
            a_snapshot = human_feature_state(repo, HUMAN_FEATURE)["acceptance"]["validation"]
            self.assertIn(".sdlc-v1/context/engineering.md", a_snapshot["documents"])
            self.assertNotIn(".sdlc-v1/context/engineering-other.md", a_snapshot["documents"])

    def test_shared_observation_rejects_failed_check_labelled_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo, with_cli=True, second_feature=True, human_required=False)
            human_complete_task(repo)
            human_complete_task(repo, HUMAN_OTHER_FEATURE, HUMAN_OTHER_TASK)
            (repo / "cli.py").write_text("print(999)\n", encoding="utf-8")
            test_support.git(repo, "add", "cli.py")
            test_support.git(repo, "commit", "-m", "record broken business candidate")
            checked = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            run = run_integration_check(repo, INTEGRATION_ITEM_A, checked)
            self.assertNotEqual(run["exit"], 0)
            test_support.git(repo, "add", "integration")
            test_support.git(repo, "commit", "-m", "record actual failing check")
            candidate = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            observation = repo / INTEGRATION_OBSERVATION
            observation.parent.mkdir(parents=True, exist_ok=True)
            conditions = {HUMAN_FEATURE: {"required": [INTEGRATION_ITEM_A], "results": {
                INTEGRATION_ITEM_A: {"result": "pass", "evidence": "failed check",
                                     "source": run["path"]},
            }}}
            observation.write_text(integration_observation(candidate, conditions=conditions),
                                   encoding="utf-8")
            expected = {key: run[key] for key in ("command", "exit", "stdout")}
            self.assertNotEqual(integration_evidence_errors(
                repo, HUMAN_FEATURE, INTEGRATION_ITEM_A, candidate=candidate, expected=expected), [])
            self.assertEqual(human_state(repo)["validation"]["result"], "pending")
            self.assertEqual(human_feature_state(repo, HUMAN_OTHER_FEATURE)["validation"]["result"], "pending")

    def test_shared_observation_rejects_a_later_business_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo, with_cli=True, second_feature=True, human_required=False)
            human_complete_task(repo)
            checked = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            run = run_integration_check(repo, INTEGRATION_ITEM_A, checked)
            self.assertEqual(run["exit"], 0)
            test_support.git(repo, "add", "integration")
            test_support.git(repo, "commit", "-m", "record integration evidence")
            observed = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            conditions = {HUMAN_FEATURE: {
                "required": [INTEGRATION_ITEM_A],
                "results": {INTEGRATION_ITEM_A: {
                    "result": "pass", "evidence": "business check", "source": run["path"],
                }},
            }}
            observation = repo / INTEGRATION_OBSERVATION
            observation.parent.mkdir(parents=True, exist_ok=True)
            observation.write_text(integration_observation(observed, conditions=conditions),
                                   encoding="utf-8")
            test_support.git(repo, "add", INTEGRATION_OBSERVATION)
            test_support.git(repo, "commit", "-m", "record shared observation")
            before_change = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            expected = {key: run[key] for key in ("command", "exit", "stdout")}
            self.assertEqual(integration_evidence_errors(
                repo, HUMAN_FEATURE, INTEGRATION_ITEM_A,
                candidate=before_change, expected=expected,
            ), [])
            # The evidence's commit is still an ancestor, but its business code
            # no longer matches the candidate being accepted.
            (repo / "cli.py").write_text("print(999)\n", encoding="utf-8")
            test_support.git(repo, "add", "cli.py")
            test_support.git(repo, "commit", "-m", "change business behavior")
            changed = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            self.assertTrue(is_ancestor(repo, checked, changed))
            self.assertNotEqual(integration_evidence_errors(
                repo, HUMAN_FEATURE, INTEGRATION_ITEM_A,
                candidate=changed, expected=expected,
            ), [])
            self.assertEqual(human_state(repo)["validation"]["result"], "pending")

    def test_a_shared_checkout_blocks_the_other_feature_formal_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo, second_feature=True)
            human_complete_task(repo)
            branch = human_state(repo)["branch"]
            # The other feature leaves an uncommitted business difference.
            (repo / "cli.py").write_text(SOLUTION, encoding="utf-8")
            state_path = repo / ".sdlc-v1/state.json"
            before = state_path.read_bytes()
            result = human_cli(repo, "record-validation", "--feature-id", HUMAN_FEATURE,
                               "--result", "pass")
            self.assertEqual(result.returncode, 2)
            self.assertIn("validation-and-release-require-clean-worktree", result.stderr)
            self.assertEqual(state_path.read_bytes(), before)
            # Both registrations keep their branch and their own records.
            state = lifecycle.load(repo)
            self.assertEqual(state["features"][HUMAN_FEATURE]["branch"], branch)
            self.assertEqual(state["features"][HUMAN_OTHER_FEATURE]["branch"], branch)
            self.assertEqual(state["features"][HUMAN_FEATURE]["validation"]["result"], "pending")
            self.assertEqual(state["features"][HUMAN_OTHER_FEATURE]["validation"]["result"], "pending")

    def test_a_new_business_commit_blocks_review_and_release_of_the_other_feature(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo, with_cli=True, second_feature=True)
            human_complete_task(repo)
            validated_commit = human_pass_and_review(repo)
            # The other feature commits a business change afterwards.
            (repo / "cli.py").write_text(SOLUTION + "\n# other business change\n", encoding="utf-8")
            commit(repo, "other business change")
            head = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            difference = subprocess.run(
                ["git", "-C", str(repo), "diff", "--quiet", validated_commit, head,
                 "--", ".", ":(glob,exclude).sdlc-v1/**"],
                capture_output=True,
            )
            self.assertEqual(difference.returncode, 1)
            review = human_cli(repo, "record-review", "--feature-id", HUMAN_FEATURE,
                               "--decision", "approved", "--by", "scripted reference")
            self.assertEqual(review.returncode, 2)
            self.assertIn("review-commit-does-not-match-validation", review.stderr)
            release = human_cli(repo, "record-release", "--feature-id", HUMAN_FEATURE,
                                "--commit", validated_commit)
            self.assertEqual(release.returncode, 2)
            self.assertIn("release-commit-does-not-match-validation", release.stderr)
            # The original records are unchanged.
            feature = human_state(repo)
            self.assertEqual(feature["review"]["decision"], "approved")
            self.assertEqual(feature["release"]["status"], "pending")
            self.assertEqual(feature["validation"]["commit"], validated_commit)

    # ------------------------------------------------------------------
    # 5. Release registration and delivery evidence
    # ------------------------------------------------------------------

    def test_release_registers_the_delivered_commit_from_the_unpacked_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            evidence_path = root / "release-evidence.json"
            prepare_human(repo, with_cli=True, release_evidence_ref=str(evidence_path))
            human_complete_task(repo)
            checks = subprocess.run([sys.executable, "-B", "-m", "unittest", "-q", "test_cli"],
                                    cwd=repo, capture_output=True, text=True)
            self.assertEqual(checks.returncode, 0, checks.stderr)
            delivered = human_pass_and_review(repo)
            engineering_path = repo / ".sdlc-v1/context/engineering.md"
            bound_body = engineering_path.read_bytes()
            # The review record is committed separately, so HEAD B already
            # differs from the validated implementation A by state only.
            head = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            self.assertNotEqual(delivered, head)
            # The delivered revision really runs outside the repository.
            unpacked, actual_source = unpack_archive(repo, delivered, root / "unpacked")
            # Read the source identity from the very bytes that were unpacked.
            self.assertEqual(actual_source, delivered)
            result = subprocess.run(
                [sys.executable, "-B", "cli.py", "3"], cwd=unpacked,
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "6")
            self.assertEqual((unpacked / "cli.py").read_bytes(),
                             tracked_bytes(repo, delivered, "cli.py"))
            evidence_path.write_text(json.dumps({"source_commit": actual_source,
                                                 "command": "python3 -B cli.py 3",
                                                 "exit": result.returncode,
                                                 "stdout": result.stdout.strip()}),
                                     encoding="utf-8")
            self.assertEqual(engineering_path.read_bytes(), bound_body)
            for point in ("validation", "review"):
                self.assertEqual(human_verify(repo, "--feature-id", HUMAN_FEATURE,
                                              "--point", point)["result"], "match")
            difference = subprocess.run(
                ["git", "-C", str(repo), "diff", "--quiet", delivered, head,
                 "--", ".", ":(glob,exclude).sdlc-v1/**"],
                capture_output=True,
            )
            self.assertEqual(difference.returncode, 0)
            result = human_cli(repo, "record-release", "--feature-id", HUMAN_FEATURE,
                               "--commit", delivered)
            self.assertEqual(result.returncode, 0)
            feature = human_state(repo)
            self.assertEqual(feature["release"]["status"], "released")
            self.assertEqual(feature["release"]["commit"], delivered)
            self.assertEqual(feature["validation"]["commit"], delivered)
            self.assertEqual(json.loads(evidence_path.read_text(encoding="utf-8"))["source_commit"], delivered)
            self.assertEqual(engineering_path.read_bytes(), bound_body)

    def test_archive_source_identity_distinguishes_two_commits_with_equal_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            prepare_human(repo, with_cli=True)
            human_complete_task(repo)
            revision_a = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            # A later commit changes only the bound context, so the business
            # file is byte-identical in both revisions.
            engineering_path = repo / ".sdlc-v1/context/engineering.md"
            with engineering_path.open("a", encoding="utf-8") as stream:
                stream.write("\nHandoff evidence.\n")
            revision_b = commit(repo, "context-only handoff")
            self.assertNotEqual(revision_a, revision_b)
            self.assertEqual(tracked_bytes(repo, revision_a, "cli.py"),
                             tracked_bytes(repo, revision_b, "cli.py"))
            # The archive of each revision states its own source, so unpacking
            # the wrong one is detectable even though the files are identical.
            _, source_a = unpack_archive(repo, revision_a, root / "unpacked-a")
            unpacked_b, source_b = unpack_archive(repo, revision_b, root / "unpacked-b")
            self.assertEqual(source_a, revision_a)
            self.assertEqual(source_b, revision_b)
            with self.assertRaises(AssertionError):
                self.assertEqual(source_b, revision_a)
            # The unpacked business file is identical in both cases, so only the
            # archive identity distinguishes them.
            self.assertEqual((unpacked_b / "cli.py").read_bytes(),
                             tracked_bytes(repo, revision_a, "cli.py"))
            result = subprocess.run(
                [sys.executable, "-B", "cli.py", "3"], cwd=unpacked_b,
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "6")

    def test_rebinding_validation_to_another_commit_rejects_the_delivered_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo, with_cli=True)
            human_complete_task(repo)
            delivered = human_pass_and_review(repo)
            # Append bound evidence and re-record validation at the new commit.
            engineering_path = repo / ".sdlc-v1/context/engineering.md"
            with engineering_path.open("a", encoding="utf-8") as stream:
                stream.write("\nExtra evidence.\n")
            commit(repo, "extra evidence")
            cli(repo, "record-validation", "--feature-id", HUMAN_FEATURE, "--result", "pass",
                "--test-command", "python3 -m unittest -q test_cli")
            cli(repo, "record-review", "--feature-id", HUMAN_FEATURE, "--decision", "approved",
                "--by", "scripted reference")
            commit(repo, "rebound validation")
            feature = human_state(repo)
            self.assertNotEqual(feature["validation"]["commit"], delivered)
            # Registering the already delivered commit is refused.
            result = human_cli(repo, "record-release", "--feature-id", HUMAN_FEATURE,
                               "--commit", delivered)
            self.assertEqual(result.returncode, 2)
            self.assertIn("release-commit-does-not-match-validation", result.stderr)
            self.assertEqual(human_state(repo)["release"]["status"], "pending")

    def test_untracked_context_is_rejected_before_the_release_registration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            delivered = human_pass_and_review(repo)
            state_path = repo / ".sdlc-v1/state.json"
            before = state_path.read_bytes()
            # Remove one bound context from the index while keeping the file.
            test_support.git(repo, "rm", "--cached", "-q", ".sdlc-v1/context/engineering.md")
            result = human_cli(repo, "record-release", "--feature-id", HUMAN_FEATURE,
                               "--commit", delivered)
            self.assertEqual(result.returncode, 2)
            self.assertIn("context-must-be-git-tracked-before-validation", result.stderr)
            self.assertEqual(state_path.read_bytes(), before)
            self.assertEqual(human_state(repo)["release"]["status"], "pending")

    def test_conflicted_context_index_is_rejected_before_the_release_registration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            delivered = human_pass_and_review(repo)
            state_path = repo / ".sdlc-v1/state.json"
            before = state_path.read_bytes()
            # Stage an unmerged index entry for one bound context.
            blob = subprocess.run(
                ["git", "-C", str(repo), "hash-object", "-w", "--stdin"],
                input="# conflict\n", capture_output=True, text=True, check=True,
            ).stdout.strip()
            for stage in (1, 2, 3):
                subprocess.run(
                    ["git", "-C", str(repo), "update-index", "--index-info"],
                    input=f"100644 {blob} {stage}\t.sdlc-v1/context/engineering.md\n",
                    capture_output=True, text=True, check=True,
                )
            unmerged = test_support.git(repo, "ls-files", "-u", "--",
                                       ".sdlc-v1/context/engineering.md").stdout
            self.assertNotEqual(unmerged.strip(), "")
            result = human_cli(repo, "record-release", "--feature-id", HUMAN_FEATURE,
                               "--commit", delivered)
            self.assertEqual(result.returncode, 2)
            self.assertIn("context-has-unmerged-index-entries", result.stderr)
            self.assertEqual(state_path.read_bytes(), before)
            self.assertEqual(human_state(repo)["release"]["status"], "pending")

    def test_staged_state_blocks_the_release_registration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            # Leave the recorded state uncommitted, then stage it.
            validated_commit = human_pass_and_review(repo, commit_result=False)
            test_support.git(repo, "add", ".sdlc-v1/state.json")
            state_path = repo / ".sdlc-v1/state.json"
            before = state_path.read_bytes()
            # Business paths are clean while the state file is staged.
            self.assertEqual(
                test_support.git(repo, "status", "--porcelain=v1", "--untracked-files=all",
                                 "--", ".", ":(glob,exclude).sdlc-v1/**").stdout,
                "",
            )
            result = human_cli(repo, "record-release", "--feature-id", HUMAN_FEATURE,
                               "--commit", validated_commit)
            self.assertEqual(result.returncode, 2)
            self.assertIn("state-is-staged-commit-or-unstage-before-update", result.stderr)
            self.assertEqual(state_path.read_bytes(), before)
            self.assertEqual(human_state(repo)["release"]["status"], "pending")

    def test_interrupted_deployment_recovery_inputs_are_distinguishable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            prepare_human(repo, with_cli=True)
            human_complete_task(repo)
            delivered = human_pass_and_review(repo)
            operation = {
                "operation": "op-1",
                "original_version": "prev",
                "expected_version": delivered,
            }
            # The operation is persisted before any external action.
            operation_record = root / "operation.json"
            operation_record.write_text(json.dumps(operation, indent=2, sort_keys=True),
                                        encoding="utf-8")
            self.assertTrue(operation_record.exists())
            target = root / "target"
            simulate_deploy(target, operation)
            # The receipt is re-read from the persistent target, not reused from
            # the caller's memory.
            receipt = read_deploy_receipt(target)
            persisted = json.loads(operation_record.read_text(encoding="utf-8"))
            self.assertEqual(receipt["operation"], persisted["operation"])
            self.assertEqual(receipt["version"], persisted["expected_version"])
            # (a) The action took effect but was not registered yet.
            self.assertEqual((target / "version").read_text(encoding="utf-8").strip(), delivered)
            self.assertEqual((target / "applications.log").read_text(encoding="utf-8").count("\n"), 1)
            self.assertEqual(human_state(repo)["release"]["status"], "pending")
            # The outstanding local smoke is actually executed against the
            # archived revision before the registration is made.
            unpacked, actual_source = unpack_archive(repo, delivered, root / "unpacked")
            self.assertEqual(actual_source, persisted["expected_version"])
            smoke = subprocess.run(
                [sys.executable, "-B", "cli.py", "3"], cwd=unpacked,
                capture_output=True, text=True,
            )
            self.assertEqual(smoke.returncode, 0)
            self.assertEqual(smoke.stdout.strip(), "6")
            # The registration uses the version the persisted record allows.
            self.assertEqual(persisted["expected_version"], delivered)
            result = human_cli(repo, "record-release", "--feature-id", HUMAN_FEATURE,
                               "--commit", persisted["expected_version"])
            self.assertEqual(result.returncode, 0)
            # The application is not repeated.
            self.assertEqual((target / "applications.log").read_text(encoding="utf-8").count("\n"), 1)
            self.assertEqual(human_state(repo)["release"]["commit"], delivered)

    def test_unregistered_but_applied_target_does_not_prove_the_registration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            prepare_human(repo, with_cli=True)
            human_complete_task(repo)
            delivered = human_pass_and_review(repo)
            operation = {
                "operation": "op-1",
                "original_version": "prev",
                "expected_version": delivered,
            }
            target = root / "target"
            simulate_deploy(target, operation)
            # The target shows the delivered version, but nothing registered it.
            self.assertEqual((target / "version").read_text(encoding="utf-8").strip(), delivered)
            self.assertEqual(human_state(repo)["release"]["status"], "pending")
            self.assertIsNone(human_state(repo)["release"]["commit"])
            # A version that happens to match is not proof that the registration
            # already happened; the recorded release is still absent.
            self.assertNotEqual(human_state(repo)["release"]["status"], "released")

    def test_repeated_registration_is_refused_and_changes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            prepare_human(repo, with_cli=True)
            human_complete_task(repo)
            delivered = human_pass_and_review(repo)
            # The first registration succeeds.
            result = human_cli(repo, "record-release", "--feature-id", HUMAN_FEATURE,
                               "--commit", delivered)
            self.assertEqual(result.returncode, 0)
            released = human_state(repo)["release"]
            state_path = repo / ".sdlc-v1/state.json"
            before = state_path.read_bytes()
            # A repeated registration is refused and changes nothing. This is a
            # CLI counterexample, not a recovery step.
            repeat = human_cli(repo, "record-release", "--feature-id", HUMAN_FEATURE,
                               "--commit", delivered)
            self.assertEqual(repeat.returncode, 2)
            self.assertIn("feature-not-ready-for-release", repeat.stderr)
            self.assertEqual(state_path.read_bytes(), before)
            self.assertEqual(human_state(repo)["release"], released)

    def test_multi_stage_release_resumes_each_environment_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            prepare_human(repo, with_cli=True)
            human_complete_task(repo)
            delivered = human_pass_and_review(repo)
            # This disposable fixture has an independent, synthetic authorization
            # for each stage and the same delivered version.
            authorization_path = root / "stage-authorization.json"
            authorization_path.write_text(json.dumps({
                "synthetic": True, "version": delivered,
                "operations": {name: f"op-{name}" for name in ("staging", "canary", "full")},
            }), encoding="utf-8")
            targets = {}
            for environment in ("staging", "canary", "full"):
                targets[environment] = root / "targets" / environment
            staging_operation = {
                "operation": "op-staging",
                "environment": "staging",
                "original_version": "prev",
                "expected_version": delivered,
            }
            stage_operation_record(root, "staging", staging_operation)
            self.assertEqual(stage_preconditions_errors(root, "staging", delivered), [])
            # Staging is applied, then the run is interrupted.
            simulate_deploy(targets["staging"], staging_operation)
            self.assertEqual(deploy_applications(targets["staging"]), 1)
            # The recovery re-reads the operation record and the receipt from disk.
            persisted = read_operation_record(root, "staging")
            receipt = read_deploy_receipt(targets["staging"])
            self.assertEqual(persisted["operation"], staging_operation["operation"])
            self.assertEqual(receipt["operation"], persisted["operation"])
            self.assertEqual(receipt["version"], persisted["expected_version"])
            self.assertEqual(
                (targets["staging"] / "version").read_text(encoding="utf-8").strip(), delivered,
            )
            # The interrupted staging application is not repeated.
            self.assertEqual(deploy_applications(targets["staging"]), 1)
            # The outstanding local smoke really runs against the fixed revision.
            staging_evidence = root / "evidence" / "staging-smoke.json"
            archive_smoke(repo, delivered, root / "unpacked-staging", staging_evidence)
            smoke = read_smoke_evidence(staging_evidence)
            self.assertEqual(smoke["source_commit"], delivered)
            self.assertEqual(smoke["exit"], 0)
            self.assertEqual(smoke["stdout"], "6")
            # The persisted record is confirmed by running the command again.
            self.assertEqual(verify_smoke_evidence(staging_evidence), [])
            # The stage evidence is complete, so the later stages may follow.
            self.assertEqual(read_deploy_receipt(targets["staging"])["version"], delivered)
            for environment in ("canary", "full"):
                operation = {
                    "operation": f"op-{environment}",
                    "environment": environment,
                    "original_version": "prev",
                    "expected_version": delivered,
                }
                stage_operation_record(root, environment, operation)
                # Each stage pre-checks its own persisted record first.
                persisted = read_operation_record(root, environment)
                self.assertEqual(persisted["operation"], operation["operation"])
                self.assertEqual(persisted["expected_version"], delivered)
                if environment == "canary":
                    # Missing authorization must stop before the first application.
                    authorized = authorization_path.read_text(encoding="utf-8")
                    denied = json.loads(authorized)
                    del denied["operations"]["canary"]
                    authorization_path.write_text(json.dumps(denied), encoding="utf-8")
                    self.assertNotEqual(stage_preconditions_errors(root, environment, delivered), [])
                    self.assertEqual(deploy_applications(targets[environment]), 0)
                    authorization_path.write_text(authorized, encoding="utf-8")
                else:
                    # Full deployment requires a canary observation, not only smoke.
                    self.assertNotEqual(stage_preconditions_errors(root, environment, delivered), [])
                    self.assertEqual(deploy_applications(targets[environment]), 0)
                    observation_path = root / "evidence" / "canary-observation.json"
                    observation = {
                        "synthetic": True, "operation": "op-canary",
                        "version": delivered, "failures": 1,
                    }
                    observation_path.write_text(json.dumps(observation), encoding="utf-8")
                    self.assertNotEqual(stage_preconditions_errors(root, environment, delivered), [])
                    self.assertEqual(deploy_applications(targets[environment]), 0)
                    observation["failures"] = 0
                    observation_path.write_text(json.dumps(observation), encoding="utf-8")
                self.assertEqual(stage_preconditions_errors(root, environment, delivered), [])
                simulate_deploy(targets[environment], operation)
                # The receipt is read back from disk, not from memory.
                stage_receipt = read_deploy_receipt(targets[environment])
                self.assertEqual(stage_receipt["operation"], persisted["operation"])
                self.assertEqual(stage_receipt["version"], persisted["expected_version"])
                # Each stage runs its own real local smoke.
                stage_evidence = root / "evidence" / f"{environment}-smoke.json"
                archive_smoke(repo, delivered, root / f"unpacked-{environment}", stage_evidence)
                stage_smoke = read_smoke_evidence(stage_evidence)
                self.assertEqual(stage_smoke["source_commit"], delivered)
                self.assertEqual(stage_smoke["exit"], 0)
                self.assertEqual(stage_smoke["stdout"], "6")
                # The persisted record is confirmed by running the command again.
                self.assertEqual(verify_smoke_evidence(stage_evidence), [])
                # Each stage applied exactly once.
                self.assertEqual(deploy_applications(targets[environment]), 1)
            # The registration happens once, after every stage is complete.
            result = human_cli(repo, "record-release", "--feature-id", HUMAN_FEATURE,
                               "--commit", delivered)
            self.assertEqual(result.returncode, 0)
            feature = human_state(repo)
            self.assertEqual(feature["release"]["status"], "released")
            self.assertEqual(feature["release"]["commit"], delivered)
            self.assertEqual(feature["validation"]["commit"], delivered)
            # No stage was applied twice during the whole run.
            for environment in ("staging", "canary", "full"):
                self.assertEqual(deploy_applications(targets[environment]), 1)

    def test_lost_registration_receipt_resumes_without_new_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            prepare_human(repo, with_cli=True)
            human_complete_task(repo)
            delivered = human_pass_and_review(repo)
            review_ref = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            operation = {
                "operation": "op-staging",
                "environment": "staging",
                "original_version": "prev",
                "expected_version": delivered,
            }
            operation_path = stage_operation_record(root, "staging", operation)
            checkpoint = write_human_checkpoint(
                repo, HUMAN_FEATURE, location="selected Feature and workspace",
                point="validation", approved=approved_mapping(repo, HUMAN_FEATURE, "validation"),
                tested_commit=delivered, review="approved by scripted reference",
                pending="registration receipt for op-staging has not been reconciled",
                next_step="compare the original operation, target and receipt",
                references=[f"原 state：{review_ref}:.sdlc-v1/state.json", f"operation：{operation_path}"],
            )
            checkpoint_before = checkpoint.read_bytes()
            target = root / "targets" / "staging"
            simulate_deploy(target, operation)
            # The smoke really ran before the registration.
            evidence_path = root / "evidence" / "staging-smoke.json"
            archive_smoke(repo, delivered, root / "unpacked", evidence_path)
            smoke = read_smoke_evidence(evidence_path)
            self.assertEqual(smoke["exit"], 0)
            self.assertEqual(smoke["stdout"], "6")
            self.assertEqual(verify_smoke_evidence(evidence_path), [])
            # The registration succeeds and its caller's return value is lost.
            result = human_cli(repo, "record-release", "--feature-id", HUMAN_FEATURE,
                               "--commit", delivered)
            self.assertEqual(result.returncode, 0)
            del result
            applications_before = deploy_applications(target)
            state_before = (repo / ".sdlc-v1/state.json").read_bytes()
            # The recovery reads only the state, the next stage and the original
            # operation record. It performs no deployment and no registration.
            persisted = read_operation_record(root, "staging")
            self.assertEqual(persisted["operation"], operation["operation"])
            self.assertEqual(persisted["expected_version"], delivered)
            feature = human_state(repo)
            self.assertEqual(feature["release"]["status"], "released")
            self.assertEqual(feature["release"]["commit"], delivered)
            self.assertEqual(feature["status"], "released")
            self.assertEqual(lifecycle.next_action(repo)["stage"], "done")
            # A completed state is not enough to discard the unresolved
            # operation's checkpoint. Its original reference remains readable.
            self.assertEqual(checkpoint.read_bytes(), checkpoint_before)
            self.assertIn(str(operation_path), checkpoint.read_text(encoding="utf-8"))
            self.assertEqual(read_deploy_receipt(target)["operation"], persisted["operation"])
            self.assertEqual(read_deploy_receipt(target)["version"], persisted["expected_version"])
            # The recovery added no deployment call and no registration call.
            self.assertEqual(deploy_applications(target), applications_before)
            self.assertEqual((repo / ".sdlc-v1/state.json").read_bytes(), state_before)

    def test_mismatched_operation_evidence_is_not_treated_as_the_same_action(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            prepare_human(repo, with_cli=True)
            human_complete_task(repo)
            delivered = human_pass_and_review(repo)
            operation = {
                "operation": "op-1",
                "original_version": "prev",
                "expected_version": delivered,
            }
            target = root / "target"
            simulate_deploy(target, operation)
            # A later action wrote a different receipt for the same target version.
            other = dict(operation, operation="op-2")
            simulate_deploy(target, other)
            receipt = json.loads((target / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["operation"], "op-2")
            self.assertEqual((target / "version").read_text(encoding="utf-8").strip(), delivered)
            # The version matches, but the operation identity does not, so the
            # receipt cannot be used as evidence for this operation.
            self.assertNotEqual(receipt["operation"], operation["operation"])
            self.assertEqual((target / "applications.log").read_text(encoding="utf-8").count("\n"), 2)
            # The matching version alone registered nothing.
            self.assertEqual(human_state(repo)["release"]["status"], "pending")
            self.assertIsNone(human_state(repo)["release"]["commit"])

    # ------------------------------------------------------------------
    # 6. Branch migration and refresh identity
    # ------------------------------------------------------------------

    def test_migrated_branch_requires_the_new_registered_identity_to_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            human_pass_and_review(repo)
            branch = human_state(repo)["branch"]
            test_support.git(repo, "checkout", "-b", "feature/fix")
            head = test_support.git(repo, "rev-parse", "HEAD").stdout.strip()
            migration = human_cli(
                repo, "migrate-feature-branch", "--feature-id", HUMAN_FEATURE,
                "--expected-branch", branch, "--branch", "feature/fix",
                "--expected-head", head, "--reason", "moved to the fix branch",
            )
            self.assertEqual(migration.returncode, 0)
            self.assertEqual(human_state(repo)["branch"], "feature/fix")
            # Append evidence before the refresh so the plan point must move.
            engineering = repo / ".sdlc-v1/context/engineering.md"
            with engineering.open("a", encoding="utf-8") as stream:
                stream.write(HUMAN_EVIDENCE_APPEND)
            commit(repo, "append evidence after migration")
            before = copy.deepcopy(human_state(repo))
            state_path = repo / ".sdlc-v1/state.json"
            state_before = state_path.read_bytes()
            # The historical branch no longer refreshes the plan point.
            stale = human_cli(
                repo, "start-feature", "--requirement-id", REQ, "--feature-id", HUMAN_FEATURE,
                "--branch", branch,
                "--engineering-context-ref", ".sdlc-v1/context/engineering.md",
                "--refresh-acceptance",
            )
            self.assertEqual(stale.returncode, 2)
            self.assertIn("feature-identity-mismatch", stale.stderr)
            # The rejected call leaves the state unchanged.
            self.assertEqual(state_path.read_bytes(), state_before)
            self.assertEqual(human_state(repo), before)
            # The current registered identity does.
            current = human_cli(
                repo, "start-feature", "--requirement-id", REQ, "--feature-id", HUMAN_FEATURE,
                "--branch", "feature/fix",
                "--engineering-context-ref", ".sdlc-v1/context/engineering.md",
                "--refresh-acceptance",
            )
            self.assertEqual(current.returncode, 0)
            after = human_state(repo)
            # Only the plan snapshot and its related time change.
            self.assertNotEqual(after["acceptance"]["plan"], before["acceptance"]["plan"])
            self.assertEqual(after["acceptance"]["validation"], before["acceptance"]["validation"])
            self.assertEqual(after["acceptance"]["review"], before["acceptance"]["review"])
            self.assertEqual(after["validation"], before["validation"])
            self.assertEqual(after["review"], before["review"])
            self.assertEqual(after["release"], before["release"])
            self.assertEqual(after["tasks"], before["tasks"])
            self.assertEqual(after["status"], before["status"])
            self.assertEqual(after["branch"], "feature/fix")

    # ------------------------------------------------------------------
    # 7. Acceptance point selectors
    # ------------------------------------------------------------------

    def test_spec_point_uses_the_requirement_selector_before_registration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            test_support.initialize_git_repo(repo, readme="# Integer doubling CLI\n")
            lifecycle.initialize(repo)
            product = context(repo, "product", HUMAN_PRODUCT)
            lifecycle.capture_requirement(
                repo=repo, requirement_id=REQ, title="Double integers", product_context_ref=product,
            )
            lifecycle.mark_requirement_ready(repo=repo, requirement_id=REQ)
            commit(repo, "ready requirement")
            # An unregistered Feature cannot be selected at all.
            unregistered = human_cli(repo, "verify-acceptance", "--feature-id", HUMAN_FEATURE,
                                     "--point", "spec_ready")
            self.assertEqual(unregistered.returncode, 2)
            self.assertIn("feature-not-found", unregistered.stderr)
            # The Requirement selector reaches the spec_ready point.
            spec = human_cli(repo, "verify-acceptance", "--requirement-id", REQ,
                             "--point", "spec_ready")
            self.assertEqual(spec.returncode, 0)
            self.assertEqual(json.loads(spec.stdout)["result"], "match")
            # The Requirement selector does not accept other points.
            other = human_cli(repo, "verify-acceptance", "--requirement-id", REQ, "--point", "plan")
            self.assertEqual(other.returncode, 2)
            self.assertIn("invalid-acceptance-point", other.stderr)
            # The query writes nothing.
            state_path = repo / ".sdlc-v1/state.json"
            before = state_path.read_bytes()
            human_cli(repo, "verify-acceptance", "--requirement-id", REQ, "--point", "spec_ready")
            self.assertEqual(state_path.read_bytes(), before)

    def test_registered_feature_and_requirement_selectors_agree_on_spec_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            requirement = human_cli(repo, "verify-acceptance", "--requirement-id", REQ,
                                    "--point", "spec_ready")
            feature = human_cli(repo, "verify-acceptance", "--feature-id", HUMAN_FEATURE,
                                "--point", "spec_ready")
            self.assertEqual(requirement.returncode, 0)
            self.assertEqual(feature.returncode, 0)
            requirement_payload = json.loads(requirement.stdout)
            feature_payload = json.loads(feature.stdout)
            self.assertEqual(requirement_payload["target_type"], "requirement")
            self.assertEqual(feature_payload["target_type"], "feature")
            requirement_files = requirement_payload["points"][0]["files"]
            feature_files = feature_payload["points"][0]["files"]
            self.assertEqual(requirement_files[0]["path"], feature_files[0]["path"])
            self.assertEqual(requirement_files[0]["current_digest"], feature_files[0]["current_digest"])
            # Neither query writes state or context.
            state_path = repo / ".sdlc-v1/state.json"
            before = state_path.read_bytes()
            product_before = (repo / ".sdlc-v1/context/product.md").read_bytes()
            human_cli(repo, "verify-acceptance", "--feature-id", HUMAN_FEATURE, "--point", "spec_ready")
            self.assertEqual(state_path.read_bytes(), before)
            self.assertEqual((repo / ".sdlc-v1/context/product.md").read_bytes(), product_before)

    def test_evidence_append_alone_leaves_the_approved_digest_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            prepare_human(repo)
            human_complete_task(repo)
            before = human_verify(repo, "--feature-id", HUMAN_FEATURE, "--point", "plan")
            engineering_path = repo / ".sdlc-v1/context/engineering.md"
            with engineering_path.open("a", encoding="utf-8") as stream:
                stream.write(HUMAN_EVIDENCE_APPEND)
            after = human_verify(repo, "--feature-id", HUMAN_FEATURE, "--point", "plan")
            self.assertEqual(after["result"], "stale")
            # The product condition is untouched by a pure evidence append.
            before_product = next(
                item["current_digest"] for item in before["points"][0]["files"]
                if item["path"].endswith("product.md")
            )
            after_product = next(
                item["current_digest"] for item in after["points"][0]["files"]
                if item["path"].endswith("product.md")
            )
            self.assertEqual(before_product, after_product)



if __name__ == "__main__":
    unittest.main()
