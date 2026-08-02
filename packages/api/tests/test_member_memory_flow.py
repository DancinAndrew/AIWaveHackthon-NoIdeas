"""Contract tests for member memory on the walking skeleton execution path.

These are the behaviours that make the personalisation visible: a returning
member is not asked for an address the platform already has, a blocked vendor is
never dispatched, price sensitivity reorders the candidates, and one observation
merges into the preference row instead of replacing it.
"""

from __future__ import annotations

import os
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from walking_skeleton.member_memory import (  # noqa: E402
    InMemoryMemberMemoryStore,
    MemberAddress,
    MemberAppliance,
    MemberMemory,
    MemberPreference,
)
from walking_skeleton.orchestration import (  # noqa: E402
    AgentTurn,
    AgentTurnRequest,
    Delegation,
)
from walking_skeleton.service import WalkingSkeletonService  # noqa: E402

RESIDENT = "resident-demo-001"
FAST_DEAR_PROVIDER = "31324fe0-9899-5382-8211-d0122c20bda0"  # 京鑫, SLA 1h, 1800
SLOW_CHEAP_PROVIDER = "29722c58-1d40-5dd9-9bf3-4cfcdfefb60a"  # 新旺, SLA 4h, 1200

HOME = MemberAddress(
    county_code="01",
    district_code="010",
    district_name="內湖區",
    label="住家",
    is_default=True,
)
WATER_HEATER = MemberAppliance(
    appliance_id="A1",
    kind="WATER_HEATER",
    brand="櫻花",
    variant="數位恆溫",
    installed_year=2019,
    location="陽台",
)


class ScriptedOrchestrator:
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
        return _turn()


def _turn(
    *,
    assistant_message: str = "好的。",
    extracted: dict[str, Any] | None = None,
) -> AgentTurn:
    return AgentTurn(
        service_type="utility_repair",
        target_agent="utility_repair_agent",
        mode="agentcore-runtime",
        assistant_message=assistant_message,
        extracted_fields=extracted or {},
        reasoning_mode="model",
        model_id="amazon.nova-2-lite-v1:0",
    )


def _memory(
    *,
    addresses: tuple[MemberAddress, ...] = (HOME,),
    appliances: tuple[MemberAppliance, ...] = (WATER_HEATER,),
    preference: MemberPreference | None = None,
) -> MemberMemory:
    return MemberMemory(
        addresses=addresses,
        appliances=appliances,
        preference=preference or MemberPreference(),
    )


def _service(
    memory: MemberMemory,
    turns: list[AgentTurn],
) -> tuple[WalkingSkeletonService, ScriptedOrchestrator, InMemoryMemberMemoryStore]:
    store = InMemoryMemberMemoryStore({RESIDENT: memory})
    orchestrator = ScriptedOrchestrator(turns)
    service = WalkingSkeletonService(
        orchestrator=orchestrator,
        member_memory=store,
    )
    return service, orchestrator, store


def _reach_confirmation(
    service: WalkingSkeletonService,
    *,
    say_district: bool = False,
) -> str:
    conversation_id = service.create_conversation(RESIDENT)["conversationId"]
    service.add_resident_message(conversation_id, RESIDENT, "熱水器沒有熱水")
    service.add_resident_message(conversation_id, RESIDENT, "沒有漏電也沒有冒煙")
    if say_district:
        service.add_resident_message(conversation_id, RESIDENT, "台北市內湖區")
    service.add_resident_message(conversation_id, RESIDENT, "明天下午兩點到五點")
    return conversation_id


class RememberedFieldsTests(unittest.TestCase):
    def test_remembered_district_is_not_asked_for_again(self) -> None:
        service, _, _ = _service(_memory(), [])

        conversation_id = service.create_conversation(RESIDENT)["conversationId"]
        first = service.add_resident_message(
            conversation_id, RESIDENT, "熱水器沒有熱水"
        )
        second = service.add_resident_message(
            conversation_id, RESIDENT, "沒有漏電也沒有冒煙"
        )

        self.assertEqual(first["serviceRequest"]["districtName"], "內湖區")
        # The safety answer is the last missing field, so the next question is
        # the time window rather than the address.
        self.assertIn("時段", second["assistantMessage"]["content"])
        self.assertNotIn("服務地區", second["assistantMessage"]["content"])

    def test_remembered_values_reach_the_agent_as_known_fields(self) -> None:
        service, orchestrator, _ = _service(_memory(), [])

        conversation_id = service.create_conversation(RESIDENT)["conversationId"]
        service.add_resident_message(conversation_id, RESIDENT, "熱水器沒有熱水")

        known = orchestrator.requests[0].known_fields
        self.assertEqual(known["rememberedDistrictName"], "內湖區")
        self.assertEqual(known["rememberedAppliance"], "陽台2019 年櫻花數位恆溫熱水器")

    def test_without_memory_the_address_is_still_requested(self) -> None:
        service = WalkingSkeletonService(orchestrator=ScriptedOrchestrator([]))

        conversation_id = service.create_conversation(RESIDENT)["conversationId"]
        service.add_resident_message(conversation_id, RESIDENT, "熱水器沒有熱水")
        second = service.add_resident_message(
            conversation_id, RESIDENT, "沒有漏電也沒有冒煙"
        )

        self.assertIn("服務地區", second["assistantMessage"]["content"])

    def test_several_addresses_are_not_guessed(self) -> None:
        service, orchestrator, _ = _service(
            _memory(
                addresses=(
                    MemberAddress("01", "010", "內湖區", "住家"),
                    MemberAddress("01", "005", "信義區", "爸媽家"),
                )
            ),
            [],
        )

        conversation_id = service.create_conversation(RESIDENT)["conversationId"]
        first = service.add_resident_message(
            conversation_id, RESIDENT, "熱水器沒有熱水"
        )

        self.assertIsNone(first["serviceRequest"]["districtName"])
        self.assertEqual(
            orchestrator.requests[0].known_fields["rememberedDistrictChoices"],
            ["內湖區", "信義區"],
        )

    def test_a_remembered_district_outside_the_master_table_is_ignored(self) -> None:
        service, _, _ = _service(
            _memory(addresses=(MemberAddress("02", "999", "板橋區", "住家", True),)),
            [],
        )

        conversation_id = service.create_conversation(RESIDENT)["conversationId"]
        first = service.add_resident_message(
            conversation_id, RESIDENT, "熱水器沒有熱水"
        )

        self.assertIsNone(first["serviceRequest"]["districtName"])


class PiiBoundaryTests(unittest.TestCase):
    """Address detail must not leave the store.

    Asserting on the bare token "detail" was too broad: it collides with the
    `collecting_details` stage name and would pass or fail for reasons unrelated
    to PII. These assertions name the leak instead: street-level tokens, and the
    fact that the projection has nowhere to carry one.
    """

    # Tokens that only appear in a street-level address, never in a district name.
    STREET_TOKENS = ("號", "路", "街", "巷", "弄", "樓", "室")

    def test_no_street_detail_can_reach_the_agent_or_the_turn_payload(self) -> None:
        service, orchestrator, _ = _service(
            _memory(
                addresses=(
                    MemberAddress(
                        county_code="01",
                        district_code="010",
                        district_name="內湖區",
                        label="住家",
                        is_default=True,
                    ),
                )
            ),
            [],
        )

        conversation_id = service.create_conversation(RESIDENT)["conversationId"]
        first = service.add_resident_message(
            conversation_id, RESIDENT, "熱水器沒有熱水"
        )

        request_payload = orchestrator.requests[0]
        for token in self.STREET_TOKENS:
            for value in request_payload.known_fields.values():
                self.assertNotIn(token, str(value), f"street token {token} in prompt")
            self.assertNotIn(token, repr(first["serviceRequest"]))

    def test_the_memory_projection_has_nowhere_to_hold_a_street_detail(self) -> None:
        service, orchestrator, _ = _service(_memory(), [])

        conversation_id = service.create_conversation(RESIDENT)["conversationId"]
        service.add_resident_message(conversation_id, RESIDENT, "熱水器沒有熱水")

        # Remembered keys are an allowlist, so a future field cannot leak in by
        # simply being added to the address record.
        self.assertEqual(
            set(orchestrator.requests[0].known_fields)
            - {
                "issueType",
                "districtName",
                "preferredTime",
                "urgency",
                "riskScreened",
            },
            {"rememberedDistrictName", "rememberedAppliance"},
        )
        self.assertNotIn("detail", MemberAddress.__slots__)


class PreferenceDrivenMatchingTests(unittest.TestCase):
    def test_blocked_vendor_is_never_dispatched(self) -> None:
        service, _, _ = _service(
            _memory(
                preference=MemberPreference(
                    blocked_vendor_ids=(FAST_DEAR_PROVIDER,)
                )
            ),
            [],
        )

        conversation_id = _reach_confirmation(service)
        confirmed = service.add_resident_message(
            conversation_id, RESIDENT, "確認送出"
        )

        self.assertEqual(
            confirmed["providerTask"]["provider"]["providerId"],
            SLOW_CHEAP_PROVIDER,
        )
        request = service.store.service_requests[
            confirmed["progress"]["serviceRequestId"]
        ]
        self.assertNotIn(FAST_DEAR_PROVIDER, request["candidateProviderIds"])

    def test_price_sensitive_member_gets_the_cheaper_candidate_first(self) -> None:
        service, _, _ = _service(
            _memory(preference=MemberPreference(price_sensitivity=0.9)), []
        )

        conversation_id = _reach_confirmation(service)
        confirmed = service.add_resident_message(
            conversation_id, RESIDENT, "確認送出"
        )

        self.assertEqual(
            confirmed["providerTask"]["provider"]["providerId"],
            SLOW_CHEAP_PROVIDER,
        )
        request = service.store.service_requests[
            confirmed["progress"]["serviceRequestId"]
        ]
        self.assertEqual(request["matchRuleVersion"], "preference-weighted-1")
        self.assertIn("價格", request["matchReason"])

    def test_price_insensitive_member_keeps_the_faster_candidate_first(self) -> None:
        service, _, _ = _service(
            _memory(preference=MemberPreference(price_sensitivity=0.1)), []
        )

        conversation_id = _reach_confirmation(service)
        confirmed = service.add_resident_message(
            conversation_id, RESIDENT, "確認送出"
        )

        self.assertEqual(
            confirmed["providerTask"]["provider"]["providerId"],
            FAST_DEAR_PROVIDER,
        )

    def test_a_member_with_no_learned_preference_keeps_the_plain_ordering(
        self,
    ) -> None:
        service, _, _ = _service(_memory(), [])

        conversation_id = _reach_confirmation(service)
        confirmed = service.add_resident_message(
            conversation_id, RESIDENT, "確認送出"
        )
        request = service.store.service_requests[
            confirmed["progress"]["serviceRequestId"]
        ]

        self.assertEqual(
            confirmed["providerTask"]["provider"]["providerId"],
            FAST_DEAR_PROVIDER,
        )
        self.assertNotIn("matchRuleVersion", request)


class PreferenceWriteBackTests(unittest.TestCase):
    def test_observed_preference_merges_without_clearing_other_fields(self) -> None:
        base = MemberPreference(
            price_sensitivity=0.4,
            preferred_vendor_tags=("原廠零件",),
            blocked_vendor_ids=("V009",),
            notes=("偏好先報價再施工",),
        )
        service, _, store = _service(
            _memory(preference=base),
            [
                _turn(
                    extracted={
                        "observedPreference": {
                            "priceSensitivity": 0.95,
                            "note": "只考慮低價方案",
                        }
                    }
                )
            ],
        )

        conversation_id = service.create_conversation(RESIDENT)["conversationId"]
        service.add_resident_message(
            conversation_id, RESIDENT, "熱水器沒有熱水，預算不要太高"
        )

        preference = store.load(RESIDENT).preference
        self.assertEqual(preference.price_sensitivity, 0.95)
        self.assertEqual(preference.preferred_vendor_tags, ("原廠零件",))
        self.assertEqual(preference.blocked_vendor_ids, ("V009",))
        self.assertEqual(
            preference.notes, ("偏好先報價再施工", "只考慮低價方案")
        )

    def test_write_back_is_recorded_as_an_event(self) -> None:
        service, _, _ = _service(
            _memory(),
            [_turn(extracted={"observedPreference": {"priceSensitivity": 0.9}})],
        )

        conversation_id = service.create_conversation(RESIDENT)["conversationId"]
        first = service.add_resident_message(
            conversation_id, RESIDENT, "熱水器沒有熱水，越便宜越好"
        )

        events = service.store.events[first["serviceRequest"]["serviceRequestId"]]
        self.assertIn(
            "member_preference_updated",
            [event["eventType"] for event in events],
        )

    def test_keys_outside_the_preference_allowlist_are_dropped(self) -> None:
        service, _, store = _service(
            _memory(preference=MemberPreference(price_sensitivity=0.4)),
            [
                _turn(
                    extracted={
                        "observedPreference": {
                            "residentMobile": "0912345678",
                            "notes": ["injected"],
                            "priceSensitivity": 0.7,
                        }
                    }
                )
            ],
        )

        conversation_id = service.create_conversation(RESIDENT)["conversationId"]
        service.add_resident_message(conversation_id, RESIDENT, "熱水器沒有熱水")

        preference = store.load(RESIDENT).preference
        self.assertEqual(preference.price_sensitivity, 0.7)
        self.assertEqual(preference.notes, ())

    def test_a_turn_without_an_observation_writes_nothing(self) -> None:
        base = MemberPreference(price_sensitivity=0.4)
        service, _, store = _service(_memory(preference=base), [_turn()])

        conversation_id = service.create_conversation(RESIDENT)["conversationId"]
        service.add_resident_message(conversation_id, RESIDENT, "熱水器沒有熱水")

        self.assertEqual(store.load(RESIDENT).preference, base)


class MemoryIsADefaultNotAnAuthorityTests(unittest.TestCase):
    def test_a_district_the_resident_states_wins_over_memory(self) -> None:
        service, _, _ = _service(
            _memory(),
            [_turn(extracted={"districtName": "信義區"})],
        )

        conversation_id = service.create_conversation(RESIDENT)["conversationId"]
        first = service.add_resident_message(
            conversation_id, RESIDENT, "熱水器沒有熱水，這次在信義區"
        )

        self.assertEqual(first["serviceRequest"]["districtName"], "信義區")

    def test_memory_does_not_skip_the_safety_screen(self) -> None:
        service, _, _ = _service(
            _memory(preference=MemberPreference(price_sensitivity=0.9)), []
        )

        conversation_id = service.create_conversation(RESIDENT)["conversationId"]
        first = service.add_resident_message(
            conversation_id, RESIDENT, "熱水器沒有熱水"
        )

        self.assertEqual(first["progress"]["stage"], "collecting_details")
        request = service.store.service_requests[
            first["serviceRequest"]["serviceRequestId"]
        ]
        self.assertFalse(request["riskScreened"])


if __name__ == "__main__":
    unittest.main()


class ReplyWordingOwnershipTests(unittest.TestCase):
    """Who owns the sentence when the flow has something specific to ask.

    The flow decides *what* must be conveyed; the agent may only decide *how* it
    is phrased. An agent reply that carries no ask must not replace a question,
    otherwise the resident is left with "好的。" and no idea what to provide.
    """

    def test_acknowledgement_only_reply_does_not_replace_the_question(self) -> None:
        service, _, _ = _service(_memory(), [_turn(assistant_message="好的。")])

        conversation_id = service.create_conversation(RESIDENT)["conversationId"]
        service.add_resident_message(conversation_id, RESIDENT, "熱水器沒有熱水")
        second = service.add_resident_message(
            conversation_id, RESIDENT, "沒有漏電也沒有冒煙"
        )

        self.assertIn("時段", second["assistantMessage"]["content"])

    def test_a_genuine_question_from_the_agent_is_used(self) -> None:
        service, _, _ = _service(
            _memory(),
            [
                _turn(),
                _turn(assistant_message="了解，你希望師傅哪一天過去比較方便？"),
            ],
        )

        conversation_id = service.create_conversation(RESIDENT)["conversationId"]
        service.add_resident_message(conversation_id, RESIDENT, "熱水器沒有熱水")
        second = service.add_resident_message(
            conversation_id, RESIDENT, "沒有漏電也沒有冒煙"
        )

        self.assertEqual(
            second["assistantMessage"]["content"],
            "了解，你希望師傅哪一天過去比較方便？",
        )

    def test_a_statement_that_merely_contains_a_polite_word_is_rejected(self) -> None:
        service, _, _ = _service(
            _memory(),
            [_turn(), _turn(assistant_message="可以了，我幫你直接送出。")],
        )

        conversation_id = service.create_conversation(RESIDENT)["conversationId"]
        service.add_resident_message(conversation_id, RESIDENT, "熱水器沒有熱水")
        second = service.add_resident_message(
            conversation_id, RESIDENT, "沒有漏電也沒有冒煙"
        )

        self.assertIn("時段", second["assistantMessage"]["content"])
        self.assertNotIn("直接送出", second["assistantMessage"]["content"])

    def test_a_bare_interrogative_particle_is_too_short_to_count(self) -> None:
        service, _, _ = _service(
            _memory(), [_turn(), _turn(assistant_message="好嗎？")]
        )

        conversation_id = service.create_conversation(RESIDENT)["conversationId"]
        service.add_resident_message(conversation_id, RESIDENT, "熱水器沒有熱水")
        second = service.add_resident_message(
            conversation_id, RESIDENT, "沒有漏電也沒有冒煙"
        )

        self.assertIn("時段", second["assistantMessage"]["content"])

    def test_safety_wording_is_never_rephrased_by_the_agent(self) -> None:
        service, _, _ = _service(
            _memory(),
            [_turn(assistant_message="這聽起來還好，請問是哪一台熱水器呢？")],
        )

        conversation_id = service.create_conversation(RESIDENT)["conversationId"]
        first = service.add_resident_message(
            conversation_id, RESIDENT, "插座冒煙還有焦味"
        )

        self.assertIn("119", first["assistantMessage"]["content"])
        self.assertNotIn("還好", first["assistantMessage"]["content"])


class AppFactoryWiringTests(unittest.TestCase):
    """The memory store has to be reachable from `create_app()`.

    Without this the feature is fully implemented and fully tested yet cannot be
    demonstrated, because the running application never constructs a store.
    """

    def setUp(self) -> None:
        from walking_skeleton.api import create_app

        self._create_app = create_app
        self._previous = os.environ.get("MEMBER_MEMORY_BACKEND")

    def tearDown(self) -> None:
        if self._previous is None:
            os.environ.pop("MEMBER_MEMORY_BACKEND", None)
        else:
            os.environ["MEMBER_MEMORY_BACKEND"] = self._previous

    def _service(self):
        app = self._create_app(testing=True)
        return app.extensions["walking_skeleton_service"]

    def test_default_keeps_memory_switched_off(self) -> None:
        os.environ.pop("MEMBER_MEMORY_BACKEND", None)

        self.assertEqual(self._service().member_memory.backend, "none")

    def test_demo_backend_is_reachable_from_the_app_factory(self) -> None:
        os.environ["MEMBER_MEMORY_BACKEND"] = "demo"

        service = self._service()

        self.assertEqual(service.member_memory.backend, "in-memory")
        self.assertEqual(
            service.member_memory.load(RESIDENT).default_address.district_name,
            "內湖區",
        )

    def test_an_unsupported_backend_fails_closed(self) -> None:
        os.environ["MEMBER_MEMORY_BACKEND"] = "dynamodb"

        with self.assertRaises(ValueError):
            self._create_app(testing=True)
