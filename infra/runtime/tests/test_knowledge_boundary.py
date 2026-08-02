"""Contract tests for the `static_only` knowledge boundary.

The `service_type` filter blocks a horizontal leak between domains, which is
obvious when it fails. This boundary blocks the vertical one inside a domain:
answering a live question (price, stock, bookable slots, schedule, case status)
from a static document. That failure looks correct, which is why it needs its own
enforcement rather than an instruction in a prompt.

A policy question is not a live question. "取消要收多少錢" asks about the
cancellation policy and must still be answerable from the terms document.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from knowledge import (  # noqa: E402
    DEFAULT_NEVER_AUTHORITATIVE_FIELDS,
    OUTCOME_OK,
    OUTCOME_SUPPRESSED,
    KnowledgeBaseReader,
    detect_live_value_topics,
)


def _chunk(
    *,
    text: str = "每次派工的基本工資為 800 元，超時另計。",
    doc_kind: str = "terms",
    scope: str | None = "static_only",
    never_authoritative_for: Any = None,
    source_doc_id: str = "kb-utility-repair-001",
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "service_type": "utility_repair",
        "doc_kind": doc_kind,
        "source_doc_id": source_doc_id,
    }
    if scope is not None:
        metadata["authoritative_scope"] = scope
    if never_authoritative_for is not None:
        metadata["never_authoritative_for"] = never_authoritative_for
    return {
        "content": {"text": text},
        "metadata": metadata,
        "location": {"s3Location": {"uri": "s3://bucket/utility_repair/04-terms.md"}},
        "score": 0.66,
    }


class FakeRetrieveClient:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._results = results

    def retrieve(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"retrievalResults": self._results}


def _reader(results: list[dict[str, Any]]) -> tuple[KnowledgeBaseReader, FakeRetrieveClient]:
    client = FakeRetrieveClient(results)
    return (
        KnowledgeBaseReader(client=client, knowledge_base_id="KB12345678"),
        client,
    )


class LiveValueTopicDetectionTests(unittest.TestCase):
    def test_asking_for_a_concrete_amount_is_a_live_value_question(self) -> None:
        self.assertEqual(detect_live_value_topics("這次維修大概多少錢？"), ("price",))

    def test_asking_about_policy_is_not_a_live_value_question(self) -> None:
        for message in (
            "取消要收多少錢？",
            "保固範圍怎麼計費？",
            "退款政策是什麼？",
        ):
            with self.subTest(message=message):
                self.assertEqual(detect_live_value_topics(message), ())

    def test_static_guidance_questions_are_not_live_value_questions(self) -> None:
        for message in ("漏水要注意什麼嗎？", "保固多久？", "師傅到之前我要先做什麼？"):
            with self.subTest(message=message):
                self.assertEqual(detect_live_value_topics(message), ())

    def test_availability_schedule_inventory_and_status_are_detected(self) -> None:
        self.assertIn("availability", detect_live_value_topics("這週六約得到嗎？"))
        self.assertIn("schedule", detect_live_value_topics("哪位師傅有空？"))
        self.assertIn("inventory", detect_live_value_topics("那個零件還有貨嗎？"))
        self.assertIn("case_status", detect_live_value_topics("我的案子處理到哪了？"))


class StaticOnlySuppressionTests(unittest.TestCase):
    def test_price_question_never_gets_a_static_only_answer(self) -> None:
        reader, client = _reader([_chunk()])

        result = reader.search(service_type="utility_repair", query="這次維修多少錢？")

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(result.references, ())
        self.assertEqual(result.outcome, OUTCOME_SUPPRESSED)
        self.assertEqual(result.live_value_topics, ("price",))

    def test_suppression_record_identifies_the_chunk_without_repeating_it(self) -> None:
        reader, _ = _reader([_chunk()])

        result = reader.search(service_type="utility_repair", query="報價是多少？")

        self.assertEqual(len(result.suppressed), 1)
        record = result.suppressed[0]
        self.assertEqual(record.source_doc_id, "kb-utility-repair-001")
        self.assertEqual(record.doc_kind, "terms")
        self.assertEqual(record.reason, "static_only_not_authoritative_for_price")
        payload = record.to_payload()
        self.assertEqual(
            set(payload), {"sourceDocId", "docKind", "reason"}
        )
        self.assertNotIn("800", str(payload))

    def test_policy_question_still_receives_the_terms_document(self) -> None:
        reader, _ = _reader([_chunk(text="取消政策：到場前兩小時免費取消。")])

        result = reader.search(
            service_type="utility_repair", query="取消要收多少錢？"
        )

        self.assertEqual(len(result.references), 1)
        self.assertEqual(result.outcome, OUTCOME_OK)
        self.assertEqual(result.suppressed, ())
        self.assertEqual(result.live_value_topics, ())

    def test_chunk_declaring_a_narrower_boundary_is_honoured(self) -> None:
        reader, _ = _reader(
            [_chunk(doc_kind="faq", never_authoritative_for=["case_status"])]
        )

        result = reader.search(service_type="utility_repair", query="報價是多少？")

        self.assertEqual(len(result.references), 1)
        self.assertEqual(result.suppressed, ())
        self.assertEqual(
            result.references[0].never_authoritative_for, ("case_status",)
        )

    def test_comma_separated_declaration_is_accepted(self) -> None:
        reader, _ = _reader(
            [_chunk(never_authoritative_for="price, availability")]
        )

        result = reader.search(service_type="utility_repair", query="報價是多少？")

        self.assertEqual(result.references, ())
        self.assertEqual(result.outcome, OUTCOME_SUPPRESSED)

    def test_chunk_without_a_declaration_falls_back_to_the_platform_default(
        self,
    ) -> None:
        self.assertIn("price", DEFAULT_NEVER_AUTHORITATIVE_FIELDS)
        self.assertIn("case_status", DEFAULT_NEVER_AUTHORITATIVE_FIELDS)
        reader, _ = _reader([_chunk(never_authoritative_for=None)])

        result = reader.search(
            service_type="utility_repair", query="我的案子處理到哪了？"
        )

        self.assertEqual(result.references, ())
        self.assertEqual(
            result.suppressed[0].reason,
            "static_only_not_authoritative_for_case_status",
        )

    def test_a_chunk_that_is_not_static_only_is_left_alone(self) -> None:
        reader, _ = _reader([_chunk(scope="live_mirror")])

        result = reader.search(service_type="utility_repair", query="報價是多少？")

        self.assertEqual(len(result.references), 1)
        self.assertEqual(result.outcome, OUTCOME_OK)

    def test_mixed_results_keep_only_the_permitted_chunk(self) -> None:
        reader, _ = _reader(
            [
                _chunk(source_doc_id="kb-utility-repair-001"),
                _chunk(
                    doc_kind="sop",
                    never_authoritative_for=["case_status"],
                    source_doc_id="kb-utility-repair-002",
                    text="到場後先勘查再報價。",
                ),
            ]
        )

        result = reader.search(service_type="utility_repair", query="報價是多少？")

        self.assertEqual(len(result.references), 1)
        self.assertEqual(result.references[0].doc_kind, "sop")
        self.assertEqual(len(result.suppressed), 1)
        self.assertEqual(result.outcome, OUTCOME_OK)

    def test_reference_carries_its_authoritative_scope(self) -> None:
        reader, _ = _reader([_chunk(doc_kind="sop", text="派工流程說明。")])

        result = reader.search(
            service_type="utility_repair", query="派工流程是怎麼走的？"
        )

        self.assertEqual(result.references[0].authoritative_scope, "static_only")
        self.assertEqual(
            result.references[0].to_payload()["authoritativeScope"], "static_only"
        )


if __name__ == "__main__":
    unittest.main()


class ReasoningBoundaryTests(unittest.TestCase):
    """The boundary has to reach the model turn, not just the reader."""

    def setUp(self) -> None:
        from domain_reasoning import (
            LIVE_VALUE_DIRECTIVE_PREFIX,
            DomainReasoner,
            TurnRequest,
        )
        from logical_agents import LOGICAL_AGENT_REGISTRY
        from model_gate import BedrockRequestGate, build_guarded_runtime

        self.directive_prefix = LIVE_VALUE_DIRECTIVE_PREFIX
        self._DomainReasoner = DomainReasoner
        self._TurnRequest = TurnRequest
        self._agent = LOGICAL_AGENT_REGISTRY["utility_repair_agent"]
        self._build_guarded_runtime = build_guarded_runtime
        self._gate = lambda: BedrockRequestGate(
            minimum_interval_seconds=1.05, sleep=lambda _: None
        )

    def _reason(self, message: str, results: list[dict[str, Any]]):
        from domain_reasoning import EXTRACTION_TOOL_NAME

        class FakeConverseClient:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            def converse(self, **kwargs: Any) -> dict[str, Any]:
                self.calls.append(kwargs)
                return {
                    "output": {
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "toolUse": {
                                        "toolUseId": "tooluse_1",
                                        "name": EXTRACTION_TOOL_NAME,
                                        "input": {
                                            "assistantMessage": "我先幫你確認需求。",
                                            "extractedFields": {},
                                            "riskLevel": "none",
                                        },
                                    }
                                }
                            ],
                        }
                    },
                    "stopReason": "tool_use",
                }

        model_client = FakeConverseClient()
        retrieve_client = FakeRetrieveClient(results)
        reasoner = self._DomainReasoner(
            model_client=self._build_guarded_runtime(
                model_client, gate=self._gate()
            ),
            model_id="amazon.nova-2-lite-v1:0",
            knowledge=KnowledgeBaseReader(
                client=retrieve_client,
                knowledge_base_id="KB12345678",
            ),
        )
        result = reasoner.reason(
            self._TurnRequest(
                message=message,
                agent=self._agent,
                workflow_stage="collecting_details",
                turn_goal="collect_missing_fields",
                service_districts=("內湖區",),
            )
        )
        return result, model_client, retrieve_client

    def test_live_value_question_is_retrieved_so_the_boundary_is_recorded(
        self,
    ) -> None:
        result, _, retrieve_client = self._reason(
            "這次維修大概多少錢", [_chunk()]
        )

        self.assertEqual(len(retrieve_client.calls), 1)
        self.assertTrue(result.reasoning.knowledge_base_queried)
        self.assertEqual(result.knowledge, ())
        self.assertEqual(len(result.reasoning.suppressed_knowledge), 1)
        self.assertEqual(
            result.reasoning.suppressed_knowledge[0].reason,
            "static_only_not_authoritative_for_price",
        )
        self.assertEqual(result.reasoning.live_value_topics, ("price",))

    def test_prompt_names_the_topics_that_need_live_data(self) -> None:
        _, model_client, _ = self._reason("這次維修大概多少錢", [_chunk()])

        prompt = model_client.calls[0]["system"][0]["text"]
        self.assertIn(self.directive_prefix, prompt)
        self.assertIn("price", prompt)
        self.assertNotIn("800", prompt)

    def test_suppressed_excerpt_never_reaches_the_prompt(self) -> None:
        _, model_client, _ = self._reason(
            "報價是多少",
            [_chunk(text="固定收費 1250 元，含到場費。")],
        )

        prompt = model_client.calls[0]["system"][0]["text"]
        self.assertNotIn("1250", prompt)
        self.assertNotIn("含到場費", prompt)

    def test_trace_reports_the_suppressed_outcome(self) -> None:
        result, _, _ = self._reason("報價是多少", [_chunk()])

        retrieval_entries = [
            entry for entry in result.trace if entry["action"] == "knowledge_retrieve"
        ]
        self.assertEqual(len(retrieval_entries), 1)
        self.assertEqual(retrieval_entries[0]["outcome"], OUTCOME_SUPPRESSED)

    def test_policy_question_keeps_the_reference_and_reports_nothing_withheld(
        self,
    ) -> None:
        result, model_client, _ = self._reason(
            "取消要收多少錢",
            [_chunk(text="取消政策：到場前兩小時免費取消。")],
        )

        self.assertEqual(len(result.knowledge), 1)
        self.assertEqual(result.reasoning.suppressed_knowledge, ())
        self.assertEqual(result.reasoning.live_value_topics, ())
        prompt = model_client.calls[0]["system"][0]["text"]
        self.assertNotIn(self.directive_prefix, prompt)
        self.assertIn("免費取消", prompt)
