"""Transport-independent application service for the walking skeleton.

This module owns only what is identical across service types:

* conversations, messages and the resident/provider/admin authorization checks
* service request creation, artifact versioning and the progress projection
* provider task dispatch, rematching, idempotency and optimistic locking

Everything that differs per service type lives behind `flows.ServiceFlow`.
Adding a new category means registering a new flow, not adding branches here.

Methods called by flow implementations are public on purpose; they are the
seam between the shared skeleton and per-category rules.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from .flows import ServiceFlow, UnsupportedServiceTypeError
from .geo import DISTRICTS
from .member_memory import (
    EMPTY_MEMORY,
    MemberMemory,
    MemberMemoryStore,
    NullMemberMemoryStore,
)
from .orchestration import (
    AgentTurn,
    AgentTurnRequest,
    DeterministicDemoOrchestrator,
    SupervisorOrchestrator,
)
from .product_flow import ProductPurchaseFlow
from .store import InMemoryStore
from .utility_flow import UtilityRepairFlow

# Conversation history sent to the agent for context. Bounded so a long thread
# can not grow the prompt without limit.
MAX_HISTORY_ENTRIES = 8


def default_flows() -> tuple[ServiceFlow, ...]:
    """Service types this build can handle, in supervisor routing order."""

    return (UtilityRepairFlow(), ProductPurchaseFlow())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _public_provider(provider: dict[str, Any]) -> dict[str, Any]:
    return {
        "providerId": provider["providerId"],
        "name": provider["name"],
        "rating": provider["rating"],
        "responseSlaHours": provider["responseSlaHours"],
        "capabilities": list(provider["capabilities"]),
    }


class WalkingSkeletonService:
    def __init__(
        self,
        store: InMemoryStore | None = None,
        orchestrator: SupervisorOrchestrator | None = None,
        flows: Sequence[ServiceFlow] | None = None,
        member_memory: MemberMemoryStore | None = None,
    ) -> None:
        self.store = store or InMemoryStore()
        self.orchestrator = orchestrator or DeterministicDemoOrchestrator()
        # Defaults to off: a member the platform knows nothing about must get
        # exactly the previous turn-by-turn flow.
        self.member_memory = member_memory or NullMemberMemoryStore()
        registered = tuple(default_flows() if flows is None else flows)
        self.flows: dict[str, ServiceFlow] = {
            flow.service_type: flow for flow in registered
        }

    # ------------------------------------------------------------------
    # Resident conversation API
    # ------------------------------------------------------------------

    def create_conversation(self, resident_id: str) -> dict[str, Any]:
        now = _now()
        conversation_id = _id("conv")
        conversation = {
            "conversationId": conversation_id,
            "residentId": resident_id,
            "serviceRequestId": None,
            "activeAgent": None,
            "createdAt": now,
            "updatedAt": now,
        }
        greeting = self._message(
            conversation_id,
            "assistant",
            self._greeting(),
            agent="supervisor",
        )
        with self.store.lock:
            self.store.conversations[conversation_id] = conversation
            self.store.messages[conversation_id] = [greeting]
        return {
            "conversationId": conversation_id,
            "orchestrationMode": self.orchestrator.mode,
            "activeAgent": None,
            "assistantMessage": greeting,
        }

    def add_resident_message(
        self, conversation_id: str, resident_id: str, content: str
    ) -> dict[str, Any]:
        content = content.strip()
        if not content or len(content) > 2000:
            raise ValidationError("message 必須為 1 到 2000 字")

        with self.store.lock:
            conversation = self._conversation_for_resident(conversation_id, resident_id)
            self.store.messages[conversation_id].append(
                self._message(conversation_id, "user", content)
            )
            memory = self.member_memory.load(resident_id)
            request_id = conversation.get("serviceRequestId")
            if not request_id:
                result = self._route_new_request(conversation, content, memory)
            else:
                result = self._continue_request(conversation, content, memory)
            conversation["updatedAt"] = _now()
            return result

    def list_messages(
        self, conversation_id: str, resident_id: str, after: str | None = None
    ) -> dict[str, Any]:
        with self.store.lock:
            self._conversation_for_resident(conversation_id, resident_id)
            items = list(self.store.messages[conversation_id])
            if after:
                items = [item for item in items if item["messageId"] > after]
            return {"items": items, "nextCursor": items[-1]["messageId"] if items else after}

    def list_service_requests(self, resident_id: str) -> dict[str, Any]:
        with self.store.lock:
            items = [
                self._service_request_projection(request)
                for request in self.store.service_requests.values()
                if request["residentId"] == resident_id
            ]
            items.sort(key=lambda item: item["updatedAt"], reverse=True)
            return {"items": items}

    def get_progress(self, service_request_id: str, resident_id: str) -> dict[str, Any]:
        with self.store.lock:
            request = self._request_for_resident(service_request_id, resident_id)
            return self._progress_projection(request)

    def list_reminders(self, resident_id: str) -> dict[str, Any]:
        with self.store.lock:
            reminders: list[dict[str, Any]] = []
            for request in self.store.service_requests.values():
                if request["residentId"] != resident_id:
                    continue
                progress = self.store.progress[request["serviceRequestId"]]
                if progress["waitingFor"] == "resident":
                    reminders.append(
                        {
                            "reminderId": f"reminder_{request['serviceRequestId']}",
                            "serviceRequestId": request["serviceRequestId"],
                            "label": progress["displayLabel"],
                            "actionRequired": True,
                            "updatedAt": progress["latestEventAt"],
                        }
                    )
            return {"items": reminders}

    # ------------------------------------------------------------------
    # Provider and admin API
    # ------------------------------------------------------------------

    def list_demo_providers(self) -> list[dict[str, Any]]:
        """Every provider across registered flows, for demo role switching.

        Non-sensitive by construction: it only surfaces identifiers and display
        names that already exist in the public catalogue fixtures.
        """

        items: list[dict[str, Any]] = []
        for flow in self.flows.values():
            for provider in flow.list_providers():
                items.append(
                    {
                        "providerId": provider["providerId"],
                        "name": provider["name"],
                        "serviceType": flow.service_type,
                        "serviceName": flow.service_name,
                    }
                )
        items.sort(key=lambda item: (item["serviceType"], item["name"]))
        return items

    def list_provider_tasks(self, provider_id: str) -> dict[str, Any]:
        with self.store.lock:
            items = [
                self._task_projection(task)
                for task in self.store.tasks.values()
                if task["providerId"] == provider_id and task["status"] == "pending"
            ]
            items.sort(key=lambda item: item["createdAt"])
            return {"items": items}

    def provider_response(
        self,
        *,
        task_id: str,
        provider_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        # Resource authorization precedes payload-specific validation so an
        # unassigned provider cannot use validation differences to probe tasks.
        with self.store.lock:
            task = self.store.tasks.get(task_id)
            if not task:
                raise NotFoundError("找不到廠商任務")
            if task["providerId"] != provider_id:
                raise ForbiddenError()
            flow = self._flow_for(self.store.service_requests[task["serviceRequestId"]])
        action = payload.get("action")
        if action not in {"accept", "decline", "needs_information"}:
            raise ValidationError("action 必須是 accept、decline 或 needs_information")
        expected_version = payload.get("expectedVersion")
        if not isinstance(expected_version, int):
            raise ValidationError("expectedVersion 必須是整數")
        message = payload.get("message")
        if message is not None and (not isinstance(message, str) or len(message) > 1000):
            raise ValidationError("message 必須是 1000 字以內的文字")
        if action == "needs_information" and not (isinstance(message, str) and message.strip()):
            raise ValidationError("要求補件時 message 為必填")
        if action == "accept":
            # Validate before entering the transaction so an invalid accept can
            # never consume or version-bump the pending task. Required accept
            # fields differ per service type, so the flow owns this check.
            flow.validate_accept(payload)

        operation = f"provider-response:{task_id}"
        return self.store.idempotent(
            actor_id=provider_id,
            operation=operation,
            key=idempotency_key,
            payload=payload,
            command=lambda: self._apply_provider_response(
                task_id=task_id,
                provider_id=provider_id,
                action=action,
                expected_version=expected_version,
                message=(message or "").strip(),
                payload=payload,
            ),
        )

    def select_option(
        self,
        *,
        service_request_id: str,
        resident_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Record a resident's choice among candidates.

        Only accepts the candidate identifier and an expected version. Any price
        or shipping field a client sends is ignored: amounts are always
        recomputed server-side by the flow.
        """

        with self.store.lock:
            request = self._request_for_resident(service_request_id, resident_id)
            flow = self._flow_for(request)
            if not getattr(flow, "supports_selection", False):
                raise ValidationError(
                    f"{flow.service_name}不需要選擇選項，此端點不適用"
                )

        sku = payload.get("sku")
        if not isinstance(sku, str) or not sku.strip():
            raise ValidationError("sku 為必填文字")
        expected_version = payload.get("expectedVersion")
        if not isinstance(expected_version, int):
            raise ValidationError("expectedVersion 必須是整數")

        # Only the fields the server trusts enter the idempotency fingerprint.
        fingerprint = {"sku": sku.strip(), "expectedVersion": expected_version}
        return self.store.idempotent(
            actor_id=resident_id,
            operation=f"select-option:{service_request_id}",
            key=idempotency_key,
            payload=fingerprint,
            command=lambda: self._apply_selection(
                service_request_id=service_request_id,
                resident_id=resident_id,
                sku=sku.strip(),
                expected_version=expected_version,
            ),
        )

    def _apply_selection(
        self,
        *,
        service_request_id: str,
        resident_id: str,
        sku: str,
        expected_version: int,
    ) -> dict[str, Any]:
        with self.store.lock:
            request = self._request_for_resident(service_request_id, resident_id)
            flow = self._flow_for(request)
            result = flow.select(
                self, request, sku=sku, expected_version=expected_version
            )
            conversation = self.store.conversations[request["conversationId"]]
            conversation["updatedAt"] = _now()
            return result

    def simulate_timeout(
        self,
        *,
        task_id: str,
        admin_id: str,
        reason: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        reason = reason.strip()
        if not reason or len(reason) > 500:
            raise ValidationError("reason 必須為 1 到 500 字")
        payload = {"reason": reason}
        return self.store.idempotent(
            actor_id=admin_id,
            operation=f"simulate-timeout:{task_id}",
            key=idempotency_key,
            payload=payload,
            command=lambda: self._apply_timeout(task_id, admin_id, reason),
        )

    # ------------------------------------------------------------------
    # Flow dispatch
    # ------------------------------------------------------------------

    def _flow_for_type(self, service_type: object) -> ServiceFlow | None:
        if not isinstance(service_type, str):
            return None
        return self.flows.get(service_type)

    def _flow_for(self, request: dict[str, Any]) -> ServiceFlow:
        flow = self._flow_for_type(request.get("serviceType"))
        if flow is None:
            raise UnsupportedServiceTypeError(request.get("serviceType"))
        return flow

    def _route_new_request(
        self,
        conversation: dict[str, Any],
        content: str,
        memory: MemberMemory = EMPTY_MEMORY,
    ) -> dict[str, Any]:
        # `turn()` rather than `delegate()`: the Supervisor routes and the routed
        # agent understands the same sentence in one Runtime call, so the fields
        # a resident volunteered up front are not thrown away and asked again.
        turn = self.orchestrator.turn(
            AgentTurnRequest(
                message=content,
                turn_goal="route_new_request",
                known_fields=dict(memory.to_known_fields()),
                history=self.history(conversation["conversationId"]),
                service_districts=tuple(DISTRICTS),
            )
        )
        if turn.needs_clarification:
            assistant = self.append_assistant(
                conversation["conversationId"],
                self._clarification_reply(turn.candidate_service_types),
                agent="supervisor",
            )
            return self.turn_payload(
                conversation,
                assistant,
                trace_agent="supervisor",
                trace_target=None,
                turn=turn,
            )

        flow = self._flow_for_type(turn.service_type)
        if flow is None:
            assistant = self.append_assistant(
                conversation["conversationId"],
                self._unsupported_reply(),
                agent="supervisor",
            )
            return self.turn_payload(
                conversation,
                assistant,
                trace_agent="supervisor",
                trace_target=None,
                turn=turn,
            )

        request_id = _id("sr")
        now = _now()
        request: dict[str, Any] = {
            "serviceRequestId": request_id,
            "conversationId": conversation["conversationId"],
            "residentId": conversation["residentId"],
            "serviceType": flow.service_type,
            "candidateProviderIds": [],
            "candidateIndex": -1,
            "currentProviderId": None,
            "currentTaskId": None,
            "createdAt": now,
            "updatedAt": now,
        }
        flow.init_request(request, content)
        conversation["serviceRequestId"] = request_id
        conversation["activeAgent"] = flow.agent_name
        self.store.service_requests[request_id] = request
        self.store.events[request_id] = []
        return flow.start(self, conversation, request, turn=turn, memory=memory)

    def _continue_request(
        self,
        conversation: dict[str, Any],
        content: str,
        memory: MemberMemory = EMPTY_MEMORY,
    ) -> dict[str, Any]:
        request = self.store.service_requests[conversation["serviceRequestId"]]
        flow = self._flow_for(request)
        stage = self.current_stage(request)
        turn = self.agent_turn(
            conversation,
            content,
            flow=flow,
            request=request,
            stage=stage,
            memory=memory,
        )
        return flow.continue_turn(
            self, conversation, request, content, turn=turn, memory=memory
        )

    # ------------------------------------------------------------------
    # Model-backed turn seam
    # ------------------------------------------------------------------

    def agent_turn(
        self,
        conversation: dict[str, Any],
        content: str,
        *,
        flow: ServiceFlow,
        request: dict[str, Any] | None,
        stage: str | None,
        memory: MemberMemory = EMPTY_MEMORY,
    ) -> AgentTurn | None:
        """Ask the routed domain agent to understand this turn.

        Flask decides the goal and the ordered list of fields still missing, so
        the stage machine stays deterministic while the agent handles language.
        The field vocabulary comes from the flow, never from this module.

        Returns None when the flow declares this stage model-free, so a stage that
        must answer from fixed wording never spends a model call.
        """

        turn_goal = flow.turn_goal(request, stage)
        if turn_goal is None:
            return None
        return self.orchestrator.turn(
            AgentTurnRequest(
                message=content,
                active_agent=conversation.get("activeAgent"),
                workflow_stage=stage,
                turn_goal=turn_goal,
                known_fields=flow.known_fields(request, memory),
                missing_fields=flow.missing_fields(request),
                history=self.history(conversation["conversationId"]),
                service_districts=tuple(DISTRICTS),
            )
        )

    def record_observed_preference(
        self, request: dict[str, Any], patch: dict[str, Any] | None
    ) -> None:
        """Merge an observed long-term preference, field by field.

        A merge rather than a row replace: one observed signal must not erase
        preferences learned on earlier turns.
        """

        if not isinstance(patch, dict) or not patch:
            return
        self.member_memory.merge_preference(request["residentId"], patch)
        self.event(request, "member_preference_updated", "已更新會員長期偏好")

    def history(self, conversation_id: str) -> tuple[dict[str, str], ...]:
        """Recent turns, oldest first, excluding the message being handled now."""

        # The resident message for this turn is already stored, so it is excluded
        # here and sent as the current message instead.
        messages = self.store.messages.get(conversation_id, [])[:-1]
        return tuple(
            {
                "role": "resident" if message["role"] == "user" else "agent",
                "content": message["content"],
            }
            for message in messages[-MAX_HISTORY_ENTRIES:]
        )

    def _greeting(self) -> str:
        return (
            "您好！我是 OPEN POINT 智慧助理。"
            f"你可以直接告訴我{self._supported_hints()}，我會交給對應的 Agent 一步一步確認。"
        )

    def _unsupported_reply(self) -> str:
        names = "、".join(flow.service_name for flow in self.flows.values())
        return (
            f"這個 walking skeleton 目前先示範{names or '尚未啟用的服務'}。"
            f"請描述{self._supported_hints()}，我會交給對應的 Agent。"
        )

    def _clarification_reply(self, candidates: tuple[str, ...]) -> str:
        """Ask which service the resident meant instead of guessing."""

        names = [
            self.flows[service_type].service_name
            for service_type in candidates
            if service_type in self.flows
        ]
        options = "、".join(names) if names else "多個服務"
        return (
            f"你的描述同時可能是{options}，我不確定要幫你處理哪一種，"
            "所以先不建立案件。請告訴我你想要的是哪一項，或用一句話說明目的。"
        )

    def _supported_hints(self) -> str:
        hints = [flow.routing_hint for flow in self.flows.values() if flow.routing_hint]
        return "，或".join(hints) if hints else "你的需求"

    # ------------------------------------------------------------------
    # Seams used by flow implementations
    # ------------------------------------------------------------------

    def touch(self, request: dict[str, Any]) -> None:
        request["updatedAt"] = _now()

    def current_stage(self, request: dict[str, Any]) -> str:
        return self.store.progress[request["serviceRequestId"]]["stage"]

    def current_artifact(self, request: dict[str, Any]) -> dict[str, Any] | None:
        return self.store.artifacts.get(request["serviceRequestId"])

    def set_progress(
        self, request: dict[str, Any], stage: str, *, waiting_for: str | None
    ) -> None:
        labels = self._flow_for(request).stage_labels
        if stage not in labels:
            raise UnsupportedServiceTypeError(
                f"{request.get('serviceType')} has no label for stage {stage!r}"
            )
        self.store.progress[request["serviceRequestId"]] = {
            "serviceRequestId": request["serviceRequestId"],
            "stage": stage,
            "waitingFor": waiting_for,
            "displayLabel": labels[stage],
            "residentActionRequired": waiting_for == "resident",
            "latestEventAt": _now(),
        }

    def render_artifact(
        self, request: dict[str, Any], *, supersede: bool = False
    ) -> dict[str, Any]:
        flow = self._flow_for(request)
        prior = self.store.artifacts.get(request["serviceRequestId"])
        version = (
            (prior["version"] + 1)
            if prior and supersede
            else (prior or {}).get("version", 1)
        )
        if prior and supersede:
            prior["status"] = "superseded"
        artifact = {
            "artifactId": _id("artifact"),
            "serviceRequestId": request["serviceRequestId"],
            "serviceType": flow.service_type,
            "schemaVersion": flow.schema_version,
            "version": version,
            "status": "draft",
            "summary": flow.build_summary(request),
            "canonical": flow.build_canonical(request),
            "createdBy": flow.agent_name,
            "createdAt": _now(),
        }
        self.store.artifacts[request["serviceRequestId"]] = artifact
        versions = self.store.artifact_versions.setdefault(request["serviceRequestId"], [])
        if not versions or versions[-1]["artifactId"] != artifact["artifactId"]:
            versions.append(artifact)
        return artifact

    def confirm_artifact(self, request: dict[str, Any]) -> dict[str, Any]:
        artifact = self.store.artifacts[request["serviceRequestId"]]
        artifact["status"] = "confirmed"
        artifact["confirmedAt"] = _now()
        return artifact

    def dispatch_first_candidate(
        self,
        request: dict[str, Any],
        candidates: Sequence[dict[str, Any]],
        *,
        reason: str,
        event_type: str,
        event_label: str,
    ) -> dict[str, Any]:
        request["candidateProviderIds"] = [p["providerId"] for p in candidates]
        request["candidateIndex"] = 0
        request["currentProviderId"] = candidates[0]["providerId"]
        self.touch(request)
        task = self._create_provider_task(
            request, request["currentProviderId"], reason=reason
        )
        self.event(request, event_type, event_label)
        self.set_progress(request, "waiting_provider_response", waiting_for="provider")
        return task

    def accept_resident_information(
        self,
        conversation: dict[str, Any],
        request: dict[str, Any],
        content: str,
        *,
        agent: str,
        reply: str,
        turn: AgentTurn | None = None,
    ) -> dict[str, Any]:
        request["providerAnswer"] = content
        self.touch(request)
        self.event(request, "resident_information_added", "住戶已補充廠商所需資訊")
        task = self._create_provider_task(
            request, request["currentProviderId"], reason="resident_information_added"
        )
        self.set_progress(request, "waiting_provider_response", waiting_for="provider")
        assistant = self.append_assistant(
            conversation["conversationId"], reply, agent=agent
        )
        return self.turn_payload(
            conversation, assistant, provider_task=task, turn=turn
        )

    def event(self, request: dict[str, Any], event_type: str, label: str) -> None:
        self.store.events.setdefault(request["serviceRequestId"], []).append(
            {"eventType": event_type, "label": label, "at": _now()}
        )

    def append_assistant(
        self,
        conversation_id: str,
        content: str,
        *,
        agent: str,
        kind: str = "message",
    ) -> dict[str, Any]:
        message = self._message(
            conversation_id, "assistant", content, agent=agent, kind=kind
        )
        self.store.messages[conversation_id].append(message)
        return message

    def turn_payload(
        self,
        conversation: dict[str, Any],
        assistant: dict[str, Any],
        *,
        trace_agent: str | None = None,
        trace_target: str | None = "",
        artifact: dict[str, Any] | None = None,
        provider_task: dict[str, Any] | None = None,
        turn: AgentTurn | None = None,
    ) -> dict[str, Any]:
        request_id = conversation.get("serviceRequestId")
        active_agent = conversation.get("activeAgent")
        agent = trace_agent or active_agent or "supervisor"
        # `trace_target` defaults to the sentinel "" so callers can pass None to
        # mean "nothing was delegated" without it being confused with "unset".
        target = active_agent if trace_target == "" else trace_target
        result: dict[str, Any] = {
            "conversationId": conversation["conversationId"],
            "orchestrationMode": self.orchestrator.mode,
            "activeAgent": active_agent,
            "assistantMessage": assistant,
            "trace": [
                {
                    "agent": agent,
                    "action": "delegate" if agent == "supervisor" else "continue_turn",
                    "target": target if agent == "supervisor" else None,
                    # Why the Supervisor picked this target. Without it a keyword
                    # hit and a model classification look identical, so there is
                    # no way to show that routing is actually reasoning.
                    "reasonCode": turn.reason_code if turn else None,
                    "at": _now(),
                }
            ],
            # Reported so the UI and the demo can tell a real model turn from an
            # honest deterministic fallback instead of guessing.
            "reasoning": {
                "mode": turn.reasoning_mode if turn else "rule-fallback",
                "modelId": turn.model_id if turn else None,
                "knowledgeBaseQueried": bool(turn and turn.knowledge_base_queried),
                # Surfaced so a resident can see the platform declined to answer a
                # live question from static knowledge, rather than that being silent.
                "liveValueTopics": list(turn.live_value_topics if turn else ()),
                "suppressedKnowledge": [
                    dict(record)
                    for record in (turn.suppressed_knowledge if turn else ())
                ],
            },
            "knowledge": [
                dict(reference) for reference in (turn.knowledge if turn else ())
            ],
        }
        if request_id:
            request = self.store.service_requests[request_id]
            result["serviceRequest"] = self._service_request_projection(request)
            result["progress"] = self._progress_projection(request)
        if artifact:
            result["artifact"] = artifact
        if provider_task:
            result["providerTask"] = provider_task
        return result

    def _apply_accept(
        self,
        flow: ServiceFlow,
        request: dict[str, Any],
        provider: dict[str, Any],
        payload: dict[str, Any],
    ) -> str:
        """Call `apply_accept`, passing the service only to flows that want it.

        Flows needing a guarded state transition (product orders) accept an extra
        `svc` keyword; simpler flows keep the three-argument signature.
        """

        if getattr(flow, "accept_needs_service", False):
            return flow.apply_accept(request, provider, payload, svc=self)
        return flow.apply_accept(request, provider, payload)

    def provider_of(self, request: dict[str, Any], provider_id: str) -> dict[str, Any]:
        provider = next(
            (
                item
                for item in self._flow_for(request).list_providers()
                if item["providerId"] == provider_id
            ),
            None,
        )
        if not provider:
            raise NotFoundError("找不到廠商")
        return provider

    # ------------------------------------------------------------------
    # Shared provider lifecycle
    # ------------------------------------------------------------------

    def _apply_provider_response(
        self,
        *,
        task_id: str,
        provider_id: str,
        action: str,
        expected_version: int,
        message: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self.store.lock:
            task = self.store.tasks.get(task_id)
            if not task:
                raise NotFoundError("找不到廠商任務")
            if task["providerId"] != provider_id:
                raise ForbiddenError()
            if task["status"] != "pending":
                raise ConflictError("任務已完成，不能重複操作")
            if task["version"] != expected_version:
                raise ConflictError("任務版本已更新，請重新整理")
            request = self.store.service_requests[task["serviceRequestId"]]
            flow = self._flow_for(request)
            task["status"] = action
            task["version"] += 1
            task["message"] = message
            task["completedAt"] = _now()

            if action == "needs_information":
                request["providerQuestion"] = message
                self.event(request, "provider_needs_information", "廠商已提出補充問題")
                self.set_progress(
                    request, "waiting_resident_information", waiting_for="resident"
                )
                assistant = self.append_assistant(
                    request["conversationId"],
                    f"廠商想再確認一件事：{message}",
                    agent=flow.agent_name,
                )
                return {
                    "serviceRequestId": request["serviceRequestId"],
                    "progress": self._progress_projection(request),
                    "assistantMessage": assistant,
                }

            if action == "decline":
                self.event(request, "provider_declined", message or "廠商婉拒")
                return self._rematch(request, reason="provider_declined")

            provider = self.provider_of(request, provider_id)
            final_content = self._apply_accept(flow, request, provider, payload)
            self.touch(request)
            self.event(request, "provider_confirmed", "廠商已確認到場時段")
            self.set_progress(request, "provider_confirmed", waiting_for=None)
            assistant = self.append_assistant(
                request["conversationId"],
                final_content,
                agent=flow.agent_name,
                kind="final",
            )
            return {
                "serviceRequestId": request["serviceRequestId"],
                "progress": self._progress_projection(request),
                "provider": _public_provider(provider),
                "assistantMessage": assistant,
            }

    def _apply_timeout(self, task_id: str, admin_id: str, reason: str) -> dict[str, Any]:
        with self.store.lock:
            task = self.store.tasks.get(task_id)
            if not task:
                raise NotFoundError("找不到廠商任務")
            if task["status"] != "pending":
                raise ConflictError("只有等待中的任務可以模擬逾時")
            task["status"] = "expired"
            task["version"] += 1
            task["completedAt"] = _now()
            request = self.store.service_requests[task["serviceRequestId"]]
            self.event(
                request,
                "admin_simulated_timeout",
                f"ADMIN {admin_id} 模擬逾時：{reason}",
            )
            return self._rematch(request, reason="admin_simulated_timeout")

    def _rematch(self, request: dict[str, Any], reason: str) -> dict[str, Any]:
        request["candidateIndex"] += 1
        if request["candidateIndex"] >= len(request["candidateProviderIds"]):
            self.set_progress(request, "rematching", waiting_for="admin")
            raise ConflictError("候選廠商已用完，需要管理員人工處理")
        provider_id = request["candidateProviderIds"][request["candidateIndex"]]
        request["currentProviderId"] = provider_id
        self.touch(request)
        task = self._create_provider_task(request, provider_id, reason=reason)
        self.event(request, "provider_rematched", "已依原排序改派下一位廠商")
        self.set_progress(request, "waiting_provider_response", waiting_for="provider")
        return {
            "serviceRequestId": request["serviceRequestId"],
            "progress": self._progress_projection(request),
            "providerTask": task,
        }

    def _create_provider_task(
        self, request: dict[str, Any], provider_id: str, *, reason: str
    ) -> dict[str, Any]:
        self.provider_of(request, provider_id)
        task_id = _id("task")
        task = {
            "taskId": task_id,
            "serviceRequestId": request["serviceRequestId"],
            "providerId": provider_id,
            "status": "pending",
            "version": 1,
            "reason": reason,
            "createdAt": _now(),
            "completedAt": None,
        }
        self.store.tasks[task_id] = task
        request["currentTaskId"] = task_id
        return self._task_projection(task)

    # ------------------------------------------------------------------
    # Projections
    # ------------------------------------------------------------------

    # Public aliases so flow implementations can build responses without
    # reaching into private methods.
    def progress_projection(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._progress_projection(request)

    def service_request_projection(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._service_request_projection(request)

    def _task_projection(self, task: dict[str, Any]) -> dict[str, Any]:
        request = self.store.service_requests[task["serviceRequestId"]]
        artifact = self.store.artifacts.get(request["serviceRequestId"])
        return {
            "taskId": task["taskId"],
            "serviceRequestId": task["serviceRequestId"],
            "status": task["status"],
            "version": task["version"],
            "createdAt": task["createdAt"],
            "provider": _public_provider(
                self.provider_of(request, task["providerId"])
            ),
            "brief": (
                {
                    "version": artifact["version"],
                    "summary": artifact["summary"],
                    "serviceType": artifact["serviceType"],
                }
                if artifact
                else None
            ),
            "residentInformation": request.get("providerAnswer"),
        }

    def _service_request_projection(self, request: dict[str, Any]) -> dict[str, Any]:
        flow = self._flow_for(request)
        artifact = self.store.artifacts.get(request["serviceRequestId"])
        provider = (
            _public_provider(self.provider_of(request, request["currentProviderId"]))
            if request.get("currentProviderId")
            else None
        )
        return {
            "serviceRequestId": request["serviceRequestId"],
            "conversationId": request["conversationId"],
            "serviceType": request["serviceType"],
            "serviceName": flow.service_name,
            "summary": (
                artifact["summary"] if artifact else flow.fallback_summary(request)
            ),
            "provider": provider,
            "progress": self._progress_projection(request),
            "createdAt": request["createdAt"],
            "updatedAt": request["updatedAt"],
            **flow.projection_fields(request),
        }

    def _progress_projection(self, request: dict[str, Any]) -> dict[str, Any]:
        progress = self.store.progress[request["serviceRequestId"]]
        events = self.store.events.get(request["serviceRequestId"], [])
        return {
            **progress,
            "events": list(events[-8:]),
            "currentProvider": (
                _public_provider(self.provider_of(request, request["currentProviderId"]))
                if request.get("currentProviderId")
                else None
            ),
        }

    # ------------------------------------------------------------------
    # Authorization helpers
    # ------------------------------------------------------------------

    def _conversation_for_resident(
        self, conversation_id: str, resident_id: str
    ) -> dict[str, Any]:
        conversation = self.store.conversations.get(conversation_id)
        if not conversation:
            raise NotFoundError("找不到對話")
        if conversation["residentId"] != resident_id:
            raise ForbiddenError()
        return conversation

    def _request_for_resident(
        self, request_id: str, resident_id: str
    ) -> dict[str, Any]:
        request = self.store.service_requests.get(request_id)
        if not request:
            raise NotFoundError("找不到服務需求")
        if request["residentId"] != resident_id:
            raise ForbiddenError()
        return request

    @staticmethod
    def _message(
        conversation_id: str,
        role: str,
        content: str,
        *,
        agent: str | None = None,
        kind: str = "message",
    ) -> dict[str, Any]:
        return {
            "messageId": _id("msg"),
            "conversationId": conversation_id,
            "role": role,
            "content": content,
            "agent": agent,
            "kind": kind,
            "createdAt": _now(),
        }
