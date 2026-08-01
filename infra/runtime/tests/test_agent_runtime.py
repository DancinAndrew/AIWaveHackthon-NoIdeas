from __future__ import annotations

import unittest

from infra.runtime.agent_runtime import handle_request


class AgentRuntimeContractTests(unittest.TestCase):
    def test_supervisor_calls_each_domain_agent_as_a_tool(self) -> None:
        examples = {
            "幫我訂明晚兩位的餐廳": (
                "restaurant_reservation",
                "restaurant_agent",
            ),
            "我想購買一台除濕機": ("product_purchase", "product_agent"),
            "想找人每週打掃家裡": (
                "housekeeping_service",
                "housekeeping_agent",
            ),
            "浴室水管一直漏水": (
                "utility_repair",
                "utility_repair_agent",
            ),
            "想詢問社區管委會規約": (
                "community_consultation",
                "community_service_agent",
            ),
        }

        for message, (service_type, agent_name) in examples.items():
            with self.subTest(message=message):
                result = handle_request({"message": message, "sessionId": "demo"})

                self.assertEqual(result["orchestrationMode"], "agentcore-runtime")
                self.assertEqual(result["route"]["serviceType"], service_type)
                self.assertEqual(result["route"]["agent"], agent_name)
                self.assertEqual(result["route"]["toolName"], agent_name)
                self.assertEqual(result["trace"][0]["actor"], "supervisor")
                self.assertEqual(result["trace"][0]["action"], "tool_call")
                self.assertEqual(result["trace"][0]["target"], agent_name)
                self.assertEqual(result["agentTurn"]["agent"], agent_name)

    def test_active_agent_continues_without_being_reclassified(self) -> None:
        result = handle_request(
            {
                "message": "明天下午兩點到五點",
                "sessionId": "demo",
                "activeAgent": "utility_repair_agent",
                "workflowStage": "collecting_details",
            }
        )

        self.assertEqual(result["route"]["agent"], "utility_repair_agent")
        self.assertEqual(result["route"]["reasonCode"], "active_agent_continuation")
        self.assertEqual(result["agentTurn"]["workflowStage"], "collecting_details")

    def test_utility_agent_starts_with_safety_screening(self) -> None:
        result = handle_request(
            {"message": "廚房水槽下面漏水", "sessionId": "demo"}
        )

        turn = result["agentTurn"]
        self.assertEqual(turn["agent"], "utility_repair_agent")
        self.assertEqual(turn["intent"], "collect_service_request_details")
        self.assertIn("漏電", turn["assistantMessage"])
        self.assertIn("大量積水", turn["assistantMessage"])
        self.assertIn("service_request", turn["allowedTools"])

    def test_ambiguous_cross_domain_request_requires_clarification(self) -> None:
        result = handle_request(
            {
                "message": "幫我買餐券並且訂一間餐廳",
                "sessionId": "demo",
            }
        )

        self.assertIsNone(result["route"]["agent"])
        self.assertEqual(result["route"]["reasonCode"], "ambiguous_domains")
        self.assertEqual(result["trace"], [])
        self.assertIn("一次先處理一項", result["assistantMessage"])

    def test_unsupported_request_does_not_invent_a_domain(self) -> None:
        result = handle_request(
            {"message": "幫我寫一首歌", "sessionId": "demo"}
        )

        self.assertIsNone(result["route"]["agent"])
        self.assertEqual(result["route"]["reasonCode"], "unsupported_domain")
        self.assertEqual(result["trace"], [])

    def test_invalid_payload_is_returned_as_a_safe_boundary_error(self) -> None:
        result = handle_request({"message": "   ", "sessionId": "demo"})

        self.assertEqual(
            result,
            {
                "error": {
                    "code": "invalid_runtime_payload",
                    "message": "message must be a non-empty string up to 2000 characters",
                }
            },
        )


if __name__ == "__main__":
    unittest.main()
