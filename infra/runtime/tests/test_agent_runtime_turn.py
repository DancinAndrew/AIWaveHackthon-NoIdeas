"""Runtime payload contract tests for model-backed multi-turn agent turns.

Locks the Flask↔Runtime boundary described in
``openspec/changes/define-flask-mcp-service-intake/contracts/runtime/agent-turn.json``.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = RUNTIME_ROOT.parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from agent_runtime import Supervisor  # noqa: E402
from domain_reasoning import EXTRACTION_TOOL_NAME, DomainReasoner  # noqa: E402
from knowledge import KnowledgeBaseReader  # noqa: E402
from logical_agents import LOGICAL_AGENT_REGISTRY  # noqa: E402
from model_gate import BedrockRequestGate, build_guarded_runtime  # noqa: E402

CONTRACT_PATH = (
    REPOSITORY_ROOT
    / "openspec"
    / "changes"
    / "define-flask-mcp-service-intake"
    / "contracts"
    / "runtime"
    / "agent-turn.json"
)
APPROVED_MODEL_ID = "amazon.nova-2-lite-v1:0"


class FakeConverseClient:
    def __init__(self, tool_inputs: list[dict[str, Any]]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._tool_inputs = list(tool_inputs)

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        tool_input = self._tool_inputs.pop(0)
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "toolUseId": f"tooluse_{len(self.calls)}",
                                "name": EXTRACTION_TOOL_NAME,
                                "input": tool_input,
                            }
                        }
                    ],
                }
            },
            "stopReason": "tool_use",
        }


class FakeRetrieveClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def retrieve(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "retrievalResults": [
                {
                    "content": {"text": "請先關閉止水閥並記錄漏水位置。"},
                    "metadata": {
                        "service_type": "utility_repair",
                        "doc_kind": "sop",
                        "source_doc_id": "kb-utility-repair-002",
                    },
                    "location": {
                        "s3Location": {"uri": "s3://bucket/utility_repair/02-sop.md"}
                    },
                    "score": 0.58,
                }
            ]
        }


def _supervisor(
    tool_inputs: list[dict[str, Any]],
    *,
    retrieve_client: FakeRetrieveClient | None = None,
) -> tuple[Supervisor, FakeConverseClient]:
    client = FakeConverseClient(tool_inputs)
    knowledge = (
        KnowledgeBaseReader(client=retrieve_client, knowledge_base_id="KB12345678")
        if retrieve_client is not None
        else None
    )
    reasoner = DomainReasoner(
        model_client=build_guarded_runtime(
            client,
            # Interval enforcement is covered by test_bedrock_safety.py; the wait
            # is stubbed out here so the contract suite stays fast.
            gate=BedrockRequestGate(
                minimum_interval_seconds=1.05,
                sleep=lambda _: None,
            ),
        ),
        model_id=APPROVED_MODEL_ID,
        knowledge=knowledge,
    )
    return Supervisor(LOGICAL_AGENT_REGISTRY, reasoner=reasoner), client


class AgentTurnPayloadContractTests(unittest.TestCase):
    def test_agent_turn_contains_every_contract_required_key(self) -> None:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        required = contract["$defs"]["agentTurn"]["required"]
        supervisor, _ = _supervisor(
            [
                {
                    "assistantMessage": "了解，先確認安全狀況。",
                    "extractedFields": {"issueType": "leak"},
                    "riskLevel": "none",
                }
            ]
        )

        result = supervisor.handle(
            {
                "message": "廚房水槽下面漏水",
                "sessionId": "demo",
                "turnGoal": "route_new_request",
            }
        )

        self.assertEqual(result["orchestrationMode"], "agentcore-runtime")
        for key in required:
            self.assertIn(key, result["agentTurn"], f"missing agentTurn.{key}")
        reasoning = result["agentTurn"]["reasoning"]
        self.assertEqual(reasoning["mode"], "model")
        self.assertEqual(reasoning["modelId"], APPROVED_MODEL_ID)
        self.assertFalse(reasoning["knowledgeBaseQueried"])
        self.assertEqual(
            result["agentTurn"]["riskAssessment"],
            {"level": "none", "signals": [], "source": "none"},
        )
        self.assertEqual(result["agentTurn"]["extractedFields"], {"issueType": "leak"})
        self.assertEqual(
            result["assistantMessage"], result["agentTurn"]["assistantMessage"]
        )

    def test_reasoning_payload_keys_match_the_contract(self) -> None:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        allowed = set(contract["$defs"]["reasoning"]["properties"])
        supervisor, _ = _supervisor(
            [
                {
                    "assistantMessage": "好的",
                    "extractedFields": {},
                    "riskLevel": "none",
                }
            ]
        )

        result = supervisor.handle({"message": "浴室水管漏水", "sessionId": "demo"})

        produced = set(result["agentTurn"]["reasoning"])
        self.assertEqual(produced - allowed, set(), "reasoning has undeclared keys")
        self.assertTrue(
            set(contract["$defs"]["reasoning"]["required"]).issubset(produced)
        )

    def test_knowledge_reference_keys_match_the_contract(self) -> None:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        allowed = set(contract["$defs"]["knowledgeReference"]["properties"])
        supervisor, _ = _supervisor(
            [
                {
                    "assistantMessage": "好的",
                    "extractedFields": {},
                    "riskLevel": "none",
                }
            ],
            retrieve_client=FakeRetrieveClient(),
        )

        result = supervisor.handle(
            {
                "message": "師傅到之前我需要先做什麼嗎？",
                "activeAgent": "utility_repair_agent",
                "workflowStage": "collecting_details",
                "turnGoal": "collect_missing_fields",
            }
        )

        references = result["agentTurn"]["knowledge"]
        self.assertEqual(len(references), 1)
        self.assertEqual(set(references[0]) - allowed, set())

    def test_response_is_json_serialisable_for_the_runtime_boundary(self) -> None:
        supervisor, _ = _supervisor(
            [
                {
                    "assistantMessage": "好的",
                    "extractedFields": {"districtName": "內湖區"},
                    "riskLevel": "none",
                }
            ]
        )

        result = supervisor.handle(
            {
                "message": "內湖區",
                "activeAgent": "utility_repair_agent",
                "workflowStage": "collecting_details",
                "turnGoal": "collect_missing_fields",
            }
        )

        json.dumps(result, ensure_ascii=False)

    def test_supervisor_trace_precedes_the_agent_model_trace(self) -> None:
        supervisor, _ = _supervisor(
            [
                {
                    "assistantMessage": "好的",
                    "extractedFields": {},
                    "riskLevel": "none",
                }
            ]
        )

        result = supervisor.handle({"message": "浴室水管漏水", "sessionId": "demo"})

        actions = [(entry["actor"], entry["action"]) for entry in result["trace"]]
        self.assertEqual(actions[0], ("supervisor", "tool_call"))
        self.assertIn(("utility_repair_agent", "model_invoke"), actions)


class MultiTurnStateTests(unittest.TestCase):
    def test_known_fields_are_passed_through_and_not_reasked(self) -> None:
        supervisor, client = _supervisor(
            [
                {
                    "assistantMessage": "你希望什麼時段到場？",
                    "extractedFields": {},
                    "riskLevel": "none",
                }
            ]
        )

        result = supervisor.handle(
            {
                "message": "嗯",
                "activeAgent": "utility_repair_agent",
                "workflowStage": "collecting_details",
                "turnGoal": "collect_missing_fields",
                "knownFields": {"districtName": "內湖區", "riskScreened": True},
                "missingFields": ["preferredTime"],
                "serviceScope": {"districts": ["內湖區", "信義區"]},
            }
        )

        prompt = client.calls[0]["system"][0]["text"]
        self.assertIn("內湖區", prompt)
        self.assertIn("preferredTime", prompt)
        self.assertEqual(result["agentTurn"]["missingFields"], ["preferredTime"])
        self.assertEqual(
            result["route"]["reasonCode"], "active_agent_continuation"
        )

    def test_history_reaches_the_model_as_prior_turns(self) -> None:
        supervisor, client = _supervisor(
            [
                {
                    "assistantMessage": "好的",
                    "extractedFields": {"preferredTime": "週六白天"},
                    "riskLevel": "none",
                }
            ]
        )

        supervisor.handle(
            {
                "message": "禮拜六白天都可以",
                "activeAgent": "utility_repair_agent",
                "workflowStage": "collecting_details",
                "turnGoal": "collect_missing_fields",
                "history": [
                    {"role": "resident", "content": "廚房水槽下面在滴水"},
                    {"role": "agent", "content": "請問服務地區？"},
                    {"role": "resident", "content": "內湖區"},
                ],
            }
        )

        messages = client.calls[0]["messages"]
        rendered = [block["text"] for m in messages for block in m["content"]]
        self.assertIn("廚房水槽下面在滴水", "\n".join(rendered))
        self.assertIn("禮拜六白天都可以", rendered[-1])

    def test_knowledge_question_is_answered_with_domain_references(self) -> None:
        retrieve_client = FakeRetrieveClient()
        supervisor, _ = _supervisor(
            [
                {
                    "assistantMessage": "先關閉止水閥可以降低鄰損風險。",
                    "extractedFields": {},
                    "riskLevel": "none",
                }
            ],
            retrieve_client=retrieve_client,
        )

        result = supervisor.handle(
            {
                "message": "在師傅到之前我需要先做什麼嗎？",
                "activeAgent": "utility_repair_agent",
                "workflowStage": "collecting_details",
                "turnGoal": "collect_missing_fields",
            }
        )

        self.assertTrue(result["agentTurn"]["reasoning"]["knowledgeBaseQueried"])
        self.assertEqual(len(result["agentTurn"]["knowledge"]), 1)
        reference = result["agentTurn"]["knowledge"][0]
        self.assertEqual(reference["serviceType"], "utility_repair")
        self.assertEqual(reference["docKind"], "sop")
        self.assertTrue(reference["excerpt"])


class UnroutedTurnTests(unittest.TestCase):
    def test_unsupported_domain_never_invokes_the_model(self) -> None:
        supervisor, client = _supervisor([])

        result = supervisor.handle({"message": "幫我寫一首歌", "sessionId": "demo"})

        self.assertEqual(client.calls, [])
        self.assertEqual(result["route"]["reasonCode"], "unsupported_domain")
        self.assertNotIn("agentTurn", result)

    def test_ambiguous_domain_never_invokes_the_model(self) -> None:
        supervisor, client = _supervisor([])

        result = supervisor.handle(
            {"message": "幫我買餐券並且訂一間餐廳", "sessionId": "demo"}
        )

        self.assertEqual(client.calls, [])
        self.assertEqual(result["route"]["reasonCode"], "ambiguous_domains")


if __name__ == "__main__":
    unittest.main()
