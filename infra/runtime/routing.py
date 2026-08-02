"""Supervisor domain classification for sentences the keyword table misses.

Routing stays deterministic wherever it can be: an exact keyword hit or an active
agent never spends a model call. Only an unmatched first sentence is classified
by the approved model, and the result is fail-closed — anything outside the five
approved service types becomes the existing clarification or unsupported reply,
never an invented domain.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from logical_agents import LogicalAgent
from model_gate import BedrockSafetyError

logger = logging.getLogger(__name__)

ROUTE_TOOL_NAME = "record_service_type_classification"
AMBIGUOUS = "ambiguous"
UNSUPPORTED = "unsupported"
MAX_OUTPUT_TOKENS = 120
MODEL_TEMPERATURE = 0.0

REASON_MODEL_CLASSIFICATION = "model_classification"
REASON_AMBIGUOUS = "ambiguous_domains"
REASON_UNSUPPORTED = "unsupported_domain"

ROUTER_INSTRUCTIONS = (
    "你是台灣社區生活管家平台的 Supervisor，只負責把住戶的一句需求分類到"
    "正好一個服務類別。\n"
    "類別定義：\n"
    "- restaurant_reservation：餐廳訂位、訂桌、聚餐安排。\n"
    "- product_purchase：購買商品、下單、採買、預購。\n"
    "- housekeeping_service：居家清潔、打掃、收納、家事服務。\n"
    "- utility_repair：水電修繕，包含漏水、滴水、排水不通、馬桶、熱水器、"
    "插座、跳電、電線等設備故障。\n"
    "- community_consultation：社區與管委會相關諮詢，例如規約、管理費、公設。\n"
    "規則：\n"
    "1. 住戶用口語或不完整的說法也要判斷，例如「水槽下面在滴水」屬於 utility_repair。\n"
    "2. 同時涉及兩個以上類別時回 ambiguous。\n"
    "3. 五類都不符合時回 unsupported，不要勉強挑一個最接近的。\n"
    "4. 只能透過提供的工具輸出結果。\n"
)


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """Classification outcome consumed by the Supervisor."""

    agent_name: str | None
    reason_code: str
    trace: tuple[dict[str, Any], ...] = ()


class DomainRouter:
    """Classify one unmatched resident sentence into an approved domain."""

    def __init__(
        self,
        *,
        model_client: Any | None,
        model_id: str | None,
        registry: Mapping[str, LogicalAgent],
    ) -> None:
        self._model_client = model_client
        self._model_id = (model_id or "").strip() or None
        self._agent_by_service_type = {
            agent.service_type: agent.name for agent in registry.values()
        }

    @property
    def available(self) -> bool:
        return self._model_client is not None and self._model_id is not None

    def classify(self, message: str) -> RouteDecision:
        if not self.available:
            return RouteDecision(agent_name=None, reason_code=REASON_UNSUPPORTED)

        entry: dict[str, Any] = {
            "actor": "supervisor",
            "action": "model_invoke",
            "target": self._model_id,
            "reasonCode": "domain_classification",
        }

        try:
            response = self._model_client.converse(
                modelId=self._model_id,
                system=[{"text": ROUTER_INSTRUCTIONS}],
                messages=[{"role": "user", "content": [{"text": message}]}],
                inferenceConfig={
                    "maxTokens": MAX_OUTPUT_TOKENS,
                    "temperature": MODEL_TEMPERATURE,
                },
                toolConfig=self._tool_config(),
            )
        except BedrockSafetyError:
            logger.warning("classification rejected by the shared bedrock gate")
            entry["outcome"] = "failed"
            return RouteDecision(None, REASON_UNSUPPORTED, (entry,))
        except Exception as error:  # noqa: BLE001 - never fail the whole turn
            logger.warning(
                "domain classification failed error_type=%s", type(error).__name__
            )
            entry["outcome"] = "failed"
            return RouteDecision(None, REASON_UNSUPPORTED, (entry,))

        service_type = _classified_service_type(response)
        if service_type == AMBIGUOUS:
            entry["outcome"] = "ok"
            return RouteDecision(None, REASON_AMBIGUOUS, (entry,))

        agent_name = self._agent_by_service_type.get(service_type or "")
        if agent_name is None:
            # Includes the explicit "unsupported" answer, a missing tool call and
            # any value outside the approved allowlist.
            entry["outcome"] = "empty" if service_type == UNSUPPORTED else "failed"
            return RouteDecision(None, REASON_UNSUPPORTED, (entry,))

        entry["outcome"] = "ok"
        return RouteDecision(agent_name, REASON_MODEL_CLASSIFICATION, (entry,))

    def _tool_config(self) -> dict[str, Any]:
        allowed = sorted(self._agent_by_service_type) + [AMBIGUOUS, UNSUPPORTED]
        return {
            "tools": [
                {
                    "toolSpec": {
                        "name": ROUTE_TOOL_NAME,
                        "description": (
                            "回報這句需求所屬的服務類別。這是唯一允許的輸出方式。"
                        ),
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "required": ["serviceType"],
                                "properties": {
                                    "serviceType": {
                                        "type": "string",
                                        "enum": allowed,
                                    },
                                    "reason": {
                                        "type": "string",
                                        "description": "不含個資的簡短分類理由。",
                                    },
                                },
                            }
                        },
                    }
                }
            ],
            "toolChoice": {"tool": {"name": ROUTE_TOOL_NAME}},
        }


def _classified_service_type(response: Any) -> str | None:
    if not isinstance(response, Mapping):
        return None
    output = response.get("output")
    message = output.get("message") if isinstance(output, Mapping) else None
    content = message.get("content") if isinstance(message, Mapping) else None
    if not isinstance(content, list):
        return None
    for block in content:
        if not isinstance(block, Mapping):
            continue
        tool_use = block.get("toolUse")
        if not isinstance(tool_use, Mapping):
            continue
        if tool_use.get("name") != ROUTE_TOOL_NAME:
            continue
        payload = tool_use.get("input")
        if not isinstance(payload, Mapping):
            continue
        service_type = payload.get("serviceType")
        if isinstance(service_type, str) and service_type:
            return service_type
    return None
