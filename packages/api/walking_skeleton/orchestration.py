from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Any, Protocol

from bedrock_safety import DEFAULT_BEDROCK_REQUEST_GATE, BedrockRequestGate


MAX_RUNTIME_RESPONSE_BYTES = 1_000_000
APPROVED_ROUTES = frozenset(
    {
        ("restaurant_reservation", "restaurant_agent"),
        ("product_purchase", "product_agent"),
        ("housekeeping_service", "housekeeping_agent"),
        ("utility_repair", "utility_repair_agent"),
        ("community_consultation", "community_service_agent"),
    }
)


APPROVED_REASON_CODES = frozenset(
    {
        "domain_keyword_match",
        "model_classification",
        "active_agent_continuation",
        "ambiguous_domains",
        "unsupported_domain",
    }
)
_SERVICE_TYPE_BY_AGENT = {agent: service for service, agent in APPROVED_ROUTES}

# Reason codes that legitimately carry no route. The Supervisor answers with one
# of these instead of guessing a domain, so they are a normal outcome rather than
# a protocol failure.
UNROUTED_REASON_CODES = frozenset({"ambiguous_domains", "unsupported_domain"})

MAX_HISTORY_ENTRIES = 12
MAX_ASSISTANT_MESSAGE_LENGTH = 2_000
MAX_KNOWLEDGE_REFERENCES = 5
MAX_LIVE_VALUE_TOPICS = 10
MAX_SUPPRESSED_KNOWLEDGE_RECORDS = 10


@dataclass(frozen=True, slots=True)
class Delegation:
    """Supervisor decision consumed by the transport-independent core.

    `needs_clarification` distinguishes "I could not route this" from "this
    could be two different services". Only the latter should ask the resident to
    choose; silently picking one would create a case in the wrong domain.
    """

    service_type: str | None
    target_agent: str | None
    mode: str
    needs_clarification: bool = False
    candidate_service_types: tuple[str, ...] = ()
    # Why the Supervisor chose this route. Surfaced so the demo can distinguish a
    # keyword hit from a model classification instead of both looking identical.
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class AgentTurnRequest:
    """One turn of resident input, described for the routed domain agent."""

    message: str
    active_agent: str | None = None
    workflow_stage: str | None = None
    turn_goal: str | None = None
    known_fields: Mapping[str, Any] = field(default_factory=dict)
    missing_fields: tuple[str, ...] = ()
    history: tuple[Mapping[str, str], ...] = ()
    service_districts: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"message": self.message}
        if self.active_agent:
            payload["activeAgent"] = self.active_agent
        if self.workflow_stage:
            payload["workflowStage"] = self.workflow_stage
        if self.turn_goal:
            payload["turnGoal"] = self.turn_goal
        if self.known_fields:
            payload["knownFields"] = dict(self.known_fields)
        if self.missing_fields:
            payload["missingFields"] = list(self.missing_fields)
        if self.history:
            payload["history"] = [
                dict(entry) for entry in self.history[-MAX_HISTORY_ENTRIES:]
            ]
        if self.service_districts:
            payload["serviceScope"] = {"districts": list(self.service_districts)}
        return payload


@dataclass(frozen=True, slots=True)
class AgentTurn:
    """Validated per-turn understanding returned by the routed domain agent.

    ``extracted_fields`` is model output. It has already been validated against
    the runtime contract, and the application service validates it again field by
    field before any of it reaches stored state.
    """

    service_type: str | None
    target_agent: str | None
    mode: str
    assistant_message: str | None = None
    extracted_fields: Mapping[str, Any] = field(default_factory=dict)
    risk_level: str = "none"
    risk_source: str = "none"
    knowledge: tuple[Mapping[str, Any], ...] = ()
    reasoning_mode: str = "rule-fallback"
    model_id: str | None = None
    knowledge_base_queried: bool = False
    live_value_topics: tuple[str, ...] = ()
    suppressed_knowledge: tuple[Mapping[str, Any], ...] = ()
    # Mirrored from the routing decision. `turn()` is the only call the routing
    # path makes now, so dropping these here would silently disable the
    # "this could be two services, ask first" branch.
    needs_clarification: bool = False
    candidate_service_types: tuple[str, ...] = ()
    reason_code: str | None = None

    @property
    def model_backed(self) -> bool:
        return self.reasoning_mode == "model"


class SupervisorOrchestrator(Protocol):
    """Boundary implemented by deterministic local and AgentCore adapters."""

    mode: str

    def delegate(self, message: str) -> Delegation: ...

    def turn(self, request: AgentTurnRequest) -> AgentTurn: ...


class AgentCoreRuntimeClient(Protocol):
    def invoke_agent_runtime(self, **kwargs: Any) -> Mapping[str, Any]: ...


class AgentCoreOrchestrationError(RuntimeError):
    """Raised when staging cannot prove the formal AgentCore delegation."""


class DeterministicDemoOrchestrator:
    """Offline fallback with an explicit, non-AgentCore execution label."""

    mode = "deterministic-demo"

    # Symptom vocabulary: something is broken and needs fixing.
    _utility_terms = (
        "水管",
        "漏水",
        "水龍頭",
        "馬桶",
        "排水",
        "插座",
        "跳電",
        "電線",
        "冒煙",
        "火花",
        "熱水器",
        "水電",
        "修繕",
        "維修",
        # Failure verbs rather than appliance nouns. "想買冷氣" must stay a pure
        # purchase, while "冷氣壞了想買新的" must be treated as ambiguous.
        "壞了",
        "壞掉",
        "故障",
        "不會動",
        "沒反應",
    )

    # Purchase-intent vocabulary. Deliberately intent verbs rather than the 38
    # catalogue item types: the product flow resolves the item type from the
    # catalogue, so the supervisor does not need to know the product vocabulary.
    _product_terms = (
        "買",
        "購買",
        "採購",
        "訂購",
        "選購",
        "下單",
        "有沒有賣",
        "缺貨",
        "到貨",
        "運費",
        "宅配",
        "超商取貨",
    )

    def delegate(self, message: str) -> Delegation:
        utility = any(term in message for term in self._utility_terms)
        product = any(term in message for term in self._product_terms)

        if utility and product:
            # e.g. 「冷氣壞了想直接買一台新的還是修比較好」. Choosing one here would
            # create a case the resident never asked for, so ask instead.
            return Delegation(
                service_type=None,
                target_agent=None,
                mode=self.mode,
                needs_clarification=True,
                candidate_service_types=("utility_repair", "product_purchase"),
            )
        if utility:
            return Delegation(
                service_type="utility_repair",
                target_agent="utility_repair_agent",
                mode=self.mode,
            )
        if product:
            return Delegation(
                service_type="product_purchase",
                target_agent="product_agent",
                mode=self.mode,
            )
        return Delegation(service_type=None, target_agent=None, mode=self.mode)

    def turn(self, request: AgentTurnRequest) -> AgentTurn:
        """Route only. No model runs offline, so no fields are extracted.

        The application service falls back to its own deterministic extractors,
        which keeps the offline demo working without claiming a model was used.
        """

        if request.active_agent:
            # A turn inside an existing case never re-routes. The active agent is
            # authoritative, so the keyword table must not pull the resident into
            # another domain mid-conversation.
            return AgentTurn(
                service_type=_SERVICE_TYPE_BY_AGENT.get(request.active_agent),
                target_agent=request.active_agent,
                mode=self.mode,
                reasoning_mode="rule-fallback",
                reason_code="active_agent_continuation",
            )
        delegation = self.delegate(request.message)
        return AgentTurn(
            service_type=delegation.service_type,
            target_agent=delegation.target_agent,
            mode=self.mode,
            reasoning_mode="rule-fallback",
            needs_clarification=delegation.needs_clarification,
            candidate_service_types=delegation.candidate_service_types,
            reason_code=(
                "ambiguous_domains"
                if delegation.needs_clarification
                else "domain_keyword_match"
                if delegation.target_agent
                else "unsupported_domain"
            ),
        )


class AgentCoreSupervisorOrchestrator:
    """Invoke the staging Runtime and validate its Supervisor tool trace."""

    mode = "agentcore-runtime"

    def __init__(
        self,
        *,
        client: AgentCoreRuntimeClient,
        runtime_arn: str,
        qualifier: str = "staging",
        request_gate: BedrockRequestGate = DEFAULT_BEDROCK_REQUEST_GATE,
    ) -> None:
        if not runtime_arn:
            raise AgentCoreOrchestrationError("AgentCore runtime ARN is required")
        self._client = client
        self._runtime_arn = runtime_arn
        self._qualifier = qualifier
        self._request_gate = request_gate

    def delegate(self, message: str) -> Delegation:
        payload = self._invoke({"message": message})
        return self._validate_delegation(payload)

    def turn(self, request: AgentTurnRequest) -> AgentTurn:
        """Run one domain agent turn in the Runtime and validate what comes back.

        Routing validation stays fail-closed. The per-turn understanding is
        additive: a Runtime that cannot produce it still yields a usable turn that
        honestly reports ``rule-fallback``.
        """

        payload = self._invoke(request.to_payload())
        delegation = self._validate_delegation(payload)
        return _agent_turn_from_payload(payload, delegation)

    def _invoke(self, request_body: Mapping[str, Any]) -> object:
        request_payload = json.dumps(
            request_body,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            response = self._request_gate.invoke(
                self._client.invoke_agent_runtime,
                agentRuntimeArn=self._runtime_arn,
                qualifier=self._qualifier,
                contentType="application/json",
                accept="application/json",
                payload=request_payload,
            )
        except Exception as error:
            raise AgentCoreOrchestrationError(
                f"AgentCore invocation failed ({type(error).__name__})"
            ) from error
        if response.get("statusCode") != 200:
            raise AgentCoreOrchestrationError("AgentCore returned a non-200 status")
        body = response.get("response")
        if not hasattr(body, "read"):
            raise AgentCoreOrchestrationError("AgentCore response body is missing")
        raw_body = body.read(MAX_RUNTIME_RESPONSE_BYTES + 1)
        if not isinstance(raw_body, bytes) or len(raw_body) > MAX_RUNTIME_RESPONSE_BYTES:
            raise AgentCoreOrchestrationError("AgentCore response body is invalid or too large")
        try:
            return json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AgentCoreOrchestrationError(
                "AgentCore response is not valid UTF-8 JSON"
            ) from error

    def _validate_delegation(self, payload: object) -> Delegation:
        if not isinstance(payload, Mapping):
            raise AgentCoreOrchestrationError("AgentCore response must be an object")
        if payload.get("orchestrationMode") != self.mode:
            raise AgentCoreOrchestrationError("AgentCore response mode is not formal runtime")
        route = payload.get("route")
        trace = payload.get("trace")
        if not isinstance(route, Mapping) or not isinstance(trace, list):
            raise AgentCoreOrchestrationError("AgentCore route or trace is malformed")
        service_type = route.get("serviceType")
        target_agent = route.get("agent")
        reason_code = route.get("reasonCode")
        if reason_code is not None and reason_code not in APPROVED_REASON_CODES:
            raise AgentCoreOrchestrationError("AgentCore reported an unapproved reason code")
        if service_type is None and target_agent is None:
            # An unrouted turn is a legitimate answer, not a malformed response.
            # The model classification path attaches a `model_invoke` trace entry
            # even when it declines to route, so requiring an empty trace here
            # rejected valid "ambiguous" and "unsupported" replies and turned an
            # honest clarification into a 500.
            if reason_code in UNROUTED_REASON_CODES or not trace:
                return Delegation(
                    service_type=None,
                    target_agent=None,
                    mode=self.mode,
                    needs_clarification=reason_code == "ambiguous_domains",
                    reason_code=reason_code,
                )
            raise AgentCoreOrchestrationError(
                "AgentCore returned no route without an approved reason code"
            )
        if (service_type, target_agent) not in APPROVED_ROUTES:
            raise AgentCoreOrchestrationError("AgentCore selected an unapproved route")
        has_supervisor_tool_call = any(
            isinstance(item, Mapping)
            and item.get("actor") == "supervisor"
            and item.get("action") == "tool_call"
            and item.get("target") == target_agent
            for item in trace
        )
        if not has_supervisor_tool_call:
            raise AgentCoreOrchestrationError(
                "AgentCore did not provide a matching Supervisor tool trace"
            )
        return Delegation(
            service_type=str(service_type),
            target_agent=str(target_agent),
            mode=self.mode,
            reason_code=reason_code,
        )


def _agent_turn_from_payload(payload: object, delegation: Delegation) -> AgentTurn:
    """Project the runtime response onto the application-facing turn value."""

    agent_turn = payload.get("agentTurn") if isinstance(payload, Mapping) else None
    if not isinstance(agent_turn, Mapping):
        # An unrouted turn has no agentTurn by design, so this is also the path
        # that carries a clarification back to the caller.
        return AgentTurn(
            service_type=delegation.service_type,
            target_agent=delegation.target_agent,
            mode=delegation.mode,
            reasoning_mode="rule-fallback",
            needs_clarification=delegation.needs_clarification,
            candidate_service_types=delegation.candidate_service_types,
            reason_code=delegation.reason_code,
        )

    reasoning = agent_turn.get("reasoning")
    reasoning = reasoning if isinstance(reasoning, Mapping) else {}
    reasoning_mode = reasoning.get("mode")
    if reasoning_mode not in {"model", "rule-fallback"}:
        reasoning_mode = "rule-fallback"

    risk = agent_turn.get("riskAssessment")
    risk = risk if isinstance(risk, Mapping) else {}
    risk_level = risk.get("level") if risk.get("level") in {"none", "high"} else "none"
    risk_source = (
        risk.get("source")
        if risk.get("source") in {"none", "model", "deterministic", "both"}
        else "none"
    )

    extracted = agent_turn.get("extractedFields")
    extracted = dict(extracted) if isinstance(extracted, Mapping) else {}

    assistant_message = agent_turn.get("assistantMessage")
    if not isinstance(assistant_message, str) or not assistant_message.strip():
        assistant_message = None
    else:
        assistant_message = assistant_message.strip()[:MAX_ASSISTANT_MESSAGE_LENGTH]

    return AgentTurn(
        service_type=delegation.service_type,
        target_agent=delegation.target_agent,
        mode=delegation.mode,
        assistant_message=assistant_message,
        extracted_fields=extracted,
        risk_level=risk_level,
        risk_source=risk_source,
        knowledge=_knowledge_references(agent_turn.get("knowledge")),
        reasoning_mode=reasoning_mode,
        model_id=(
            reasoning.get("modelId")
            if isinstance(reasoning.get("modelId"), str)
            else None
        ),
        knowledge_base_queried=reasoning.get("knowledgeBaseQueried") is True,
        live_value_topics=_bounded_strings(reasoning.get("liveValueTopics")),
        suppressed_knowledge=_suppressed_knowledge(
            reasoning.get("suppressedKnowledge")
        ),
        needs_clarification=delegation.needs_clarification,
        candidate_service_types=delegation.candidate_service_types,
        reason_code=delegation.reason_code,
    )


def _bounded_strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        item.strip()[:60]
        for item in value[:MAX_LIVE_VALUE_TOPICS]
        if isinstance(item, str) and item.strip()
    )


def _suppressed_knowledge(value: object) -> tuple[Mapping[str, Any], ...]:
    """Keep the audit record only. The withheld excerpt must never travel."""

    if not isinstance(value, list):
        return ()
    records: list[Mapping[str, Any]] = []
    for raw in value[:MAX_SUPPRESSED_KNOWLEDGE_RECORDS]:
        if not isinstance(raw, Mapping):
            continue
        reason = raw.get("reason")
        doc_kind = raw.get("docKind")
        if not isinstance(reason, str) or not reason.strip():
            continue
        records.append(
            {
                "sourceDocId": (
                    raw.get("sourceDocId")
                    if isinstance(raw.get("sourceDocId"), str)
                    else None
                ),
                "docKind": doc_kind if isinstance(doc_kind, str) else "unspecified",
                "reason": reason.strip()[:200],
            }
        )
    return tuple(records)


def _knowledge_references(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    references: list[Mapping[str, Any]] = []
    for raw in value[:MAX_KNOWLEDGE_REFERENCES]:
        if not isinstance(raw, Mapping):
            continue
        excerpt = raw.get("excerpt")
        if not isinstance(excerpt, str) or not excerpt.strip():
            continue
        references.append(
            {
                "serviceType": raw.get("serviceType"),
                "docKind": raw.get("docKind"),
                "sourceDocId": raw.get("sourceDocId"),
                "excerpt": excerpt.strip(),
            }
        )
    return tuple(references)


def create_orchestrator_from_environment() -> SupervisorOrchestrator:
    """Select the honest local fallback or the formal staging Runtime."""

    mode = os.getenv("ORCHESTRATION_MODE", "deterministic-demo").strip().lower()
    if mode == "deterministic-demo":
        return DeterministicDemoOrchestrator()
    if mode != "agentcore-runtime":
        raise AgentCoreOrchestrationError(
            f"unsupported ORCHESTRATION_MODE: {mode!r}"
        )
    runtime_arn = os.getenv("AGENT_RUNTIME_ARN", "").strip()
    qualifier = os.getenv("AGENT_RUNTIME_QUALIFIER", "staging").strip()
    if not runtime_arn:
        raise AgentCoreOrchestrationError(
            "AGENT_RUNTIME_ARN is required in AgentCore mode"
        )

    import boto3
    from botocore.config import Config

    client = boto3.client(
        "bedrock-agentcore",
        region_name=os.getenv("AWS_REGION", "us-west-2"),
        config=Config(
            retries={"total_max_attempts": 1, "mode": "standard"},
            connect_timeout=5,
            read_timeout=25,
        ),
    )
    return AgentCoreSupervisorOrchestrator(
        client=client,
        runtime_arn=runtime_arn,
        qualifier=qualifier,
    )
