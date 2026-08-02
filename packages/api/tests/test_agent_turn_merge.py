"""Contract tests for how Flask consumes a model-backed agent turn.

The application service stays the authority: it validates every extracted field
against its own reference data, keeps the deterministic safety check as the floor,
and keeps ownership of any wording that states a fact (document version, matched
provider, safety instructions).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from walking_skeleton.orchestration import (  # noqa: E402
    AgentTurn,
    AgentTurnRequest,
    Delegation,
    DeterministicDemoOrchestrator,
)
from walking_skeleton.service import WalkingSkeletonService  # noqa: E402

RESIDENT = "resident-demo-001"
MODEL_ID = "amazon.nova-2-lite-v1:0"


def _model_turn(
    *,
    assistant_message: str = "好的，我記下來了。",
    extracted: dict[str, Any] | None = None,
    risk_level: str = "none",
    risk_source: str = "none",
    knowledge: tuple[dict[str, Any], ...] = (),
) -> AgentTurn:
    return AgentTurn(
        service_type="utility_repair",
        target_agent="utility_repair_agent",
        mode="agentcore-runtime",
        assistant_message=assistant_message,
        extracted_fields=extracted or {},
        risk_level=risk_level,
        risk_source=risk_source,
        knowledge=knowledge,
        reasoning_mode="model",
        model_id=MODEL_ID,
        knowledge_base_queried=bool(knowledge),
    )


class ScriptedOrchestrator:
    """Stand-in for the AgentCore adapter that records what Flask asked for."""

    mode = "agentcore-runtime"

    def __init__(self, turns: list[AgentTurn]) -> None:
        self.requests: list[AgentTurnRequest] = []
        self._turns = list(turns)

    def delegate(self, message: str) -> Delegation:
        return Delegation("utility_repair", "utility_repair_agent", self.mode)

    def turn(self, request: AgentTurnRequest) -> AgentTurn:
        self.requests.append(request)
        if self._turns:
            return self._turns.pop(0)
        return _model_turn()


def _service(turns: list[AgentTurn]) -> tuple[WalkingSkeletonService, ScriptedOrchestrator]:
    orchestrator = ScriptedOrchestrator(turns)
    return WalkingSkeletonService(orchestrator=orchestrator), orchestrator


def _start(service: WalkingSkeletonService, message: str) -> tuple[str, dict[str, Any]]:
    conversation_id = service.create_conversation(RESIDENT)["conversationId"]
    result = service.add_resident_message(conversation_id, RESIDENT, message)
    return conversation_id, result


class MultiTurnUnderstandingTests(unittest.TestCase):
    def test_one_sentence_plus_a_safety_answer_reaches_the_brief(self) -> None:
        service, _ = _service(
            [
                _model_turn(
                    assistant_message="先確認安全：現場有沒有冒煙、漏電或大量積水？",
                    extracted={
                        "issueType": "leak",
                        "districtName": "內湖區",
                        "preferredTime": "禮拜六白天",
                    },
                ),
                _model_turn(
                    assistant_message="安全狀況了解。",
                    extracted={"riskScreenAnswered": True},
                ),
            ]
        )

        conversation_id, first = _start(
            service, "廚房水槽下面一直在滴水，我住內湖區，禮拜六白天都可以"
        )

        self.assertEqual(first["progress"]["stage"], "collecting_details")
        self.assertEqual(first["serviceRequest"]["districtName"], "內湖區")
        self.assertEqual(first["serviceRequest"]["preferredTime"], "禮拜六白天")

        second = service.add_resident_message(
            conversation_id, RESIDENT, "沒有漏電也沒有冒煙，水量不大"
        )

        self.assertEqual(second["progress"]["stage"], "awaiting_resident_confirmation")
        self.assertIn("內湖區", second["artifact"]["summary"])
        self.assertIn("禮拜六白天", second["artifact"]["summary"])

    def test_turn_request_carries_stage_known_and_missing_fields(self) -> None:
        service, orchestrator = _service(
            [
                _model_turn(extracted={"districtName": "內湖區"}),
                _model_turn(),
            ]
        )

        conversation_id, _ = _start(service, "浴室水管漏水")
        service.add_resident_message(conversation_id, RESIDENT, "沒有漏電")

        first, second = orchestrator.requests
        self.assertEqual(first.turn_goal, "route_new_request")
        self.assertIsNone(first.active_agent)
        self.assertIn("內湖區", first.service_districts)

        self.assertEqual(second.active_agent, "utility_repair_agent")
        self.assertEqual(second.workflow_stage, "collecting_details")
        self.assertEqual(second.turn_goal, "screen_safety")
        self.assertEqual(second.missing_fields[0], "riskScreening")
        self.assertIn("preferredTime", second.missing_fields)
        self.assertEqual(second.known_fields["districtName"], "內湖區")
        self.assertIn(
            "浴室水管漏水",
            [entry["content"] for entry in second.history],
        )
        self.assertEqual(
            {entry["role"] for entry in second.history} - {"resident", "agent"},
            set(),
        )

    def test_reasoning_and_knowledge_are_surfaced_for_the_ui(self) -> None:
        service, _ = _service(
            [
                _model_turn(
                    knowledge=(
                        {
                            "serviceType": "utility_repair",
                            "docKind": "sop",
                            "sourceDocId": "kb-utility-repair-002",
                            "excerpt": "先關閉止水閥並記錄漏水位置。",
                        },
                    )
                )
            ]
        )

        _, first = _start(service, "水管漏水，到之前我需要先做什麼嗎？")

        self.assertEqual(first["reasoning"]["mode"], "model")
        self.assertEqual(first["reasoning"]["modelId"], MODEL_ID)
        self.assertTrue(first["reasoning"]["knowledgeBaseQueried"])
        self.assertEqual(len(first["knowledge"]), 1)
        self.assertEqual(first["knowledge"][0]["docKind"], "sop")


class ValidatedMergeTests(unittest.TestCase):
    def test_area_outside_the_demo_scope_is_answered_honestly(self) -> None:
        service, _ = _service(
            [
                _model_turn(
                    assistant_message="板橋區目前不在服務範圍。",
                    extracted={"districtName": "板橋區", "areaOutOfScope": True},
                )
            ]
        )

        _, first = _start(service, "浴室水管漏水，我住板橋")

        self.assertIsNone(first["serviceRequest"]["districtName"])
        message = first["assistantMessage"]["content"]
        self.assertIn("服務範圍", message)
        self.assertIn("內湖區", message)

    def test_unknown_district_is_never_written_to_state(self) -> None:
        service, _ = _service(
            [_model_turn(extracted={"districtName": "火星區"})]
        )

        _, first = _start(service, "浴室水管漏水")

        self.assertIsNone(first["serviceRequest"]["districtName"])

    def test_keys_and_values_outside_the_contract_are_ignored(self) -> None:
        service, _ = _service(
            [
                _model_turn(
                    extracted={
                        "issueType": "definitely_not_valid",
                        "preferredTime": "",
                        "urgency": "whenever",
                        "residentPhone": "0912345678",
                        "safetyHold": False,
                        "candidateProviderIds": ["attacker"],
                    }
                )
            ]
        )

        _, first = _start(service, "浴室水管漏水")

        request = service.store.service_requests[first["serviceRequest"]["serviceRequestId"]]
        self.assertEqual(request["issueType"], "leak")
        self.assertIsNone(request["preferredTime"])
        self.assertEqual(request["urgency"], "routine")
        self.assertNotIn("residentPhone", request)
        self.assertEqual(request["candidateProviderIds"], [])

    def test_model_confirmation_only_counts_in_the_confirmation_stage(self) -> None:
        service, _ = _service(
            [
                _model_turn(
                    extracted={
                        "districtName": "內湖區",
                        "preferredTime": "明天下午兩點到五點",
                        "confirmsBrief": True,
                    }
                ),
                _model_turn(extracted={"riskScreenAnswered": True}),
                _model_turn(extracted={"confirmsBrief": True}),
            ]
        )

        conversation_id, first = _start(service, "浴室水管漏水")
        self.assertEqual(first["progress"]["stage"], "collecting_details")

        second = service.add_resident_message(conversation_id, RESIDENT, "沒有漏電")
        self.assertEqual(second["progress"]["stage"], "awaiting_resident_confirmation")

        third = service.add_resident_message(conversation_id, RESIDENT, "好，就這樣送出吧")
        self.assertEqual(third["progress"]["stage"], "waiting_provider_response")
        self.assertIsNotNone(third["providerTask"])


class SafetyPrecedenceTests(unittest.TestCase):
    def test_model_cannot_clear_a_deterministic_hazard(self) -> None:
        service, _ = _service(
            [
                _model_turn(
                    assistant_message="我幫你安排師傅明天過去看看。",
                    extracted={
                        "riskScreenAnswered": True,
                        "hazardFlags": {
                            "electricShockRisk": False,
                            "exposedWires": False,
                            "smokeOrBurningSmell": False,
                            "activeFlooding": False,
                        },
                    },
                )
            ]
        )

        _, first = _start(service, "插座冒煙還有焦味")

        request = service.store.service_requests[first["serviceRequest"]["serviceRequestId"]]
        self.assertTrue(request["safetyHold"])
        self.assertTrue(request["hazardFlags"]["smokeOrBurningSmell"])
        self.assertFalse(request["riskScreened"])
        self.assertEqual(first["progress"]["stage"], "safety_hold")
        self.assertNotIn("安排師傅", first["assistantMessage"]["content"])

    def test_model_only_high_risk_still_holds_the_case(self) -> None:
        service, _ = _service(
            [
                _model_turn(
                    assistant_message="這個聽起來有點危險。",
                    risk_level="high",
                    risk_source="model",
                )
            ]
        )

        _, first = _start(service, "摸到熱水器外殼會麻麻的")

        request = service.store.service_requests[first["serviceRequest"]["serviceRequestId"]]
        self.assertTrue(request["safetyHold"])
        self.assertEqual(first["progress"]["stage"], "safety_hold")
        self.assertIn("119", first["assistantMessage"]["content"])

    def test_safety_hold_turns_do_not_consult_the_model(self) -> None:
        service, orchestrator = _service(
            [_model_turn(risk_level="high", risk_source="model")]
        )

        conversation_id, _ = _start(service, "插座冒煙")
        service.add_resident_message(conversation_id, RESIDENT, "現在還好嗎")

        self.assertEqual(len(orchestrator.requests), 1)


class WordingOwnershipTests(unittest.TestCase):
    def test_model_wording_is_used_when_asking_for_a_missing_field(self) -> None:
        service, _ = _service(
            [
                _model_turn(
                    assistant_message="先確認安全：現場有沒有冒煙、漏電或大量積水？"
                )
            ]
        )

        _, first = _start(service, "浴室水管漏水")

        self.assertEqual(
            first["assistantMessage"]["content"],
            "先確認安全：現場有沒有冒煙、漏電或大量積水？",
        )

    def test_flask_owns_the_wording_when_it_states_a_fact(self) -> None:
        service, _ = _service(
            [
                _model_turn(
                    extracted={
                        "districtName": "內湖區",
                        "preferredTime": "明天下午兩點到五點",
                    }
                ),
                _model_turn(
                    assistant_message="都問完了，我直接幫你派工囉！",
                    extracted={"riskScreenAnswered": True},
                ),
            ]
        )

        conversation_id, _ = _start(service, "浴室水管漏水")
        second = service.add_resident_message(conversation_id, RESIDENT, "沒有漏電")

        message = second["assistantMessage"]["content"]
        self.assertIn("第 1 版", message)
        self.assertIn("確認送出", message)
        self.assertNotIn("直接幫你派工", message)


class DeterministicModeTests(unittest.TestCase):
    def test_offline_mode_never_claims_a_model_ran(self) -> None:
        service = WalkingSkeletonService(orchestrator=DeterministicDemoOrchestrator())

        conversation_id, first = _start(service, "浴室水管漏水")

        self.assertEqual(first["orchestrationMode"], "deterministic-demo")
        self.assertEqual(first["reasoning"]["mode"], "rule-fallback")
        self.assertIsNone(first["reasoning"]["modelId"])
        self.assertEqual(first["knowledge"], [])

        second = service.add_resident_message(
            conversation_id, RESIDENT, "沒有漏電也沒有冒煙"
        )
        third = service.add_resident_message(conversation_id, RESIDENT, "內湖區")
        fourth = service.add_resident_message(
            conversation_id, RESIDENT, "明天下午兩點到五點"
        )

        self.assertEqual(second["progress"]["stage"], "collecting_details")
        self.assertEqual(third["progress"]["stage"], "collecting_details")
        self.assertEqual(fourth["progress"]["stage"], "awaiting_resident_confirmation")


if __name__ == "__main__":
    unittest.main()


class KnowledgeBoundaryProjectionTests(unittest.TestCase):
    """Flask must surface the boundary, not quietly drop it.

    A resident asking for a price needs to see that the platform declined to
    answer from static knowledge. Hiding that is how a stale price becomes an
    answer nobody questions.
    """

    def test_live_value_topics_and_suppressed_records_reach_the_client(self) -> None:
        service, _ = _service(
            [
                AgentTurn(
                    service_type="utility_repair",
                    target_agent="utility_repair_agent",
                    mode="agentcore-runtime",
                    assistant_message="這需要師傅到場勘查後才報價，我先幫你把需求整理好。",
                    reasoning_mode="model",
                    model_id=MODEL_ID,
                    knowledge_base_queried=True,
                    live_value_topics=("price",),
                    suppressed_knowledge=(
                        {
                            "sourceDocId": "kb-utility-repair-001",
                            "docKind": "terms",
                            "reason": "static_only_not_authoritative_for_price",
                        },
                    ),
                )
            ]
        )

        _, first = _start(service, "水管漏水，這次維修大概多少錢")

        reasoning = first["reasoning"]
        self.assertEqual(reasoning["liveValueTopics"], ["price"])
        self.assertEqual(len(reasoning["suppressedKnowledge"]), 1)
        record = reasoning["suppressedKnowledge"][0]
        self.assertEqual(record["docKind"], "terms")
        self.assertEqual(
            record["reason"], "static_only_not_authoritative_for_price"
        )
        self.assertNotIn("excerpt", record)
        self.assertEqual(first["knowledge"], [])

    def test_turns_without_a_boundary_hit_report_empty_lists(self) -> None:
        service, _ = _service([_model_turn()])

        _, first = _start(service, "浴室水管漏水")

        self.assertEqual(first["reasoning"]["liveValueTopics"], [])
        self.assertEqual(first["reasoning"]["suppressedKnowledge"], [])


class ReplyWordingOwnershipTest(unittest.TestCase):
    """措辭要交給 Agent，前提是模型真的跑了。

    Runtime 在 rule-fallback 時回的是它自己的罐頭句，那句話不知道 Flask 的
    stage 走到哪裡，逐輪重複同一個問題。住戶看到的就是「一直在問同一件事」，
    即使狀態機其實每輪都在前進。
    """

    def setUp(self) -> None:
        self.service = WalkingSkeletonService()

    def _turn(self, *, reasoning_mode: str, assistant_message: str) -> AgentTurn:
        return AgentTurn(
            service_type="utility_repair",
            target_agent="utility_repair_agent",
            mode="agentcore-runtime",
            assistant_message=assistant_message,
            reasoning_mode=reasoning_mode,
        )

    def test_rule_fallback_wording_never_replaces_the_flow_question(self) -> None:
        turn = self._turn(
            reasoning_mode="rule-fallback",
            assistant_message="先確認安全：現場是否有漏電、裸線、冒煙焦味？",
        )

        reply = self.service.choose_reply(
            "請告訴我服務地區（例如台北市內湖區）。", turn, model_may_rephrase=True
        )

        self.assertEqual(reply, "請告訴我服務地區（例如台北市內湖區）。")

    def test_model_backed_wording_may_still_replace_the_flow_question(self) -> None:
        turn = self._turn(
            reasoning_mode="model",
            assistant_message="了解，那你家在哪一個行政區呢？",
        )

        reply = self.service.choose_reply(
            "請告訴我服務地區（例如台北市內湖區）。", turn, model_may_rephrase=True
        )

        self.assertEqual(reply, "了解，那你家在哪一個行政區呢？")
