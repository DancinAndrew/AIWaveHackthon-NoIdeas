from __future__ import annotations

import json
import os
from dataclasses import dataclass
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


class SupervisorOrchestrator(Protocol):
    """Boundary implemented by deterministic local and AgentCore adapters."""

    mode: str

    def delegate(self, message: str) -> Delegation: ...


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
        request_payload = json.dumps(
            {"message": message},
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
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AgentCoreOrchestrationError(
                "AgentCore response is not valid UTF-8 JSON"
            ) from error
        return self._validate_delegation(payload)

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
        if service_type is None and target_agent is None and not trace:
            return Delegation(
                service_type=None,
                target_agent=None,
                mode=self.mode,
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
        )


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
