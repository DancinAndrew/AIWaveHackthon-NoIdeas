"""Product purchase routing, slot filling and candidate presentation.

Covers stage 3 of the MVP: the supervisor routes purchase intent to the product
agent, the flow asks only for missing slots, and a complete request produces a
priced candidate list without creating an order, artifact or provider task.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from walking_skeleton.api import create_app  # noqa: E402
from walking_skeleton.orchestration import DeterministicDemoOrchestrator  # noqa: E402
from walking_skeleton.product_flow import (  # noqa: E402
    extract_budget,
    extract_quantity,
)

RESIDENT_HEADERS = {
    "Content-Type": "application/json",
    "X-Demo-Resident-Id": "resident-product-001",
    "X-Demo-Role": "RESIDENT",
}


class SupervisorRoutingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = DeterministicDemoOrchestrator()

    def test_purchase_intent_routes_to_product_agent(self) -> None:
        delegation = self.orchestrator.delegate("想買一台除濕機，預算五千")
        self.assertEqual(delegation.service_type, "product_purchase")
        self.assertEqual(delegation.target_agent, "product_agent")
        self.assertEqual(delegation.mode, "deterministic-demo")
        self.assertFalse(delegation.needs_clarification)

    def test_utility_symptom_still_routes_to_utility_agent(self) -> None:
        delegation = self.orchestrator.delegate("浴室水管一直漏水")
        self.assertEqual(delegation.service_type, "utility_repair")
        self.assertEqual(delegation.target_agent, "utility_repair_agent")
        self.assertFalse(delegation.needs_clarification)

    def test_ambiguous_message_asks_instead_of_guessing(self) -> None:
        delegation = self.orchestrator.delegate("冷氣壞了想直接買一台新的還是修比較好")
        self.assertTrue(delegation.needs_clarification)
        self.assertIsNone(delegation.service_type)
        self.assertIsNone(delegation.target_agent)
        self.assertEqual(
            set(delegation.candidate_service_types),
            {"utility_repair", "product_purchase"},
        )

    def test_unrelated_message_is_not_routed(self) -> None:
        delegation = self.orchestrator.delegate("今天天氣怎麼樣")
        self.assertIsNone(delegation.service_type)
        self.assertFalse(delegation.needs_clarification)


class ExtractorTest(unittest.TestCase):
    def test_budget_digit_forms(self) -> None:
        self.assertEqual(extract_budget("預算 3000 以內"), 3000)
        self.assertEqual(extract_budget("3000 元以內"), 3000)
        self.assertEqual(extract_budget("不超過 2,500"), 2500)
        self.assertEqual(extract_budget("預算 5 千"), 5000)

    def test_budget_chinese_numeral(self) -> None:
        self.assertEqual(extract_budget("預算五千以內"), 5000)
        self.assertEqual(extract_budget("兩萬以內"), 20000)

    def test_budget_absent(self) -> None:
        self.assertIsNone(extract_budget("想買藍牙耳機"))

    def test_quantity_forms(self) -> None:
        self.assertEqual(extract_quantity("買兩台"), 2)
        self.assertEqual(extract_quantity("要 3 個"), 3)
        self.assertEqual(extract_quantity("數量：4"), 4)
        self.assertEqual(extract_quantity("x5"), 5)

    def test_quantity_absent(self) -> None:
        self.assertIsNone(extract_quantity("想買藍牙耳機，預算 3000"))


class ProductConversationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(testing=True)
        self.client = self.app.test_client()

    def _start(self) -> str:
        response = self.client.post(
            "/api/v1/conversations", json={}, headers=RESIDENT_HEADERS
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()["data"]["conversationId"]

    def _say(self, conversation_id: str, message: str) -> dict:
        response = self.client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"message": message},
            headers=RESIDENT_HEADERS,
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["data"]

    def test_greeting_mentions_both_supported_services(self) -> None:
        response = self.client.post(
            "/api/v1/conversations", json={}, headers=RESIDENT_HEADERS
        )
        greeting = response.get_json()["data"]["assistantMessage"]["content"]
        # Composed from every registered flow's routing hint, so both domains
        # must be discoverable from the greeting alone.
        self.assertIn("漏水", greeting)
        self.assertIn("商品", greeting)

    def test_ambiguous_first_message_creates_no_request(self) -> None:
        conversation_id = self._start()
        turn = self._say(conversation_id, "冷氣壞了想直接買一台新的還是修比較好")
        self.assertIsNone(turn.get("serviceRequest"))
        self.assertIn("不確定", turn["assistantMessage"]["content"])
        self.assertIsNone(turn["activeAgent"])

    def test_asks_only_for_missing_slots_in_order(self) -> None:
        conversation_id = self._start()

        first = self._say(conversation_id, "我想買藍牙耳機")
        self.assertEqual(first["serviceRequest"]["serviceType"], "product_purchase")
        self.assertEqual(first["progress"]["stage"], "collecting_details")
        self.assertIn("預算", first["assistantMessage"]["content"])

        second = self._say(conversation_id, "預算 3000 以內")
        self.assertIn("哪一區", second["assistantMessage"]["content"])
        # The item type is already known, so it must not be asked again.
        self.assertNotIn("想買什麼商品", second["assistantMessage"]["content"])

        third = self._say(conversation_id, "內湖區")
        self.assertEqual(third["progress"]["stage"], "awaiting_resident_selection")

    def test_single_message_with_every_slot_goes_straight_to_candidates(self) -> None:
        conversation_id = self._start()
        turn = self._say(
            conversation_id, "想買藍牙耳機，預算 3000 以內，送台北市內湖區"
        )
        self.assertEqual(turn["progress"]["stage"], "awaiting_resident_selection")
        self.assertEqual(turn["progress"]["waitingFor"], "resident")
        self.assertTrue(turn["progress"]["residentActionRequired"])

        request = turn["serviceRequest"]
        self.assertEqual(request["itemType"], "藍牙耳機")
        self.assertEqual(request["districtName"], "內湖區")
        self.assertEqual(request["quantity"], 1)
        self.assertEqual(len(request["candidates"]), 3)

    def test_candidate_amounts_reconcile_and_respect_budget(self) -> None:
        conversation_id = self._start()
        turn = self._say(
            conversation_id, "想買藍牙耳機，預算 3000 以內，送台北市內湖區"
        )
        for candidate in turn["serviceRequest"]["candidates"]:
            self.assertLessEqual(candidate["unitPrice"], 3000)
            self.assertGreaterEqual(candidate["available"], 1)
            self.assertEqual(
                candidate["originalAmount"]
                - candidate["discountAmount"]
                + candidate["shippingFeeAmount"],
                candidate["finalAmount"],
            )
            self.assertTrue(candidate["reasons"])
            self.assertEqual(candidate["ruleVersion"], "1.0.0")

    def test_projection_exposes_the_candidate_list_version(self) -> None:
        """The client echoes this value back when selecting, so it must ship."""

        conversation_id = self._start()
        first = self._say(
            conversation_id, "想買藍牙耳機，預算 3000 以內，送台北市內湖區"
        )
        self.assertEqual(first["serviceRequest"]["candidatesVersion"], 1)

        # Any re-search must advance it so a stale list cannot be selected from.
        second = self._say(conversation_id, "改成預算 20000 以內")
        self.assertEqual(second["serviceRequest"]["candidatesVersion"], 2)

    def test_selection_stage_creates_no_order_artifact_or_task(self) -> None:
        conversation_id = self._start()
        turn = self._say(
            conversation_id, "想買藍牙耳機，預算 3000 以內，送台北市內湖區"
        )
        self.assertIsNone(turn.get("artifact"))
        self.assertIsNone(turn.get("providerTask"))
        self.assertIsNone(turn["serviceRequest"]["orderNo"])
        self.assertIsNone(turn["serviceRequest"]["selectedSku"])

        service = self.app.extensions["walking_skeleton_service"]
        self.assertEqual(service.store.artifacts, {})
        self.assertEqual(service.store.tasks, {})

    def test_stated_quantity_is_used_and_not_defaulted(self) -> None:
        conversation_id = self._start()
        turn = self._say(
            conversation_id, "想買兩台藍牙耳機，預算 3000 以內，送內湖區"
        )
        self.assertEqual(turn["serviceRequest"]["quantity"], 2)
        self.assertNotIn("數量預設", turn["assistantMessage"]["content"])

    def test_default_quantity_is_disclosed(self) -> None:
        conversation_id = self._start()
        turn = self._say(
            conversation_id, "想買藍牙耳機，預算 3000 以內，送內湖區"
        )
        self.assertIn("數量預設為 1", turn["assistantMessage"]["content"])

    def test_volunteered_contact_details_are_not_stored(self) -> None:
        conversation_id = self._start()
        turn = self._say(
            conversation_id,
            "想買藍牙耳機，預算 3000 以內，送內湖區，我的電話 0912345678，"
            "地址是復興南路一段 390 號，email test@example.com",
        )
        request = turn["serviceRequest"]
        service = self.app.extensions["walking_skeleton_service"]
        stored = service.store.service_requests[request["serviceRequestId"]]

        haystack = repr(stored) + repr(request)
        for secret in ("0912345678", "test@example.com", "390號"):
            self.assertNotIn(secret, haystack, f"{secret} must not be stored")
        # Delivery still needs the district, so that is kept.
        self.assertEqual(request["districtName"], "內湖區")

    def test_no_candidate_within_budget_reports_out_of_stock(self) -> None:
        conversation_id = self._start()
        turn = self._say(conversation_id, "想買除濕機，預算 100 以內，送內湖區")
        self.assertEqual(turn["progress"]["stage"], "out_of_stock")
        self.assertEqual(turn["progress"]["waitingFor"], "resident")
        self.assertEqual(turn["serviceRequest"]["candidates"], [])
        self.assertIsNone(turn["serviceRequest"]["orderNo"])

    def test_adjusting_budget_after_out_of_stock_returns_to_selection(self) -> None:
        conversation_id = self._start()
        self._say(conversation_id, "想買除濕機，預算 100 以內，送內湖區")
        turn = self._say(conversation_id, "預算改成 20000 以內")
        self.assertEqual(turn["progress"]["stage"], "awaiting_resident_selection")
        self.assertTrue(turn["serviceRequest"]["candidates"])

    def test_product_and_utility_cases_coexist_for_one_resident(self) -> None:
        product_conversation = self._start()
        self._say(product_conversation, "想買藍牙耳機，預算 3000 以內，送內湖區")

        utility_conversation = self._start()
        self._say(utility_conversation, "浴室水管漏水")

        listing = self.client.get("/api/v1/service-requests", headers=RESIDENT_HEADERS)
        items = listing.get_json()["data"]["items"]
        names = {item["serviceName"] for item in items}
        self.assertEqual(names, {"商品購買", "水電修繕"})
        for item in items:
            self.assertIn(item["progress"]["stage"], {
                "awaiting_resident_selection",
                "collecting_details",
            })

    def test_utility_flow_is_unaffected_by_product_registration(self) -> None:
        conversation_id = self._start()
        turn = self._say(conversation_id, "浴室水管一直漏水")
        self.assertEqual(turn["serviceRequest"]["serviceType"], "utility_repair")
        self.assertEqual(turn["progress"]["stage"], "collecting_details")
        self.assertIn("漏電", turn["assistantMessage"]["content"])


class SupplierDerivationTest(unittest.TestCase):
    def test_suppliers_are_derived_from_the_catalogue(self) -> None:
        from walking_skeleton.product_catalog import ProductCatalog

        catalog = ProductCatalog.load()
        suppliers = catalog.suppliers()
        self.assertEqual(len(suppliers), 8)
        for supplier in suppliers:
            self.assertTrue(supplier["providerId"])
            self.assertTrue(supplier["name"])
            self.assertGreaterEqual(supplier["rating"], 0)
            self.assertLessEqual(supplier["rating"], 5)
            self.assertTrue(supplier["capabilities"])
            self.assertGreater(supplier["productCount"], 0)
        # Cached, so repeated calls are the same object contents.
        self.assertEqual(suppliers, catalog.suppliers())


if __name__ == "__main__":
    unittest.main()
