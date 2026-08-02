"""Model-backed reasoning for one conversational turn inside the Runtime.

The domain agent uses Amazon Bedrock Converse with a single forced tool so the
model must answer through a closed schema.  Three boundaries are deliberate:

* Deterministic hazard rules run in this Runtime **and** in the Flask
  application service.  A model that misses a hazard cannot lower the risk
  level, and safety wording is fixed text that the model never authors.
* Model output is re-validated field by field here, and validated again by Flask
  before it reaches any stored state.  Unknown keys and bad types are dropped.
* When the model is unavailable or breaks the contract, the turn completes with
  runtime rules and reports ``rule-fallback`` rather than claiming the model ran.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from knowledge import (
    POLICY_MARKERS,
    SKIPPED_RESULT,
    KnowledgeReference,
    KnowledgeResult,
    SuppressedReference,
    detect_live_value_topics,
)
from logical_agents import (
    HAZARD_FLAG_KEYS,
    FIELD_ALIASES,
    URGENCY_LEVELS,
    UTILITY_ISSUE_TYPES,
    LogicalAgent,
)
from model_gate import BedrockSafetyError

logger = logging.getLogger(__name__)

EXTRACTION_TOOL_NAME = "record_service_request_understanding"
MAX_HISTORY_TURNS = 8
MAX_OUTPUT_TOKENS = 700
MODEL_TEMPERATURE = 0.2
MAX_ASSISTANT_MESSAGE_LENGTH = 600
MAX_DISTRICT_NAME_LENGTH = 40
MAX_PREFERRED_TIME_LENGTH = 100
MAX_RISK_SIGNALS = 10
MAX_PREFERENCE_ITEMS = 10
MAX_PREFERENCE_NOTE_LENGTH = 200

MODE_MODEL = "model"
MODE_RULE_FALLBACK = "rule-fallback"

RISK_NONE = "none"
RISK_HIGH = "high"
SOURCE_NONE = "none"
SOURCE_MODEL = "model"
SOURCE_DETERMINISTIC = "deterministic"
SOURCE_BOTH = "both"

# Fixed safety wording. The model never authors this text, and it must survive a
# knowledge base miss or a model outage.
SAFETY_HOLD_MESSAGE = (
    "這有觸電或火災風險，請先不要觸碰設備、插座或積水，也不要自行拆修。"
    "若能在遠離危險處的前提下安全斷電，才操作總開關；"
    "持續冒煙、火花或有人受傷，請立即聯絡 119 或台電 1911。"
)

# Deterministic hazard rules. Kept aligned with the Flask安全檢查 on purpose:
# the specification requires the stop-work rule to exist in both places so
# neither a model nor a knowledge base miss can become a single point of failure.
HIGH_RISK_SIGNAL_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("electric_shock_risk", ("觸電", "漏電", "火花")),
    ("exposed_wires", ("裸線",)),
    ("smoke_or_burning_smell", ("冒煙", "焦味")),
    ("active_flooding", ("大量積水", "淹水")),
)
NEGATED_RISK_PHRASES = (
    "沒有漏電",
    "無漏電",
    "沒有冒煙",
    "無冒煙",
    "沒有積水",
    "無積水",
    "水量不大",
)

KNOWLEDGE_QUESTION_MARKERS = (
    "？",
    "?",
    "嗎",
    "怎麼",
    "如何",
    "為什麼",
    "要不要",
    "需要",
    "注意",
    "多久",
    # Policy wording is the static knowledge base's primary use case, so it is a
    # retrieval trigger in its own right rather than only a suppression guard.
    *POLICY_MARKERS,
)
GOALS_ALWAYS_RETRIEVING = ("screen_safety",)

# Named so a test can assert the directive is present without pinning wording.
LIVE_VALUE_DIRECTIVE_PREFIX = "以下主題只能由平台的即時結構化資料回答"
LIVE_VALUE_DIRECTIVE = (
    LIVE_VALUE_DIRECTIVE_PREFIX + "：{topics}。\n"
    "住戶這一輪就是在問這類資料。你 MUST NOT 依靜態知識庫、條款或你自己的印象給出"
    "任何金額、庫存、可預約時段、師傅排班或案件狀態。請誠實說明這需要由平台查詢後回覆，"
    "或改為蒐集查詢所需的欄位。"
)

DEGRADED_MODEL_NOT_CONFIGURED = "model_not_configured"
DEGRADED_DOMAIN_NOT_ENABLED = "domain_model_extraction_not_enabled"
DEGRADED_MISSING_TOOL_USE = "model_output_missing_tool_use"
DEGRADED_INVALID_OUTPUT = "model_output_failed_contract_validation"


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    level: str = RISK_NONE
    signals: tuple[str, ...] = ()
    source: str = SOURCE_NONE

    def to_payload(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "signals": list(self.signals),
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class Reasoning:
    mode: str
    model_id: str | None
    knowledge_base_queried: bool
    degraded_reason: str | None = None
    live_value_topics: tuple[str, ...] = ()
    suppressed_knowledge: tuple[SuppressedReference, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "modelId": self.model_id,
            "knowledgeBaseQueried": self.knowledge_base_queried,
            "degradedReason": self.degraded_reason,
            "liveValueTopics": list(self.live_value_topics),
            "suppressedKnowledge": [
                record.to_payload() for record in self.suppressed_knowledge
            ],
        }


@dataclass(frozen=True, slots=True)
class TurnRequest:
    message: str
    agent: LogicalAgent
    session_id: str | None = None
    workflow_stage: str | None = None
    turn_goal: str | None = None
    known_fields: Mapping[str, Any] = field(default_factory=dict)
    missing_fields: tuple[str, ...] = ()
    history: tuple[Mapping[str, str], ...] = ()
    service_districts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TurnResult:
    assistant_message: str
    extracted_fields: dict[str, Any]
    missing_fields: tuple[str, ...]
    risk: RiskAssessment
    knowledge: tuple[KnowledgeReference, ...]
    reasoning: Reasoning
    trace: tuple[dict[str, Any], ...]


class DomainReasoner:
    """Run one domain agent turn, with the model when it is safely available."""

    def __init__(
        self,
        *,
        model_client: Any | None,
        model_id: str | None,
        knowledge: Any | None,
    ) -> None:
        self._model_client = model_client
        self._model_id = (model_id or "").strip() or None
        self._knowledge = knowledge

    def reason(self, request: TurnRequest) -> TurnResult:
        trace: list[dict[str, Any]] = []

        deterministic = _deterministic_risk(request.message)
        knowledge_result = self._retrieve_knowledge(
            request,
            high_risk=deterministic.level == RISK_HIGH,
            trace=trace,
        )

        model_output, degraded_reason = self._invoke_model(
            request,
            knowledge_result,
            trace=trace,
        )

        if model_output is None:
            return self._rule_fallback(
                request,
                deterministic=deterministic,
                knowledge_result=knowledge_result,
                degraded_reason=degraded_reason,
                trace=trace,
            )

        extracted = model_output["extractedFields"]
        risk = _merge_risk(
            deterministic=deterministic,
            model_level=model_output["riskLevel"],
            model_signals=model_output["riskSignals"],
        )
        assistant_message = (
            SAFETY_HOLD_MESSAGE
            if risk.level == RISK_HIGH
            else model_output["assistantMessage"]
        )
        return TurnResult(
            assistant_message=assistant_message,
            extracted_fields=extracted,
            missing_fields=_remaining_missing_fields(request.missing_fields, extracted),
            risk=risk,
            knowledge=knowledge_result.references,
            reasoning=Reasoning(
                mode=MODE_MODEL,
                model_id=self._model_id,
                knowledge_base_queried=knowledge_result.queried,
                live_value_topics=knowledge_result.live_value_topics,
                suppressed_knowledge=knowledge_result.suppressed,
            ),
            trace=tuple(trace),
        )

    def _retrieve_knowledge(
        self,
        request: TurnRequest,
        *,
        high_risk: bool,
        trace: list[dict[str, Any]],
    ) -> KnowledgeResult:
        if self._knowledge is None:
            return SKIPPED_RESULT
        if not _should_query_knowledge(
            message=request.message,
            turn_goal=request.turn_goal,
            high_risk=high_risk,
        ):
            # A live-value question may still retrieve a chunk that is
            # authoritative for the surrounding policy, so it is retrieved and
            # then gated per chunk rather than skipped outright.
            if not detect_live_value_topics(request.message):
                return SKIPPED_RESULT

        result = self._knowledge.search(
            service_type=request.agent.service_type,
            query=request.message,
        )
        if result.queried:
            trace.append(
                {
                    "actor": request.agent.name,
                    "action": "knowledge_retrieve",
                    "target": request.agent.service_type,
                    "reasonCode": "safety_guidance" if high_risk else "resident_question",
                    "outcome": result.outcome,
                }
            )
        return result

    def _invoke_model(
        self,
        request: TurnRequest,
        knowledge_result: KnowledgeResult,
        *,
        trace: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, str | None]:
        if self._model_client is None or self._model_id is None:
            return None, DEGRADED_MODEL_NOT_CONFIGURED
        if not request.agent.supports_model_extraction:
            return None, DEGRADED_DOMAIN_NOT_ENABLED

        entry: dict[str, Any] = {
            "actor": request.agent.name,
            "action": "model_invoke",
            "target": self._model_id,
            "reasonCode": "turn_understanding",
        }
        trace.append(entry)

        try:
            response = self._model_client.converse(
                modelId=self._model_id,
                system=[{"text": _system_prompt(request, knowledge_result)}],
                messages=_conversation_messages(request),
                inferenceConfig={
                    "maxTokens": MAX_OUTPUT_TOKENS,
                    "temperature": MODEL_TEMPERATURE,
                },
                toolConfig=_tool_config(request.agent),
            )
        except BedrockSafetyError:
            entry["outcome"] = "failed"
            logger.warning(
                "model request rejected by the shared bedrock gate agent=%s",
                request.agent.name,
            )
            return None, "model_not_approved"
        except Exception as error:  # noqa: BLE001 - a turn must still complete
            entry["outcome"] = "failed"
            logger.warning(
                "model invocation failed agent=%s error_type=%s",
                request.agent.name,
                type(error).__name__,
            )
            return None, f"model_invocation_failed ({type(error).__name__})"

        raw = _tool_use_input(response)
        if raw is None:
            entry["outcome"] = "failed"
            return None, DEGRADED_MISSING_TOOL_USE

        parsed = _validate_model_output(raw, request.agent)
        if parsed is None:
            entry["outcome"] = "failed"
            return None, DEGRADED_INVALID_OUTPUT

        entry["outcome"] = "ok"
        return parsed, None

    def _rule_fallback(
        self,
        request: TurnRequest,
        *,
        deterministic: RiskAssessment,
        knowledge_result: KnowledgeResult,
        degraded_reason: str | None,
        trace: list[dict[str, Any]],
    ) -> TurnResult:
        assistant_message = (
            SAFETY_HOLD_MESSAGE
            if deterministic.level == RISK_HIGH
            else request.agent.assistant_message
        )
        return TurnResult(
            assistant_message=assistant_message,
            extracted_fields={},
            missing_fields=tuple(request.missing_fields),
            risk=deterministic,
            knowledge=knowledge_result.references,
            reasoning=Reasoning(
                mode=MODE_RULE_FALLBACK,
                model_id=None,
                knowledge_base_queried=knowledge_result.queried,
                degraded_reason=degraded_reason,
                live_value_topics=knowledge_result.live_value_topics,
                suppressed_knowledge=knowledge_result.suppressed,
            ),
            trace=tuple(trace),
        )


def _should_query_knowledge(
    *,
    message: str,
    turn_goal: str | None,
    high_risk: bool,
) -> bool:
    if high_risk or turn_goal in GOALS_ALWAYS_RETRIEVING:
        return True
    return any(marker in message for marker in KNOWLEDGE_QUESTION_MARKERS)


def _deterministic_risk(message: str) -> RiskAssessment:
    cleaned = message
    for phrase in NEGATED_RISK_PHRASES:
        cleaned = cleaned.replace(phrase, "")

    signals = tuple(
        signal
        for signal, terms in HIGH_RISK_SIGNAL_TERMS
        if any(term in cleaned for term in terms)
    )
    if not signals:
        return RiskAssessment()
    return RiskAssessment(
        level=RISK_HIGH,
        signals=signals,
        source=SOURCE_DETERMINISTIC,
    )


def _merge_risk(
    *,
    deterministic: RiskAssessment,
    model_level: str,
    model_signals: tuple[str, ...],
) -> RiskAssessment:
    deterministic_high = deterministic.level == RISK_HIGH
    model_high = model_level == RISK_HIGH
    if not deterministic_high and not model_high:
        return RiskAssessment()

    if deterministic_high and model_high:
        source = SOURCE_BOTH
    elif deterministic_high:
        source = SOURCE_DETERMINISTIC
    else:
        source = SOURCE_MODEL

    signals: list[str] = list(deterministic.signals)
    for signal in model_signals:
        if signal not in signals:
            signals.append(signal)
    return RiskAssessment(
        level=RISK_HIGH,
        signals=tuple(signals[:MAX_RISK_SIGNALS]),
        source=source,
    )


def _remaining_missing_fields(
    missing_fields: Sequence[str],
    extracted: Mapping[str, Any],
) -> tuple[str, ...]:
    remaining: list[str] = []
    for name in missing_fields:
        key = FIELD_ALIASES.get(name, name)
        value = extracted.get(key)
        if value is None or value is False or value == "":
            remaining.append(name)
    return tuple(remaining)


def _tool_config(agent: LogicalAgent) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "required": ["assistantMessage", "riskLevel"],
        "properties": {
            "assistantMessage": {
                "type": "string",
                "description": (
                    "要回覆住戶的繁體中文訊息，最多兩句，只針對待補欄位第一項提問。"
                ),
            },
            "riskLevel": {
                "type": "string",
                "enum": [RISK_NONE, RISK_HIGH],
                "description": "本輪是否出現需要立即停止操作的高風險徵兆。",
            },
            "riskSignals": {
                "type": "array",
                "items": {"type": "string"},
                "description": "高風險徵兆的英文 snake_case 代號，最多十項。",
            },
        },
    }
    if agent.extracted_fields_schema is not None:
        schema["properties"]["extractedFields"] = agent.extracted_fields_schema
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": EXTRACTION_TOOL_NAME,
                    "description": (
                        "回報本輪對住戶需求的理解結果與要回覆的訊息。"
                        "這是唯一允許的輸出方式。"
                    ),
                    "inputSchema": {"json": schema},
                }
            }
        ],
        "toolChoice": {"tool": {"name": EXTRACTION_TOOL_NAME}},
    }


def _system_prompt(
    request: TurnRequest,
    knowledge_result: KnowledgeResult,
) -> str:
    references: Sequence[KnowledgeReference] = knowledge_result.references
    sections = [
        request.agent.instructions,
        f"服務類別：{request.agent.service_type}",
        f"目前流程階段：{request.workflow_stage or 'collecting_details'}",
        f"本輪目標：{request.turn_goal or 'collect_missing_fields'}",
        "目前已知欄位："
        + (_render_known_fields(request.known_fields) or "（尚無）"),
        "本輪待補欄位（依優先序，請只問第一項）："
        + (", ".join(request.missing_fields) or "（無）"),
        "示範服務範圍（僅這些行政區可派工）："
        + (", ".join(request.service_districts) or "（未提供）"),
    ]
    if knowledge_result.live_value_topics:
        sections.append(
            LIVE_VALUE_DIRECTIVE.format(
                topics="、".join(knowledge_result.live_value_topics)
            )
        )
    if references:
        sections.append(
            "以下是平台靜態知識庫的參考內容，只能用來補充說明，"
            "不得用來回答價格、庫存、可預約時段或案件狀態：\n"
            + "\n".join(
                f"- [{reference.doc_kind}] {reference.excerpt}"
                for reference in references
            )
        )
    return "\n".join(sections)


def _render_known_fields(known_fields: Mapping[str, Any]) -> str:
    parts = []
    for key, value in known_fields.items():
        if value is None or value == "" or value is False:
            continue
        parts.append(f"{key}={value}")
    return ", ".join(parts)


def _conversation_messages(request: TurnRequest) -> list[dict[str, Any]]:
    normalised: list[dict[str, Any]] = []
    for entry in list(request.history)[-MAX_HISTORY_TURNS:]:
        if not isinstance(entry, Mapping):
            continue
        content = entry.get("content")
        role = "user" if entry.get("role") == "resident" else "assistant"
        if not isinstance(content, str) or not content.strip():
            continue
        if not normalised and role != "user":
            # Converse requires the first message to come from the user.
            continue
        if normalised and normalised[-1]["role"] == role:
            normalised[-1]["content"].append({"text": content})
            continue
        normalised.append({"role": role, "content": [{"text": content}]})

    current = {"text": request.message}
    if normalised and normalised[-1]["role"] == "user":
        normalised[-1]["content"].append(current)
    else:
        normalised.append({"role": "user", "content": [current]})
    return normalised


def _tool_use_input(response: Any) -> Mapping[str, Any] | None:
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
        if tool_use.get("name") != EXTRACTION_TOOL_NAME:
            continue
        payload = tool_use.get("input")
        if isinstance(payload, Mapping):
            return payload
    return None


def _validate_model_output(
    raw: Mapping[str, Any],
    agent: LogicalAgent,
) -> dict[str, Any] | None:
    assistant_message = raw.get("assistantMessage")
    if not isinstance(assistant_message, str) or not assistant_message.strip():
        return None

    risk_level = raw.get("riskLevel")
    if risk_level not in {RISK_NONE, RISK_HIGH}:
        risk_level = RISK_NONE

    signals: list[str] = []
    raw_signals = raw.get("riskSignals")
    if isinstance(raw_signals, list):
        for signal in raw_signals[:MAX_RISK_SIGNALS]:
            if isinstance(signal, str) and signal.strip():
                signals.append(signal.strip()[:100])

    return {
        "assistantMessage": assistant_message.strip()[:MAX_ASSISTANT_MESSAGE_LENGTH],
        "riskLevel": risk_level,
        "riskSignals": tuple(signals),
        "extractedFields": _validate_extracted_fields(
            raw.get("extractedFields"), agent
        ),
    }


def _validate_extracted_fields(
    raw: Any,
    agent: LogicalAgent,
) -> dict[str, Any]:
    if not agent.supports_model_extraction or not isinstance(raw, Mapping):
        return {}

    validated: dict[str, Any] = {}
    for key, value in raw.items():
        validator = _FIELD_VALIDATORS.get(key)
        if validator is None:
            continue
        cleaned = validator(value)
        if cleaned is not None:
            validated[key] = cleaned
    return validated


def _enum_value(allowed: tuple[str, ...]):
    def _validate(value: Any) -> str | None:
        if isinstance(value, str) and value in allowed:
            return value
        return None

    return _validate


def _bounded_text(max_length: int):
    def _validate(value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()[:max_length]
        return None

    return _validate


def _true_flag(value: Any) -> bool | None:
    # Only an explicit true carries information; false and non-booleans are
    # dropped so a model can never clear state that Flask already established.
    return True if value is True else None


def _observed_preference(value: Any) -> dict[str, Any] | None:
    """Validate a reported long-term preference, dropping anything unexpected."""

    if not isinstance(value, Mapping):
        return None
    patch: dict[str, Any] = {}

    sensitivity = value.get("priceSensitivity")
    if isinstance(sensitivity, (int, float)) and not isinstance(sensitivity, bool):
        patch["priceSensitivity"] = max(0.0, min(float(sensitivity), 1.0))

    contact_time = value.get("preferredContactTime")
    if isinstance(contact_time, str) and contact_time in {"1", "2", "3"}:
        patch["preferredContactTime"] = contact_time

    for key in ("preferredVendorTags", "blockedVendorIds"):
        raw = value.get(key)
        if not isinstance(raw, list):
            continue
        cleaned = [
            item.strip()[:100]
            for item in raw[:MAX_PREFERENCE_ITEMS]
            if isinstance(item, str) and item.strip()
        ]
        if cleaned:
            patch[key] = cleaned

    note = value.get("note")
    if isinstance(note, str) and note.strip():
        patch["note"] = note.strip()[:MAX_PREFERENCE_NOTE_LENGTH]

    return patch or None


def _hazard_flags(value: Any) -> dict[str, bool] | None:
    if not isinstance(value, Mapping):
        return None
    flags: dict[str, bool] = {}
    for key in HAZARD_FLAG_KEYS:
        flag = value.get(key)
        if not isinstance(flag, bool):
            return None
        flags[key] = flag
    return flags


_FIELD_VALIDATORS = {
    "issueType": _enum_value(UTILITY_ISSUE_TYPES),
    "districtName": _bounded_text(MAX_DISTRICT_NAME_LENGTH),
    "areaOutOfScope": _true_flag,
    "preferredTime": _bounded_text(MAX_PREFERRED_TIME_LENGTH),
    "urgency": _enum_value(URGENCY_LEVELS),
    "riskScreenAnswered": _true_flag,
    "hazardFlags": _hazard_flags,
    "confirmsBrief": _true_flag,
    "observedPreference": _observed_preference,
}
