"""AWS CDK application entrypoint for the AIWave staging environment."""

from __future__ import annotations

import os
from pathlib import Path

from aws_cdk import App, Environment, Tags

from infra.aiwave_stack import AiwaveStagingStack, DeploymentAssets


STACK_NAME = "AiwaveStaging"
DEPLOYMENT_REGION = "us-west-2"


def build_app(
    *,
    account: str | None = None,
    assets: DeploymentAssets | None = None,
    outdir: Path | None = None,
) -> App:
    """Build the CDK app without contacting AWS or deploying resources."""

    selected_account = account or os.getenv("CDK_DEFAULT_ACCOUNT")
    selected_outdir = outdir or Path(
        os.getenv("CDK_OUTDIR", "infra/cdk.out")
    )
    app = App(outdir=str(selected_outdir))
    stack = AiwaveStagingStack(
        app,
        STACK_NAME,
        env=Environment(
            account=selected_account,
            region=DEPLOYMENT_REGION,
        ),
        assets=assets,
        description=(
            "AIWave hackathon staging: Flask, AgentCore, S3 Vectors, RDS and Amplify"
        ),
    )
    Tags.of(stack).add("Project", "AIWaveHackathon")
    Tags.of(stack).add("Environment", "staging")
    Tags.of(stack).add("ManagedBy", "CDK")
    return app


def main() -> None:
    build_app().synth()


if __name__ == "__main__":
    main()
