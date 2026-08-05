#!/usr/bin/env python3
"""Unit tests for the CC Switch Claude runner without a provider call."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
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
        self.assertNotIn("Bash", command)
        result = claude_skill_runner._structured_output({"structured_output": {
            "case_id": "small-feature", "route": ["sdlc-product-design"], "modules": ["mod.product.core"],
            "roles": ["role.product-owner"], "obligations": ["obl.product.discover.problem-frame"],
            "artifacts": ["ProductContract"], "actions": [],
            "transition": {"decision": "route", "route": ["sdlc-product-design"]},
        }})
        self.assertEqual(result["case_id"], "small-feature")

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
        self.assertEqual(claude_skill_runner._safe_failure_class(b"failed to load plugin"), "plugin")
        self.assertEqual(claude_skill_runner._safe_failure_class(b"unrecognized failure"), "opaque")


if __name__ == "__main__":
    unittest.main()
