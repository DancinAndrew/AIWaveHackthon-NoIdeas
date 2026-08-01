from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any


API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from bedrock_safety import (  # noqa: E402
    APPROVED_TEXT_MODEL_IDS,
    BedrockRequestGate,
    BedrockSafetyError,
    GuardedBedrockRuntime,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeBedrockClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"stopReason": "end_turn", "output": {"message": {}}}


class BedrockRequestGateTests(unittest.TestCase):
    def test_gate_keeps_request_starts_below_one_request_per_second(self) -> None:
        clock = FakeClock()
        gate = BedrockRequestGate(
            minimum_interval_seconds=1.05,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )
        starts: list[float] = []

        for _ in range(3):
            gate.invoke(lambda: starts.append(clock.monotonic()))

        self.assertEqual(starts, [0.0, 1.05, 2.1])
        self.assertEqual(clock.sleeps, [1.05, 1.05])

    def test_interval_of_one_second_or_less_is_rejected(self) -> None:
        for interval in (0, 0.5, 1.0):
            with self.subTest(interval=interval):
                with self.assertRaisesRegex(BedrockSafetyError, "greater than 1"):
                    BedrockRequestGate(minimum_interval_seconds=interval)

    def test_guarded_runtime_allows_only_the_approved_text_model(self) -> None:
        clock = FakeClock()
        client = FakeBedrockClient()
        runtime = GuardedBedrockRuntime(
            client,
            gate=BedrockRequestGate(
                minimum_interval_seconds=1.05,
                monotonic=clock.monotonic,
                sleep=clock.sleep,
            ),
        )
        model_id = next(iter(APPROVED_TEXT_MODEL_IDS))

        response = runtime.converse(
            modelId=model_id,
            messages=[],
        )

        self.assertEqual(response["stopReason"], "end_turn")
        self.assertEqual(client.calls[0]["modelId"], model_id)

    def test_unapproved_model_fails_before_client_or_sleep(self) -> None:
        clock = FakeClock()
        client = FakeBedrockClient()
        runtime = GuardedBedrockRuntime(
            client,
            gate=BedrockRequestGate(
                minimum_interval_seconds=1.05,
                monotonic=clock.monotonic,
                sleep=clock.sleep,
            ),
        )

        with self.assertRaisesRegex(BedrockSafetyError, "not approved"):
            runtime.converse(modelId="anthropic.unapproved", messages=[])

        self.assertEqual(client.calls, [])
        self.assertEqual(clock.sleeps, [])


if __name__ == "__main__":
    unittest.main()
