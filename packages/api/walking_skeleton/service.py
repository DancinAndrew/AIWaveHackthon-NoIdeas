from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from . import points
from .errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from .orchestration import DeterministicDemoOrchestrator, SupervisorOrchestrator
from .store import InMemoryStore


SERVICE_TYPE = "utility_repair"
ACTIVE_AGENT = "utility_repair_agent"

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

DISTRICTS: dict[str, tuple[str, str]] = {
    "大安區": ("01", "007"),
    "內湖區": ("01", "010"),
    "南港區": ("01", "008"),
    "中山區": ("01", "003"),
    "士林區": ("01", "011"),
    "信義區": ("01", "005"),
    "松山區": ("01", "006"),
    "大同區": ("01", "002"),
    "北投區": ("01", "009"),
}

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
# 驗收語句刻意保持明確，避免「好」「可以」這類泛用回覆意外觸發點數發放。
ACCEPTANCE_PHRASES = ("驗收", "確認完工", "確認完成", "施工沒問題")

STAGE_LABELS = {
    "collecting_details": "水電 Agent 正在確認需求",
    "safety_hold": "偵測到高風險，請先確保人身安全",
    "awaiting_resident_confirmation": "需求文件待住戶確認",
    "waiting_provider_response": "已媒合廠商，等待回覆",
    "waiting_resident_information": "廠商需要住戶補充資訊",
    "rematching": "正在改派下一位廠商",
    "provider_confirmed": "廠商已確認，可依約到場",
    "awaiting_resident_acceptance": "廠商已回報完工，待住戶驗收",
    "completed": "服務已完成，點數已入帳",
}


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
    ) -> None:
        self.store = store or InMemoryStore()
        self.orchestrator = orchestrator or DeterministicDemoOrchestrator()

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
            "您好！我是 OPEN POINT 智慧助理。你可以直接告訴我家中水電遇到什麼狀況，我會交給水電 Agent 一步一步確認。",
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
            request_id = conversation.get("serviceRequestId")
            if not request_id:
                result = self._start_utility_request(conversation, content)
            else:
                result = self._continue_utility_request(conversation, content)
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
        arrival_window = str(payload.get("arrivalWindow") or "").strip()
        if action == "accept" and not arrival_window:
            # Validate before entering the transaction so an invalid accept can
            # never consume or version-bump the pending task.
            raise ValidationError("廠商接受時 arrivalWindow 為必填")
        # 同理：金額格式錯誤不得消耗任務，也不得讓點數引擎算出錯誤基礎金額。
        estimated_amount = points.normalize_reported_amount(payload.get("estimatedAmount"))

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
                arrival_window=arrival_window,
                estimated_amount=estimated_amount,
            ),
        )

    def list_provider_active_cases(self, provider_id: str) -> dict[str, Any]:
        """廠商已承接、尚未完成驗收的案件；廠商從這裡回報完工。"""

        with self.store.lock:
            items = [
                self._active_case_projection(request)
                for request in self.store.service_requests.values()
                if request.get("currentProviderId") == provider_id
                and self.store.progress[request["serviceRequestId"]]["stage"]
                in {"provider_confirmed", "awaiting_resident_acceptance"}
            ]
            items.sort(key=lambda item: item["updatedAt"], reverse=True)
            return {"items": items}

    def provider_report_completion(
        self,
        *,
        service_request_id: str,
        provider_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        # 授權先於 payload 驗證，避免未指派的廠商用驗證差異探測案件是否存在。
        with self.store.lock:
            request = self.store.service_requests.get(service_request_id)
            if not request:
                raise NotFoundError("找不到服務需求")
            if request.get("currentProviderId") != provider_id:
                raise ForbiddenError()
        message = payload.get("message")
        if message is not None and (not isinstance(message, str) or len(message) > 1000):
            raise ValidationError("message 必須是 1000 字以內的文字")
        # 金額格式錯誤不得推進狀態，否則廠商要等平台人工處理才能重報。
        final_amount = points.normalize_reported_amount(payload.get("finalAmount"))

        return self.store.idempotent(
            actor_id=provider_id,
            operation=f"provider-completion:{service_request_id}",
            key=idempotency_key,
            payload=payload,
            command=lambda: self._apply_completion_report(
                service_request_id=service_request_id,
                message=(message or "").strip(),
                final_amount=final_amount,
            ),
        )

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

    def _start_utility_request(
        self, conversation: dict[str, Any], content: str
    ) -> dict[str, Any]:
        delegation = self.orchestrator.delegate(content)
        if delegation.service_type != SERVICE_TYPE:
            assistant = self._append_assistant(
                conversation["conversationId"],
                "這個 walking skeleton 目前先示範水電修繕。請描述漏水、排水、馬桶、熱水器或用電異常，我會交給水電 Agent。",
                agent="supervisor",
            )
            return self._turn_payload(conversation, assistant, trace_agent="supervisor")

        request_id = _id("sr")
        now = _now()
        request = {
            "serviceRequestId": request_id,
            "conversationId": conversation["conversationId"],
            "residentId": conversation["residentId"],
            "serviceType": SERVICE_TYPE,
            "issueType": self._issue_type(content),
            "symptoms": content,
            "riskScreened": False,
            "hazardFlags": self._hazard_flags(content),
            "safetyHold": self._has_high_risk(content),
            "countyCode": None,
            "districtCode": None,
            "districtName": None,
            "preferredTime": None,
            "urgency": "soon" if any(term in content for term in ("一直", "持續", "嚴重")) else "routine",
            "candidateProviderIds": [],
            "candidateIndex": -1,
            "currentProviderId": None,
            "currentTaskId": None,
            "providerQuestion": None,
            "providerAnswer": None,
            "estimatedAmount": None,
            "finalAmount": None,
            "completionMessage": None,
            "pointsReward": None,
            "createdAt": now,
            "updatedAt": now,
        }
        conversation["serviceRequestId"] = request_id
        conversation["activeAgent"] = ACTIVE_AGENT
        self.store.service_requests[request_id] = request
        self.store.events[request_id] = []

        if request["safetyHold"]:
            self._set_progress(request, "safety_hold", waiting_for="resident")
            assistant_text = (
                "這有觸電或火災風險，請先不要觸碰設備、插座或積水，也不要自行拆修。"
                "若能在不接近危險處的前提下安全斷電才操作總開關；持續冒煙、火花或有人受傷請立即聯絡 119／台電。"
            )
        else:
            self._set_progress(request, "collecting_details", waiting_for="resident")
            assistant_text = (
                "我已交給水電 Agent。先確認用電安全：現場是否有漏電、裸線、冒煙焦味，"
                "或水已接近插座／形成大量積水？"
            )

        assistant = self._append_assistant(
            conversation["conversationId"], assistant_text, agent=ACTIVE_AGENT
        )
        return self._turn_payload(conversation, assistant, trace_agent="supervisor")

    def _continue_utility_request(
        self, conversation: dict[str, Any], content: str
    ) -> dict[str, Any]:
        request = self.store.service_requests[conversation["serviceRequestId"]]
        stage = self.store.progress[request["serviceRequestId"]]["stage"]

        if stage == "safety_hold":
            assistant = self._append_assistant(
                conversation["conversationId"],
                "目前仍維持安全暫停，不會自動派工。請先遠離危險區並聯絡緊急單位；確認現場已由專業人員排除立即風險後，再重新建立一般修繕需求。",
                agent=ACTIVE_AGENT,
            )
            return self._turn_payload(conversation, assistant)

        if stage == "waiting_resident_information":
            request["providerAnswer"] = content
            request["updatedAt"] = _now()
            self._event(request, "resident_information_added", "住戶已補充廠商所需資訊")
            task = self._create_provider_task(
                request, request["currentProviderId"], reason="resident_information_added"
            )
            self._set_progress(request, "waiting_provider_response", waiting_for="provider")
            assistant = self._append_assistant(
                conversation["conversationId"],
                "收到，我已把補充內容回傳給原廠商，現在等待廠商確認。你可以在「我的預約」查看最新進度。",
                agent=ACTIVE_AGENT,
            )
            return self._turn_payload(conversation, assistant, provider_task=task)

        if stage == "awaiting_resident_confirmation":
            if any(phrase in content for phrase in CONFIRM_PHRASES):
                return self._confirm_and_match(conversation, request)
            self._apply_detail_extractors(request, content)
            self._render_artifact(request, supersede=True)
            assistant = self._append_assistant(
                conversation["conversationId"],
                "我已依你的修改產生新版需求文件。請確認內容，正確的話回覆「確認送出」。",
                agent=ACTIVE_AGENT,
            )
            return self._turn_payload(
                conversation,
                assistant,
                artifact=self.store.artifacts[request["serviceRequestId"]],
            )

        if stage == "awaiting_resident_acceptance":
            if any(phrase in content for phrase in ACCEPTANCE_PHRASES):
                return self._accept_completion(conversation, request)
            reward = request.get("pointsReward") or {}
            assistant = self._append_assistant(
                conversation["conversationId"],
                (
                    f"廠商已回報完工：{request.get('completionMessage') or '施工已結束'}。"
                    f"請確認現場狀況無誤後回覆「驗收」，我才會結案並發放"
                    f"{reward.get('estimatedPoints', 0)} 點 OPENPOINT。"
                    "若施工有問題請直接描述，我不會先結案。"
                ),
                agent=ACTIVE_AGENT,
            )
            return self._turn_payload(conversation, assistant)

        if stage == "completed":
            reward = request.get("pointsReward") or {}
            assistant = self._append_assistant(
                conversation["conversationId"],
                (
                    f"這個案件已完成驗收，{reward.get('grantedPoints', 0)} 點 OPENPOINT 已入帳。"
                    "有新的水電需求可以直接描述，我會另開一個案件。"
                ),
                agent=ACTIVE_AGENT,
            )
            return self._turn_payload(conversation, assistant)

        if stage in {"waiting_provider_response", "provider_confirmed"}:
            assistant = self._append_assistant(
                conversation["conversationId"],
                "案件已送出，你可以在「我的預約」查看媒合與廠商確認進度。若廠商需要補充，我會回到這個對話詢問你。",
                agent=ACTIVE_AGENT,
            )
            return self._turn_payload(conversation, assistant)

        self._apply_detail_extractors(request, content)
        if not request["riskScreened"]:
            # 「沒有漏電、冒煙或積水」是對整串風險的否定；先辨識這種
            # 安全篩檢回答，避免只靠關鍵字把否定句誤判為高風險。
            safe_screen_answer = self._is_risk_screen_answer(content) and not any(
                conjunction in content for conjunction in ("但是", "但有", "可是", "仍然")
            )
            if safe_screen_answer:
                request["riskScreened"] = True
                request["hazardFlags"] = {
                    "electricShockRisk": False,
                    "exposedWires": False,
                    "smokeOrBurningSmell": False,
                    "activeFlooding": False,
                }
                assistant_text = "安全狀況了解。請告訴我服務地區（例如台北市內湖區），詳細門牌不需要在 AI 對話中提供。"
            elif self._has_high_risk(content):
                request["safetyHold"] = True
                request["hazardFlags"] = self._hazard_flags(content)
                self._set_progress(request, "safety_hold", waiting_for="resident")
                assistant_text = "偵測到立即風險，請不要觸碰設備或積水，也不要自行拆修；持續冒煙、火花或有人受傷請立即聯絡 119／台電。"
            else:
                assistant_text = "我需要先確認安全：是否有漏電、裸線、冒煙焦味，或大量積水接近插座？"
        elif not request["districtName"]:
            assistant_text = "請告訴我服務地區（例如台北市內湖區），詳細門牌不需要在 AI 對話中提供。"
        elif not request["preferredTime"]:
            assistant_text = "你希望廠商什麼日期與時段到場？例如明天下午兩點到五點。"
        else:
            artifact = self._render_artifact(request)
            self._set_progress(request, "awaiting_resident_confirmation", waiting_for="resident")
            assistant_text = (
                f"我已整理第 {artifact['version']} 版水電需求文件：{artifact['summary']}。"
                "請確認內容，正確的話回覆「確認送出」；確認前不會委派廠商。"
            )

        request["updatedAt"] = _now()
        assistant = self._append_assistant(
            conversation["conversationId"], assistant_text, agent=ACTIVE_AGENT
        )
        return self._turn_payload(
            conversation,
            assistant,
            artifact=self.store.artifacts.get(request["serviceRequestId"]),
        )

    def _confirm_and_match(
        self, conversation: dict[str, Any], request: dict[str, Any]
    ) -> dict[str, Any]:
        artifact = self.store.artifacts[request["serviceRequestId"]]
        artifact["status"] = "confirmed"
        artifact["confirmedAt"] = _now()
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
        if not candidates:
            raise ConflictError("目前服務地區沒有符合硬條件的水電廠商")
        request["candidateProviderIds"] = [p["providerId"] for p in candidates]
        request["candidateIndex"] = 0
        request["currentProviderId"] = candidates[0]["providerId"]
        request["updatedAt"] = _now()
        task = self._create_provider_task(request, request["currentProviderId"], reason="initial_match")
        self._event(request, "provider_matched", "已依地區與回覆 SLA 委派第一順位廠商")
        self._set_progress(request, "waiting_provider_response", waiting_for="provider")
        assistant = self._append_assistant(
            conversation["conversationId"],
            f"需求文件已確認。我已依服務地區與回覆速度委派 {task['provider']['name']}，現在等待廠商回覆；目前不需要你操作。",
            agent=ACTIVE_AGENT,
        )
        return self._turn_payload(
            conversation, assistant, artifact=artifact, provider_task=task
        )

    def _apply_provider_response(
        self,
        *,
        task_id: str,
        provider_id: str,
        action: str,
        expected_version: int,
        message: str,
        arrival_window: str,
        estimated_amount: int | None = None,
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
            task["status"] = action
            task["version"] += 1
            task["message"] = message
            task["completedAt"] = _now()

            if action == "needs_information":
                request["providerQuestion"] = message
                self._event(request, "provider_needs_information", "廠商已提出補充問題")
                self._set_progress(request, "waiting_resident_information", waiting_for="resident")
                assistant = self._append_assistant(
                    request["conversationId"],
                    f"廠商想再確認一件事：{message}",
                    agent=ACTIVE_AGENT,
                )
                return {
                    "serviceRequestId": request["serviceRequestId"],
                    "progress": self._progress_projection(request),
                    "assistantMessage": assistant,
                }

            if action == "decline":
                self._event(request, "provider_declined", message or "廠商婉拒")
                return self._rematch(request, reason="provider_declined")

            provider = self._provider(provider_id)
            request["confirmedArrivalWindow"] = arrival_window
            request["providerConfirmationMessage"] = message
            request["estimatedAmount"] = estimated_amount
            # 訂單成立即揭露預計回饋，狀態停在「01 待發放」；實際發放屬於後續的
            # 服務完成流程，這裡不動用任何外部帳務。
            reward = points.estimate_reward(
                service_type=request["serviceType"],
                issue_type=request["issueType"],
                reported_amount=estimated_amount,
                estimated_at=_now(),
            )
            request["pointsReward"] = reward
            request["updatedAt"] = _now()
            self._event(request, "provider_confirmed", "廠商已確認到場時段")
            self._event(
                request,
                "points_reward_estimated",
                f"預計回饋 {reward['estimatedPoints']} 點 {reward['program']}（{reward['statusLabel']}）",
            )
            self._set_progress(request, "provider_confirmed", waiting_for=None)
            final_content = (
                f"{provider['name']} 已在平台內確認可於 {arrival_window} 到場。"
                f"注意事項：{message or '到場後先勘查，確認範圍與費用後才施工。'}"
                f"{points.reward_disclosure_sentence(reward)}"
                "這是 Demo 的平台內確認，不代表外部付款或不可逆交易已完成。"
            )
            assistant = self._append_assistant(
                request["conversationId"], final_content, agent=ACTIVE_AGENT, kind="final"
            )
            return {
                "serviceRequestId": request["serviceRequestId"],
                "progress": self._progress_projection(request),
                "provider": _public_provider(provider),
                "pointsReward": reward,
                "assistantMessage": assistant,
            }

    def _apply_completion_report(
        self,
        *,
        service_request_id: str,
        message: str,
        final_amount: int | None,
    ) -> dict[str, Any]:
        with self.store.lock:
            request = self.store.service_requests[service_request_id]
            stage = self.store.progress[service_request_id]["stage"]
            if stage != "provider_confirmed":
                raise ConflictError("只有已確認到場的案件可以回報完工")
            request["completionMessage"] = message
            request["finalAmount"] = final_amount
            request["updatedAt"] = _now()
            self._event(request, "provider_reported_completion", "廠商已回報完工，等待住戶驗收")
            self._set_progress(
                request, "awaiting_resident_acceptance", waiting_for="resident"
            )
            reward = request.get("pointsReward") or {}
            assistant = self._append_assistant(
                request["conversationId"],
                (
                    f"廠商回報施工已完成：{message or '施工已結束'}。"
                    "請確認現場狀況無誤後回覆「驗收」，我會結案並發放"
                    f" {reward.get('estimatedPoints', 0)} 點 OPENPOINT。"
                ),
                agent=ACTIVE_AGENT,
            )
            return {
                "serviceRequestId": service_request_id,
                "progress": self._progress_projection(request),
                "assistantMessage": assistant,
            }

    def _accept_completion(
        self, conversation: dict[str, Any], request: dict[str, Any]
    ) -> dict[str, Any]:
        request_id = request["serviceRequestId"]
        estimate = request.get("pointsReward")
        if not estimate:
            raise ConflictError("案件缺少回饋點數紀錄，無法結案")
        # Ledger 是「是否已發放」的真實來源。狀態機已保證只會進來一次，
        # 這裡再擋一層，讓重複驗收不可能重複入帳。
        if self._granted_ledger_entry(request_id):
            raise ConflictError("這個案件的點數已經發放過")

        granted_at = _now()
        reward = points.grant_reward(
            estimate=estimate,
            issue_type=request["issueType"],
            final_amount=request.get("finalAmount"),
            granted_at=granted_at,
        )
        request["pointsReward"] = reward
        request["updatedAt"] = granted_at

        ledger_id = _id("ledger")
        self.store.point_ledger[ledger_id] = points.ledger_entry(
            ledger_id=ledger_id,
            service_request_id=request_id,
            resident_id=request["residentId"],
            reward=reward,
            reason_code="service_completed",
        )

        self._event(request, "resident_accepted_completion", "住戶已完成驗收")
        self._event(
            request,
            "points_granted",
            f"{reward['grantedPoints']} 點 {reward['program']} 已入帳（{reward['statusLabel']}）",
        )
        self._set_progress(request, "completed", waiting_for=None)
        assistant = self._append_assistant(
            conversation["conversationId"],
            points.grant_disclosure_sentence(reward),
            agent=ACTIVE_AGENT,
            kind="final",
        )
        return self._turn_payload(conversation, assistant)

    def _granted_ledger_entry(self, service_request_id: str) -> dict[str, Any] | None:
        return next(
            (
                entry
                for entry in self.store.point_ledger.values()
                if entry["serviceRequestId"] == service_request_id
                and entry["direction"] == points.DIRECTION_EARN
            ),
            None,
        )

    def _active_case_projection(self, request: dict[str, Any]) -> dict[str, Any]:
        artifact = self.store.artifacts.get(request["serviceRequestId"])
        progress = self.store.progress[request["serviceRequestId"]]
        return {
            "serviceRequestId": request["serviceRequestId"],
            "stage": progress["stage"],
            "displayLabel": progress["displayLabel"],
            "summary": artifact["summary"] if artifact else request["symptoms"],
            "arrivalWindow": request.get("confirmedArrivalWindow"),
            "estimatedAmount": request.get("estimatedAmount"),
            "canReportCompletion": progress["stage"] == "provider_confirmed",
            "updatedAt": request["updatedAt"],
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
            self._event(
                request,
                "admin_simulated_timeout",
                f"ADMIN {admin_id} 模擬逾時：{reason}",
            )
            return self._rematch(request, reason="admin_simulated_timeout")

    def _rematch(self, request: dict[str, Any], reason: str) -> dict[str, Any]:
        request["candidateIndex"] += 1
        if request["candidateIndex"] >= len(request["candidateProviderIds"]):
            self._set_progress(request, "rematching", waiting_for="admin")
            raise ConflictError("候選廠商已用完，需要管理員人工處理")
        provider_id = request["candidateProviderIds"][request["candidateIndex"]]
        request["currentProviderId"] = provider_id
        request["updatedAt"] = _now()
        task = self._create_provider_task(request, provider_id, reason=reason)
        self._event(request, "provider_rematched", "已依原排序改派下一位廠商")
        self._set_progress(request, "waiting_provider_response", waiting_for="provider")
        return {
            "serviceRequestId": request["serviceRequestId"],
            "progress": self._progress_projection(request),
            "providerTask": task,
        }

    def _create_provider_task(
        self, request: dict[str, Any], provider_id: str, *, reason: str
    ) -> dict[str, Any]:
        provider = self._provider(provider_id)
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

    def _task_projection(self, task: dict[str, Any]) -> dict[str, Any]:
        request = self.store.service_requests[task["serviceRequestId"]]
        artifact = self.store.artifacts.get(request["serviceRequestId"])
        return {
            "taskId": task["taskId"],
            "serviceRequestId": task["serviceRequestId"],
            "status": task["status"],
            "version": task["version"],
            "createdAt": task["createdAt"],
            "provider": _public_provider(self._provider(task["providerId"])),
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

    def _render_artifact(
        self, request: dict[str, Any], *, supersede: bool = False
    ) -> dict[str, Any]:
        prior = self.store.artifacts.get(request["serviceRequestId"])
        version = (prior["version"] + 1) if prior and supersede else (prior or {}).get("version", 1)
        if prior and supersede:
            prior["status"] = "superseded"
        summary = (
            f"{request['districtName']}｜{request['symptoms']}｜"
            f"希望時段：{request['preferredTime']}｜風險篩檢：未發現立即危險"
        )
        artifact = {
            "artifactId": _id("artifact"),
            "serviceRequestId": request["serviceRequestId"],
            "serviceType": SERVICE_TYPE,
            "schemaVersion": "1.0.0",
            "version": version,
            "status": "draft",
            "summary": summary,
            "canonical": {
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
            },
            "createdBy": ACTIVE_AGENT,
            "createdAt": _now(),
        }
        self.store.artifacts[request["serviceRequestId"]] = artifact
        versions = self.store.artifact_versions.setdefault(request["serviceRequestId"], [])
        if not versions or versions[-1]["artifactId"] != artifact["artifactId"]:
            versions.append(artifact)
        return artifact

    def _turn_payload(
        self,
        conversation: dict[str, Any],
        assistant: dict[str, Any],
        *,
        trace_agent: str = ACTIVE_AGENT,
        artifact: dict[str, Any] | None = None,
        provider_task: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_id = conversation.get("serviceRequestId")
        result: dict[str, Any] = {
            "conversationId": conversation["conversationId"],
            "orchestrationMode": self.orchestrator.mode,
            "activeAgent": conversation.get("activeAgent"),
            "assistantMessage": assistant,
            "trace": [
                {
                    "agent": trace_agent,
                    "action": "delegate" if trace_agent == "supervisor" else "continue_turn",
                    "target": ACTIVE_AGENT if trace_agent == "supervisor" else None,
                    "at": _now(),
                }
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

    def _service_request_projection(self, request: dict[str, Any]) -> dict[str, Any]:
        artifact = self.store.artifacts.get(request["serviceRequestId"])
        provider = (
            _public_provider(self._provider(request["currentProviderId"]))
            if request.get("currentProviderId")
            else None
        )
        return {
            "serviceRequestId": request["serviceRequestId"],
            "conversationId": request["conversationId"],
            "serviceType": request["serviceType"],
            "serviceName": "水電修繕",
            "issueType": request["issueType"],
            "summary": artifact["summary"] if artifact else request["symptoms"],
            "districtName": request["districtName"],
            "preferredTime": request["preferredTime"],
            "safetyHold": request["safetyHold"],
            "provider": provider,
            "pointsReward": request.get("pointsReward"),
            "progress": self._progress_projection(request),
            "createdAt": request["createdAt"],
            "updatedAt": request["updatedAt"],
        }

    def _progress_projection(self, request: dict[str, Any]) -> dict[str, Any]:
        progress = self.store.progress[request["serviceRequestId"]]
        events = self.store.events.get(request["serviceRequestId"], [])
        return {
            **progress,
            "events": list(events[-8:]),
            "pointsReward": request.get("pointsReward"),
            "currentProvider": (
                _public_provider(self._provider(request["currentProviderId"]))
                if request.get("currentProviderId")
                else None
            ),
        }

    def _set_progress(
        self, request: dict[str, Any], stage: str, *, waiting_for: str | None
    ) -> None:
        now = _now()
        self.store.progress[request["serviceRequestId"]] = {
            "serviceRequestId": request["serviceRequestId"],
            "stage": stage,
            "waitingFor": waiting_for,
            "displayLabel": STAGE_LABELS[stage],
            "residentActionRequired": waiting_for == "resident",
            "latestEventAt": now,
        }

    def _event(self, request: dict[str, Any], event_type: str, label: str) -> None:
        self.store.events.setdefault(request["serviceRequestId"], []).append(
            {"eventType": event_type, "label": label, "at": _now()}
        )

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

    def _append_assistant(
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

    @staticmethod
    def _provider(provider_id: str) -> dict[str, Any]:
        provider = next(
            (item for item in DEMO_PROVIDERS if item["providerId"] == provider_id),
            None,
        )
        if not provider:
            raise NotFoundError("找不到廠商")
        return provider

    @staticmethod
    def _issue_type(content: str) -> str:
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

    @staticmethod
    def _has_high_risk(content: str) -> bool:
        cleaned = content
        for phrase in NEGATED_RISK_PHRASES:
            cleaned = cleaned.replace(phrase, "")
        return any(term in cleaned for term in HIGH_RISK_TERMS)

    @staticmethod
    def _hazard_flags(content: str) -> dict[str, bool]:
        high_risk = WalkingSkeletonService._has_high_risk(content)
        return {
            "electricShockRisk": high_risk and any(term in content for term in ("觸電", "漏電", "火花")),
            "exposedWires": high_risk and "裸線" in content,
            "smokeOrBurningSmell": high_risk and any(term in content for term in ("冒煙", "焦味")),
            "activeFlooding": high_risk and any(term in content for term in ("大量積水", "淹水")),
        }

    @staticmethod
    def _is_risk_screen_answer(content: str) -> bool:
        return any(
            phrase in content
            for phrase in (
                "沒有",
                "都沒有",
                "無異常",
                "水量不大",
                "沒有危險",
                "已確認安全",
            )
        )

    def _apply_detail_extractors(self, request: dict[str, Any], content: str) -> None:
        for district_name, codes in DISTRICTS.items():
            if district_name in content:
                request["countyCode"], request["districtCode"] = codes
                request["districtName"] = district_name
                break
        time_match = re.search(
            r"((?:今天|明天|後天|週[一二三四五六日天]|\d{1,2}[/-]\d{1,2})[^。！？]{0,20}(?:上午|下午|晚上|早上|中午)[^。！？]{0,20})",
            content,
        )
        if time_match:
            request["preferredTime"] = time_match.group(1).strip()
        elif any(term in content for term in ("上午", "下午", "晚上", "早上")):
            request["preferredTime"] = content
        request["updatedAt"] = _now()
