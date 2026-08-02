"""Contract tests for model-backed domain reasoning inside the Runtime.

These lock the parts a live demo depends on: one forced structured tool call,
multi-field extraction from free-form Traditional Chinese, closed output
validation, deterministic safety winning over the model, and honest degradation
when the model is unavailable.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from domain_reasoning import (  # noqa: E402
    EXTRACTION_TOOL_NAME,
    MAX_HISTORY_TURNS,
    SAFETY_HOLD_MESSAGE,
    DomainReasoner,
    TurnRequest,
)
from knowledge import KnowledgeBaseReader  # noqa: E402
from logical_agents import LOGICAL_AGENT_REGISTRY  # noqa: E402
from model_gate import BedrockRequestGate, build_guarded_runtime  # noqa: E402

UTILITY_AGENT = LOGICAL_AGENT_REGISTRY["utility_repair_agent"]
APPROVED_MODEL_ID = "amazon.nova-2-lite-v1:0"
SERVICE_DISTRICTS = ("內湖區", "信義區", "松山區")


def _test_gate() -> BedrockRequestGate:
    """Real gate semantics with the wait stubbed out to keep tests fast.

    Interval enforcement itself is covered by
    ``packages/api/tests/test_bedrock_safety.py``.
    """

    return BedrockRequestGate(minimum_interval_seconds=1.05, sleep=lambda _: None)


class FakeConverseClient:
    """Minimal Bedrock Converse stand-in that records the exact request."""

    def __init__(
        self,
        *,
        tool_input: dict[str, Any] | None = None,
        content: list[dict[str, Any]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._error = error
        if content is not None:
            self._content = content
        elif tool_input is not None:
            self._content = [
                {
                    "toolUse": {
                        "toolUseId": "tooluse_1",
                        "name": EXTRACTION_TOOL_NAME,
                        "input": tool_input,
                    }
                }
            ]
        else:
            self._content = [{"text": "沒有使用工具"}]

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return {
            "output": {"message": {"role": "assistant", "content": self._content}},
            "stopReason": "tool_use",
        }


class FakeRetrieveClient:
    def __init__(self, *, results: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._results = (
            results
            if results is not None
            else [
                {
                    "content": {"text": "漏水未處理可能造成鄰損，請先關閉止水閥。"},
                    "metadata": {
                        "service_type": "utility_repair",
                        "doc_kind": "notice",
                        "source_doc_id": "kb-utility-repair-003",
                    },
                    "location": {
                        "s3Location": {"uri": "s3://bucket/utility_repair/03-notice.md"}
                    },
                    "score": 0.64,
                }
            ]
        )

    def retrieve(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"retrievalResults": self._results}


def _reasoner(
    client: FakeConverseClient,
    *,
    model_id: str = APPROVED_MODEL_ID,
    retrieve_client: FakeRetrieveClient | None = None,
) -> DomainReasoner:
    knowledge = None
    if retrieve_client is not None:
        knowledge = KnowledgeBaseReader(
            client=retrieve_client,
            knowledge_base_id="KB12345678",
        )
    return DomainReasoner(
        model_client=build_guarded_runtime(client, gate=_test_gate()),
        model_id=model_id,
        knowledge=knowledge,
    )


def _request(
    message: str,
    *,
    turn_goal: str = "collect_missing_fields",
    workflow_stage: str = "collecting_details",
    known_fields: dict[str, Any] | None = None,
    missing_fields: tuple[str, ...] = ("district", "preferredTime"),
    history: tuple[dict[str, str], ...] = (),
) -> TurnRequest:
    return TurnRequest(
        message=message,
        session_id="demo-session",
        agent=UTILITY_AGENT,
        workflow_stage=workflow_stage,
        turn_goal=turn_goal,
        known_fields=known_fields or {},
        missing_fields=missing_fields,
        history=history,
        service_districts=SERVICE_DISTRICTS,
    )


class ModelRequestShapeTests(unittest.TestCase):
    def test_request_forces_the_single_extraction_tool(self) -> None:
        client = FakeConverseClient(tool_input={"assistantMessage": "好的"})
        _reasoner(client).reason(_request("水龍頭在滴水"))

        self.assertEqual(len(client.calls), 1)
        call = client.calls[0]
        self.assertEqual(call["modelId"], APPROVED_MODEL_ID)
        tool_config = call["toolConfig"]
        self.assertEqual(len(tool_config["tools"]), 1)
        self.assertEqual(
            tool_config["tools"][0]["toolSpec"]["name"], EXTRACTION_TOOL_NAME
        )
        self.assertEqual(
            tool_config["toolChoice"], {"tool": {"name": EXTRACTION_TOOL_NAME}}
        )
        self.assertTrue(call["system"][0]["text"])

    def test_prompt_carries_stage_known_and_missing_fields_and_scope(self) -> None:
        client = FakeConverseClient(tool_input={"assistantMessage": "好的"})
        _reasoner(client).reason(
            _request(
                "水龍頭在滴水",
                known_fields={"districtName": "內湖區", "riskScreened": True},
                missing_fields=("preferredTime",),
            )
        )

        call = client.calls[0]
        prompt = call["system"][0]["text"] + "\n".join(
            block["text"]
            for message in call["messages"]
            for block in message["content"]
            if "text" in block
        )
        self.assertIn("collecting_details", prompt)
        self.assertIn("preferredTime", prompt)
        self.assertIn("內湖區", prompt)
        self.assertIn("信義區", prompt)

    def test_history_is_replayed_as_multi_turn_context_and_capped(self) -> None:
        history = tuple(
            {"role": "resident" if index % 2 == 0 else "agent", "content": f"訊息{index}"}
            for index in range(MAX_HISTORY_TURNS + 6)
        )
        client = FakeConverseClient(tool_input={"assistantMessage": "好的"})
        _reasoner(client).reason(_request("最新一句", history=history))

        messages = client.calls[0]["messages"]
        self.assertLessEqual(len(messages), MAX_HISTORY_TURNS + 1)
        self.assertEqual(messages[-1]["role"], "user")
        self.assertIn("最新一句", messages[-1]["content"][0]["text"])
        self.assertEqual(
            [message["role"] for message in messages],
            [
                "user" if index % 2 == 0 else "assistant"
                for index in range(len(messages) - 1)
            ]
            + ["user"],
        )


class ModelExtractionTests(unittest.TestCase):
    def test_one_sentence_yields_every_field_the_resident_provided(self) -> None:
        client = FakeConverseClient(
            tool_input={
                "assistantMessage": "了解，我先確認安全狀況。",
                "extractedFields": {
                    "issueType": "leak",
                    "districtName": "信義區",
                    "preferredTime": "週六白天",
                    "urgency": "soon",
                },
                "riskLevel": "none",
                "riskSignals": [],
            }
        )

        result = _reasoner(client).reason(
            _request("廚房水槽下面一直在滴水，我住信義區，禮拜六白天都可以")
        )

        self.assertEqual(result.reasoning.mode, "model")
        self.assertEqual(result.reasoning.model_id, APPROVED_MODEL_ID)
        self.assertEqual(
            result.extracted_fields,
            {
                "issueType": "leak",
                "districtName": "信義區",
                "preferredTime": "週六白天",
                "urgency": "soon",
            },
        )
        self.assertEqual(result.assistant_message, "了解，我先確認安全狀況。")
        self.assertEqual(
            [(entry["actor"], entry["action"]) for entry in result.trace],
            [("utility_repair_agent", "model_invoke")],
        )
        self.assertEqual(result.trace[0]["target"], APPROVED_MODEL_ID)

    def test_area_outside_demo_scope_is_flagged_instead_of_silently_dropped(
        self,
    ) -> None:
        client = FakeConverseClient(
            tool_input={
                "assistantMessage": "板橋區目前不在示範服務範圍。",
                "extractedFields": {
                    "districtName": "板橋區",
                    "areaOutOfScope": True,
                },
                "riskLevel": "none",
            }
        )

        result = _reasoner(client).reason(_request("我住板橋"))

        self.assertEqual(result.extracted_fields["districtName"], "板橋區")
        self.assertTrue(result.extracted_fields["areaOutOfScope"])

    def test_keys_and_values_outside_the_contract_are_dropped(self) -> None:
        client = FakeConverseClient(
            tool_input={
                "assistantMessage": "好的",
                "extractedFields": {
                    "districtName": "內湖區",
                    "issueType": "not_a_real_issue_type",
                    "preferredTime": 12345,
                    "residentPhone": "0912345678",
                    "sqlToRun": "DROP TABLE service_requests",
                },
                "riskLevel": "none",
            }
        )

        result = _reasoner(client).reason(_request("內湖區"))

        self.assertEqual(result.extracted_fields, {"districtName": "內湖區"})

    def test_hazard_flags_must_be_complete_booleans_to_be_accepted(self) -> None:
        client = FakeConverseClient(
            tool_input={
                "assistantMessage": "好的",
                "extractedFields": {"hazardFlags": {"electricShockRisk": "yes"}},
                "riskLevel": "none",
            }
        )

        result = _reasoner(client).reason(_request("沒有異常"))

        self.assertNotIn("hazardFlags", result.extracted_fields)


class SafetyPrecedenceTests(unittest.TestCase):
    def test_runtime_rules_override_a_model_that_misses_high_risk(self) -> None:
        client = FakeConverseClient(
            tool_input={
                "assistantMessage": "沒問題，我幫你安排師傅明天過去看看。",
                "extractedFields": {"issueType": "electrical"},
                "riskLevel": "none",
            }
        )

        result = _reasoner(client).reason(_request("插座冒煙還有焦味"))

        self.assertEqual(result.risk.level, "high")
        self.assertEqual(result.risk.source, "deterministic")
        self.assertEqual(result.assistant_message, SAFETY_HOLD_MESSAGE)
        self.assertIn("smoke_or_burning_smell", result.risk.signals)

    def test_model_only_high_risk_still_holds_with_fixed_wording(self) -> None:
        client = FakeConverseClient(
            tool_input={
                "assistantMessage": "我覺得有點危險。",
                "extractedFields": {},
                "riskLevel": "high",
                "riskSignals": ["resident_reports_shock_sensation"],
            }
        )

        result = _reasoner(client).reason(_request("摸到洗衣機外殼會麻麻的"))

        self.assertEqual(result.risk.level, "high")
        self.assertEqual(result.risk.source, "model")
        self.assertEqual(result.assistant_message, SAFETY_HOLD_MESSAGE)

    def test_both_sources_agreeing_is_recorded_as_both(self) -> None:
        client = FakeConverseClient(
            tool_input={
                "assistantMessage": "危險",
                "extractedFields": {},
                "riskLevel": "high",
                "riskSignals": ["smoke"],
            }
        )

        result = _reasoner(client).reason(_request("電線裸線而且在冒煙"))

        self.assertEqual(result.risk.source, "both")

    def test_negated_risk_answer_is_not_treated_as_high_risk(self) -> None:
        client = FakeConverseClient(
            tool_input={
                "assistantMessage": "安全狀況了解。",
                "extractedFields": {"riskScreenAnswered": True},
                "riskLevel": "none",
            }
        )

        result = _reasoner(client).reason(_request("沒有漏電也沒有冒煙，水量不大"))

        self.assertEqual(result.risk.level, "none")
        self.assertEqual(result.assistant_message, "安全狀況了解。")


class HonestDegradationTests(unittest.TestCase):
    def test_missing_tool_use_block_degrades_to_runtime_rules(self) -> None:
        client = FakeConverseClient(content=[{"text": "我不想用工具"}])

        result = _reasoner(client).reason(_request("水管漏水"))

        self.assertEqual(result.reasoning.mode, "rule-fallback")
        self.assertIsNotNone(result.reasoning.degraded_reason)
        self.assertTrue(result.assistant_message)
        self.assertEqual(result.trace[0]["outcome"], "failed")

    def test_model_error_degrades_without_leaking_details(self) -> None:
        client = FakeConverseClient(
            error=RuntimeError("secret-arn:aws:bedrock:us-west-2:123456789012:foo")
        )

        result = _reasoner(client).reason(_request("水管漏水"))

        self.assertEqual(result.reasoning.mode, "rule-fallback")
        self.assertNotIn("123456789012", result.reasoning.degraded_reason or "")
        self.assertNotIn("arn:aws", result.reasoning.degraded_reason or "")

    def test_unapproved_model_never_reaches_the_client(self) -> None:
        client = FakeConverseClient(tool_input={"assistantMessage": "好的"})

        result = _reasoner(client, model_id="anthropic.claude-3-sonnet").reason(
            _request("水管漏水")
        )

        self.assertEqual(client.calls, [])
        self.assertEqual(result.reasoning.mode, "rule-fallback")

    def test_no_model_client_reports_rule_fallback(self) -> None:
        reasoner = DomainReasoner(model_client=None, model_id=None, knowledge=None)

        result = reasoner.reason(_request("水管漏水"))

        self.assertEqual(result.reasoning.mode, "rule-fallback")
        self.assertFalse(result.reasoning.knowledge_base_queried)
        self.assertTrue(result.assistant_message)

    def test_degraded_turn_still_applies_deterministic_safety(self) -> None:
        reasoner = DomainReasoner(model_client=None, model_id=None, knowledge=None)

        result = reasoner.reason(_request("插座冒煙"))

        self.assertEqual(result.risk.level, "high")
        self.assertEqual(result.assistant_message, SAFETY_HOLD_MESSAGE)


class KnowledgeIntegrationTests(unittest.TestCase):
    def test_question_turns_attach_domain_filtered_references(self) -> None:
        retrieve_client = FakeRetrieveClient()
        client = FakeConverseClient(
            tool_input={
                "assistantMessage": "漏水沒處理可能造成鄰損。",
                "extractedFields": {},
                "riskLevel": "none",
            }
        )

        result = _reasoner(client, retrieve_client=retrieve_client).reason(
            _request("漏水不處理會怎麼樣嗎？")
        )

        self.assertTrue(result.reasoning.knowledge_base_queried)
        self.assertEqual(len(result.knowledge), 1)
        self.assertEqual(result.knowledge[0].service_type, "utility_repair")
        vector_search = retrieve_client.calls[0]["retrievalConfiguration"][
            "vectorSearchConfiguration"
        ]
        self.assertEqual(
            vector_search["filter"],
            {"equals": {"key": "service_type", "value": "utility_repair"}},
        )
        self.assertIn(
            ("utility_repair_agent", "knowledge_retrieve"),
            [(entry["actor"], entry["action"]) for entry in result.trace],
        )

    def test_knowledge_text_never_becomes_a_field_value(self) -> None:
        retrieve_client = FakeRetrieveClient()
        client = FakeConverseClient(
            tool_input={
                "assistantMessage": "好的",
                "extractedFields": {},
                "riskLevel": "none",
            }
        )

        result = _reasoner(client, retrieve_client=retrieve_client).reason(
            _request("漏水要注意什麼嗎？")
        )

        self.assertEqual(result.extracted_fields, {})

    def test_plain_field_answer_does_not_spend_a_retrieval_call(self) -> None:
        retrieve_client = FakeRetrieveClient()
        client = FakeConverseClient(
            tool_input={
                "assistantMessage": "好的",
                "extractedFields": {"districtName": "內湖區"},
                "riskLevel": "none",
            }
        )

        result = _reasoner(client, retrieve_client=retrieve_client).reason(
            _request("內湖區")
        )

        self.assertEqual(retrieve_client.calls, [])
        self.assertFalse(result.reasoning.knowledge_base_queried)

    def test_high_risk_turn_retrieves_safety_guidance(self) -> None:
        retrieve_client = FakeRetrieveClient()
        client = FakeConverseClient(
            tool_input={
                "assistantMessage": "危險",
                "extractedFields": {},
                "riskLevel": "high",
            }
        )

        result = _reasoner(client, retrieve_client=retrieve_client).reason(
            _request("插座冒煙")
        )

        self.assertEqual(len(retrieve_client.calls), 1)
        self.assertEqual(result.assistant_message, SAFETY_HOLD_MESSAGE)
        self.assertTrue(result.reasoning.knowledge_base_queried)


if __name__ == "__main__":
    unittest.main()
