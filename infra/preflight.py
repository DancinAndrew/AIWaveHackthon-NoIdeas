"""Local AWS credential and region preflight with an optional read-only STS check."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol


REQUIRED_REGION = "us-west-2"
MINIMUM_CREDENTIAL_LIFETIME = timedelta(minutes=15)
REQUIRED_CREDENTIAL_KEYS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_CREDENTIAL_EXPIRATION",
)


class AwsPreflightError(ValueError):
    """Raised before deployment when local AWS configuration is unsafe."""


class StsIdentityClient(Protocol):
    def get_caller_identity(self) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class AwsPreflightResult:
    region: str
    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: datetime

    def safe_summary(self) -> str:
        """Return a summary that never contains credential material."""

        masked_access_key = _mask_identifier(self.access_key_id)
        return (
            f"AWS preflight passed: region={self.region}, "
            f"access_key={masked_access_key}, temporary_credentials=true, "
            f"expires_at={self.expiration.isoformat()}"
        )


def load_env_file(path: Path) -> dict[str, str]:
    """Parse literal KEY=VALUE lines without shell evaluation or interpolation."""

    if not path.is_file():
        raise AwsPreflightError(f"environment file not found: {path}")
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        if "=" not in line:
            raise AwsPreflightError(f"invalid .env line {line_number}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not key.replace("_", "").isalnum():
            raise AwsPreflightError(f"invalid .env key on line {line_number}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def validate_aws_environment(
    environment: Mapping[str, str],
    *,
    now: datetime | None = None,
) -> AwsPreflightResult:
    """Validate temporary credentials locally without making an AWS request."""

    missing = [key for key in REQUIRED_CREDENTIAL_KEYS if not environment.get(key)]
    if missing:
        raise AwsPreflightError(
            "missing required temporary credential values: " + ", ".join(missing)
        )

    region = environment.get("AWS_REGION", "").strip()
    default_region = environment.get("AWS_DEFAULT_REGION", "").strip()
    if region and default_region and region != default_region:
        raise AwsPreflightError("AWS_REGION and AWS_DEFAULT_REGION disagree")
    selected_region = region or default_region
    if selected_region != REQUIRED_REGION:
        raise AwsPreflightError(
            f"deployment region must be {REQUIRED_REGION}, got {selected_region or 'unset'}"
        )

    expiration_text = environment["AWS_CREDENTIAL_EXPIRATION"].strip()
    try:
        expiration = datetime.fromisoformat(expiration_text.replace("Z", "+00:00"))
    except ValueError as error:
        raise AwsPreflightError(
            "AWS_CREDENTIAL_EXPIRATION must be an ISO-8601 timestamp"
        ) from error
    if expiration.tzinfo is None:
        raise AwsPreflightError("AWS_CREDENTIAL_EXPIRATION must include a timezone")
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        raise AwsPreflightError("preflight current time must include a timezone")
    if expiration.astimezone(UTC) - current_time.astimezone(UTC) < (
        MINIMUM_CREDENTIAL_LIFETIME
    ):
        raise AwsPreflightError(
            "temporary AWS credentials expire in less than 15 minutes"
        )

    return AwsPreflightResult(
        region=selected_region,
        access_key_id=environment["AWS_ACCESS_KEY_ID"],
        secret_access_key=environment["AWS_SECRET_ACCESS_KEY"],
        session_token=environment["AWS_SESSION_TOKEN"],
        expiration=expiration,
    )


def run_identity_check(client: StsIdentityClient) -> str:
    """Make exactly one read-only STS call and return a redacted result."""

    try:
        identity = client.get_caller_identity()
    except Exception as error:
        raise AwsPreflightError(
            f"STS identity check failed ({type(error).__name__})"
        ) from error
    account = identity.get("Account")
    if not isinstance(account, str) or len(account) < 4:
        raise AwsPreflightError("STS identity response did not contain an account")
    return f"STS identity verified for account …{account[-4:]}"


def _mask_identifier(value: str) -> str:
    if len(value) <= 8:
        return "…"
    return f"{value[:4]}…{value[-4:]}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--online",
        action="store_true",
        help="also perform one read-only STS GetCallerIdentity request",
    )
    arguments = parser.parse_args()

    environment = {**load_env_file(arguments.env_file), **os.environ}
    result = validate_aws_environment(environment)
    print(result.safe_summary())
    if arguments.online:
        import boto3

        session = boto3.Session(
            aws_access_key_id=result.access_key_id,
            aws_secret_access_key=result.secret_access_key,
            aws_session_token=result.session_token,
            region_name=result.region,
        )
        print(run_identity_check(session.client("sts")))
    return 0


def cli() -> int:
    try:
        return main()
    except AwsPreflightError as error:
        print(f"AWS preflight failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli())
