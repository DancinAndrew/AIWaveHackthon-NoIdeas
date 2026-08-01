from __future__ import annotations

import sys
import unittest
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

        turn = self._say(conversation_id, "台北市大安區")
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
        _, request_id, task_id, provider_id = self._confirmed_request()
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

        admin_headers = {
            "Content-Type": "application/json",
            "X-Demo-Role": "ADMIN",
            "X-Demo-Admin-Id": "admin-demo-001",
            "Idempotency-Key": "admin-timeout-001",
        }
        timed_out = self.client.post(
            f"/api/v1/admin/workflow-tasks/{next_task['taskId']}/simulate-timeout",
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
            next_task["taskId"],
        )

        progress_text = self.client.get(
            f"/api/v1/service-requests/{request_id}/progress",
            headers=RESIDENT_HEADERS,
        ).get_data(as_text=True)
        self.assertNotIn("taskToken", progress_text)


if __name__ == "__main__":
    unittest.main()
