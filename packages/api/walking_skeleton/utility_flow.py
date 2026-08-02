"""Utility repair (水電修繕) service flow.

All utility-specific rules live here: the safety screening vocabulary, the
deterministic detail extractors, the demo provider master data and the accept
contract. The shared skeleton in `service.py` MUST NOT reference any of these
constants directly.

Safety decisions are deterministic Python, never model output. `SPEC.md` requires
that high-risk utility situations stop dispatch and surface emergency guidance,
so the checks below are the control, and the Knowledge Base only supplements
wording.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from . import points
from .errors import ConflictError, ValidationError
from .flows import BASE_STAGE_LABELS
from .geo import DISTRICTS, resolve_district
from .member_memory import EMPTY_MEMORY, MemberMemory


SERVICE_TYPE = "utility_repair"
AGENT_NAME = "utility_repair_agent"
SERVICE_NAME = "水電修繕"
SCHEMA_VERSION = "1.0.0"

# IDs and names come from data/mock/master/providers.json. Service areas come
# from data/mock/master/provider_service_areas.json. The local skeleton embeds
# only two rows so the Lambda package does not need the entire generation set.
DEMO_PROVIDERS: tuple[dict[str, Any], ...] = (
    {
        "providerId": "31324fe0-9899-5382-8211-d0122c20bda0",
        "name": "京鑫水電工程行",
        "rating": 3.9,
        "responseSlaHours": 1,
        "capabilities": ["gas_certified", "weekend_available"],
        "districts": ["松山區", "大同區", "信義區", "北投區", "內湖區"],
        # inspection_fee + min_charge from the same providers.json record. Used
        # only to order candidates by member price sensitivity, never quoted.
        "entryCost": 1800,
        "source": "data/mock/master/providers.json",
    },
    {
        "providerId": "29722c58-1d40-5dd9-9bf3-4cfcdfefb60a",
        "name": "新旺水電工程行",
        "rating": 3.6,
        "responseSlaHours": 4,
        "capabilities": ["emergency_24h", "night_shift", "waterproofing"],
        "districts": ["內湖區", "南港區", "大安區", "中山區", "士林區"],
        "entryCost": 1200,
        "source": "data/mock/master/providers.json",
    },
)

# Preference keys the agent is allowed to report. Anything else is dropped before
# it can reach a member's long-lived profile.
PREFERENCE_PATCH_KEYS = (
    "priceSensitivity",
    "preferredContactTime",
    "preferredVendorTags",
    "blockedVendorIds",
    "note",
)

HIGH_RISK_TERMS = ("冒煙", "火花", "焦味", "裸線", "觸電", "漏電", "大量積水", "淹水")
NEGATED_RISK_PHRASES = (
    "沒有漏電",
    "無漏電",
    "沒有冒煙",
    "無冒煙",
    "沒有積水",
    "無積水",
    "水量不大",
)
CONFIRM_PHRASES = ("確認送出", "確認建立", "內容正確", "可以送出")

# Closed allowlist for the model extraction the Runtime returns. Everything the
# agent sends is re-validated here before it can reach stored state, so an
# unexpected key, type or enum value is dropped instead of trusted.
ISSUE_TYPES = ("electrical", "toilet", "drain", "water_heater", "leak", "other")
URGENCY_LEVELS = ("routine", "soon", "urgent", "emergency")
HAZARD_FLAG_KEYS = (
    "electricShockRisk",
    "exposedWires",
    "smokeOrBurningSmell",
    "activeFlooding",
)
MAX_PREFERRED_TIME_LENGTH = 100

# Fixed safety wording. The agent never authors this text, and the stop-work rule
# below is deliberately present here as well as in the Runtime so neither a model
# nor a knowledge base miss becomes a single point of failure.
SAFETY_HOLD_TEXT = (
    "這有觸電或火災風險，請先不要觸碰設備、插座或積水，也不要自行拆修。"
    "若能在不接近危險處的前提下安全斷電才操作總開關；"
    "持續冒煙、火花或有人受傷請立即聯絡 119／台電。"
)
SAFETY_SCREEN_QUESTION = (
    "我需要先確認安全：是否有漏電、裸線、冒煙焦味，或大量積水接近插座？"
)
DISTRICT_QUESTION = (
    "請告訴我服務地區（例如台北市內湖區），詳細門牌不需要在 AI 對話中提供。"
)
PREFERRED_TIME_QUESTION = "你希望廠商什麼日期與時段到場？例如明天下午兩點到五點。"
OUT_OF_SCOPE_TEMPLATE = (
    "目前示範的服務範圍只涵蓋台北市{districts}。"
    "請改提供這些行政區之一，我才能幫你委派合格廠商。"
)

_TURN_GOALS_BY_STAGE = {
    "collecting_details": "collect_missing_fields",
    "awaiting_resident_confirmation": "confirm_brief",
    "waiting_resident_information": "answer_provider_question",
    "waiting_provider_response": "answer_progress_question",
    "provider_confirmed": "answer_progress_question",
    "rematching": "answer_progress_question",
}

STAGE_LABELS: dict[str, str] = {
    **BASE_STAGE_LABELS,
    "collecting_details": "水電 Agent 正在確認需求",
    "safety_hold": "偵測到高風險，請先確保人身安全",
}

_URGENT_TERMS = ("一直", "持續", "嚴重")
_PREFERRED_TIME_PATTERN = re.compile(
    r"((?:今天|明天|後天|週[一二三四五六日天]|\d{1,2}[/-]\d{1,2})"
    r"[^。！？]{0,20}(?:上午|下午|晚上|早上|中午)[^。！？]{0,20})"
)
_RISK_SCREEN_SAFE_PHRASES = (
    "沒有",
    "都沒有",
    "無異常",
    "水量不大",
    "沒有危險",
    "已確認安全",
)
_RISK_SCREEN_CONTRADICTIONS = ("但是", "但有", "可是", "仍然")


def issue_type(content: str) -> str:
    if any(term in content for term in ("插座", "跳電", "電線", "漏電", "火花")):
        return "electrical"
    if "馬桶" in content:
        return "toilet"
    if any(term in content for term in ("排水", "堵塞")):
        return "drain"
    if "熱水器" in content:
        return "water_heater"
    if any(term in content for term in ("漏水", "水管", "水龍頭")):
        return "leak"
    return "other"


def has_high_risk(content: str) -> bool:
    cleaned = content
    for phrase in NEGATED_RISK_PHRASES:
        cleaned = cleaned.replace(phrase, "")
    return any(term in cleaned for term in HIGH_RISK_TERMS)


def hazard_flags(content: str) -> dict[str, bool]:
    high_risk = has_high_risk(content)
    return {
        "electricShockRisk": high_risk
        and any(term in content for term in ("觸電", "漏電", "火花")),
        "exposedWires": high_risk and "裸線" in content,
        "smokeOrBurningSmell": high_risk
        and any(term in content for term in ("冒煙", "焦味")),
        "activeFlooding": high_risk
        and any(term in content for term in ("大量積水", "淹水")),
    }


def is_risk_screen_answer(content: str) -> bool:
    return any(phrase in content for phrase in _RISK_SCREEN_SAFE_PHRASES)


def _preference_patch(value: Any) -> dict[str, Any]:
    """Keep only allowlisted preference keys the agent may report."""

    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in PREFERENCE_PATCH_KEYS if key in value}


def _price_score(
    provider: dict[str, Any],
    candidates: Sequence[dict[str, Any]],
) -> float:
    """1.0 for the cheapest entry cost among the candidates, 0.0 for the dearest."""

    costs = [candidate["entryCost"] for candidate in candidates]
    cheapest, dearest = min(costs), max(costs)
    if dearest == cheapest:
        return 1.0
    return (dearest - provider["entryCost"]) / (dearest - cheapest)


def _service_score(
    provider: dict[str, Any],
    candidates: Sequence[dict[str, Any]],
) -> float:
    """Response speed and rating, normalised across the candidates."""

    hours = [candidate["responseSlaHours"] for candidate in candidates]
    fastest, slowest = min(hours), max(hours)
    speed = (
        1.0
        if slowest == fastest
        else (slowest - provider["responseSlaHours"]) / (slowest - fastest)
    )
    return 0.6 * speed + 0.4 * (provider["rating"] / 5.0)


class UtilityRepairFlow:
    """Deterministic utility repair conversation and dispatch rules."""

    service_type = SERVICE_TYPE
    agent_name = AGENT_NAME
    service_name = SERVICE_NAME
    schema_version = SCHEMA_VERSION
    stage_labels = STAGE_LABELS
    routing_hint = "家中漏水、排水、馬桶、熱水器或用電異常"
    # Dispatch is automatic for utility repair; the resident never picks a
    # provider, so the selection endpoint must reject utility cases.
    supports_selection = False

    def init_request(self, request: dict[str, Any], content: str) -> None:
        request.update(
            {
                "issueType": issue_type(content),
                "symptoms": content,
                "riskScreened": False,
                "hazardFlags": hazard_flags(content),
                "safetyHold": has_high_risk(content),
                "countyCode": None,
                "districtCode": None,
                "districtName": None,
                "preferredTime": None,
                "urgency": "soon"
                if any(term in content for term in _URGENT_TERMS)
                else "routine",
                "providerQuestion": None,
                "providerAnswer": None,
            }
        )

    # ------------------------------------------------------------------
    # Model-backed turn contract
    # ------------------------------------------------------------------

    def known_fields(
        self,
        request: dict[str, Any] | None,
        memory: MemberMemory = EMPTY_MEMORY,
    ) -> dict[str, Any]:
        # Remembered values travel as PII-masked known fields so the agent
        # confirms instead of asking again.
        if not request:
            return dict(memory.to_known_fields())
        return {
            "issueType": request["issueType"],
            "districtName": request["districtName"],
            "preferredTime": request["preferredTime"],
            "urgency": request["urgency"],
            "riskScreened": request["riskScreened"],
            **memory.to_known_fields(),
        }

    def missing_fields(self, request: dict[str, Any] | None) -> tuple[str, ...]:
        if not request:
            return ("riskScreening", "district", "preferredTime")
        missing: list[str] = []
        if not request["riskScreened"]:
            missing.append("riskScreening")
        if not request["districtName"]:
            missing.append("district")
        if not request["preferredTime"]:
            missing.append("preferredTime")
        return tuple(missing)

    def turn_goal(self, request: dict[str, Any] | None, stage: str | None) -> str | None:
        if request is None:
            return "route_new_request"
        if stage == "safety_hold":
            # None means "do not consult the model on this turn". While a hazard
            # is unresolved the reply is fixed wording, so spending a model call
            # could only introduce wording that softens a stop-work instruction.
            return None
        if stage == "collecting_details" and not request["riskScreened"]:
            # Safety screening outranks field collection: the agent must not move
            # on to scheduling while a hazard is still unconfirmed.
            return "screen_safety"
        return _TURN_GOALS_BY_STAGE.get(stage or "", "collect_missing_fields")

    def merge_agent_extraction(
        self, request: dict[str, Any], turn: Any
    ) -> dict[str, Any]:
        """Apply validated model output and report what needs a Flask answer.

        Only allowlisted keys with contract-valid values are applied. Hazard flags
        are unioned, never cleared, so a model can not undo a deterministic hit.
        """

        extracted = dict(getattr(turn, "extracted_fields", None) or {})
        notes: dict[str, Any] = {
            "outOfScopeArea": None,
            "riskScreenAnswered": extracted.get("riskScreenAnswered") is True,
            "confirmsBrief": extracted.get("confirmsBrief") is True,
            "observedPreference": _preference_patch(
                extracted.get("observedPreference")
            ),
        }

        issue_type_value = extracted.get("issueType")
        if issue_type_value in ISSUE_TYPES:
            request["issueType"] = issue_type_value

        urgency = extracted.get("urgency")
        if urgency in URGENCY_LEVELS:
            request["urgency"] = urgency

        preferred_time = extracted.get("preferredTime")
        if isinstance(preferred_time, str) and preferred_time.strip():
            request["preferredTime"] = preferred_time.strip()[
                :MAX_PREFERRED_TIME_LENGTH
            ]

        district_name = extracted.get("districtName")
        if isinstance(district_name, str) and district_name.strip():
            candidate = district_name.strip()
            codes = DISTRICTS.get(candidate)
            if codes is None:
                # The resident named an area, but it is outside the demo master
                # data. Recording it would create an unmatchable case.
                notes["outOfScopeArea"] = candidate[:40]
            else:
                request["countyCode"], request["districtCode"] = codes
                request["districtName"] = candidate

        flags = extracted.get("hazardFlags")
        if isinstance(flags, dict) and all(
            isinstance(flags.get(key), bool) for key in HAZARD_FLAG_KEYS
        ):
            self._raise_hazard_flags(request, flags)

        return notes

    @staticmethod
    def _raise_hazard_flags(
        request: dict[str, Any], detected: dict[str, bool]
    ) -> None:
        """Raise flags only. A hazard already recorded is never cleared."""

        for key in HAZARD_FLAG_KEYS:
            request["hazardFlags"][key] = request["hazardFlags"].get(
                key, False
            ) or detected.get(key, False)

    @staticmethod
    def _high_risk(content: str, turn: Any) -> bool:
        """Union of the deterministic check and the agent assessment."""

        return has_high_risk(content) or getattr(turn, "risk_level", None) == "high"

    @staticmethod
    def _out_of_scope_text() -> str:
        return OUT_OF_SCOPE_TEMPLATE.format(districts="、".join(DISTRICTS))

    @staticmethod
    def apply_member_memory(request: dict[str, Any], memory: MemberMemory) -> None:
        """Seed the case from memory, validating every remembered value.

        Memory is a default, not an authority: a remembered district still has to
        exist in the controlled district table before it is written, otherwise a
        stale profile could create an unmatchable case.
        """

        address = memory.default_address
        if address is not None and not request["districtName"]:
            codes = DISTRICTS.get(address.district_name)
            if codes is not None:
                request["countyCode"], request["districtCode"] = codes
                request["districtName"] = address.district_name
                request["districtSource"] = "member_memory"

        appliance = memory.appliance_for()
        if appliance is not None and not request.get("rememberedAppliance"):
            request["rememberedAppliance"] = appliance.describe()

    # ------------------------------------------------------------------
    # Conversation
    # ------------------------------------------------------------------

    def start(
        self,
        svc: Any,
        conversation: dict[str, Any],
        request: dict[str, Any],
        *,
        turn: Any = None,
        memory: MemberMemory = EMPTY_MEMORY,
    ) -> dict[str, Any]:
        notes = self.merge_agent_extraction(request, turn) if turn else {}
        # After the model merge so a district the resident just stated wins over a
        # remembered one.
        self.apply_member_memory(request, memory)
        svc.record_observed_preference(request, notes.get("observedPreference"))
        request["safetyHold"] = self._high_risk(request["symptoms"], turn)

        if request["safetyHold"]:
            svc.set_progress(request, "safety_hold", waiting_for="resident")
            text = SAFETY_HOLD_TEXT
        else:
            svc.set_progress(request, "collecting_details", waiting_for="resident")
            if notes.get("outOfScopeArea"):
                # The demo service scope is a fact this flow states itself.
                text = f"{self._out_of_scope_text()}{SAFETY_SCREEN_QUESTION}"
            else:
                text = svc.choose_reply(
                    "我已交給水電 Agent。先確認用電安全：現場是否有漏電、裸線、冒煙焦味，"
                    "或水已接近插座／形成大量積水？",
                    turn,
                    model_may_rephrase=True,
                )
        assistant = svc.append_assistant(
            conversation["conversationId"], text, agent=AGENT_NAME
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
        memory: MemberMemory = EMPTY_MEMORY,
    ) -> dict[str, Any]:
        stage = svc.current_stage(request)

        if stage == "safety_hold":
            # Deliberately before any merge: while a hazard is unresolved this
            # flow answers from fixed wording only.
            assistant = svc.append_assistant(
                conversation["conversationId"],
                "目前仍維持安全暫停，不會自動派工。請先遠離危險區並聯絡緊急單位；確認現場已由專業人員排除立即風險後，再重新建立一般修繕需求。",
                agent=AGENT_NAME,
            )
            return svc.turn_payload(conversation, assistant, turn=turn)

        if stage == "waiting_resident_information":
            return svc.accept_resident_information(
                conversation,
                request,
                content,
                agent=AGENT_NAME,
                reply="收到，我已把補充內容回傳給原廠商，現在等待廠商確認。你可以在「我的預約」查看最新進度。",
                turn=turn,
            )

        if stage == "awaiting_resident_confirmation":
            notes = self.merge_agent_extraction(request, turn) if turn else {}
            if any(phrase in content for phrase in CONFIRM_PHRASES) or notes.get(
                "confirmsBrief"
            ):
                return self._confirm_and_match(
                    svc, conversation, request, turn=turn, memory=memory
                )
            self._apply_detail_extractors(request, content)
            # Re-applied after the fixed patterns so a validated model value wins
            # over a coarser regex hit on the same correction.
            if turn:
                self.merge_agent_extraction(request, turn)
            svc.touch(request)
            svc.render_artifact(request, supersede=True)
            assistant = svc.append_assistant(
                conversation["conversationId"],
                "我已依你的修改產生新版需求文件。請確認內容，正確的話回覆「確認送出」。",
                agent=AGENT_NAME,
            )
            return svc.turn_payload(
                conversation,
                assistant,
                artifact=svc.current_artifact(request),
                turn=turn,
            )

        if stage in {"waiting_provider_response", "provider_confirmed"}:
            assistant = svc.append_assistant(
                conversation["conversationId"],
                "案件已送出，你可以在「我的預約」查看媒合與廠商確認進度。若廠商需要補充，我會回到這個對話詢問你。",
                agent=AGENT_NAME,
            )
            return svc.turn_payload(conversation, assistant, turn=turn)

        # Deterministic extractors run first so the offline demo keeps working;
        # validated model values then fill in what the fixed patterns miss.
        self._apply_detail_extractors(request, content)
        notes = self.merge_agent_extraction(request, turn) if turn else {}
        self.apply_member_memory(request, memory)
        svc.record_observed_preference(request, notes.get("observedPreference"))
        scope_text = self._out_of_scope_text() if notes.get("outOfScopeArea") else ""
        model_wording_allowed = not scope_text

        safety_hold_triggered = False
        screened_this_turn = False
        if not request["riskScreened"]:
            # 「沒有漏電、冒煙或積水」是對整串風險的否定；先辨識這種
            # 安全篩檢回答，避免只靠關鍵字把否定句誤判為高風險。
            negated_screen_answer = is_risk_screen_answer(content) and not any(
                conjunction in content for conjunction in _RISK_SCREEN_CONTRADICTIONS
            )
            # Only the negation heuristic may suppress a deterministic hit. The
            # agent saying the resident answered is not permission to stand down.
            deterministic_high = has_high_risk(content) and not negated_screen_answer
            if deterministic_high or getattr(turn, "risk_level", None) == "high":
                safety_hold_triggered = True
                request["safetyHold"] = True
                self._raise_hazard_flags(request, hazard_flags(content))
                svc.set_progress(request, "safety_hold", waiting_for="resident")
            elif negated_screen_answer or notes.get("riskScreenAnswered"):
                request["riskScreened"] = True
                screened_this_turn = True

        # Safety is settled first, so a turn that supplies the last missing field
        # can advance in the same turn instead of asking one question per field.
        acknowledgement = "安全狀況了解。" if screened_this_turn else ""
        if safety_hold_triggered:
            text = SAFETY_HOLD_TEXT
            model_wording_allowed = False
        elif not request["riskScreened"]:
            text = f"{scope_text}{SAFETY_SCREEN_QUESTION}"
        elif not request["districtName"]:
            text = f"{scope_text}{acknowledgement}{DISTRICT_QUESTION}"
        elif not request["preferredTime"]:
            text = f"{scope_text}{acknowledgement}{PREFERRED_TIME_QUESTION}"
        else:
            artifact = svc.render_artifact(request)
            svc.set_progress(
                request, "awaiting_resident_confirmation", waiting_for="resident"
            )
            text = (
                f"我已整理第 {artifact['version']} 版水電需求文件：{artifact['summary']}。"
                "請確認內容，正確的話回覆「確認送出」；確認前不會委派廠商。"
            )
            # The document version and summary are facts Flask owns.
            model_wording_allowed = False

        text = svc.choose_reply(
            text, turn, model_may_rephrase=model_wording_allowed
        )

        svc.touch(request)
        assistant = svc.append_assistant(
            conversation["conversationId"], text, agent=AGENT_NAME
        )
        return svc.turn_payload(
            conversation,
            assistant,
            artifact=svc.current_artifact(request),
            turn=turn,
        )

    def build_summary(self, request: dict[str, Any]) -> str:
        return (
            f"{request['districtName']}｜{request['symptoms']}｜"
            f"希望時段：{request['preferredTime']}｜風險篩檢：未發現立即危險"
        )

    def fallback_summary(self, request: dict[str, Any]) -> str:
        return request["symptoms"]

    def build_canonical(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "issueType": request["issueType"],
            "symptoms": request["symptoms"],
            "location": {
                "countyCode": request["countyCode"],
                "districtCode": request["districtCode"],
                "districtName": request["districtName"],
            },
            "urgency": request["urgency"],
            "hazardFlags": dict(request["hazardFlags"]),
            "preferredTime": request["preferredTime"],
        }

    def projection_fields(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "issueType": request["issueType"],
            "districtName": request["districtName"],
            "preferredTime": request["preferredTime"],
            "safetyHold": request["safetyHold"],
        }

    def list_providers(self) -> tuple[dict[str, Any], ...]:
        return DEMO_PROVIDERS

    def rank_candidates(
        self,
        request: dict[str, Any],
        memory: MemberMemory = EMPTY_MEMORY,
    ) -> list[dict[str, Any]]:
        preference = memory.preference
        candidates = [
            provider
            for provider in DEMO_PROVIDERS
            if request["districtName"] in provider["districts"]
            # A blocked vendor is a hard exclusion, not a ranking penalty.
            and provider["providerId"] not in preference.blocked_vendor_ids
        ]
        if preference.is_unset:
            candidates.sort(
                key=lambda provider: (
                    provider["responseSlaHours"],
                    -provider["rating"],
                    provider["providerId"],
                )
            )
            return candidates

        # A price-sensitive member gets the cheaper entry cost first; an
        # insensitive one keeps the fastest, best-rated candidate first.
        # Provider ID is the final tiebreak so the order stays reproducible.
        #
        # Scores are computed up front rather than inside the sort key: CPython
        # makes a list appear empty for the duration of `list.sort()`, so reading
        # `candidates` from the key function raised on min() of an empty sequence.
        sensitivity = preference.price_sensitivity
        weighted = {
            provider["providerId"]: (
                sensitivity * _price_score(provider, candidates)
                + (1 - sensitivity) * _service_score(provider, candidates)
            )
            for provider in candidates
        }
        candidates.sort(
            key=lambda provider: (
                -weighted[provider["providerId"]],
                provider["providerId"],
            )
        )
        request["matchRuleVersion"] = "preference-weighted-1"
        request["matchReason"] = (
            "依會員價格敏感度排序" if sensitivity >= 0.5 else "依回覆速度與評分排序"
        )
        return candidates

    def validate_accept(self, payload: dict[str, Any]) -> None:
        if not str(payload.get("arrivalWindow") or "").strip():
            raise ValidationError("廠商接受時 arrivalWindow 為必填")
        # Validated here, before the transaction, so a malformed amount cannot
        # consume the pending task or feed the points engine a wrong basis.
        points.normalize_reported_amount(payload.get("estimatedAmount"))

    def reward_basis(
        self, request: dict[str, Any], payload: dict[str, Any]
    ) -> tuple[int, str] | None:
        """A repair has no price until it is quoted, so trust the technician.

        Falls back to a category baseline when the provider reports nothing, and
        labels it as an estimate so it never reads like a quote.
        """

        reported = points.normalize_reported_amount(payload.get("estimatedAmount"))
        request["estimatedAmount"] = reported
        return points.resolve_basis_amount(
            issue_type=request["issueType"], reported_amount=reported
        )

    def apply_accept(
        self,
        request: dict[str, Any],
        provider: dict[str, Any],
        payload: dict[str, Any],
    ) -> str:
        arrival_window = str(payload.get("arrivalWindow") or "").strip()
        message = str(payload.get("message") or "").strip()
        request["confirmedArrivalWindow"] = arrival_window
        request["providerConfirmationMessage"] = message
        return (
            f"{provider['name']} 已在平台內確認可於 {arrival_window} 到場。"
            f"注意事項：{message or '到場後先勘查，確認範圍與費用後才施工。'}"
            "這是 Demo 的平台內確認，不代表外部付款或不可逆交易已完成。"
        )

    def _confirm_and_match(
        self,
        svc: Any,
        conversation: dict[str, Any],
        request: dict[str, Any],
        *,
        turn: Any = None,
        memory: MemberMemory = EMPTY_MEMORY,
    ) -> dict[str, Any]:
        artifact = svc.confirm_artifact(request)
        candidates = self.rank_candidates(request, memory)
        if not candidates:
            raise ConflictError("目前服務地區沒有符合硬條件的水電廠商")
        task = svc.dispatch_first_candidate(
            request,
            candidates,
            reason="initial_match",
            event_type="provider_matched",
            event_label="已依地區與回覆 SLA 委派第一順位廠商",
        )
        assistant = svc.append_assistant(
            conversation["conversationId"],
            f"需求文件已確認。我已依服務地區與回覆速度委派 {task['provider']['name']}，"
            "現在等待廠商回覆；目前不需要你操作。",
            agent=AGENT_NAME,
        )
        return svc.turn_payload(
            conversation, assistant, artifact=artifact, provider_task=task, turn=turn
        )

    @staticmethod
    def _apply_detail_extractors(request: dict[str, Any], content: str) -> None:
        located = resolve_district(content)
        if located:
            (
                request["countyCode"],
                request["districtCode"],
                request["districtName"],
            ) = located
        time_match = _PREFERRED_TIME_PATTERN.search(content)
        if time_match:
            request["preferredTime"] = time_match.group(1).strip()
        elif any(term in content for term in ("上午", "下午", "晚上", "早上")):
            request["preferredTime"] = content
