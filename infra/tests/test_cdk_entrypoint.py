from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path


os.environ.setdefault("JSII_RUNTIME_PACKAGE_CACHE", "/tmp/aiwave-jsii-cache")
os.environ.setdefault("JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION", "1")

from infra.aiwave_stack import DeploymentAssets  # noqa: E402
from infra.app import build_app  # noqa: E402


class CdkEntrypointTests(unittest.TestCase):
    def test_build_app_synthesizes_the_named_staging_stack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            api_code = root / "api"
            runtime_code = root / "runtime"
            api_code.mkdir()
            runtime_code.mkdir()
            (api_code / "lambda_handler.py").write_text(
                "def handler(event, context): return {'statusCode': 200}\n",
                encoding="utf-8",
            )
            (runtime_code / "agent_runtime.py").write_text(
                "print('fixture')\n",
                encoding="utf-8",
            )

            app = build_app(
                account="123456789012",
                assets=DeploymentAssets(
                    api_code=api_code,
                    agent_runtime_code=runtime_code,
                    bundle=False,
                ),
            )
            assembly = app.synth()

            self.assertIsNotNone(assembly.get_stack_by_name("AiwaveStaging"))

    def test_root_cdk_configuration_uses_the_local_python_module(self) -> None:
        repository_root = Path(__file__).resolve().parents[2]
        configuration = json.loads(
            (repository_root / "cdk.json").read_text(encoding="utf-8")
        )

        self.assertEqual(configuration["app"], ".venv/bin/python -m infra.app")
        self.assertEqual(configuration["output"], "infra/cdk.out")


if __name__ == "__main__":
    unittest.main()
