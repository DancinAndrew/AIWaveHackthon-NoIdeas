"""Single AgentCore Runtime hosting the Supervisor and five logical agents.

The Supervisor keeps routing deterministic; the routed domain agent then runs one
model-backed turn that extracts structured fields and writes the reply. State
mutations stay outside this process: Flask re-validates every extracted field and
owns the workflow state machine, matching and delegation.

The module is loaded flat inside the deployment artifact (``agent_runtime.py`` is
the entrypoint), so sibling modules are imported by plain name after putting this
directory on ``sys.path``. That keeps the same imports working for local tests.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_RUNTIME_DIR = Path(__file__).resolve().parent
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

from bedrock_agentcore.runtime import BedrockAgentCoreApp  # noqa: E402

from domain_reasoning import DomainReasoner, TurnRequest, TurnResult  # noqa: E402
from knowledge import KnowledgeBaseReader  # noqa: E402
from logical_agents import (  # noqa: E402,F401
    LOGICAL_AGENT_REGISTRY,
    LogicalAgent,
)
from model_gate import build_guarded_runtime  # noqa: E402
from routing import (  # noqa: E402
    REASON_AMBIGUOUS,
    REASON_UNSUPPORTED,
    DomainRouter,
)

logger = logging.getLogger(__name__)

AMBIGUOUS_MESSAGE = (
    "我辨識到不只一項服務需求。為了正確建案，請一次先處理一項，"
    "並告訴我你想先處理哪一項。"
)
UNSUPPORTED_MESSAGE = (
    "目前可處理餐廳訂位、商品購買、家事服務、水電修繕與社區服務諮詢。"
    "請從其中一類描述你的需求。"
)
UNROUTED_MESSAGES = {
    REASON_AMBIGUOUS: AMBIGUOUS_MESSAGE,
    REASON_UNSUPPORTED: UNSUPPORTED_MESSAGE,
}

MAX_MESSAGE_LENGTH = 2_000
MAX_HISTORY_ENTRIES = 12
MAX_SERVICE_DISTRICTS = 400
MAX_KNOWN_FIELDS = 40
MAX_MISSING_FIELDS = 20
ORCHESTRATION_MODE = "agentcore-runtime"

TURN_GOALS = frozenset(
    {
        "route_new_request",
        "screen_safety",
        "collect_missing_fields",
        "confirm_brief",
        "answer_progress_question",
        "answer_provider_question",
    }
)
WORKFLOW_STAGES = frozenset(
    {
        "collecting_details",
        "safety_hold",
        "awaiting_resident_confirmation",
        "waiting_provider_response",
        "waiting_resident_information",
        "rematching",
        "provider_confirmed",
    }
)
GOAL_INTENTS = {
    "confirm_brief": "confirm_service_request_brief",
    "answer_progress_question": "answer_status_question",
}


class Supervisor:
    """Select one logical agent, then run that agent's turn."""

    def __init__(
        self,
        registry: Mapping[str, LogicalAgent],
        *,
        reasoner: DomainReasoner | None = None,
        router: DomainRouter | None = None,
    ) -> None:
        self._registry = dict(registry)
        self._reasoner = reasoner or DomainReasoner(
            model_client=None,
            model_id=None,
            knowledge=None,
        )
        self._router = router

    def handle(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        message = payload.get("message")
        if (
            not isinstance(message, str)
            or not message.strip()
            or len(message) > MAX_MESSAGE_LENGTH
        ):
            return _invalid_payload()

        active_agent = payload.get("activeAgent")
        if active_agent is not None:
            if not isinstance(active_agent, str) or active_agent not in self._registry:
                return _invalid_payload("activeAgent is not a registered logical agent")
            return self._delegate(
                agent=self._registry[active_agent],
                payload=payload,
                reason_code="active_agent_continuation",
            )

        matches = [
            agent
            for agent in self._registry.values()
            if any(keyword in message for keyword in agent.keywords)
        ]
        if len(matches) == 1:
            return self._delegate(
                agent=matches[0],
                payload=payload,
                reason_code="domain_keyword_match",
            )
        if len(matches) > 1:
            # Two domains in one sentence is a product decision, not a model one:
            # the resident is asked to split it instead of the model guessing.
            return _unrouted(REASON_AMBIGUOUS)
        return self._classify(message, payload)

    def _classify(self, message: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Route a sentence the keyword table does not cover."""

        if self._router is None:
            return _unrouted(REASON_UNSUPPORTED)

        decision = self._router.classify(message)
        if decision.agent_name is None:
            return _unrouted(decision.reason_code, trace=decision.trace)
        return self._delegate(
            agent=self._registry[decision.agent_name],
            payload=payload,
            reason_code=decision.reason_code,
            leading_trace=decision.trace,
        )

    def _delegate(
        self,
        *,
        agent: LogicalAgent,
        payload: Mapping[str, Any],
        reason_code: str,
        leading_trace: tuple[dict[str, Any], ...] = (),
    ) -> dict[str, Any]:
        request = _turn_request(agent, payload)
        result = self._reasoner.reason(request)
        agent_turn = _agent_turn_payload(agent, request, result)
        trace: list[dict[str, Any]] = list(leading_trace)
        trace.append(
            {
                "actor": "supervisor",
                "action": "tool_call",
                "target": agent.name,
                "reasonCode": reason_code,
            }
        )
        trace.extend(result.trace)
        return {
            "orchestrationMode": ORCHESTRATION_MODE,
            "route": {
                "serviceType": agent.service_type,
                "agent": agent.name,
                "toolName": agent.name,
                "reasonCode": reason_code,
            },
            "trace": trace,
            "agentTurn": agent_turn,
            "assistantMessage": agent_turn["assistantMessage"],
        }


def _turn_request(agent: LogicalAgent, payload: Mapping[str, Any]) -> TurnRequest:
    return TurnRequest(
        message=str(payload["message"]),
        agent=agent,
        session_id=_optional_string(payload.get("sessionId")),
        workflow_stage=_enum_or_none(payload.get("workflowStage"), WORKFLOW_STAGES),
        turn_goal=_enum_or_none(payload.get("turnGoal"), TURN_GOALS),
        known_fields=_known_fields(payload.get("knownFields")),
        missing_fields=_string_tuple(payload.get("missingFields"), MAX_MISSING_FIELDS),
        history=_history(payload.get("history")),
        service_districts=_service_districts(payload.get("serviceScope")),
    )


def _agent_turn_payload(
    agent: LogicalAgent,
    request: TurnRequest,
    result: TurnResult,
) -> dict[str, Any]:
    intent = "collect_service_request_details"
    if result.risk.level == "high" or request.workflow_stage == "safety_hold":
        intent = "hold_for_safety"
    elif request.turn_goal in GOAL_INTENTS:
        intent = GOAL_INTENTS[request.turn_goal]

    workflow_stage = request.workflow_stage or "collecting_details"
    if result.risk.level == "high":
        workflow_stage = "safety_hold"

    return {
        "agent": agent.name,
        "serviceType": agent.service_type,
        "intent": intent,
        "workflowStage": workflow_stage,
        "assistantMessage": result.assistant_message,
        "requiredFields": list(agent.required_fields),
        "missingFields": list(result.missing_fields),
        "allowedTools": list(agent.allowed_tools),
        "extractedFields": dict(result.extracted_fields),
        "riskAssessment": result.risk.to_payload(),
        "knowledge": [reference.to_payload() for reference in result.knowledge],
        "reasoning": result.reasoning.to_payload(),
    }


def _unrouted(
    reason_code: str,
    *,
    trace: tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    return {
        "orchestrationMode": ORCHESTRATION_MODE,
        "route": {
            "serviceType": None,
            "agent": None,
            "toolName": None,
            "reasonCode": reason_code,
        },
        "trace": list(trace),
        "assistantMessage": UNROUTED_MESSAGES[reason_code],
    }


def build_components_from_environment() -> tuple[DomainReasoner, DomainRouter | None]:
    """Build the reasoner and router from injected configuration.

    Missing configuration is a degraded but honest mode rather than a crash: the
    runtime still routes on keywords, completes turns with deterministic rules and
    reports ``rule-fallback``.  One Bedrock Runtime client is shared so both the
    classification and the turn request pass through the same process gate.
    """

    region = os.getenv("AWS_REGION", "us-west-2").strip() or "us-west-2"
    model_id = os.getenv("BEDROCK_MODEL_ID", "").strip()
    knowledge_base_id = os.getenv("KNOWLEDGE_BASE_ID", "").strip()

    model_client = None
    knowledge = None
    router = None
    if model_id:
        client = _boto3_client("bedrock-runtime", region)
        if client is not None:
            model_client = build_guarded_runtime(client)
            router = DomainRouter(
                model_client=model_client,
                model_id=model_id,
                registry=LOGICAL_AGENT_REGISTRY,
            )
    if knowledge_base_id:
        client = _boto3_client("bedrock-agent-runtime", region)
        if client is not None:
            knowledge = KnowledgeBaseReader(
                client=client,
                knowledge_base_id=knowledge_base_id,
            )
    reasoner = DomainReasoner(
        model_client=model_client,
        model_id=model_id or None,
        knowledge=knowledge,
    )
    return reasoner, router


def _boto3_client(service_name: str, region: str) -> Any | None:
    try:
        import boto3
        from botocore.config import Config

        return boto3.client(
            service_name,
            region_name=region,
            # SDK retries stay off so every attempt re-enters the shared gate.
            config=Config(
                retries={"total_max_attempts": 1, "mode": "standard"},
                connect_timeout=5,
                read_timeout=25,
            ),
        )
    except Exception as error:  # noqa: BLE001 - degrade instead of failing the turn
        logger.warning(
            "could not create %s client error_type=%s",
            service_name,
            type(error).__name__,
        )
        return None


_REASONER, _ROUTER = build_components_from_environment()
SUPERVISOR = Supervisor(
    LOGICAL_AGENT_REGISTRY,
    reasoner=_REASONER,
    router=_ROUTER,
)
app = BedrockAgentCoreApp()


def handle_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Pure runtime boundary used by AgentCore and local contract tests."""

    if not isinstance(payload, Mapping):
        return _invalid_payload("payload must be an object")
    return SUPERVISOR.handle(payload)


@app.entrypoint
def invoke(payload: dict[str, Any]) -> dict[str, Any]:
    """AgentCore HTTP entrypoint."""

    return handle_request(payload)


def _invalid_payload(
    message: str = "message must be a non-empty string up to 2000 characters",
) -> dict[str, Any]:
    return {"error": {"code": "invalid_runtime_payload", "message": message}}


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _enum_or_none(value: Any, allowed: frozenset[str]) -> str | None:
    return value if isinstance(value, str) and value in allowed else None


def _known_fields(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    fields: dict[str, Any] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or len(fields) >= MAX_KNOWN_FIELDS:
            continue
        if isinstance(raw, (str, int, float, bool)) or raw is None:
            fields[key] = raw
        elif isinstance(raw, Mapping):
            fields[key] = {
                str(inner_key): inner_value
                for inner_key, inner_value in raw.items()
                if isinstance(inner_value, (str, int, float, bool))
            }
    return fields


def _string_tuple(value: Any, limit: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        item.strip()[:100]
        for item in value[:limit]
        if isinstance(item, str) and item.strip()
    )


def _history(value: Any) -> tuple[Mapping[str, str], ...]:
    if not isinstance(value, list):
        return ()
    entries: list[Mapping[str, str]] = []
    for raw in value[-MAX_HISTORY_ENTRIES:]:
        if not isinstance(raw, Mapping):
            continue
        role = raw.get("role")
        content = raw.get("content")
        if role not in {"resident", "agent"}:
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        entries.append({"role": role, "content": content[:MAX_MESSAGE_LENGTH]})
    return tuple(entries)


def _service_districts(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        return ()
    return _string_tuple(value.get("districts"), MAX_SERVICE_DISTRICTS)


if __name__ == "__main__":
    app.run()
