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
from typing import Any

from .errors import ConflictError, ValidationError
from .flows import BASE_STAGE_LABELS
from .geo import resolve_district


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
        "source": "data/mock/master/providers.json",
    },
    {
        "providerId": "29722c58-1d40-5dd9-9bf3-4cfcdfefb60a",
        "name": "新旺水電工程行",
        "rating": 3.6,
        "responseSlaHours": 4,
        "capabilities": ["emergency_24h", "night_shift", "waterproofing"],
        "districts": ["內湖區", "南港區", "大安區", "中山區", "士林區"],
        "source": "data/mock/master/providers.json",
    },
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

    def start(
        self, svc: Any, conversation: dict[str, Any], request: dict[str, Any]
    ) -> dict[str, Any]:
        if request["safetyHold"]:
            svc.set_progress(request, "safety_hold", waiting_for="resident")
            text = (
                "這有觸電或火災風險，請先不要觸碰設備、插座或積水，也不要自行拆修。"
                "若能在不接近危險處的前提下安全斷電才操作總開關；持續冒煙、火花或有人受傷請立即聯絡 119／台電。"
            )
        else:
            svc.set_progress(request, "collecting_details", waiting_for="resident")
            text = (
                "我已交給水電 Agent。先確認用電安全：現場是否有漏電、裸線、冒煙焦味，"
                "或水已接近插座／形成大量積水？"
            )
        assistant = svc.append_assistant(
            conversation["conversationId"], text, agent=AGENT_NAME
        )
        return svc.turn_payload(conversation, assistant, trace_agent="supervisor")

    def continue_turn(
        self,
        svc: Any,
        conversation: dict[str, Any],
        request: dict[str, Any],
        content: str,
    ) -> dict[str, Any]:
        stage = svc.current_stage(request)

        if stage == "safety_hold":
            assistant = svc.append_assistant(
                conversation["conversationId"],
                "目前仍維持安全暫停，不會自動派工。請先遠離危險區並聯絡緊急單位；確認現場已由專業人員排除立即風險後，再重新建立一般修繕需求。",
                agent=AGENT_NAME,
            )
            return svc.turn_payload(conversation, assistant)

        if stage == "waiting_resident_information":
            return svc.accept_resident_information(
                conversation,
                request,
                content,
                agent=AGENT_NAME,
                reply="收到，我已把補充內容回傳給原廠商，現在等待廠商確認。你可以在「我的預約」查看最新進度。",
            )

        if stage == "awaiting_resident_confirmation":
            if any(phrase in content for phrase in CONFIRM_PHRASES):
                return self._confirm_and_match(svc, conversation, request)
            self._apply_detail_extractors(request, content)
            svc.touch(request)
            svc.render_artifact(request, supersede=True)
            assistant = svc.append_assistant(
                conversation["conversationId"],
                "我已依你的修改產生新版需求文件。請確認內容，正確的話回覆「確認送出」。",
                agent=AGENT_NAME,
            )
            return svc.turn_payload(
                conversation, assistant, artifact=svc.current_artifact(request)
            )

        if stage in {"waiting_provider_response", "provider_confirmed"}:
            assistant = svc.append_assistant(
                conversation["conversationId"],
                "案件已送出，你可以在「我的預約」查看媒合與廠商確認進度。若廠商需要補充，我會回到這個對話詢問你。",
                agent=AGENT_NAME,
            )
            return svc.turn_payload(conversation, assistant)

        self._apply_detail_extractors(request, content)
        if not request["riskScreened"]:
            # 「沒有漏電、冒煙或積水」是對整串風險的否定；先辨識這種
            # 安全篩檢回答，避免只靠關鍵字把否定句誤判為高風險。
            safe_screen_answer = is_risk_screen_answer(content) and not any(
                conjunction in content for conjunction in _RISK_SCREEN_CONTRADICTIONS
            )
            if safe_screen_answer:
                request["riskScreened"] = True
                request["hazardFlags"] = {
                    "electricShockRisk": False,
                    "exposedWires": False,
                    "smokeOrBurningSmell": False,
                    "activeFlooding": False,
                }
                text = "安全狀況了解。請告訴我服務地區（例如台北市內湖區），詳細門牌不需要在 AI 對話中提供。"
            elif has_high_risk(content):
                request["safetyHold"] = True
                request["hazardFlags"] = hazard_flags(content)
                svc.set_progress(request, "safety_hold", waiting_for="resident")
                text = "偵測到立即風險，請不要觸碰設備或積水，也不要自行拆修；持續冒煙、火花或有人受傷請立即聯絡 119／台電。"
            else:
                text = "我需要先確認安全：是否有漏電、裸線、冒煙焦味，或大量積水接近插座？"
        elif not request["districtName"]:
            text = "請告訴我服務地區（例如台北市內湖區），詳細門牌不需要在 AI 對話中提供。"
        elif not request["preferredTime"]:
            text = "你希望廠商什麼日期與時段到場？例如明天下午兩點到五點。"
        else:
            artifact = svc.render_artifact(request)
            svc.set_progress(
                request, "awaiting_resident_confirmation", waiting_for="resident"
            )
            text = (
                f"我已整理第 {artifact['version']} 版水電需求文件：{artifact['summary']}。"
                "請確認內容，正確的話回覆「確認送出」；確認前不會委派廠商。"
            )

        svc.touch(request)
        assistant = svc.append_assistant(
            conversation["conversationId"], text, agent=AGENT_NAME
        )
        return svc.turn_payload(
            conversation, assistant, artifact=svc.current_artifact(request)
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

    def rank_candidates(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = [
            provider
            for provider in DEMO_PROVIDERS
            if request["districtName"] in provider["districts"]
        ]
        candidates.sort(
            key=lambda provider: (
                provider["responseSlaHours"],
                -provider["rating"],
                provider["providerId"],
            )
        )
        return candidates

    def validate_accept(self, payload: dict[str, Any]) -> None:
        if not str(payload.get("arrivalWindow") or "").strip():
            raise ValidationError("廠商接受時 arrivalWindow 為必填")

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
        self, svc: Any, conversation: dict[str, Any], request: dict[str, Any]
    ) -> dict[str, Any]:
        artifact = svc.confirm_artifact(request)
        candidates = self.rank_candidates(request)
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
            conversation, assistant, artifact=artifact, provider_task=task
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
