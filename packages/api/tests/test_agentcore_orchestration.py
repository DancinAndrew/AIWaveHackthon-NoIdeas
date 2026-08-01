from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from typing import Any


API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from walking_skeleton.orchestration import (  # noqa: E402
    AgentCoreOrchestrationError,
    AgentCoreSupervisorOrchestrator,
)


class ImmediateGate:
    def invoke(self, operation, *args, **kwargs):
        return operation(*args, **kwargs)


class FakeAgentCoreClient:
    def __init__(self, payload: dict[str, Any], *, status: int = 200) -> None:
        self.payload = payload
        self.status = status
        self.calls: list[dict[str, Any]] = []

    def invoke_agent_runtime(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "statusCode": self.status,
            "contentType": "application/json",
            "response": io.BytesIO(json.dumps(self.payload).encode("utf-8")),
        }


class AgentCoreSupervisorOrchestratorTests(unittest.TestCase):
    def test_valid_runtime_trace_becomes_a_delegation(self) -> None:
        client = FakeAgentCoreClient(
            {
                "orchestrationMode": "agentcore-runtime",
                "route": {
                    "serviceType": "utility_repair",
                    "agent": "utility_repair_agent",
                },
                "trace": [
                    {
                        "actor": "supervisor",
                        "action": "tool_call",
                        "target": "utility_repair_agent",
                    }
                ],
            }
        )
        orchestrator = AgentCoreSupervisorOrchestrator(
            client=client,
            runtime_arn="arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/demo",
            qualifier="staging",
            request_gate=ImmediateGate(),
        )

        delegation = orchestrator.delegate("浴室水管漏水")

        self.assertEqual(delegation.service_type, "utility_repair")
        self.assertEqual(delegation.target_agent, "utility_repair_agent")
        self.assertEqual(delegation.mode, "agentcore-runtime")
        self.assertEqual(len(client.calls), 1)
        call = client.calls[0]
        self.assertEqual(call["qualifier"], "staging")
        self.assertEqual(call["contentType"], "application/json")
        self.assertEqual(call["accept"], "application/json")
        self.assertEqual(
            json.loads(call["payload"].decode("utf-8"))["message"],
            "浴室水管漏水",
        )

    def test_unsupported_runtime_route_is_valid_without_tool_trace(self) -> None:
        client = FakeAgentCoreClient(
            {
                "orchestrationMode": "agentcore-runtime",
                "route": {"serviceType": None, "agent": None},
                "trace": [],
            }
        )
        orchestrator = AgentCoreSupervisorOrchestrator(
            client=client,
            runtime_arn="runtime-arn",
            request_gate=ImmediateGate(),
        )

        delegation = orchestrator.delegate("幫我寫一首歌")

        self.assertIsNone(delegation.service_type)
        self.assertIsNone(delegation.target_agent)

    def test_mismatched_or_unapproved_trace_fails_closed(self) -> None:
        invalid_payloads = (
            {
                "orchestrationMode": "agentcore-runtime",
                "route": {
                    "serviceType": "utility_repair",
                    "agent": "product_agent",
                },
                "trace": [],
            },
            {
                "orchestrationMode": "deterministic-demo",
                "route": {
                    "serviceType": "utility_repair",
                    "agent": "utility_repair_agent",
                },
                "trace": [],
            },
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                orchestrator = AgentCoreSupervisorOrchestrator(
                    client=FakeAgentCoreClient(payload),
                    runtime_arn="runtime-arn",
                    request_gate=ImmediateGate(),
                )
                with self.assertRaises(AgentCoreOrchestrationError):
                    orchestrator.delegate("水管漏水")

    def test_non_200_and_invalid_json_fail_without_local_fallback(self) -> None:
        failing_client = FakeAgentCoreClient({}, status=503)
        orchestrator = AgentCoreSupervisorOrchestrator(
            client=failing_client,
            runtime_arn="runtime-arn",
            request_gate=ImmediateGate(),
        )
        with self.assertRaises(AgentCoreOrchestrationError):
            orchestrator.delegate("水管漏水")

        invalid_json_client = FakeAgentCoreClient({})
        invalid_json_client.invoke_agent_runtime = lambda **_kwargs: {
            "statusCode": 200,
            "response": io.BytesIO(b"not-json"),
        }
        orchestrator = AgentCoreSupervisorOrchestrator(
            client=invalid_json_client,
            runtime_arn="runtime-arn",
            request_gate=ImmediateGate(),
        )
        with self.assertRaises(AgentCoreOrchestrationError):
            orchestrator.delegate("水管漏水")


if __name__ == "__main__":
    unittest.main()
