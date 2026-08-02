"""Cross-category dispatch contract for the walking skeleton backbone.

These tests pin the seam that lets a second service type be added without
editing `service.py`: routing MUST come from the orchestrator's delegation,
continuation MUST come from the stored request's `serviceType`, and a service
type with no registered flow MUST fail loudly instead of silently running
another category's flow.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from walking_skeleton.flows import (  # noqa: E402
    BASE_STAGE_LABELS,
    UnsupportedServiceTypeError,
)
from walking_skeleton.orchestration import (  # noqa: E402
    AgentTurn,
    AgentTurnRequest,
    Delegation,
)
from walking_skeleton.service import WalkingSkeletonService  # noqa: E402
from walking_skeleton.utility_flow import UtilityRepairFlow  # noqa: E402


class StubOrchestrator:
    """Routes to a fixed delegation so tests control the supervisor decision."""

    mode = "deterministic-demo"

    def __init__(self, delegation: Delegation) -> None:
        self.delegation = delegation
        self.requests: list[AgentTurnRequest] = []

    def delegate(self, message: str) -> Delegation:
        return self.delegation

    def turn(self, request: AgentTurnRequest) -> AgentTurn:
        """Route only, with no extraction, so dispatch stays the thing under test."""

        self.requests.append(request)
        return AgentTurn(
            service_type=self.delegation.service_type,
            target_agent=self.delegation.target_agent,
            mode=self.mode,
            needs_clarification=self.delegation.needs_clarification,
            candidate_service_types=self.delegation.candidate_service_types,
        )


class RecordingFlow:
    """Minimal second flow used to prove dispatch is data-driven."""

    service_type = "stub_service"
    agent_name = "stub_agent"
    service_name = "測試服務"
    schema_version = "9.9.9"
    stage_labels = dict(BASE_STAGE_LABELS)
    routing_hint = "測試需求"

    def __init__(self) -> None:
        self.started: list[str] = []
        self.continued: list[str] = []

    def init_request(self, request: dict[str, Any], content: str) -> None:
        request["stubField"] = content

    def known_fields(
        self, request: dict[str, Any] | None, memory: Any = None
    ) -> dict[str, Any]:
        return {}

    def missing_fields(self, request: dict[str, Any] | None) -> tuple[str, ...]:
        return ()

    def turn_goal(
        self, request: dict[str, Any] | None, stage: str | None
    ) -> str | None:
        return "route_new_request" if request is None else "collect_missing_fields"

    def merge_agent_extraction(
        self, request: dict[str, Any], turn: Any
    ) -> dict[str, Any]:
        return {}

    def start(
        self,
        svc: Any,
        conversation: dict[str, Any],
        request: dict[str, Any],
        *,
        turn: Any = None,
        memory: Any = None,
    ) -> dict[str, Any]:
        self.started.append(request["serviceRequestId"])
        svc.set_progress(request, "collecting_details", waiting_for="resident")
        assistant = svc.append_assistant(
            conversation["conversationId"], "stub start", agent=self.agent_name
        )
        return svc.turn_payload(
            conversation, assistant, trace_agent="supervisor", turn=turn
        )

    def continue_turn(
        self,
        svc: Any,
        conversation: dict[str, Any],
        request: dict[str, Any],
        content: str,
        *,
        turn: Any = None,
        memory: Any = None,
    ) -> dict[str, Any]:
        self.continued.append(content)
        assistant = svc.append_assistant(
            conversation["conversationId"], "stub continue", agent=self.agent_name
        )
        return svc.turn_payload(conversation, assistant, turn=turn)

    def build_summary(self, request: dict[str, Any]) -> str:
        return "stub summary"

    def fallback_summary(self, request: dict[str, Any]) -> str:
        return request["stubField"]

    def build_canonical(self, request: dict[str, Any]) -> dict[str, Any]:
        return {"stubField": request["stubField"]}

    def projection_fields(self, request: dict[str, Any]) -> dict[str, Any]:
        return {"stubField": request["stubField"]}

    def list_providers(self) -> tuple[dict[str, Any], ...]:
        return ()

    def rank_candidates(
        self, request: dict[str, Any], memory: Any = None
    ) -> list[dict[str, Any]]:
        return []

    def validate_accept(self, payload: dict[str, Any]) -> None:
        return None

    def apply_accept(
        self,
        request: dict[str, Any],
        provider: dict[str, Any],
        payload: dict[str, Any],
    ) -> str:
        return "stub accepted"


RESIDENT = "resident-dispatch-001"


class ServiceFlowDispatchTest(unittest.TestCase):
    def _service(
        self, delegation: Delegation, flows: tuple[Any, ...]
    ) -> WalkingSkeletonService:
        return WalkingSkeletonService(
            orchestrator=StubOrchestrator(delegation), flows=flows
        )

    def _conversation(self, service: WalkingSkeletonService) -> str:
        return service.create_conversation(RESIDENT)["conversationId"]

    def test_delegation_selects_the_matching_flow(self) -> None:
        stub = RecordingFlow()
        utility = UtilityRepairFlow()
        service = self._service(
            Delegation(
                service_type="stub_service",
                target_agent="stub_agent",
                mode="deterministic-demo",
            ),
            (utility, stub),
        )
        conversation_id = self._conversation(service)

        turn = service.add_resident_message(conversation_id, RESIDENT, "任意需求")

        self.assertEqual(turn["assistantMessage"]["content"], "stub start")
        self.assertEqual(turn["activeAgent"], "stub_agent")
        self.assertEqual(turn["serviceRequest"]["serviceType"], "stub_service")
        self.assertEqual(turn["serviceRequest"]["serviceName"], "測試服務")
        self.assertEqual(len(stub.started), 1)

    def test_continuation_dispatches_on_stored_service_type(self) -> None:
        stub = RecordingFlow()
        service = self._service(
            Delegation(
                service_type="stub_service",
                target_agent="stub_agent",
                mode="deterministic-demo",
            ),
            (UtilityRepairFlow(), stub),
        )
        conversation_id = self._conversation(service)
        service.add_resident_message(conversation_id, RESIDENT, "任意需求")

        turn = service.add_resident_message(conversation_id, RESIDENT, "第二句")

        self.assertEqual(turn["assistantMessage"]["content"], "stub continue")
        self.assertEqual(stub.continued, ["第二句"])

    def test_utility_and_stub_requests_use_their_own_flow(self) -> None:
        """Two service types must not share one hardcoded handler."""

        stub = RecordingFlow()
        utility_service = self._service(
            Delegation(
                service_type="utility_repair",
                target_agent="utility_repair_agent",
                mode="deterministic-demo",
            ),
            (UtilityRepairFlow(), stub),
        )
        utility_conversation = self._conversation(utility_service)
        utility_turn = utility_service.add_resident_message(
            utility_conversation, RESIDENT, "浴室漏水"
        )

        self.assertEqual(
            utility_turn["serviceRequest"]["serviceType"], "utility_repair"
        )
        self.assertEqual(utility_turn["serviceRequest"]["serviceName"], "水電修繕")
        self.assertEqual(stub.started, [], "utility routing must not reach the stub flow")

    def test_unregistered_service_type_is_answered_not_silently_routed(self) -> None:
        service = self._service(
            Delegation(
                service_type="restaurant_reservation",
                target_agent="restaurant_agent",
                mode="deterministic-demo",
            ),
            (UtilityRepairFlow(),),
        )
        conversation_id = self._conversation(service)

        turn = service.add_resident_message(conversation_id, RESIDENT, "想訂位")

        self.assertIsNone(turn.get("serviceRequest"))
        self.assertIsNone(turn["activeAgent"])
        self.assertIn("水電修繕", turn["assistantMessage"]["content"])
        self.assertEqual(turn["trace"][0]["agent"], "supervisor")
        self.assertIsNone(
            turn["trace"][0]["target"],
            "no delegation happened, so the trace must not name a target agent",
        )
        self.assertEqual(service.store.service_requests, {})

    def test_stored_request_with_unknown_service_type_raises(self) -> None:
        """A stored request whose flow is gone is a server bug, not client input."""

        stub = RecordingFlow()
        service = self._service(
            Delegation(
                service_type="stub_service",
                target_agent="stub_agent",
                mode="deterministic-demo",
            ),
            (stub,),
        )
        conversation_id = self._conversation(service)
        service.add_resident_message(conversation_id, RESIDENT, "任意需求")

        # Simulate a build where the flow was removed but data still references it.
        service.flows.pop("stub_service")

        with self.assertRaises(UnsupportedServiceTypeError):
            service.add_resident_message(conversation_id, RESIDENT, "第二句")

    def test_unknown_stage_label_is_rejected(self) -> None:
        """A flow may only use stages it declares a label for."""

        stub = RecordingFlow()
        service = self._service(
            Delegation(
                service_type="stub_service",
                target_agent="stub_agent",
                mode="deterministic-demo",
            ),
            (stub,),
        )
        conversation_id = self._conversation(service)
        service.add_resident_message(conversation_id, RESIDENT, "任意需求")
        request = next(iter(service.store.service_requests.values()))

        with self.assertRaises(UnsupportedServiceTypeError):
            service.set_progress(request, "safety_hold", waiting_for="resident")


if __name__ == "__main__":
    unittest.main()
