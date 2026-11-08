#!/usr/bin/env python3
"""Reusable local fixtures and deterministic oracles, not independent Agent runs."""
from __future__ import annotations

import copy
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


def cli(repo: Path, *args: str) -> None:
    subprocess.run(
        [sys.executable, str(HERE / "lifecycle_state.py"), "--repo", str(repo), *args],
        check=True, capture_output=True, text=True,
    )


def commit(repo: Path, message: str) -> None:
    test_support.git(repo, "add", ".")
    test_support.git(repo, "commit", "-m", message)


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
        coverage_note = "\nCoverage tool unavailable in this fixture; default correctness coverage is NOT_RUN.\n"
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
        (repo / "cli.py").write_text(SOLUTION, encoding="utf-8")
        result, command = run_check(repo, [sys.executable, "-m", "unittest", "-q", "test_cli"])
        assert result.returncode == 0
        cli(repo, "set-task-status", "--feature-id", FEATURE, "--task-id", "TASK-one", "--status", "in_progress")
        cli(repo, "set-task-status", "--feature-id", FEATURE, "--task-id", "TASK-one", "--status", "done")
        commit(repo, "implement CLI")
        with (repo / ".sdlc-v1/context/engineering.md").open("a", encoding="utf-8") as stream:
            stream.write(
                "Scripted reference transitions only; independent validation and review "
                "and default correctness coverage are NOT_RUN.\n"
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


if __name__ == "__main__":
    unittest.main()
