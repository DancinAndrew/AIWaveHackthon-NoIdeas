"""Product catalogue, availability, pricing and ranking rules.

Two kinds of test live here on purpose:

* Rule tests build tiny synthetic products so a pricing or filtering rule can be
  pinned without depending on which SKUs happen to exist in the fixtures.
* Integrity tests run against all 300 real fixture rows. The important one is
  `test_sale_price_matches_rule_for_every_product`: it is the regression guard
  for the double-discount bug, because `sale_price` is a derived value and must
  never be used as a pricing input.
"""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from walking_skeleton.product_catalog import (  # noqa: E402
    PRODUCT_RANKING_RULE_VERSION,
    ProductCatalog,
    default_catalog_dir,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "data" / "mock" / "master"


def product(
    sku: str,
    *,
    list_price: int,
    item_type: str = "藍牙耳機",
    category: str = "3C周邊",
    brand: str = "測試牌",
    rating: float = 4.0,
    promotion: dict[str, Any] | None = None,
    delivery: dict[str, Any] | None = None,
    specs: dict[str, str] | None = None,
    supplier_id: str = "sup-1",
) -> dict[str, Any]:
    """Minimal product row shaped like data/mock/master/products.json."""

    return {
        "sku": sku,
        "product_id": f"pid-{sku}",
        "supplier_id": supplier_id,
        "supplier_name": "測試商城",
        "category": category,
        "name": f"{brand} {item_type}",
        "brand": brand,
        "item_type": item_type,
        "specs": specs if specs is not None else {"顏色": "黑"},
        "unit": "件",
        "list_price": list_price,
        # Derived by the same rule the catalogue applies at quantity 1.
        "sale_price": (
            round(list_price * (1 - promotion["discount_rate"]))
            if promotion and promotion["applies_from_quantity"] <= 1
            else list_price
        ),
        "currency": "TWD",
        "promotion": promotion,
        "delivery": delivery
        or {
            "code": "home_delivery",
            "label": "宅配到府",
            "fee": 120,
            "free_over": 990,
            "estimated_days": 3,
            "cold_chain": False,
        },
        "return_policy": {"code": "standard_7d", "label": "到貨 7 日內未拆封可退貨"},
        "warranty_months": 12,
        "rating": rating,
        "source": "test",
    }


def stock(sku: str, on_hand: int, reserved: int = 0, restock_eta: str | None = None):
    return {
        "sku": sku,
        "supplier_id": "sup-1",
        "stock_on_hand": on_hand,
        "reserved": reserved,
        "restock_eta": restock_eta,
        "updated_at": "2026-08-01T00:00:00+08:00",
    }


class AvailabilityTest(unittest.TestCase):
    def test_available_quantity_subtracts_reserved(self) -> None:
        catalog = ProductCatalog([product("S1", list_price=500)], [stock("S1", 3, 2)])
        self.assertEqual(catalog.available_quantity("S1"), 1)

    def test_available_quantity_never_negative(self) -> None:
        catalog = ProductCatalog([product("S1", list_price=500)], [stock("S1", 1, 5)])
        self.assertEqual(catalog.available_quantity("S1"), 0)

    def test_unknown_sku_has_no_availability(self) -> None:
        catalog = ProductCatalog([product("S1", list_price=500)], [stock("S1", 5)])
        self.assertEqual(catalog.available_quantity("NOPE"), 0)

    def test_restock_eta_is_exposed_without_being_invented(self) -> None:
        catalog = ProductCatalog(
            [product("S1", list_price=500), product("S2", list_price=500)],
            [stock("S1", 0, restock_eta="2026-08-20"), stock("S2", 0)],
        )
        self.assertEqual(catalog.restock_eta("S1"), "2026-08-20")
        self.assertIsNone(catalog.restock_eta("S2"))


class PricingTest(unittest.TestCase):
    def test_no_promotion_prices_at_list_price(self) -> None:
        catalog = ProductCatalog([product("S1", list_price=1460)], [stock("S1", 5)])
        quote = catalog.quote("S1", 1)
        self.assertEqual(quote.unit_price, 1460)
        self.assertEqual(quote.discount_amount, 0)
        self.assertFalse(quote.promotion_applied)

    def test_promotion_applies_when_quantity_gate_met(self) -> None:
        promo = {
            "code": "clearance",
            "label": "出清 7 折",
            "discount_rate": 0.3,
            "applies_from_quantity": 1,
        }
        catalog = ProductCatalog(
            [product("S1", list_price=6440, promotion=promo)], [stock("S1", 5)]
        )
        quote = catalog.quote("S1", 1)
        # 6440 * 0.7 == 4508. Using sale_price as the base would give 3156.
        self.assertEqual(quote.unit_price, 4508)
        self.assertEqual(quote.original_amount, 6440)
        self.assertEqual(quote.discount_amount, 1932)
        self.assertTrue(quote.promotion_applied)

    def test_promotion_ignored_below_quantity_gate(self) -> None:
        promo = {
            "code": "second_80",
            "label": "第二件 8 折",
            "discount_rate": 0.2,
            "applies_from_quantity": 2,
        }
        catalog = ProductCatalog(
            [product("S1", list_price=3780, promotion=promo)], [stock("S1", 5)]
        )
        single = catalog.quote("S1", 1)
        self.assertEqual(single.unit_price, 3780)
        self.assertEqual(single.discount_amount, 0)
        self.assertFalse(single.promotion_applied)

        pair = catalog.quote("S1", 2)
        self.assertEqual(pair.unit_price, 3024)
        self.assertEqual(pair.original_amount, 7560)
        self.assertEqual(pair.discount_amount, 1512)
        self.assertTrue(pair.promotion_applied)

    def test_free_shipping_threshold_met(self) -> None:
        catalog = ProductCatalog([product("S1", list_price=1200)], [stock("S1", 5)])
        quote = catalog.quote("S1", 1)
        self.assertEqual(quote.shipping_fee_amount, 0)
        self.assertTrue(quote.free_shipping_applied)
        self.assertEqual(quote.final_amount, 1200)

    def test_free_shipping_threshold_not_met(self) -> None:
        catalog = ProductCatalog([product("S1", list_price=840)], [stock("S1", 5)])
        quote = catalog.quote("S1", 1)
        self.assertEqual(quote.shipping_fee_amount, 120)
        self.assertFalse(quote.free_shipping_applied)
        self.assertEqual(quote.final_amount, 960)

    def test_free_shipping_promotion_waives_the_fee(self) -> None:
        """A 「本檔免運」 promotion must not show its label while charging."""

        promo = {
            "code": "free_shipping",
            "label": "本檔免運",
            "discount_rate": 0.0,
            "applies_from_quantity": 1,
        }
        large = {
            "code": "large_item",
            "label": "大型商品專車",
            "fee": 400,
            "free_over": 9999,
            "estimated_days": 7,
            "cold_chain": False,
        }
        catalog = ProductCatalog(
            [product("S1", list_price=550, promotion=promo, delivery=large)],
            [stock("S1", 5)],
        )
        quote = catalog.quote("S1", 1)
        self.assertEqual(quote.shipping_fee_amount, 0)
        self.assertTrue(quote.free_shipping_applied)
        self.assertEqual(quote.free_shipping_source, "promotion")
        # The promotion waives shipping, not item price.
        self.assertEqual(quote.discount_amount, 0)
        self.assertEqual(quote.unit_price, 550)
        self.assertEqual(quote.final_amount, 550)

    def test_free_shipping_promotion_respects_its_quantity_gate(self) -> None:
        promo = {
            "code": "free_shipping",
            "label": "本檔免運",
            "discount_rate": 0.0,
            "applies_from_quantity": 2,
        }
        catalog = ProductCatalog(
            [product("S1", list_price=200, promotion=promo)], [stock("S1", 5)]
        )
        single = catalog.quote("S1", 1)
        self.assertEqual(single.shipping_fee_amount, 120)
        self.assertIsNone(single.free_shipping_source)

        pair = catalog.quote("S1", 2)
        self.assertEqual(pair.shipping_fee_amount, 0)
        self.assertEqual(pair.free_shipping_source, "promotion")

    def test_threshold_free_shipping_is_labelled_as_threshold(self) -> None:
        catalog = ProductCatalog([product("S1", list_price=1200)], [stock("S1", 5)])
        quote = catalog.quote("S1", 1)
        self.assertEqual(quote.free_shipping_source, "threshold")

    def test_free_shipping_promotion_reason_does_not_claim_zero_saving(self) -> None:
        promo = {
            "code": "free_shipping",
            "label": "本檔免運",
            "discount_rate": 0.0,
            "applies_from_quantity": 1,
        }
        catalog = ProductCatalog(
            [product("S1", list_price=550, promotion=promo)], [stock("S1", 5)]
        )
        found = catalog.search(item_type="藍牙耳機", budget_max=1000, quantity=1)
        reasons = found[0].reasons
        self.assertFalse(
            any("省 0 元" in reason for reason in reasons),
            reasons,
        )
        self.assertTrue(any("免運" in reason for reason in reasons), reasons)

    def test_large_item_never_reaches_free_shipping(self) -> None:
        large = {
            "code": "large_item",
            "label": "大型商品專車",
            "fee": 400,
            "free_over": 9999,
            "estimated_days": 7,
            "cold_chain": False,
        }
        catalog = ProductCatalog(
            [product("S1", list_price=4508, delivery=large)], [stock("S1", 5)]
        )
        quote = catalog.quote("S1", 1)
        self.assertEqual(quote.shipping_fee_amount, 400)
        self.assertFalse(quote.free_shipping_applied)

    def test_list_price_is_the_base_for_a_readable_breakdown(self) -> None:
        """The UI shows 定價 − 折扣 + 運費 = 實付, so those must reconcile.

        `unit_price` is already discounted, so exposing only that next to a
        discount row would make the discount look unapplied.
        """

        promo = {
            "code": "member_5pct",
            "label": "會員 95 折",
            "discount_rate": 0.05,
            "applies_from_quantity": 1,
        }
        catalog = ProductCatalog(
            [product("S1", list_price=10680, promotion=promo)], [stock("S1", 5)]
        )
        quote = catalog.quote("S1", 1)
        self.assertEqual(quote.list_price, 10680)
        self.assertEqual(quote.unit_price, 10146)
        self.assertEqual(quote.original_amount, 10680)
        self.assertEqual(quote.discount_amount, 534)
        # 定價 10,680 − 折扣 534 + 運費 0 = 實付 10,146
        self.assertEqual(
            quote.original_amount - quote.discount_amount + quote.shipping_fee_amount,
            quote.final_amount,
        )
        self.assertEqual(quote.final_amount, 10146)

    def test_list_price_scales_with_quantity_in_the_base_line(self) -> None:
        promo = {
            "code": "bundle_2",
            "label": "第二件 8 折",
            "discount_rate": 0.2,
            "applies_from_quantity": 2,
        }
        catalog = ProductCatalog(
            [product("S1", list_price=3780, promotion=promo)], [stock("S1", 5)]
        )
        quote = catalog.quote("S1", 2)
        self.assertEqual(quote.list_price, 3780)
        self.assertEqual(quote.original_amount, 3780 * 2)
        self.assertEqual(quote.discount_amount, 1512)
        self.assertEqual(
            quote.original_amount - quote.discount_amount + quote.shipping_fee_amount,
            quote.final_amount,
        )

    def test_amounts_are_integers_and_reconcile(self) -> None:
        promo = {
            "code": "clearance",
            "label": "出清 7 折",
            "discount_rate": 0.3,
            "applies_from_quantity": 1,
        }
        catalog = ProductCatalog(
            [product("S1", list_price=6440, promotion=promo)], [stock("S1", 5)]
        )
        quote = catalog.quote("S1", 2)
        for value in (
            quote.unit_price,
            quote.original_amount,
            quote.discount_amount,
            quote.shipping_fee_amount,
            quote.final_amount,
        ):
            self.assertIsInstance(value, int)
        self.assertEqual(
            quote.original_amount - quote.discount_amount + quote.shipping_fee_amount,
            quote.final_amount,
        )

    def test_quantity_must_be_positive(self) -> None:
        catalog = ProductCatalog([product("S1", list_price=500)], [stock("S1", 5)])
        with self.assertRaises(ValueError):
            catalog.quote("S1", 0)


class HardFilterTest(unittest.TestCase):
    def _catalog(self) -> ProductCatalog:
        return ProductCatalog(
            [
                product("IN-BUDGET", list_price=900),
                product("OVER-BUDGET", list_price=1200),
                product("NO-STOCK", list_price=900),
                product("RESERVED-OUT", list_price=900),
                product("OTHER-TYPE", list_price=900, item_type="機械鍵盤"),
                product("OTHER-BRAND", list_price=900, brand="別的牌"),
                product(
                    "WRONG-SPEC",
                    list_price=900,
                    specs={"顏色": "白"},
                ),
            ],
            [
                stock("IN-BUDGET", 10),
                stock("OVER-BUDGET", 10),
                stock("NO-STOCK", 0),
                stock("RESERVED-OUT", 2, 2),
                stock("OTHER-TYPE", 10),
                stock("OTHER-BRAND", 10),
                stock("WRONG-SPEC", 10),
            ],
        )

    def _skus(self, **kwargs) -> list[str]:
        defaults = {"item_type": "藍牙耳機", "budget_max": 1000, "quantity": 1}
        defaults.update(kwargs)
        return [c.sku for c in self._catalog().search(**defaults)]

    def test_budget_excludes_more_expensive_unit_price(self) -> None:
        self.assertNotIn("OVER-BUDGET", self._skus())

    def test_budget_boundary_is_inclusive(self) -> None:
        catalog = ProductCatalog([product("EXACT", list_price=1000)], [stock("EXACT", 5)])
        found = catalog.search(item_type="藍牙耳機", budget_max=1000, quantity=1)
        self.assertEqual([c.sku for c in found], ["EXACT"])

    def test_zero_stock_is_excluded(self) -> None:
        self.assertNotIn("NO-STOCK", self._skus())

    def test_reserved_stock_is_excluded(self) -> None:
        self.assertNotIn("RESERVED-OUT", self._skus())

    def test_other_item_type_is_excluded(self) -> None:
        self.assertNotIn("OTHER-TYPE", self._skus())

    def test_brand_preference_excludes_other_brands(self) -> None:
        self.assertNotIn("OTHER-BRAND", self._skus(brands=["測試牌"]))

    def test_required_spec_excludes_mismatch(self) -> None:
        self.assertNotIn("WRONG-SPEC", self._skus(required_specs={"顏色": "黑"}))

    def test_quantity_larger_than_availability_is_excluded(self) -> None:
        catalog = ProductCatalog([product("S1", list_price=500)], [stock("S1", 2)])
        self.assertEqual(catalog.search(item_type="藍牙耳機", budget_max=1000, quantity=3), [])

    def test_category_search_matches_when_item_type_absent(self) -> None:
        catalog = ProductCatalog(
            [product("S1", list_price=500, item_type="機械鍵盤", category="3C周邊")],
            [stock("S1", 5)],
        )
        found = catalog.search(category="3C周邊", budget_max=1000, quantity=1)
        self.assertEqual([c.sku for c in found], ["S1"])

    def test_search_requires_item_type_or_category(self) -> None:
        catalog = ProductCatalog([product("S1", list_price=500)], [stock("S1", 5)])
        with self.assertRaises(ValueError):
            catalog.search(budget_max=1000, quantity=1)


class RankingTest(unittest.TestCase):
    def _catalog(self) -> ProductCatalog:
        promo = {
            "code": "clearance",
            "label": "出清 7 折",
            "discount_rate": 0.3,
            "applies_from_quantity": 1,
        }
        cvs = {
            "code": "cvs_pickup",
            "label": "超商取貨",
            "fee": 60,
            "free_over": 490,
            "estimated_days": 4,
            "cold_chain": False,
        }
        return ProductCatalog(
            [
                product("PROMO", list_price=3860, promotion=promo, rating=3.7, delivery=cvs),
                product("TOP-RATED", list_price=1460, rating=4.3),
                product("CHEAPEST", list_price=840, rating=3.5),
            ],
            [stock("PROMO", 9), stock("TOP-RATED", 27), stock("CHEAPEST", 27)],
        )

    def test_ranking_is_deterministic_across_repeated_calls(self) -> None:
        catalog = self._catalog()
        runs = [
            [(c.sku, c.score) for c in catalog.search(
                item_type="藍牙耳機", budget_max=3000, quantity=1
            )]
            for _ in range(10)
        ]
        self.assertEqual(len(set(map(tuple, runs))), 1, runs[:2])

    def test_tie_break_is_sku_lexicographic(self) -> None:
        catalog = ProductCatalog(
            [
                product("SKU-B", list_price=500, rating=4.0),
                product("SKU-A", list_price=500, rating=4.0),
            ],
            [stock("SKU-A", 5), stock("SKU-B", 5)],
        )
        found = catalog.search(item_type="藍牙耳機", budget_max=1000, quantity=1)
        self.assertEqual([c.score for c in found][0], [c.score for c in found][1])
        self.assertEqual([c.sku for c in found], ["SKU-A", "SKU-B"])

    def test_reasons_are_rule_generated_strings(self) -> None:
        catalog = self._catalog()
        found = catalog.search(item_type="藍牙耳機", budget_max=3000, quantity=1)
        by_sku = {c.sku: c for c in found}

        self.assertTrue(all(c.reasons for c in found))
        self.assertTrue(
            any("出清 7 折" in reason for reason in by_sku["PROMO"].reasons),
            by_sku["PROMO"].reasons,
        )
        self.assertTrue(
            any("免運" in reason for reason in by_sku["CHEAPEST"].reasons),
            by_sku["CHEAPEST"].reasons,
        )
        self.assertTrue(
            any("實付金額最低" in reason for reason in by_sku["CHEAPEST"].reasons),
            by_sku["CHEAPEST"].reasons,
        )

    def test_limit_caps_candidate_count(self) -> None:
        catalog = self._catalog()
        self.assertEqual(
            len(catalog.search(item_type="藍牙耳機", budget_max=3000, quantity=1, limit=2)),
            2,
        )

    def test_rule_version_is_pinned(self) -> None:
        self.assertEqual(PRODUCT_RANKING_RULE_VERSION, "1.0.0")


class FixtureIntegrityTest(unittest.TestCase):
    """Runs against the real 300-row fixtures."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.digests = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                FIXTURE_DIR / "products.json",
                FIXTURE_DIR / "product_inventory.json",
            )
        }
        cls.catalog = ProductCatalog.load()

    def test_default_directory_points_at_the_mock_master_fixtures(self) -> None:
        self.assertEqual(default_catalog_dir(), FIXTURE_DIR)

    def test_loads_every_product_and_inventory_row(self) -> None:
        self.assertEqual(len(self.catalog.products), 300)
        self.assertEqual(len(self.catalog.inventory), 300)

    def test_indexes_cover_all_item_types_and_categories(self) -> None:
        raw = json.loads((FIXTURE_DIR / "products.json").read_text(encoding="utf-8"))
        self.assertEqual(
            set(self.catalog.item_types()), {item["item_type"] for item in raw}
        )
        self.assertEqual(
            set(self.catalog.categories()), {item["category"] for item in raw}
        )
        for item in raw:
            self.assertIn(item["sku"], self.catalog.products)

    def test_sale_price_matches_rule_for_every_product(self) -> None:
        """Regression guard for the double-discount bug.

        `sale_price` is the unit price once the promotion quantity gate is met,
        so for gate <= 1 it must equal the rule's quantity-1 unit price. Any
        drift means the catalogue data and the pricing rule disagree.
        """

        checked = 0
        for sku, item in self.catalog.products.items():
            promotion = item.get("promotion")
            gate = promotion["applies_from_quantity"] if promotion else 1
            if gate > 1:
                # Gate not met at quantity 1, so sale_price must equal list_price.
                self.assertEqual(
                    item["sale_price"],
                    item["list_price"],
                    f"{sku} has an unmet promotion gate but a discounted sale_price",
                )
                continue
            self.assertEqual(
                self.catalog.quote(sku, 1).unit_price,
                item["sale_price"],
                f"{sku} pricing rule disagrees with sale_price",
            )
            checked += 1
        self.assertGreater(checked, 200, "expected most fixtures to exercise this rule")

    def test_no_negative_availability_in_fixtures(self) -> None:
        for sku in self.catalog.products:
            self.assertGreaterEqual(self.catalog.available_quantity(sku), 0, sku)

    def test_loading_does_not_mutate_fixture_files(self) -> None:
        ProductCatalog.load()
        for path in (
            FIXTURE_DIR / "products.json",
            FIXTURE_DIR / "product_inventory.json",
        ):
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                self.digests[path.name],
                f"{path.name} was modified by loading",
            )

    def test_real_demo_scenario_returns_priced_candidates(self) -> None:
        found = self.catalog.search(
            item_type="藍牙耳機", budget_max=3000, quantity=1, limit=3
        )
        self.assertEqual(len(found), 3)
        for candidate in found:
            self.assertLessEqual(candidate.quote.unit_price, 3000)
            self.assertGreaterEqual(candidate.available, 1)
            self.assertEqual(
                candidate.quote.original_amount
                - candidate.quote.discount_amount
                + candidate.quote.shipping_fee_amount,
                candidate.quote.final_amount,
            )

    def test_resolve_item_type_from_free_text(self) -> None:
        self.assertEqual(
            self.catalog.resolve_item_type("想買一台除濕機，預算五千"), "除濕機"
        )
        self.assertIsNone(self.catalog.resolve_item_type("我家浴室漏水"))


if __name__ == "__main__":
    unittest.main()
