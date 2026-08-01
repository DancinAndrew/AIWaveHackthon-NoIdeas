"""Single AgentCore Runtime hosting the Supervisor and five logical agents.

The module keeps routing and agent contracts deterministic at the application
boundary.  Nova can later replace the selector without changing the response
shape; state mutations remain restricted to AgentCore Gateway tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from bedrock_agentcore.runtime import BedrockAgentCoreApp


MAX_MESSAGE_LENGTH = 2_000
ORCHESTRATION_MODE = "agentcore-runtime"


@dataclass(frozen=True, slots=True)
class LogicalAgent:
    """In-process domain agent exposed to the Supervisor as a typed tool."""

    name: str
    service_type: str
    keywords: tuple[str, ...]
    assistant_message: str
    required_fields: tuple[str, ...]
    allowed_tools: tuple[str, ...]

    def invoke(
        self,
        *,
        workflow_stage: str | None,
    ) -> dict[str, Any]:
        return {
            "agent": self.name,
            "serviceType": self.service_type,
            "intent": "collect_service_request_details",
            "workflowStage": workflow_stage or "collecting_details",
            "assistantMessage": self.assistant_message,
            "requiredFields": list(self.required_fields),
            "allowedTools": list(self.allowed_tools),
        }


LOGICAL_AGENT_REGISTRY: dict[str, LogicalAgent] = {
    "restaurant_agent": LogicalAgent(
        name="restaurant_agent",
        service_type="restaurant_reservation",
        keywords=("餐廳", "訂位", "訂桌", "用餐", "聚餐"),
        assistant_message=(
            "我已接手餐廳訂位需求。請先告訴我日期、時段、人數與偏好的地區或料理。"
        ),
        required_fields=("date", "timeWindow", "partySize", "area", "cuisine"),
        allowed_tools=("knowledge_base_search", "service_request"),
    ),
    "product_agent": LogicalAgent(
        name="product_agent",
        service_type="product_purchase",
        keywords=("購買", "買", "商品", "下單", "餐券", "採買"),
        assistant_message=(
            "我已接手商品購買需求。請告訴我商品、數量、預算與希望收到的時間。"
        ),
        required_fields=("product", "quantity", "budget", "deliveryWindow"),
        allowed_tools=("knowledge_base_search", "service_request"),
    ),
    "housekeeping_agent": LogicalAgent(
        name="housekeeping_agent",
        service_type="housekeeping_service",
        keywords=("家事", "打掃", "清潔", "居家整理", "收納"),
        assistant_message=(
            "我已接手家事服務需求。請告訴我服務地區、空間大小、項目與希望時段。"
        ),
        required_fields=("district", "spaceSize", "tasks", "preferredTime"),
        allowed_tools=("knowledge_base_search", "service_request"),
    ),
    "utility_repair_agent": LogicalAgent(
        name="utility_repair_agent",
        service_type="utility_repair",
        keywords=(
            "水電",
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
        ),
        assistant_message=(
            "我已接手水電修繕需求。先確認安全：現場是否有漏電、裸線、冒煙焦味，"
            "或水已接近插座、形成大量積水？"
        ),
        required_fields=(
            "riskScreening",
            "issueType",
            "symptoms",
            "district",
            "preferredTime",
        ),
        allowed_tools=(
            "knowledge_base_search",
            "service_request",
            "provider_matching",
        ),
    ),
    "community_service_agent": LogicalAgent(
        name="community_service_agent",
        service_type="community_consultation",
        keywords=("社區", "管委會", "規約", "管理費", "公設", "管理中心"),
        assistant_message=(
            "我已接手社區服務諮詢。請告訴我想詢問的主題、社區範圍與希望處理的期限。"
        ),
        required_fields=("topic", "communityScope", "desiredResolutionDate"),
        allowed_tools=("knowledge_base_search", "service_request"),
    ),
}


class Supervisor:
    """Select one logical agent and record the tool delegation trace."""

    def __init__(self, registry: Mapping[str, LogicalAgent]) -> None:
        self._registry = dict(registry)

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
                workflow_stage=_optional_string(payload.get("workflowStage")),
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
                workflow_stage=_optional_string(payload.get("workflowStage")),
                reason_code="domain_keyword_match",
            )
        if len(matches) > 1:
            return {
                "orchestrationMode": ORCHESTRATION_MODE,
                "route": {
                    "serviceType": None,
                    "agent": None,
                    "toolName": None,
                    "reasonCode": "ambiguous_domains",
                },
                "trace": [],
                "assistantMessage": (
                    "我辨識到不只一項服務需求。為了正確建案，請一次先處理一項，"
                    "並告訴我你想先處理哪一項。"
                ),
            }
        return {
            "orchestrationMode": ORCHESTRATION_MODE,
            "route": {
                "serviceType": None,
                "agent": None,
                "toolName": None,
                "reasonCode": "unsupported_domain",
            },
            "trace": [],
            "assistantMessage": (
                "目前可處理餐廳訂位、商品購買、家事服務、水電修繕與社區服務諮詢。"
                "請從其中一類描述你的需求。"
            ),
        }

    def _delegate(
        self,
        *,
        agent: LogicalAgent,
        workflow_stage: str | None,
        reason_code: str,
    ) -> dict[str, Any]:
        agent_turn = agent.invoke(workflow_stage=workflow_stage)
        return {
            "orchestrationMode": ORCHESTRATION_MODE,
            "route": {
                "serviceType": agent.service_type,
                "agent": agent.name,
                "toolName": agent.name,
                "reasonCode": reason_code,
            },
            "trace": [
                {
                    "actor": "supervisor",
                    "action": "tool_call",
                    "target": agent.name,
                    "reasonCode": reason_code,
                }
            ],
            "agentTurn": agent_turn,
            "assistantMessage": agent_turn["assistantMessage"],
        }


SUPERVISOR = Supervisor(LOGICAL_AGENT_REGISTRY)
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


if __name__ == "__main__":
    app.run()
