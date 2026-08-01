from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from infra.preflight import (
    AwsPreflightError,
    load_env_file,
    run_identity_check,
    validate_aws_environment,
)


def valid_environment() -> dict[str, str]:
    expiration = datetime.now(UTC) + timedelta(hours=2)
    return {
        "AWS_ACCESS_KEY_ID": "ASIAEXAMPLEACCESS",
        "AWS_SECRET_ACCESS_KEY": "example-secret-value",
        "AWS_SESSION_TOKEN": "example-session-token",
        "AWS_CREDENTIAL_EXPIRATION": expiration.isoformat(),
        "AWS_DEFAULT_REGION": "us-west-2",
        "AWS_REGION": "us-west-2",
    }


class AwsPreflightTests(unittest.TestCase):
    def test_valid_temporary_credentials_return_redacted_summary(self) -> None:
        environment = valid_environment()

        result = validate_aws_environment(environment)
        summary = result.safe_summary()

        self.assertEqual(result.region, "us-west-2")
        self.assertIn("ASIA…CESS", summary)
        self.assertNotIn(environment["AWS_ACCESS_KEY_ID"], summary)
        self.assertNotIn(environment["AWS_SECRET_ACCESS_KEY"], summary)
        self.assertNotIn(environment["AWS_SESSION_TOKEN"], summary)

    def test_only_us_west_2_is_accepted(self) -> None:
        environment = valid_environment()
        environment["AWS_REGION"] = "us-east-1"

        with self.assertRaisesRegex(AwsPreflightError, "us-west-2"):
            validate_aws_environment(environment)

    def test_region_variables_must_not_disagree(self) -> None:
        environment = valid_environment()
        environment["AWS_DEFAULT_REGION"] = "us-east-1"

        with self.assertRaisesRegex(AwsPreflightError, "disagree"):
            validate_aws_environment(environment)

    def test_expired_or_nearly_expired_credentials_are_rejected(self) -> None:
        for offset in (timedelta(minutes=-1), timedelta(minutes=4)):
            with self.subTest(offset=offset):
                environment = valid_environment()
                environment["AWS_CREDENTIAL_EXPIRATION"] = (
                    datetime.now(UTC) + offset
                ).isoformat()

                with self.assertRaisesRegex(AwsPreflightError, "expire"):
                    validate_aws_environment(environment)

    def test_session_token_and_expiration_are_required(self) -> None:
        for key in ("AWS_SESSION_TOKEN", "AWS_CREDENTIAL_EXPIRATION"):
            with self.subTest(key=key):
                environment = valid_environment()
                environment.pop(key)

                with self.assertRaisesRegex(AwsPreflightError, key):
                    validate_aws_environment(environment)

    def test_env_file_parser_does_not_execute_shell_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "must-not-exist"
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "AWS_REGION=us-west-2\n"
                f"UNTRUSTED=$(touch {marker})\n"
                'QUOTED="literal value"\n',
                encoding="utf-8",
            )

            parsed = load_env_file(env_file)

            self.assertFalse(marker.exists())
            self.assertEqual(parsed["UNTRUSTED"], f"$(touch {marker})")
            self.assertEqual(parsed["QUOTED"], "literal value")

    def test_online_check_uses_read_only_sts_identity_call(self) -> None:
        class FakeStsClient:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def get_caller_identity(self) -> dict[str, str]:
                self.calls.append("get_caller_identity")
                return {
                    "Account": "123456789012",
                    "Arn": "arn:aws:sts::123456789012:assumed-role/demo/session",
                    "UserId": "example",
                }

        client = FakeStsClient()

        result = run_identity_check(client)

        self.assertEqual(client.calls, ["get_caller_identity"])
        self.assertEqual(result, "STS identity verified for account …9012")


if __name__ == "__main__":
    unittest.main()
