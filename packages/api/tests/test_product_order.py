"""Selection, order creation, mock payment authorization and supplier accept.

Stage 4 of the product purchase MVP. The security-relevant assertions are:

* the selection endpoint never trusts a client-supplied amount
* only the case owner can select, and only flows that declare selection support
* an order is created only after an explicit confirmation
* `authorizing_payment` is an observable step, and a failed authorization must
  not dispatch a supplier
* order status only moves along the competition-defined transitions
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from walking_skeleton.api import create_app  # noqa: E402
from walking_skeleton.product_flow import ProductPurchaseFlow  # noqa: E402
from walking_skeleton.service import WalkingSkeletonService  # noqa: E402
from walking_skeleton.utility_flow import UtilityRepairFlow  # noqa: E402

RESIDENT = "resident-order-001"
RESIDENT_HEADERS = {
    "Content-Type": "application/json",
    "X-Demo-Resident-Id": RESIDENT,
    "X-Demo-Role": "RESIDENT",
}
COMPLETE_REQUEST = "想買藍牙耳機，預算 3000 以內，送台北市內湖區"


class ProductOrderTestBase(unittest.TestCase):
    payment_succeeds = True

    def setUp(self) -> None:
        authorizer = (lambda order: self.payment_succeeds)
        self.app = create_app(testing=True)
        self.service: WalkingSkeletonService = self.app.extensions[
            "walking_skeleton_service"
        ]
        # Swap in a flow whose mock authorizer the test controls.
        self.service.flows = {
            flow.service_type: flow
            for flow in (
                UtilityRepairFlow(),
                ProductPurchaseFlow(payment_authorizer=authorizer),
            )
        }
        self.client = self.app.test_client()

    def _conversation(self) -> str:
        response = self.client.post(
            "/api/v1/conversations", json={}, headers=RESIDENT_HEADERS
        )
        return response.get_json()["data"]["conversationId"]

    def _say(self, conversation_id: str, message: str) -> dict[str, Any]:
        response = self.client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"message": message},
            headers=RESIDENT_HEADERS,
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["data"]

    def _reach_selection(self) -> tuple[str, dict[str, Any]]:
        conversation_id = self._conversation()
        turn = self._say(conversation_id, COMPLETE_REQUEST)
        self.assertEqual(turn["progress"]["stage"], "awaiting_resident_selection")
        return conversation_id, turn["serviceRequest"]

    def _select(
        self,
        service_request_id: str,
        sku: str,
        expected_version: int,
        *,
        extra: dict[str, Any] | None = None,
        key: str = "select-1",
        headers: dict[str, str] | None = None,
    ):
        body: dict[str, Any] = {"sku": sku, "expectedVersion": expected_version}
        if extra:
            body.update(extra)
        return self.client.post(
            f"/api/v1/service-requests/{service_request_id}/selections",
            json=body,
            headers={**(headers or RESIDENT_HEADERS), "Idempotency-Key": key},
        )


class SelectionEndpointTest(ProductOrderTestBase):
    def test_selection_creates_version_one_artifact(self) -> None:
        conversation_id, request = self._reach_selection()
        sku = request["candidates"][0]["sku"]

        response = self._select(request["serviceRequestId"], sku, 1)
        self.assertEqual(response.status_code, 200, response.get_json())
        data = response.get_json()["data"]

        self.assertEqual(data["artifact"]["version"], 1)
        self.assertEqual(data["artifact"]["status"], "draft")
        self.assertEqual(data["artifact"]["serviceType"], "product_purchase")
        self.assertEqual(data["progress"]["stage"], "awaiting_resident_confirmation")
        self.assertEqual(data["serviceRequest"]["selectedSku"], sku)
        self.assertIsNone(data["serviceRequest"]["orderNo"])

    def test_client_supplied_amounts_are_ignored(self) -> None:
        conversation_id, request = self._reach_selection()
        candidate = request["candidates"][0]

        response = self._select(
            request["serviceRequestId"],
            candidate["sku"],
            1,
            extra={"finalAmount": 1, "shippingFee": 0, "unitPrice": 1},
        )
        self.assertEqual(response.status_code, 200)
        amounts = response.get_json()["data"]["artifact"]["canonical"]["amounts"]
        self.assertEqual(amounts["finalAmount"], candidate["finalAmount"])
        self.assertEqual(amounts["shippingFeeAmount"], candidate["shippingFeeAmount"])
        self.assertEqual(amounts["unitPrice"], candidate["unitPrice"])
        self.assertNotEqual(amounts["finalAmount"], 1)

    def test_sku_outside_candidate_list_is_rejected(self) -> None:
        conversation_id, request = self._reach_selection()
        response = self._select(request["serviceRequestId"], "SKU-999999", 1)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            self.service.store.progress[request["serviceRequestId"]]["stage"],
            "awaiting_resident_selection",
        )

    def test_stale_expected_version_conflicts(self) -> None:
        conversation_id, request = self._reach_selection()
        sku = request["candidates"][0]["sku"]
        response = self._select(request["serviceRequestId"], sku, 99)
        self.assertEqual(response.status_code, 409)

    def test_selecting_with_the_projected_version_succeeds_after_a_research(
        self,
    ) -> None:
        """Mirrors exactly what the UI does: echo back the projected version."""

        conversation_id, request = self._reach_selection()
        # Change requirements so the candidate list is recomputed.
        turn = self._say(conversation_id, "改成預算 20000 以內")
        refreshed = turn["serviceRequest"]
        self.assertEqual(refreshed["candidatesVersion"], 2)

        response = self._select(
            refreshed["serviceRequestId"],
            refreshed["candidates"][0]["sku"],
            refreshed["candidatesVersion"],
            key="after-research",
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(
            response.get_json()["data"]["progress"]["stage"],
            "awaiting_resident_confirmation",
        )

    def test_reselecting_supersedes_the_previous_summary(self) -> None:
        conversation_id, request = self._reach_selection()
        first_sku = request["candidates"][0]["sku"]
        second_sku = request["candidates"][1]["sku"]

        self._select(request["serviceRequestId"], first_sku, 1, key="sel-a")
        second = self._select(request["serviceRequestId"], second_sku, 1, key="sel-b")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.get_json()["data"]["artifact"]["version"], 2)

        versions = self.service.store.artifact_versions[request["serviceRequestId"]]
        self.assertEqual(versions[0]["status"], "superseded")
        self.assertEqual(versions[-1]["status"], "draft")

    def test_utility_case_cannot_use_the_selection_endpoint(self) -> None:
        conversation_id = self._conversation()
        turn = self._say(conversation_id, "浴室水管一直漏水")
        service_request_id = turn["serviceRequest"]["serviceRequestId"]

        response = self._select(service_request_id, "SKU-100000", 1)
        self.assertEqual(response.status_code, 422)
        self.assertIn("不需要選擇", response.get_json()["error"]["message"])

    def test_other_resident_cannot_select(self) -> None:
        conversation_id, request = self._reach_selection()
        sku = request["candidates"][0]["sku"]

        response = self._select(
            request["serviceRequestId"],
            sku,
            1,
            headers={**RESIDENT_HEADERS, "X-Demo-Resident-Id": "resident-attacker"},
        )
        self.assertIn(response.status_code, (403, 404))
        body = response.get_data(as_text=True)
        self.assertNotIn(sku, body, "an unauthorized caller must not learn the SKU")

    def test_idempotency_key_is_required(self) -> None:
        conversation_id, request = self._reach_selection()
        response = self.client.post(
            f"/api/v1/service-requests/{request['serviceRequestId']}/selections",
            json={"sku": request["candidates"][0]["sku"], "expectedVersion": 1},
            headers=RESIDENT_HEADERS,
        )
        self.assertEqual(response.status_code, 422)

    def test_repeating_the_same_selection_is_idempotent(self) -> None:
        conversation_id, request = self._reach_selection()
        sku = request["candidates"][0]["sku"]

        first = self._select(request["serviceRequestId"], sku, 1, key="same")
        second = self._select(request["serviceRequestId"], sku, 1, key="same")
        self.assertEqual(first.get_json()["data"], second.get_json()["data"])
        self.assertEqual(
            len(self.service.store.artifact_versions[request["serviceRequestId"]]), 1
        )

    def test_same_key_with_different_body_conflicts(self) -> None:
        conversation_id, request = self._reach_selection()
        self._select(request["serviceRequestId"], request["candidates"][0]["sku"], 1, key="k")
        response = self._select(
            request["serviceRequestId"], request["candidates"][1]["sku"], 1, key="k"
        )
        self.assertEqual(response.status_code, 409)

    def test_changing_requirements_returns_to_selection(self) -> None:
        conversation_id, request = self._reach_selection()
        self._select(request["serviceRequestId"], request["candidates"][0]["sku"], 1)

        turn = self._say(conversation_id, "改成兩台")
        self.assertEqual(turn["progress"]["stage"], "awaiting_resident_selection")
        self.assertEqual(turn["serviceRequest"]["quantity"], 2)
        self.assertIsNone(turn["serviceRequest"]["selectedSku"])

        # The version moved on, so the old expected version must now conflict.
        stale = self._select(
            request["serviceRequestId"], request["candidates"][0]["sku"], 1, key="stale"
        )
        self.assertEqual(stale.status_code, 409)


class OrderConfirmationTest(ProductOrderTestBase):
    def _selected(self) -> tuple[str, dict[str, Any], dict[str, Any]]:
        conversation_id, request = self._reach_selection()
        candidate = request["candidates"][0]
        self._select(request["serviceRequestId"], candidate["sku"], 1)
        return conversation_id, request, candidate

    def test_question_before_confirming_creates_no_order(self) -> None:
        conversation_id, request, _ = self._selected()
        turn = self._say(conversation_id, "這台有保固嗎")
        self.assertEqual(turn["progress"]["stage"], "awaiting_resident_confirmation")
        self.assertIsNone(turn["serviceRequest"]["orderNo"])
        self.assertEqual(self.service.store.tasks, {})

    def test_confirmation_creates_order_authorizes_and_dispatches(self) -> None:
        conversation_id, request, candidate = self._selected()
        turn = self._say(conversation_id, "確認送出")

        projection = turn["serviceRequest"]
        self.assertTrue(projection["orderNo"].startswith("ORD"))
        self.assertEqual(projection["orderStatus"], "02")
        self.assertEqual(turn["progress"]["stage"], "waiting_provider_response")
        self.assertEqual(turn["progress"]["waitingFor"], "provider")
        self.assertIsNotNone(turn.get("providerTask"))

        stored = self.service.store.service_requests[projection["serviceRequestId"]]
        self.assertEqual(stored["orderType"], "05")
        self.assertTrue(stored["paymentAuthorized"])
        # The order snapshot must equal the candidate the resident chose.
        self.assertEqual(stored["orderAmounts"]["finalAmount"], candidate["finalAmount"])

    def test_confirmed_artifact_amounts_match_the_order(self) -> None:
        conversation_id, request, _ = self._selected()
        self._say(conversation_id, "確認送出")
        service_request_id = request["serviceRequestId"]
        artifact = self.service.store.artifacts[service_request_id]
        stored = self.service.store.service_requests[service_request_id]
        self.assertEqual(artifact["status"], "confirmed")
        self.assertEqual(artifact["canonical"]["amounts"], stored["orderAmounts"])

    def test_order_summary_lines_add_up_for_the_resident(self) -> None:
        """定價 − 折扣 = 小計, then 小計 + 運費 = 實付, all visible in the text."""

        conversation_id = self._conversation()
        turn = self._say(
            conversation_id, "想買除濕機，預算 15000 以內，送台北市大安區"
        )
        request = turn["serviceRequest"]
        discounted = [c for c in request["candidates"] if c["discountAmount"] > 0]
        self.assertTrue(discounted, "expected a discounted除濕機 candidate")
        candidate = discounted[0]

        response = self._select(
            request["serviceRequestId"],
            candidate["sku"],
            request["candidatesVersion"],
            key="readable",
        )
        content = response.get_json()["data"]["assistantMessage"]["content"]

        subtotal = candidate["originalAmount"] - candidate["discountAmount"]
        self.assertIn(f"定價　：{candidate['listPrice']:,} 元", content)
        self.assertIn(f"折扣　：-{candidate['discountAmount']:,} 元", content)
        self.assertIn(f"小計　：{subtotal:,} 元", content)
        self.assertIn(f"實付　：{candidate['finalAmount']:,} 元", content)
        # The already-discounted unit price must not masquerade as the base line.
        self.assertNotIn(f"定價　：{candidate['unitPrice']:,} 元", content)
        self.assertEqual(
            subtotal + candidate["shippingFeeAmount"], candidate["finalAmount"]
        )

    def test_multi_quantity_summary_shows_the_unit_times_quantity(self) -> None:
        conversation_id = self._conversation()
        turn = self._say(
            conversation_id, "想買兩台電鍋，預算 4000 以內，送台北市信義區"
        )
        request = turn["serviceRequest"]
        self.assertEqual(request["quantity"], 2)
        candidate = request["candidates"][0]

        response = self._select(
            request["serviceRequestId"],
            candidate["sku"],
            request["candidatesVersion"],
            key="multi-qty",
        )
        content = response.get_json()["data"]["assistantMessage"]["content"]
        self.assertIn(
            f"定價　：{candidate['listPrice']:,} 元 × 2 ＝ {candidate['originalAmount']:,} 元",
            content,
        )
        self.assertIn("數量　：2", content)

    def test_free_shipping_promotion_summary_avoids_zero_saving_wording(self) -> None:
        """A 「本檔免運」 promotion must not be summarised as 省 0 元."""

        conversation_id = self._conversation()
        turn = self._say(conversation_id, "想買咖啡豆，預算 500 以內，送台北市中山區")
        request = turn["serviceRequest"]
        promo_free = [
            candidate
            for candidate in request["candidates"]
            if candidate["freeShippingSource"] == "promotion"
        ]
        if not promo_free:
            self.skipTest("no free-shipping promotion in this candidate list")

        response = self._select(
            request["serviceRequestId"],
            promo_free[0]["sku"],
            request["candidatesVersion"],
            key="free-ship",
        )
        content = response.get_json()["data"]["assistantMessage"]["content"]
        self.assertNotIn("省 0 元", content)
        self.assertIn("免運費", content)
        self.assertIn("0 元（本檔促銷免運）", content)

    def test_payment_message_discloses_the_mock_and_avoids_paid_wording(self) -> None:
        conversation_id, request, _ = self._selected()
        turn = self._say(conversation_id, "確認送出")
        content = turn["assistantMessage"]["content"]
        self.assertIn("Demo 模擬付款授權", content)
        self.assertIn("未產生真實扣款", content)
        for forbidden in ("已付款", "已扣款", "付款完成", "已完成付款"):
            self.assertNotIn(forbidden, content)

    def test_order_events_record_creation_and_authorization(self) -> None:
        conversation_id, request, _ = self._selected()
        self._say(conversation_id, "確認送出")
        events = {
            event["eventType"]
            for event in self.service.store.events[request["serviceRequestId"]]
        }
        self.assertIn("product_order_created", events)
        self.assertIn("payment_authorized", events)
        self.assertIn("supplier_matched", events)


class PaymentFailureTest(ProductOrderTestBase):
    payment_succeeds = False

    def test_failed_authorization_holds_the_order_and_skips_dispatch(self) -> None:
        conversation_id, request = self._reach_selection()
        self._select(request["serviceRequestId"], request["candidates"][0]["sku"], 1)

        turn = self._say(conversation_id, "確認送出")
        self.assertEqual(turn["progress"]["stage"], "authorizing_payment")
        self.assertEqual(turn["serviceRequest"]["orderStatus"], "01")
        self.assertIsNone(turn.get("providerTask"))
        self.assertEqual(self.service.store.tasks, {})

        stored = self.service.store.service_requests[request["serviceRequestId"]]
        self.assertFalse(stored["paymentAuthorized"])

    def test_retry_after_authorization_succeeds(self) -> None:
        conversation_id, request = self._reach_selection()
        self._select(request["serviceRequestId"], request["candidates"][0]["sku"], 1)
        self._say(conversation_id, "確認送出")

        self.payment_succeeds = True
        turn = self._say(conversation_id, "再試一次")
        self.assertEqual(turn["progress"]["stage"], "waiting_provider_response")
        self.assertEqual(turn["serviceRequest"]["orderStatus"], "02")
        # Retrying must not create a second order.
        stored = self.service.store.service_requests[request["serviceRequestId"]]
        self.assertEqual(
            [
                event["eventType"]
                for event in self.service.store.events[request["serviceRequestId"]]
            ].count("product_order_created"),
            1,
        )
        self.assertTrue(stored["orderNo"])


class SupplierAcceptTest(ProductOrderTestBase):
    def _dispatched(self) -> tuple[str, dict[str, Any], dict[str, Any]]:
        conversation_id, request = self._reach_selection()
        candidate = request["candidates"][0]
        self._select(request["serviceRequestId"], candidate["sku"], 1)
        turn = self._say(conversation_id, "確認送出")
        return conversation_id, request, turn["providerTask"]

    def _supplier_headers(self, provider_id: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Demo-Role": "PROVIDER",
            "X-Demo-Provider-Id": provider_id,
        }

    def test_supplier_sees_order_details_without_resident_identity(self) -> None:
        conversation_id, request, task = self._dispatched()
        headers = self._supplier_headers(task["provider"]["providerId"])
        listing = self.client.get("/api/v1/provider-service-requests", headers=headers)
        items = listing.get_json()["data"]["items"]
        self.assertEqual(len(items), 1)

        body = listing.get_data(as_text=True)
        # The supplier needs the product, amount and delivery district.
        self.assertIn("內湖區", body)
        self.assertIn("實付", body)
        # It must not learn who the resident is or how to contact them.
        # Matched by shape rather than substring: bare digit pairs collide with
        # request IDs and UUIDs, which made an earlier version of this test flaky.
        self.assertNotIn(RESIDENT, body)
        self.assertIsNone(re.search(r"09\d{2}[\s-]?\d{3}[\s-]?\d{3}", body))
        self.assertIsNone(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", body))
        self.assertIsNone(re.search(r"\d+號", body))
        self.assertIsNone(items[0]["residentInformation"])

    def test_supplier_cannot_read_another_suppliers_task(self) -> None:
        conversation_id, request, task = self._dispatched()
        other = next(
            supplier["providerId"]
            for supplier in self.service.flows["product_purchase"].catalog.suppliers()
            if supplier["providerId"] != task["provider"]["providerId"]
        )
        response = self.client.post(
            f"/api/v1/provider-service-requests/{task['taskId']}/responses",
            json={
                "action": "accept",
                "expectedVersion": task["version"],
                "estimatedShipDate": "2026-08-05",
            },
            headers={**self._supplier_headers(other), "Idempotency-Key": "wrong-sup"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.service.store.tasks[task["taskId"]]["status"], "pending")

    def test_accept_requires_estimated_ship_date(self) -> None:
        conversation_id, request, task = self._dispatched()
        headers = self._supplier_headers(task["provider"]["providerId"])
        response = self.client.post(
            f"/api/v1/provider-service-requests/{task['taskId']}/responses",
            json={"action": "accept", "expectedVersion": task["version"]},
            headers={**headers, "Idempotency-Key": "no-date"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("estimatedShipDate", response.get_json()["error"]["message"])
        # The rejected accept must not consume the task.
        self.assertEqual(self.service.store.tasks[task["taskId"]]["status"], "pending")
        self.assertEqual(
            self.service.store.tasks[task["taskId"]]["version"], task["version"]
        )

    def test_accept_confirms_the_order_and_produces_a_final_message(self) -> None:
        conversation_id, request, task = self._dispatched()
        headers = self._supplier_headers(task["provider"]["providerId"])
        response = self.client.post(
            f"/api/v1/provider-service-requests/{task['taskId']}/responses",
            json={
                "action": "accept",
                "expectedVersion": task["version"],
                "estimatedShipDate": "2026-08-05",
                "message": "當日下午出貨",
            },
            headers={**headers, "Idempotency-Key": "accept-1"},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        data = response.get_json()["data"]
        self.assertEqual(data["progress"]["stage"], "provider_confirmed")

        stored = self.service.store.service_requests[request["serviceRequestId"]]
        self.assertEqual(stored["orderStatus"], "03")
        self.assertEqual(stored["estimatedShipDate"], "2026-08-05")

        final = data["assistantMessage"]
        self.assertEqual(final["kind"], "final")
        self.assertIn("2026-08-05", final["content"])
        self.assertIn("實付", final["content"])
        self.assertIn("退換貨政策", final["content"])
        self.assertIn("未產生真實扣款", final["content"])

    def test_accept_is_idempotent(self) -> None:
        conversation_id, request, task = self._dispatched()
        headers = self._supplier_headers(task["provider"]["providerId"])
        body = {
            "action": "accept",
            "expectedVersion": task["version"],
            "estimatedShipDate": "2026-08-05",
        }
        first = self.client.post(
            f"/api/v1/provider-service-requests/{task['taskId']}/responses",
            json=body,
            headers={**headers, "Idempotency-Key": "dup"},
        )
        second = self.client.post(
            f"/api/v1/provider-service-requests/{task['taskId']}/responses",
            json=body,
            headers={**headers, "Idempotency-Key": "dup"},
        )
        self.assertEqual(first.get_json()["data"], second.get_json()["data"])

    def test_utility_accept_still_requires_arrival_window(self) -> None:
        """The shared accept path must keep utility's own required field."""

        conversation_id = self._conversation()
        for line in (
            "浴室水管一直漏水",
            "沒有漏電也沒有冒煙",
            "內湖區",
            "明天下午兩點",
            "確認送出",
        ):
            turn = self._say(conversation_id, line)
        task = turn["providerTask"]
        headers = self._supplier_headers(task["provider"]["providerId"])
        response = self.client.post(
            f"/api/v1/provider-service-requests/{task['taskId']}/responses",
            json={"action": "accept", "expectedVersion": task["version"]},
            headers={**headers, "Idempotency-Key": "utility-no-window"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("arrivalWindow", response.get_json()["error"]["message"])


class OrderStateMachineTest(ProductOrderTestBase):
    def test_illegal_transition_is_rejected(self) -> None:
        flow = self.service.flows["product_purchase"]
        request = {"orderStatus": "01", "orderVersion": 1, "serviceRequestId": "sr_x"}

        with self.assertRaises(Exception) as caught:
            flow._transition_order(self.service, request, "03")
        self.assertIn("不可由", str(caught.exception))
        self.assertEqual(request["orderStatus"], "01")

    def test_legal_transition_bumps_version(self) -> None:
        flow = self.service.flows["product_purchase"]
        request = {"orderStatus": "01", "orderVersion": 1, "serviceRequestId": "sr_x"}
        flow._transition_order(self.service, request, "02")
        self.assertEqual(request["orderStatus"], "02")
        self.assertEqual(request["orderVersion"], 2)

    def test_terminal_status_cannot_move(self) -> None:
        flow = self.service.flows["product_purchase"]
        request = {"orderStatus": "90", "orderVersion": 3, "serviceRequestId": "sr_x"}
        with self.assertRaises(Exception):
            flow._transition_order(self.service, request, "03")

    def test_transition_map_matches_competition_status_codes(self) -> None:
        from walking_skeleton.product_flow import (
            _ALLOWED_ORDER_TRANSITIONS,
            ORDER_STATUS_LABELS,
        )

        self.assertEqual(
            set(ORDER_STATUS_LABELS),
            {"01", "02", "03", "04", "80", "90", "99"},
        )
        self.assertEqual(set(_ALLOWED_ORDER_TRANSITIONS), set(ORDER_STATUS_LABELS))
        for allowed in _ALLOWED_ORDER_TRANSITIONS.values():
            self.assertTrue(allowed <= set(ORDER_STATUS_LABELS))


if __name__ == "__main__":
    unittest.main()
