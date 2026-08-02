"""Tests for assembling the AgentCore Runtime deployment artifact.

The Bedrock request gate and model allowlist have one owner in
``packages/api/bedrock_safety.py``. The Runtime artifact must contain that exact
module rather than a second copy that can drift away from the Flask Lambda.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from infra.aiwave_stack import SHARED_RUNTIME_MODULES, DeploymentAssets


class StagedAgentRuntimeCodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name)
        self.api_code = self.root / "api"
        self.runtime_code = self.root / "runtime"
        (self.api_code).mkdir()
        (self.runtime_code / "tests").mkdir(parents=True)
        (self.runtime_code / "__pycache__").mkdir()

        (self.api_code / "bedrock_safety.py").write_text(
            "APPROVED_TEXT_MODEL_IDS = frozenset()\n", encoding="utf-8"
        )
        (self.runtime_code / "agent_runtime.py").write_text(
            "print('fixture')\n", encoding="utf-8"
        )
        (self.runtime_code / "requirements.txt").write_text(
            "boto3\n", encoding="utf-8"
        )
        (self.runtime_code / "tests" / "test_fixture.py").write_text(
            "# not shipped\n", encoding="utf-8"
        )
        (self.runtime_code / "__pycache__" / "stale.pyc").write_bytes(b"\x00")

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def _assets(self) -> DeploymentAssets:
        return DeploymentAssets(
            api_code=self.api_code,
            agent_runtime_code=self.runtime_code,
            bundle=False,
            staging_root=self.root / "staging",
        )

    def test_shared_bedrock_gate_is_copied_into_the_runtime_artifact(self) -> None:
        staged = self._assets().staged_agent_runtime_code()

        self.assertNotEqual(staged, self.runtime_code)
        self.assertTrue((staged / "agent_runtime.py").is_file())
        for module_name in SHARED_RUNTIME_MODULES:
            self.assertTrue(
                (staged / module_name).is_file(), f"missing shared {module_name}"
            )
        self.assertEqual(
            (staged / "bedrock_safety.py").read_text(encoding="utf-8"),
            (self.api_code / "bedrock_safety.py").read_text(encoding="utf-8"),
        )

    def test_tests_and_caches_are_not_shipped(self) -> None:
        staged = self._assets().staged_agent_runtime_code()

        self.assertFalse((staged / "tests").exists())
        self.assertFalse((staged / "__pycache__").exists())
        self.assertTrue((staged / "requirements.txt").is_file())

    def test_staging_is_repeatable_and_drops_stale_files(self) -> None:
        assets = self._assets()
        staged = assets.staged_agent_runtime_code()
        (staged / "left_over.py").write_text("stale\n", encoding="utf-8")

        staged_again = assets.staged_agent_runtime_code()

        self.assertEqual(staged, staged_again)
        self.assertFalse((staged_again / "left_over.py").exists())

    def test_missing_shared_module_falls_back_to_the_runtime_directory(self) -> None:
        (self.api_code / "bedrock_safety.py").unlink()

        staged = self._assets().staged_agent_runtime_code()

        self.assertEqual(staged, self.runtime_code)

    def test_repository_assets_stage_outside_the_tracked_tree(self) -> None:
        assets = DeploymentAssets.from_repository()

        self.assertIsNotNone(assets.staging_root)
        self.assertIn("cdk.out", str(assets.staging_root))


if __name__ == "__main__":
    unittest.main()
