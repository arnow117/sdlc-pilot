#!/usr/bin/env python3
"""Unit tests for the CC Switch Claude runner without a provider call."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import claude_skill_runner  # noqa: E402


class ClaudeSkillRunnerTest(unittest.TestCase):
    def test_provider_environment_is_scoped_to_one_claude_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "cc-switch.db"
            connection = sqlite3.connect(database)
            connection.execute("CREATE TABLE providers (name TEXT, app_type TEXT, settings_config TEXT)")
            connection.execute(
                "INSERT INTO providers VALUES (?, ?, ?)",
                ("GLM", "claude", json.dumps({"env": {
                    "ANTHROPIC_AUTH_TOKEN": "test-token", "ANTHROPIC_BASE_URL": "https://example.invalid",
                    "OTHER_SECRET": "must-not-be-forwarded",
                }})),
            )
            connection.commit()
            connection.close()
            environment = claude_skill_runner._provider_environment(database, "GLM")
            self.assertEqual(set(environment), {"ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"})
            with self.assertRaisesRegex(claude_skill_runner.ClaudeSkillRunnerError, "unknown-or-incompatible"):
                claude_skill_runner._provider_environment(database, "missing")

    def test_command_and_structured_output_are_read_only_and_normalized(self) -> None:
        command = claude_skill_runner._build_command(model="sonnet", max_budget_usd=0.5, prompt="test")
        self.assertIn("Read,Glob,Grep", command)
        self.assertEqual(command[command.index("--disallowed-tools") + 1], "Read,Glob,Grep")
        self.assertNotIn("Bash", command)
        self.assertNotIn("--json-schema", command)
        self.assertNotIn("--plugin-dir", command)
        self.assertIn("--safe-mode", command)
        self.assertEqual(command[command.index("--effort") + 1], "low")
        self.assertEqual(command[command.index("--max-turns") + 1], "2")
        result = claude_skill_runner._structured_output({"structured_output": {
            "case_id": "small-feature", "route": ["sdlc-product-design"], "modules": ["mod.product.core"],
            "roles": ["role.product-owner"], "obligations": ["obl.product.discover.problem-frame"],
            "artifacts": ["ProductContract"], "actions": [],
            "transition": {"decision": "route", "route": ["sdlc-product-design"]},
        }})
        self.assertEqual(result["case_id"], "small-feature")
        invalid = claude_skill_runner._invalid_live_output({"case": {"case_id": "small-feature"}})
        self.assertEqual(invalid["case_id"], "small-feature")
        self.assertEqual(invalid["route"], [])
        self.assertEqual(invalid["transition"], {"decision": "reject", "route": []})
        with self.assertRaisesRegex(claude_skill_runner.ClaudeSkillRunnerError, "missing-case-id"):
            claude_skill_runner._invalid_live_output({"case": {}})

    def test_context_pack_reads_only_selected_checkout_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            source = checkout / "skills" / "sdlc-product-design"
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text("# product source\n", encoding="utf-8")
            request = {"invocation": {"steps": [{"skill": "sdlc-product-design"}]}}
            pack = claude_skill_runner._context_pack(checkout, request)
            self.assertEqual(pack, "### skills/sdlc-product-design/SKILL.md\n\n# product source")
            (source / "SKILL.md").write_text("x" * (claude_skill_runner.MAX_SKILL_SOURCE_CHARS + 1), encoding="utf-8")
            self.assertIn("Source excerpt truncated locally", claude_skill_runner._context_pack(checkout, request))
            with self.assertRaisesRegex(claude_skill_runner.ClaudeSkillRunnerError, "invalid-invocation-skill"):
                claude_skill_runner._context_pack(checkout, {"invocation": {"steps": [{"skill": "../escape"}]}})

    def test_context_pack_includes_only_the_selected_policy_surface(self) -> None:
        request = {"invocation": {"steps": [
            {"skill": "sdlc-product-design", "phase": "behavior-design", "operation": "behavior-design"},
            {"skill": "sdlc-software-delivery", "phase": "engineering-spec", "operation": "engineering-spec"},
        ]}}
        pack = claude_skill_runner._context_pack(ROOT, request)
        self.assertIn("SDLC evaluation policy surface", pack)
        self.assertIn('"route_format":"<skill>:<phase>"', pack)
        self.assertIn('"id":"phase.product.behavior-design"', pack)
        self.assertIn('"id":"phase.delivery.engineering-spec"', pack)
        self.assertIn('"id":"mod.product.behavior-bdd"', pack)
        self.assertIn('"id":"mod.delivery.engineering-spec"', pack)
        self.assertLessEqual(len(pack.encode("utf-8")), claude_skill_runner.MAX_CONTEXT_PACK_BYTES)

    def test_prompt_requires_the_exact_result_object_shape(self) -> None:
        prompt = claude_skill_runner._prompt(
            {"invocation": {"case_id": "case", "steps": [{"skill": "sdlc"}]}}, "# context",
        )
        self.assertIn("exactly these top-level keys", prompt)
        self.assertIn("Do not add reasoning", prompt)
        self.assertIn("actions must be an empty array", prompt)
        self.assertIn("arrays of strings", prompt)
        self.assertIn("<skill>:<phase>", prompt)
        self.assertIn("Top-level route is always the selected invocation sequence", prompt)
        self.assertIn("transition.decision must be route", prompt)
        self.assertIn("exact kind of every selected phase output_contract", prompt)
        self.assertIn("transitive depends_on closure", prompt)

    def test_claude_timeout_terminates_the_process_group(self) -> None:
        command = [
            sys.executable, "-c",
            "import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); time.sleep(30)",
        ]
        with self.assertRaisesRegex(claude_skill_runner.ClaudeSkillRunnerError, "claude-runner-timeout"):
            claude_skill_runner._run_claude(
                command, cwd=Path.cwd(), environment=os.environ, timeout_seconds=1,
            )

    def test_configured_model_uses_the_provider_mapping(self) -> None:
        self.assertEqual(
            claude_skill_runner._resolve_model({"ANTHROPIC_MODEL": "glm-5.2"}, "configured"),
            "glm-5.2",
        )
        self.assertEqual(
            claude_skill_runner._resolve_model({"ANTHROPIC_MODEL": "glm-5.2"}, "explicit-model"),
            "explicit-model",
        )
        with self.assertRaisesRegex(claude_skill_runner.ClaudeSkillRunnerError, "missing-model"):
            claude_skill_runner._resolve_model({}, "configured")

    def test_failure_diagnostics_are_classified_without_returning_raw_stderr(self) -> None:
        self.assertEqual(claude_skill_runner._safe_failure_class(b"unknown model 'sonnet'"), "model")
        self.assertEqual(claude_skill_runner._safe_failure_class(b"401 unauthorized token=secret"), "authentication")
        self.assertEqual(claude_skill_runner._safe_failure_class(b"max budget would be exceeded"), "budget")
        self.assertEqual(claude_skill_runner._safe_failure_class(b"prompt too long for context window"), "context-length")
        self.assertEqual(claude_skill_runner._safe_failure_class(b"maximum turn limit reached"), "turn-limit")
        self.assertEqual(claude_skill_runner._safe_failure_class(b"invalid tool use response"), "tool-execution")
        self.assertEqual(claude_skill_runner._safe_failure_class(b"failed to load plugin"), "plugin")
        self.assertEqual(
            claude_skill_runner._safe_failure_class(
                b"", b'{"is_error":true,"subtype":"error_during_execution","errors":["[ede_diagnostic] aborted"]}',
            ),
            "client-execution",
        )
        self.assertEqual(
            claude_skill_runner._safe_failure_class(
                b"", b'{"is_error":true,"errors":["401 unauthorized token=secret"]}',
            ),
            "authentication",
        )
        self.assertEqual(claude_skill_runner._safe_failure_class(b"unrecognized failure"), "claude-cli-stderr")
        self.assertEqual(claude_skill_runner._safe_failure_class(b"", b"not JSON"), "claude-non-json-output")
        self.assertEqual(
            claude_skill_runner._safe_failure_class(b"", b'{"is_error":true,"errors":["unclassified"]}'),
            "claude-error-result",
        )
        self.assertEqual(claude_skill_runner._safe_failure_class(b""), "claude-empty-failure")

    def test_unparseable_provider_success_becomes_a_scoreable_invalid_output(self) -> None:
        request = {
            "source_ref": "a" * 40,
            "planned_runs": 1,
            "case": {"case_id": "small-feature"},
            "invocation": {"steps": [{"skill": "sdlc"}]},
        }
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            with mock.patch.object(claude_skill_runner, "_git", return_value="a" * 40), \
                    mock.patch.object(claude_skill_runner, "_provider_environment", return_value={}), \
                    mock.patch.object(claude_skill_runner, "_resolve_model", return_value="glm-5.2"), \
                    mock.patch.object(claude_skill_runner.tempfile, "mkdtemp", return_value=str(workspace)), \
                    mock.patch.object(claude_skill_runner, "_context_pack", return_value="context"), \
                    mock.patch.object(claude_skill_runner, "_run_claude", return_value=subprocess.CompletedProcess([], 0, b"not-json", b"")), \
                    mock.patch.object(claude_skill_runner, "_claude_version", return_value="fixture"):
                result = claude_skill_runner.run_once(
                    request, repo=ROOT, provider_name="GLM", model="configured", max_budget_usd=0.2,
                    database=workspace / "unused.db", timeout_seconds=1,
                    evaluator_model="unconfigured", evaluator_version="unconfigured",
                )
        self.assertEqual(result["manifests"]["output_validity"], "invalid-structured-output")
        self.assertEqual(result["output"]["case_id"], "small-feature")
        self.assertEqual(result["execution"]["model_version"], "glm-5.2")


if __name__ == "__main__":
    unittest.main()
