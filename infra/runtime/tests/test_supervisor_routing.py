"""Supervisor routing contract tests.

The keyword table stays as a zero-cost fast path, but a resident sentence it does
not cover must still reach the right domain agent instead of being told the
request is unsupported. Classification is fail-closed: anything the model returns
outside the approved five service types degrades to the existing clarification or
unsupported response, never to an invented domain.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from agent_runtime import Supervisor  # noqa: E402
from domain_reasoning import EXTRACTION_TOOL_NAME, DomainReasoner  # noqa: E402
from logical_agents import LOGICAL_AGENT_REGISTRY  # noqa: E402
from model_gate import BedrockRequestGate, build_guarded_runtime  # noqa: E402
from routing import ROUTE_TOOL_NAME, DomainRouter  # noqa: E402

APPROVED_MODEL_ID = "amazon.nova-2-lite-v1:0"


def _test_gate() -> BedrockRequestGate:
    return BedrockRequestGate(minimum_interval_seconds=1.05, sleep=lambda _: None)


class ScriptedConverseClient:
    """Returns one queued tool payload per call, keyed by the requested tool."""

    def __init__(self, *, payloads: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._payloads = list(payloads or [])
        self.error: Exception | None = None

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        tool_name = kwargs["toolConfig"]["toolChoice"]["tool"]["name"]
        payload = self._payloads.pop(0) if self._payloads else {}
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "toolUseId": f"tooluse_{len(self.calls)}",
                                "name": tool_name,
                                "input": payload,
                            }
                        }
                    ],
                }
            },
            "stopReason": "tool_use",
        }

    @property
    def requested_tools(self) -> list[str]:
        return [
            call["toolConfig"]["toolChoice"]["tool"]["name"] for call in self.calls
        ]


class TextOnlyConverseClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "output": {
                "message": {"role": "assistant", "content": [{"text": "無法分類"}]}
            },
            "stopReason": "end_turn",
        }


def _supervisor(
    client: Any,
    *,
    model_id: str = APPROVED_MODEL_ID,
    with_router: bool = True,
) -> Supervisor:
    guarded = build_guarded_runtime(client, gate=_test_gate())
    router = (
        DomainRouter(
            model_client=guarded,
            model_id=model_id,
            registry=LOGICAL_AGENT_REGISTRY,
        )
        if with_router
        else None
    )
    reasoner = DomainReasoner(
        model_client=guarded,
        model_id=model_id,
        knowledge=None,
    )
    return Supervisor(LOGICAL_AGENT_REGISTRY, reasoner=reasoner, router=router)


TURN_PAYLOAD = {
    "assistantMessage": "了解，先確認安全狀況。",
    "extractedFields": {"issueType": "leak"},
    "riskLevel": "none",
}


class KeywordFastPathTests(unittest.TestCase):
    def test_keyword_match_skips_classification(self) -> None:
        client = ScriptedConverseClient(payloads=[TURN_PAYLOAD])
        supervisor = _supervisor(client)

        result = supervisor.handle({"message": "浴室水管漏水", "sessionId": "demo"})

        self.assertEqual(result["route"]["reasonCode"], "domain_keyword_match")
        self.assertEqual(client.requested_tools, [EXTRACTION_TOOL_NAME])

    def test_active_agent_skips_classification(self) -> None:
        client = ScriptedConverseClient(payloads=[TURN_PAYLOAD])
        supervisor = _supervisor(client)

        result = supervisor.handle(
            {
                "message": "禮拜六白天都可以",
                "activeAgent": "utility_repair_agent",
                "workflowStage": "collecting_details",
            }
        )

        self.assertEqual(result["route"]["reasonCode"], "active_agent_continuation")
        self.assertEqual(client.requested_tools, [EXTRACTION_TOOL_NAME])

    def test_multiple_keyword_matches_still_ask_for_clarification(self) -> None:
        client = ScriptedConverseClient()
        supervisor = _supervisor(client)

        result = supervisor.handle({"message": "幫我買餐券並且訂一間餐廳"})

        self.assertEqual(client.calls, [])
        self.assertEqual(result["route"]["reasonCode"], "ambiguous_domains")


class ModelClassificationTests(unittest.TestCase):
    def test_sentence_outside_the_keyword_table_reaches_the_right_agent(self) -> None:
        client = ScriptedConverseClient(
            payloads=[{"serviceType": "utility_repair"}, TURN_PAYLOAD]
        )
        supervisor = _supervisor(client)

        result = supervisor.handle(
            {"message": "廚房水槽下面在滴水，昨天開始的", "sessionId": "demo"}
        )

        self.assertEqual(result["route"]["serviceType"], "utility_repair")
        self.assertEqual(result["route"]["agent"], "utility_repair_agent")
        self.assertEqual(result["route"]["reasonCode"], "model_classification")
        self.assertEqual(
            client.requested_tools, [ROUTE_TOOL_NAME, EXTRACTION_TOOL_NAME]
        )
        self.assertEqual(result["agentTurn"]["extractedFields"], {"issueType": "leak"})

    def test_classification_request_forces_the_single_route_tool(self) -> None:
        client = ScriptedConverseClient(
            payloads=[{"serviceType": "utility_repair"}, TURN_PAYLOAD]
        )
        _supervisor(client).handle({"message": "洗手台下面在滴水"})

        call = client.calls[0]
        self.assertEqual(call["modelId"], APPROVED_MODEL_ID)
        tool_config = call["toolConfig"]
        self.assertEqual(len(tool_config["tools"]), 1)
        self.assertEqual(tool_config["tools"][0]["toolSpec"]["name"], ROUTE_TOOL_NAME)
        self.assertEqual(
            tool_config["toolChoice"], {"tool": {"name": ROUTE_TOOL_NAME}}
        )
        enum_values = tool_config["tools"][0]["toolSpec"]["inputSchema"]["json"][
            "properties"
        ]["serviceType"]["enum"]
        self.assertEqual(
            sorted(enum_values),
            sorted(
                [
                    "restaurant_reservation",
                    "product_purchase",
                    "housekeeping_service",
                    "utility_repair",
                    "community_consultation",
                    "ambiguous",
                    "unsupported",
                ]
            ),
        )

    def test_classification_trace_is_attributed_to_the_supervisor(self) -> None:
        client = ScriptedConverseClient(
            payloads=[{"serviceType": "utility_repair"}, TURN_PAYLOAD]
        )
        result = _supervisor(client).handle({"message": "熱水不夠熱"})

        actions = [(entry["actor"], entry["action"]) for entry in result["trace"]]
        self.assertEqual(actions[0], ("supervisor", "model_invoke"))
        self.assertEqual(actions[1], ("supervisor", "tool_call"))
        self.assertIn(("utility_repair_agent", "model_invoke"), actions)

    def test_model_reported_ambiguity_asks_for_clarification(self) -> None:
        client = ScriptedConverseClient(payloads=[{"serviceType": "ambiguous"}])

        result = _supervisor(client).handle({"message": "幫我把家裡弄好一點"})

        self.assertEqual(result["route"]["reasonCode"], "ambiguous_domains")
        self.assertNotIn("agentTurn", result)
        self.assertIn("一次先處理一項", result["assistantMessage"])

    def test_model_reported_unsupported_domain_is_respected(self) -> None:
        client = ScriptedConverseClient(payloads=[{"serviceType": "unsupported"}])

        result = _supervisor(client).handle({"message": "幫我寫一首歌"})

        self.assertEqual(result["route"]["reasonCode"], "unsupported_domain")
        self.assertNotIn("agentTurn", result)


class FailClosedClassificationTests(unittest.TestCase):
    def test_unknown_service_type_never_invents_a_domain(self) -> None:
        client = ScriptedConverseClient(payloads=[{"serviceType": "pet_grooming"}])

        result = _supervisor(client).handle({"message": "幫我帶狗去洗澡"})

        self.assertEqual(result["route"]["reasonCode"], "unsupported_domain")
        self.assertIsNone(result["route"]["agent"])
        self.assertEqual(client.requested_tools, [ROUTE_TOOL_NAME])

    def test_missing_tool_use_falls_back_to_unsupported(self) -> None:
        client = TextOnlyConverseClient()

        result = _supervisor(client).handle({"message": "有些事情想麻煩你"})

        self.assertEqual(result["route"]["reasonCode"], "unsupported_domain")

    def test_classification_error_falls_back_to_unsupported(self) -> None:
        client = ScriptedConverseClient()
        client.error = RuntimeError("ThrottlingException")

        result = _supervisor(client).handle({"message": "有些事情想麻煩你"})

        self.assertEqual(result["route"]["reasonCode"], "unsupported_domain")

    def test_unapproved_model_never_reaches_the_client(self) -> None:
        client = ScriptedConverseClient(payloads=[{"serviceType": "utility_repair"}])

        result = _supervisor(client, model_id="anthropic.claude-3-sonnet").handle(
            {"message": "廚房水槽下面在滴水"}
        )

        self.assertEqual(client.calls, [])
        self.assertEqual(result["route"]["reasonCode"], "unsupported_domain")

    def test_without_a_router_the_previous_behaviour_is_preserved(self) -> None:
        client = ScriptedConverseClient()

        result = _supervisor(client, with_router=False).handle(
            {"message": "廚房水槽下面在滴水"}
        )

        self.assertEqual(client.calls, [])
        self.assertEqual(result["route"]["reasonCode"], "unsupported_domain")


if __name__ == "__main__":
    unittest.main()
