from __future__ import annotations

import sys
import unittest
from importlib import import_module
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from walking_skeleton.api import create_app  # noqa: E402


RESIDENT_HEADERS = {
    "Content-Type": "application/json",
    "X-Demo-Resident-Id": "resident-demo-001",
    "X-Demo-Role": "RESIDENT",
}


class UtilityWalkingSkeletonContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(testing=True)
        self.client = self.app.test_client()

    def _start_conversation(self) -> str:
        response = self.client.post(
            "/api/v1/conversations", json={}, headers=RESIDENT_HEADERS
        )
        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["data"]["orchestrationMode"], "deterministic-demo")
        return payload["data"]["conversationId"]

    def _say(self, conversation_id: str, message: str):
        return self.client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"message": message},
            headers=RESIDENT_HEADERS,
        )

    def _confirmed_request(self) -> tuple[str, str, str, str]:
        conversation_id = self._start_conversation()

        turn = self._say(conversation_id, "我家浴室洗手台下方水管一直漏水")
        self.assertEqual(turn.status_code, 200)
        data = turn.get_json()["data"]
        self.assertEqual(data["activeAgent"], "utility_repair_agent")
        self.assertEqual(data["trace"][0]["agent"], "supervisor")
        self.assertIn("用電", data["assistantMessage"]["content"])
        service_request_id = data["serviceRequest"]["serviceRequestId"]

        turn = self._say(conversation_id, "沒有漏電、冒煙或積水，水量不大")
        self.assertIn("地區", turn.get_json()["data"]["assistantMessage"]["content"])

        # 內湖區在 mock provider service areas 中有兩家合格廠商，能驗證改派。
        turn = self._say(conversation_id, "台北市內湖區")
        self.assertIn("時段", turn.get_json()["data"]["assistantMessage"]["content"])

        turn = self._say(conversation_id, "明天下午兩點到五點都可以")
        data = turn.get_json()["data"]
        self.assertEqual(data["progress"]["stage"], "awaiting_resident_confirmation")
        self.assertEqual(data["artifact"]["version"], 1)
        self.assertEqual(data["artifact"]["status"], "draft")
        self.assertIn("確認送出", data["assistantMessage"]["content"])

        turn = self._say(conversation_id, "確認送出")
        self.assertEqual(turn.status_code, 200)
        data = turn.get_json()["data"]
        self.assertEqual(data["progress"]["stage"], "waiting_provider_response")
        self.assertEqual(data["progress"]["waitingFor"], "provider")
        self.assertEqual(data["artifact"]["status"], "confirmed")
        return (
            conversation_id,
            service_request_id,
            data["providerTask"]["taskId"],
            data["providerTask"]["provider"]["providerId"],
        )

    def test_full_needs_information_then_accept_flow(self) -> None:
        conversation_id, request_id, task_id, provider_id = self._confirmed_request()
        provider_headers = {
            "Content-Type": "application/json",
            "X-Demo-Provider-Id": provider_id,
            "X-Demo-Role": "PROVIDER",
            "Idempotency-Key": "provider-question-001",
        }

        queue = self.client.get(
            "/api/v1/provider-service-requests", headers=provider_headers
        )
        self.assertEqual(queue.status_code, 200)
        self.assertEqual(queue.get_json()["data"]["items"][0]["taskId"], task_id)

        needs_info = self.client.post(
            f"/api/v1/provider-service-requests/{task_id}/responses",
            json={
                "action": "needs_information",
                "expectedVersion": 1,
                "message": "請問總水閥是否能關閉？",
            },
            headers=provider_headers,
        )
        self.assertEqual(needs_info.status_code, 200)
        data = needs_info.get_json()["data"]
        self.assertEqual(data["progress"]["stage"], "waiting_resident_information")
        self.assertEqual(data["progress"]["waitingFor"], "resident")

        messages = self.client.get(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=RESIDENT_HEADERS,
        ).get_json()["data"]["items"]
        self.assertIn("總水閥", messages[-1]["content"])

        resident_reply = self._say(conversation_id, "可以，總水閥在門外")
        data = resident_reply.get_json()["data"]
        self.assertEqual(data["progress"]["stage"], "waiting_provider_response")
        follow_up_task = data["providerTask"]

        accept_headers = dict(provider_headers)
        accept_headers["Idempotency-Key"] = "provider-accept-001"
        accepted = self.client.post(
            f"/api/v1/provider-service-requests/{follow_up_task['taskId']}/responses",
            json={
                "action": "accept",
                "expectedVersion": follow_up_task["version"],
                "arrivalWindow": "2026-08-03 14:00-17:00",
                "message": "到場先檢測漏水點，費用現場確認後才施工。",
            },
            headers=accept_headers,
        )
        self.assertEqual(accepted.status_code, 200)
        final_data = accepted.get_json()["data"]
        self.assertEqual(final_data["progress"]["stage"], "provider_confirmed")

        progress = self.client.get(
            f"/api/v1/service-requests/{request_id}/progress",
            headers=RESIDENT_HEADERS,
        )
        self.assertEqual(progress.status_code, 200)
        self.assertIn("已確認", progress.get_json()["data"]["displayLabel"])

        messages = self.client.get(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=RESIDENT_HEADERS,
        ).get_json()["data"]["items"]
        self.assertIn(final_data["provider"]["name"], messages[-1]["content"])
        self.assertIn("平台內確認", messages[-1]["content"])

        bookings = self.client.get(
            "/api/v1/service-requests", headers=RESIDENT_HEADERS
        ).get_json()["data"]["items"]
        self.assertEqual(bookings[0]["serviceRequestId"], request_id)
        self.assertEqual(bookings[0]["progress"]["stage"], "provider_confirmed")

    def test_high_risk_electrical_message_stops_matching(self) -> None:
        conversation_id = self._start_conversation()
        turn = self._say(conversation_id, "牆上插座一直冒煙還有火花，旁邊地板是濕的")
        self.assertEqual(turn.status_code, 200)
        data = turn.get_json()["data"]
        self.assertTrue(data["serviceRequest"]["safetyHold"])
        self.assertEqual(data["progress"]["stage"], "safety_hold")
        self.assertIn("不要觸碰", data["assistantMessage"]["content"])
        self.assertNotIn("providerTask", data)

    def test_provider_cannot_read_or_answer_another_providers_task(self) -> None:
        _, _, task_id, _ = self._confirmed_request()
        wrong_provider_headers = {
            "Content-Type": "application/json",
            "X-Demo-Provider-Id": "provider-not-assigned",
            "X-Demo-Role": "PROVIDER",
            "Idempotency-Key": "cross-provider-attempt",
        }
        queue = self.client.get(
            "/api/v1/provider-service-requests", headers=wrong_provider_headers
        )
        self.assertEqual(queue.get_json()["data"]["items"], [])

        answer = self.client.post(
            f"/api/v1/provider-service-requests/{task_id}/responses",
            json={"action": "accept", "expectedVersion": 1},
            headers=wrong_provider_headers,
        )
        self.assertEqual(answer.status_code, 403)
        self.assertNotIn("taskToken", answer.get_data(as_text=True))

    def test_decline_rematches_and_admin_can_simulate_timeout(self) -> None:
        _, _, task_id, provider_id = self._confirmed_request()
        provider_headers = {
            "Content-Type": "application/json",
            "X-Demo-Provider-Id": provider_id,
            "X-Demo-Role": "PROVIDER",
            "Idempotency-Key": "provider-decline-001",
        }
        declined = self.client.post(
            f"/api/v1/provider-service-requests/{task_id}/responses",
            json={
                "action": "decline",
                "expectedVersion": 1,
                "message": "目前滿單",
            },
            headers=provider_headers,
        )
        self.assertEqual(declined.status_code, 200)
        next_task = declined.get_json()["data"]["providerTask"]
        self.assertNotEqual(next_task["provider"]["providerId"], provider_id)
        self.assertEqual(
            declined.get_json()["data"]["progress"]["stage"],
            "waiting_provider_response",
        )

        # 內湖 mock 只有兩家符合硬條件。另開一案驗證第一家逾時後改派，
        # 避免為了測試捏造第三家不在服務區的廠商。
        _, timeout_request_id, timeout_task_id, _ = self._confirmed_request()
        admin_headers = {
            "Content-Type": "application/json",
            "X-Demo-Role": "ADMIN",
            "X-Demo-Admin-Id": "admin-demo-001",
            "Idempotency-Key": "admin-timeout-001",
        }
        timed_out = self.client.post(
            f"/api/v1/admin/workflow-tasks/{timeout_task_id}/simulate-timeout",
            json={"reason": "Demo 展示逾時改派"},
            headers=admin_headers,
        )
        self.assertEqual(timed_out.status_code, 200)
        self.assertEqual(
            timed_out.get_json()["data"]["progress"]["stage"],
            "waiting_provider_response",
        )
        self.assertNotEqual(
            timed_out.get_json()["data"]["providerTask"]["taskId"],
            timeout_task_id,
        )

        progress_text = self.client.get(
            f"/api/v1/service-requests/{timeout_request_id}/progress",
            headers=RESIDENT_HEADERS,
        ).get_data(as_text=True)
        self.assertNotIn("taskToken", progress_text)

    def test_provider_write_is_idempotent_and_rejects_changed_payload(self) -> None:
        _, _, task_id, provider_id = self._confirmed_request()
        headers = {
            "Content-Type": "application/json",
            "X-Demo-Provider-Id": provider_id,
            "X-Demo-Role": "PROVIDER",
            "Idempotency-Key": "provider-question-retry",
        }
        payload = {
            "action": "needs_information",
            "expectedVersion": 1,
            "message": "請問總水閥是否能關閉？",
        }
        first = self.client.post(
            f"/api/v1/provider-service-requests/{task_id}/responses",
            json=payload,
            headers=headers,
        )
        second = self.client.post(
            f"/api/v1/provider-service-requests/{task_id}/responses",
            json=payload,
            headers=headers,
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.get_json()["data"], first.get_json()["data"])

        changed = self.client.post(
            f"/api/v1/provider-service-requests/{task_id}/responses",
            json={**payload, "message": "改成另一個問題"},
            headers=headers,
        )
        self.assertEqual(changed.status_code, 409)

    def test_invalid_accept_does_not_consume_task(self) -> None:
        _, _, task_id, provider_id = self._confirmed_request()
        headers = {
            "Content-Type": "application/json",
            "X-Demo-Provider-Id": provider_id,
            "X-Demo-Role": "PROVIDER",
            "Idempotency-Key": "invalid-accept",
        }
        invalid = self.client.post(
            f"/api/v1/provider-service-requests/{task_id}/responses",
            json={"action": "accept", "expectedVersion": 1},
            headers=headers,
        )
        self.assertEqual(invalid.status_code, 422)
        queue = self.client.get(
            "/api/v1/provider-service-requests", headers=headers
        ).get_json()["data"]["items"]
        self.assertEqual(queue[0]["taskId"], task_id)
        self.assertEqual(queue[0]["version"], 1)

    def _accept(self, task_id: str, provider_id: str, key: str, **extra):
        headers = {
            "Content-Type": "application/json",
            "X-Demo-Provider-Id": provider_id,
            "X-Demo-Role": "PROVIDER",
            "Idempotency-Key": key,
        }
        return self.client.post(
            f"/api/v1/provider-service-requests/{task_id}/responses",
            json={
                "action": "accept",
                "expectedVersion": 1,
                "arrivalWindow": "2026-08-03 14:00-17:00",
                **extra,
            },
            headers=headers,
        )

    def test_order_established_discloses_reported_amount_reward(self) -> None:
        conversation_id, request_id, task_id, provider_id = self._confirmed_request()

        accepted = self._accept(
            task_id, provider_id, "accept-reward-reported", estimatedAmount=5000
        )
        self.assertEqual(accepted.status_code, 200)
        reward = accepted.get_json()["data"]["pointsReward"]
        self.assertEqual(reward["program"], "OPENPOINT")
        self.assertEqual(reward["estimatedPoints"], 50)
        self.assertEqual(reward["basisAmount"], 5000)
        self.assertEqual(reward["amountSource"], "provider_reported")
        # 訂單成立只揭露「預計」，狀態必須停在 mms_order_record 的 01 待發放。
        self.assertEqual(reward["status"], "01")
        self.assertFalse(reward["capped"])

        content = self.client.get(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=RESIDENT_HEADERS,
        ).get_json()["data"]["items"][-1]["content"]
        self.assertIn("50 點 OPENPOINT", content)
        self.assertIn("待發放", content)
        self.assertIn("尚未連動 OPENPOINT 正式帳戶", content)

        progress = self.client.get(
            f"/api/v1/service-requests/{request_id}/progress",
            headers=RESIDENT_HEADERS,
        ).get_json()["data"]
        self.assertEqual(progress["pointsReward"]["estimatedPoints"], 50)
        self.assertIn(
            "points_reward_estimated",
            [event["eventType"] for event in progress["events"]],
        )

    def test_my_bookings_shows_reward_from_issue_type_baseline(self) -> None:
        _, request_id, task_id, provider_id = self._confirmed_request()

        # 廠商未回報金額時改用類別基準（leak = 2800），並誠實標示來源。
        accepted = self._accept(task_id, provider_id, "accept-reward-baseline")
        self.assertEqual(accepted.status_code, 200)

        bookings = self.client.get(
            "/api/v1/service-requests", headers=RESIDENT_HEADERS
        ).get_json()["data"]["items"]
        booking = next(
            item for item in bookings if item["serviceRequestId"] == request_id
        )
        self.assertEqual(booking["pointsReward"]["estimatedPoints"], 28)
        self.assertEqual(booking["pointsReward"]["basisAmount"], 2800)
        self.assertEqual(booking["pointsReward"]["amountSource"], "issue_type_baseline")

    def test_reward_applies_single_order_cap(self) -> None:
        _, _, task_id, provider_id = self._confirmed_request()

        accepted = self._accept(
            task_id, provider_id, "accept-reward-capped", estimatedAmount=1_000_000
        )

        reward = accepted.get_json()["data"]["pointsReward"]
        self.assertEqual(reward["estimatedPoints"], 500)
        self.assertTrue(reward["capped"])

    def test_invalid_estimated_amount_does_not_consume_task(self) -> None:
        _, _, task_id, provider_id = self._confirmed_request()
        headers = {
            "Content-Type": "application/json",
            "X-Demo-Provider-Id": provider_id,
            "X-Demo-Role": "PROVIDER",
            "Idempotency-Key": "invalid-amount",
        }

        for bad_amount in (0, -100, "abc", True, 1_000_001):
            invalid = self.client.post(
                f"/api/v1/provider-service-requests/{task_id}/responses",
                json={
                    "action": "accept",
                    "expectedVersion": 1,
                    "arrivalWindow": "2026-08-03 14:00-17:00",
                    "estimatedAmount": bad_amount,
                },
                headers=headers,
            )
            self.assertEqual(invalid.status_code, 422, msg=f"amount={bad_amount!r}")

        queue = self.client.get(
            "/api/v1/provider-service-requests", headers=headers
        ).get_json()["data"]["items"]
        self.assertEqual(queue[0]["taskId"], task_id)
        self.assertEqual(queue[0]["version"], 1)

    def _provider_headers(self, provider_id: str, key: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Demo-Provider-Id": provider_id,
            "X-Demo-Role": "PROVIDER",
            "Idempotency-Key": key,
        }

    def _confirmed_and_accepted(self, *, estimated_amount: int | None = 5000):
        conversation_id, request_id, task_id, provider_id = self._confirmed_request()
        extra = {} if estimated_amount is None else {"estimatedAmount": estimated_amount}
        accepted = self._accept(task_id, provider_id, f"accept-{request_id}", **extra)
        self.assertEqual(accepted.status_code, 200)
        return conversation_id, request_id, provider_id

    def _report_completion(self, request_id: str, provider_id: str, key: str, **body):
        return self.client.post(
            f"/api/v1/provider-active-cases/{request_id}/completion",
            json=body,
            headers=self._provider_headers(provider_id, key),
        )

    def test_provider_completion_then_resident_acceptance_grants_points(self) -> None:
        conversation_id, request_id, provider_id = self._confirmed_and_accepted()

        active = self.client.get(
            "/api/v1/provider-active-cases",
            headers=self._provider_headers(provider_id, "list-active"),
        ).get_json()["data"]["items"]
        self.assertEqual(active[0]["serviceRequestId"], request_id)
        self.assertTrue(active[0]["canReportCompletion"])

        reported = self._report_completion(
            request_id,
            provider_id,
            "completion-001",
            message="已更換水管接頭並測試無滲漏",
            finalAmount=6200,
        )
        self.assertEqual(reported.status_code, 200)
        self.assertEqual(
            reported.get_json()["data"]["progress"]["stage"],
            "awaiting_resident_acceptance",
        )
        self.assertEqual(
            reported.get_json()["data"]["progress"]["waitingFor"], "resident"
        )

        # 完工回報後點數仍未發放，狀態必須停在 01 待發放。
        booking = self.client.get(
            "/api/v1/service-requests", headers=RESIDENT_HEADERS
        ).get_json()["data"]["items"][0]
        self.assertEqual(booking["pointsReward"]["status"], "01")
        self.assertIsNone(booking["pointsReward"]["grantedPoints"])

        accepted = self._say(conversation_id, "驗收")
        self.assertEqual(accepted.status_code, 200)
        data = accepted.get_json()["data"]
        self.assertEqual(data["progress"]["stage"], "completed")
        self.assertIsNone(data["progress"]["waitingFor"])

        reward = data["serviceRequest"]["pointsReward"]
        # 依 ADR-0007，發放必須以完工金額重算：6200 × 1% = 62，而非預估的 50。
        self.assertEqual(reward["status"], "02")
        self.assertEqual(reward["grantedPoints"], 62)
        self.assertEqual(reward["estimatedPoints"], 50)
        self.assertEqual(reward["basisAmount"], 6200)
        self.assertTrue(reward["amountAdjusted"])
        self.assertIsNotNone(reward["grantedAt"])

        content = data["assistantMessage"]["content"]
        self.assertIn("62 點 OPENPOINT 已入帳", content)
        self.assertIn("訂單成立時預估 50 點", content)
        self.assertIn("尚未連動 OPENPOINT 正式帳戶", content)

        events = [event["eventType"] for event in data["progress"]["events"]]
        self.assertIn("resident_accepted_completion", events)
        self.assertIn("points_granted", events)

    def test_completion_without_final_amount_reuses_the_disclosed_basis(self) -> None:
        conversation_id, request_id, provider_id = self._confirmed_and_accepted()

        self._report_completion(request_id, provider_id, "completion-noamount")
        data = self._say(conversation_id, "驗收").get_json()["data"]

        reward = data["serviceRequest"]["pointsReward"]
        self.assertEqual(reward["grantedPoints"], 50)
        self.assertEqual(reward["basisAmount"], 5000)
        self.assertFalse(reward["amountAdjusted"])

    def test_repeated_acceptance_cannot_grant_points_twice(self) -> None:
        conversation_id, request_id, provider_id = self._confirmed_and_accepted()
        self._report_completion(request_id, provider_id, "completion-002")
        self._say(conversation_id, "驗收")

        again = self._say(conversation_id, "驗收")

        self.assertEqual(again.status_code, 200)
        data = again.get_json()["data"]
        self.assertEqual(data["progress"]["stage"], "completed")
        self.assertIn("已入帳", data["assistantMessage"]["content"])

        service = self.app.extensions["walking_skeleton_service"]
        earn_entries = [
            entry
            for entry in service.store.point_ledger.values()
            if entry["serviceRequestId"] == request_id
            and entry["direction"] == "earn"
        ]
        self.assertEqual(len(earn_entries), 1)
        self.assertEqual(earn_entries[0]["points"], 50)
        self.assertEqual(earn_entries[0]["status"], "02")

    def test_resident_can_report_a_problem_instead_of_accepting(self) -> None:
        conversation_id, request_id, provider_id = self._confirmed_and_accepted()
        self._report_completion(request_id, provider_id, "completion-003")

        replied = self._say(conversation_id, "接頭還是有一點滴水")

        data = replied.get_json()["data"]
        # 不得因為廠商說完工就結案；沒有明確驗收就不能發點。
        self.assertEqual(data["progress"]["stage"], "awaiting_resident_acceptance")
        self.assertEqual(data["serviceRequest"]["pointsReward"]["status"], "01")
        service = self.app.extensions["walking_skeleton_service"]
        self.assertEqual(service.store.point_ledger, {})

    def test_completion_requires_a_confirmed_case_and_the_assigned_provider(self) -> None:
        _, request_id, task_id, provider_id = self._confirmed_request()

        # 廠商尚未承接，案件還在等待回覆，不能回報完工。
        too_early = self._report_completion(request_id, provider_id, "completion-early")
        self.assertEqual(too_early.status_code, 409)

        self._accept(task_id, provider_id, "accept-for-authz")
        forbidden = self._report_completion(
            request_id, "provider-not-assigned", "completion-forbidden"
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_invalid_final_amount_does_not_advance_the_case(self) -> None:
        _, request_id, provider_id = self._confirmed_and_accepted()

        for bad_amount in (0, -1, "abc", True, 1_000_001):
            invalid = self._report_completion(
                request_id,
                provider_id,
                "completion-invalid",
                finalAmount=bad_amount,
            )
            self.assertEqual(invalid.status_code, 422, msg=f"amount={bad_amount!r}")

        progress = self.client.get(
            f"/api/v1/service-requests/{request_id}/progress",
            headers=RESIDENT_HEADERS,
        ).get_json()["data"]
        self.assertEqual(progress["stage"], "provider_confirmed")

    def test_reward_is_not_disclosed_before_the_order_is_established(self) -> None:
        _, request_id, _, _ = self._confirmed_request()

        booking = self.client.get(
            "/api/v1/service-requests", headers=RESIDENT_HEADERS
        ).get_json()["data"]["items"][0]

        self.assertEqual(booking["serviceRequestId"], request_id)
        self.assertEqual(booking["progress"]["stage"], "waiting_provider_response")
        self.assertIsNone(booking["pointsReward"])

    def test_body_actor_fields_cannot_override_trusted_headers(self) -> None:
        created = self.client.post(
            "/api/v1/conversations",
            json={"residentId": "resident-attacker"},
            headers=RESIDENT_HEADERS,
        )
        conversation_id = created.get_json()["data"]["conversationId"]
        wrong_resident_headers = {
            **RESIDENT_HEADERS,
            "X-Demo-Resident-Id": "resident-attacker",
        }
        forbidden = self.client.get(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=wrong_resident_headers,
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_lambda_flask_entrypoint_exposes_versioned_health(self) -> None:
        legacy_module = import_module("app")
        response = legacy_module.app.test_client().get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["data"]["service"], "utility-walking-skeleton"
        )

    def test_health_reports_the_active_orchestrator_mode(self) -> None:
        service = self.app.extensions["walking_skeleton_service"]
        service.orchestrator = type(
            "AgentCoreRuntimeOrchestratorStub",
            (),
            {"mode": "agentcore-runtime"},
        )()

        response = self.client.get("/api/v1/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["data"]["orchestrationMode"],
            "agentcore-runtime",
        )

    def test_local_cors_allows_vite_hosts_but_not_arbitrary_origins(self) -> None:
        localhost = self.client.get(
            "/api/v1/health", headers={"Origin": "http://localhost:5173"}
        )
        loopback = self.client.get(
            "/api/v1/health", headers={"Origin": "http://127.0.0.1:5173"}
        )
        untrusted = self.client.get(
            "/api/v1/health", headers={"Origin": "https://untrusted.example"}
        )
        self.assertEqual(
            localhost.headers["Access-Control-Allow-Origin"],
            "http://localhost:5173",
        )
        self.assertEqual(
            loopback.headers["Access-Control-Allow-Origin"],
            "http://127.0.0.1:5173",
        )
        self.assertNotIn("Access-Control-Allow-Origin", untrusted.headers)


if __name__ == "__main__":
    unittest.main()


class NegatedRiskScopeTest(unittest.TestCase):
    """否定詞的涵蓋範圍，必須與 Runtime 端的判斷一致。

    兩邊各有一份確定性風險規則是刻意的防禦縱深，但兩份規則對同一句話必須
    得到同樣的結論，否則會出現「Runtime 說安全、Flask 說高風險」這種住戶
    無法脫離的迴圈。
    """

    def setUp(self) -> None:
        self.has_high_risk = import_module("walking_skeleton.utility_flow").has_high_risk

    def test_one_negation_covers_the_whole_listed_group(self) -> None:
        self.assertFalse(self.has_high_risk("沒有漏電、冒煙或積水，水量不大"))

    def test_repeated_negation_still_clears(self) -> None:
        self.assertFalse(self.has_high_risk("沒有漏電也沒有冒煙，水量不大"))

    def test_plain_risk_report_still_holds(self) -> None:
        self.assertTrue(self.has_high_risk("插座冒煙而且有焦味"))

    def test_risk_before_the_negation_still_holds(self) -> None:
        self.assertTrue(self.has_high_risk("有冒煙，沒有漏電"))

    def test_contradiction_after_the_negation_still_holds(self) -> None:
        self.assertTrue(self.has_high_risk("沒有漏電但有冒煙"))

    def test_continuous_marker_is_not_a_negation(self) -> None:
        self.assertTrue(self.has_high_risk("插座不斷冒煙"))

    def test_hazard_flags_do_not_report_a_negated_hazard(self) -> None:
        hazard_flags = import_module("walking_skeleton.utility_flow").hazard_flags

        flags = hazard_flags("沒有漏電但有冒煙")

        self.assertTrue(flags["smokeOrBurningSmell"])
        self.assertFalse(flags["electricShockRisk"])
