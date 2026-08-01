from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from tool_lambda import handle_tool  # noqa: E402
from walking_skeleton.service import WalkingSkeletonService  # noqa: E402


def gateway_context(
    tool_name: str = "utility-repair-tools___utility_service_request",
) -> SimpleNamespace:
    return SimpleNamespace(
        client_context=SimpleNamespace(
            custom={
                "bedrockAgentCoreMessageVersion": "1.0",
                "bedrockAgentCoreAwsRequestId": "aws-request-001",
                "bedrockAgentCoreMcpMessageId": "mcp-message-001",
                "bedrockAgentCoreGatewayId": "gateway-001",
                "bedrockAgentCoreTargetId": "target-001",
                "bedrockAgentCoreToolName": tool_name,
            }
        )
    )


class GatewayToolLambdaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = WalkingSkeletonService()

    def call(self, operation: str, payload: dict) -> dict:
        return handle_tool(
            {"operation": operation, "payload": payload},
            gateway_context(),
            service=self.service,
        )

    def test_create_conversation_and_resident_turn_share_application_core(self) -> None:
        created = self.call(
            "create_conversation",
            {"residentId": "resident-gateway-001"},
        )
        conversation_id = created["data"]["conversationId"]

        turn = self.call(
            "add_resident_message",
            {
                "residentId": "resident-gateway-001",
                "conversationId": conversation_id,
                "message": "浴室水管一直漏水",
            },
        )

        self.assertTrue(created["ok"])
        self.assertTrue(turn["ok"])
        self.assertEqual(turn["data"]["activeAgent"], "utility_repair_agent")
        self.assertEqual(turn["meta"]["toolName"], "utility_service_request")
        self.assertEqual(turn["meta"]["awsRequestId"], "aws-request-001")

    def test_progress_enforces_resident_resource_ownership(self) -> None:
        created = self.call(
            "create_conversation",
            {"residentId": "resident-owner"},
        )
        conversation_id = created["data"]["conversationId"]
        turn = self.call(
            "add_resident_message",
            {
                "residentId": "resident-owner",
                "conversationId": conversation_id,
                "message": "廚房水槽漏水",
            },
        )
        request_id = turn["data"]["serviceRequest"]["serviceRequestId"]

        denied = self.call(
            "get_progress",
            {
                "residentId": "different-resident",
                "serviceRequestId": request_id,
            },
        )

        self.assertFalse(denied["ok"])
        self.assertEqual(denied["error"]["code"], "forbidden")

    def test_provider_or_admin_operation_is_not_exposed_to_the_agent(self) -> None:
        result = self.call(
            "simulate_timeout",
            {"residentId": "resident-gateway-001", "taskId": "task-1"},
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "tool_operation_not_allowed")

    def test_gateway_tool_name_and_message_version_fail_closed(self) -> None:
        wrong_tool = handle_tool(
            {"operation": "create_conversation", "payload": {}},
            gateway_context("utility-repair-tools___different_tool"),
            service=self.service,
        )
        wrong_version_context = gateway_context()
        wrong_version_context.client_context.custom[
            "bedrockAgentCoreMessageVersion"
        ] = "2.0"
        wrong_version = handle_tool(
            {"operation": "create_conversation", "payload": {}},
            wrong_version_context,
            service=self.service,
        )

        self.assertEqual(wrong_tool["error"]["code"], "invalid_gateway_context")
        self.assertEqual(wrong_version["error"]["code"], "invalid_gateway_context")

    def test_malformed_event_returns_json_safe_error(self) -> None:
        result = handle_tool(
            {"operation": "add_resident_message", "payload": "not-an-object"},
            gateway_context(),
            service=self.service,
        )

        self.assertEqual(
            result,
            {
                "ok": False,
                "error": {
                    "code": "invalid_tool_input",
                    "message": "payload must be an object",
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
