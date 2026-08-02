"""Product catalogue, availability, pricing and deterministic ranking.

Boundary rules this module exists to enforce:

* Prices, stock and shipping come only from structured data. The Knowledge Base
  is never a source for them, and a model never produces an amount.
* `list_price` is the single pricing base. `sale_price` is a *derived* value —
  the unit price once a promotion's quantity gate is met — so using it as an
  input double-discounts the 160 fixture rows whose promotion is already baked
  in, and wrongly discounts the 42 rows whose gate is 2.
* Ranking is a versioned rule. The same snapshot plus the same request must
  produce the same order and the same scores, and every reason string is
  generated here rather than by a model.

The public functions take plain data and return plain dataclasses so a Flask
route and an AgentCore Gateway tool Lambda can share them without either
transport leaking in.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Bump when the hard filter or the scoring weights change, so stored candidate
# lists can be told apart from ones produced by a newer rule.
PRODUCT_RANKING_RULE_VERSION = "1.0.0"

# Scoring weights. They sum to 1.0 so `score` reads as a percentage.
_WEIGHT_BUDGET_FIT = 0.35
_WEIGHT_RATING = 0.25
_WEIGHT_SPEED = 0.20
_WEIGHT_PROMOTION = 0.20

# Longest delivery estimate in the fixtures; used to normalise the speed score.
_SLOWEST_DELIVERY_DAYS = 7

_DEFAULT_CANDIDATE_LIMIT = 3

# The fixtures carry no supplier response SLA, so one honest demo constant is
# used instead of inventing a different number per supplier.
_SUPPLIER_RESPONSE_SLA_HOURS = 24

# Promotion whose entire value is waiving the delivery fee. The fixtures encode
# it as code `free_shipping` with `discount_rate = 0.0`, so a rule that only
# looked at the rate would show the label 「本檔免運」 while still charging
# shipping. The fixtures have no explicit "waives shipping" field, so this
# interpretation comes from the promotion code and label.
FREE_SHIPPING_PROMOTION_CODE = "free_shipping"


def default_catalog_dir() -> Path:
    """Where the catalogue fixtures live.

    `PRODUCT_CATALOG_DIR` overrides it so a deployment can ship the JSON
    somewhere else without touching code.
    """

    override = os.getenv("PRODUCT_CATALOG_DIR", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "data" / "mock" / "master"


@dataclass(frozen=True, slots=True)
class Quote:
    """Every amount a resident is shown, itemised.

    `original_amount - discount_amount + shipping_fee_amount == final_amount`
    always holds, so the resident can reconcile the total by hand.
    """

    quantity: int
    # Catalogue list price for one unit, before any promotion. Exposed so the UI
    # can show a base line the resident can add up, rather than showing the
    # already-discounted unit price next to a discount row.
    list_price: int
    unit_price: int
    original_amount: int
    discount_amount: int
    shipping_fee_amount: int
    final_amount: int
    currency: str
    promotion_applied: bool
    promotion_label: str | None
    free_shipping_applied: bool
    # Why shipping is free: "promotion" when a free-shipping promotion applies,
    # "threshold" when the order reached `free_over`, None when it is charged.
    free_shipping_source: str | None
    free_shipping_threshold: int
    delivery_code: str
    delivery_label: str
    estimated_days: int
    cold_chain: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "quantity": self.quantity,
            "listPrice": self.list_price,
            "unitPrice": self.unit_price,
            "originalAmount": self.original_amount,
            "discountAmount": self.discount_amount,
            "shippingFeeAmount": self.shipping_fee_amount,
            "finalAmount": self.final_amount,
            "currency": self.currency,
            "promotionApplied": self.promotion_applied,
            "promotionLabel": self.promotion_label,
            "freeShippingApplied": self.free_shipping_applied,
            "freeShippingSource": self.free_shipping_source,
            "freeShippingThreshold": self.free_shipping_threshold,
            "deliveryCode": self.delivery_code,
            "deliveryLabel": self.delivery_label,
            "estimatedDays": self.estimated_days,
            "coldChain": self.cold_chain,
        }


@dataclass(frozen=True, slots=True)
class Candidate:
    """One ranked purchase option, ready to render without further lookups."""

    sku: str
    name: str
    brand: str
    item_type: str
    category: str
    specs: dict[str, str]
    supplier_id: str
    supplier_name: str
    rating: float
    warranty_months: int
    return_policy_label: str
    available: int
    quote: Quote
    score: int
    reasons: tuple[str, ...]
    rule_version: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "sku": self.sku,
            "name": self.name,
            "brand": self.brand,
            "itemType": self.item_type,
            "category": self.category,
            "specs": dict(self.specs),
            "supplierId": self.supplier_id,
            "supplierName": self.supplier_name,
            "rating": self.rating,
            "warrantyMonths": self.warranty_months,
            "returnPolicyLabel": self.return_policy_label,
            "available": self.available,
            "score": self.score,
            "reasons": list(self.reasons),
            "ruleVersion": self.rule_version,
            **self.quote.as_dict(),
        }


class ProductCatalog:
    """Read-only view over the product and inventory fixtures."""

    def __init__(
        self,
        products: list[dict[str, Any]],
        inventory: list[dict[str, Any]],
    ) -> None:
        self.products: dict[str, dict[str, Any]] = {
            item["sku"]: item for item in products
        }
        self.inventory: dict[str, dict[str, Any]] = {
            row["sku"]: row for row in inventory
        }
        self._by_item_type: dict[str, list[str]] = {}
        self._by_category: dict[str, list[str]] = {}
        for sku, item in self.products.items():
            self._by_item_type.setdefault(item["item_type"], []).append(sku)
            self._by_category.setdefault(item["category"], []).append(sku)
        for index in (self._by_item_type, self._by_category):
            for skus in index.values():
                skus.sort()
        # Longest first so "USB-C 傳輸線" wins over a hypothetical "傳輸線".
        self._item_type_lookup: tuple[str, ...] = tuple(
            sorted(self._by_item_type, key=len, reverse=True)
        )
        self._suppliers: tuple[dict[str, Any], ...] | None = None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, directory: Path | None = None) -> ProductCatalog:
        source = directory or default_catalog_dir()
        return cls(
            cls._read_rows(source / "products.json", "sku"),
            cls._read_rows(source / "product_inventory.json", "sku"),
        )

    @staticmethod
    def _read_rows(path: Path, key: str) -> list[dict[str, Any]]:
        if not path.is_file():
            raise RuntimeError(f"product catalogue file is missing: {path}")
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            raise RuntimeError(f"product catalogue file must be a non-empty list: {path}")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get(key), str):
                raise RuntimeError(f"every row in {path.name} needs a string {key}")
        return rows

    # ------------------------------------------------------------------
    # Vocabulary
    # ------------------------------------------------------------------

    def item_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_item_type))

    def categories(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_category))

    def resolve_item_type(self, text: str) -> str | None:
        """Find the catalogue item type named in free text, if any."""

        for item_type in self._item_type_lookup:
            if item_type in text:
                return item_type
        return None

    def resolve_category(self, text: str) -> str | None:
        for category in sorted(self._by_category, key=len, reverse=True):
            if category in text:
                return category
        return None

    def skus_for(
        self, *, item_type: str | None = None, category: str | None = None
    ) -> tuple[str, ...]:
        """Every SKU under an item type or category, ignoring stock and budget."""

        if item_type:
            return tuple(self._by_item_type.get(item_type, ()))
        if category:
            return tuple(self._by_category.get(category, ()))
        return ()

    def suppliers(self) -> tuple[dict[str, Any], ...]:
        """Suppliers derived from the catalogue rows.

        The fixtures have no supplier master file: `supplier_id` and
        `supplier_name` only exist as product fields, so the supplier list is
        aggregated here. `rating` is the mean of the supplier's product ratings
        and `capabilities` come from the delivery methods they actually offer.

        `responseSlaHours` has no source in the fixtures, so it is a fixed demo
        constant rather than an invented per-supplier number.
        """

        if self._suppliers is None:
            grouped: dict[str, dict[str, Any]] = {}
            for item in self.products.values():
                entry = grouped.setdefault(
                    item["supplier_id"],
                    {
                        "providerId": item["supplier_id"],
                        "name": item["supplier_name"],
                        "ratings": [],
                        "capabilities": set(),
                    },
                )
                entry["ratings"].append(float(item["rating"]))
                entry["capabilities"].add(str(item["delivery"]["code"]))
                if item["delivery"]["cold_chain"]:
                    entry["capabilities"].add("cold_chain")
            self._suppliers = tuple(
                {
                    "providerId": entry["providerId"],
                    "name": entry["name"],
                    "rating": round(sum(entry["ratings"]) / len(entry["ratings"]), 1),
                    "responseSlaHours": _SUPPLIER_RESPONSE_SLA_HOURS,
                    "capabilities": sorted(entry["capabilities"]),
                    "productCount": len(entry["ratings"]),
                }
                for entry in sorted(grouped.values(), key=lambda row: row["providerId"])
            )
        return self._suppliers

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    def available_quantity(self, sku: str) -> int:
        """Sellable units: on hand minus already reserved, never negative."""

        row = self.inventory.get(sku)
        if row is None:
            return 0
        return max(0, int(row["stock_on_hand"]) - int(row["reserved"]))

    def restock_eta(self, sku: str) -> str | None:
        """Supplier-provided restock estimate, or None when genuinely unknown."""

        row = self.inventory.get(sku)
        if row is None:
            return None
        eta = row.get("restock_eta")
        return eta if isinstance(eta, str) and eta else None

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------

    def quote(self, sku: str, quantity: int) -> Quote:
        item = self.products.get(sku)
        if item is None:
            raise KeyError(f"unknown sku: {sku}")
        return quote_for(item, quantity)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        *,
        item_type: str | None = None,
        category: str | None = None,
        budget_max: int,
        quantity: int,
        brands: list[str] | None = None,
        required_specs: dict[str, str] | None = None,
        limit: int = _DEFAULT_CANDIDATE_LIMIT,
    ) -> list[Candidate]:
        """Hard-condition filter followed by versioned soft ranking.

        Hard conditions are all mandatory: item type or category, unit price
        within budget, and enough sellable stock for the requested quantity.
        Brand and spec constraints are only applied when the resident stated
        them.
        """

        if quantity < 1:
            raise ValueError("quantity must be at least 1")
        if budget_max < 0:
            raise ValueError("budget_max must not be negative")
        if not item_type and not category:
            raise ValueError("search needs an item_type or a category")

        if item_type:
            skus = self._by_item_type.get(item_type, [])
        else:
            skus = self._by_category.get(category or "", [])

        wanted_brands = {brand.strip() for brand in (brands or []) if brand.strip()}
        specs = {
            name.strip(): str(value).strip()
            for name, value in (required_specs or {}).items()
            if str(value).strip()
        }

        passed: list[tuple[dict[str, Any], int, Quote]] = []
        for sku in skus:
            item = self.products[sku]
            available = self.available_quantity(sku)
            if available < quantity:
                continue
            if wanted_brands and item["brand"] not in wanted_brands:
                continue
            if specs and not _specs_match(item.get("specs") or {}, specs):
                continue
            priced = quote_for(item, quantity)
            if priced.unit_price > budget_max:
                continue
            passed.append((item, available, priced))

        if not passed:
            return []

        cheapest_final = min(priced.final_amount for _, _, priced in passed)
        scored = [
            (
                _score(item, priced, budget_max=budget_max),
                item,
                available,
                priced,
            )
            for item, available, priced in passed
        ]
        # Highest score first; SKU ascending keeps ties fully reproducible.
        scored.sort(key=lambda row: (-row[0], row[1]["sku"]))

        return [
            Candidate(
                sku=item["sku"],
                name=item["name"],
                brand=item["brand"],
                item_type=item["item_type"],
                category=item["category"],
                specs=dict(item.get("specs") or {}),
                supplier_id=item["supplier_id"],
                supplier_name=item["supplier_name"],
                rating=float(item["rating"]),
                warranty_months=int(item["warranty_months"]),
                return_policy_label=item["return_policy"]["label"],
                available=available,
                quote=priced,
                score=score,
                reasons=_reasons(
                    item,
                    priced,
                    budget_max=budget_max,
                    is_cheapest=priced.final_amount == cheapest_final,
                ),
                rule_version=PRODUCT_RANKING_RULE_VERSION,
            )
            for score, item, available, priced in scored[: max(1, limit)]
        ]


# ----------------------------------------------------------------------
# Rules
# ----------------------------------------------------------------------


def quote_for(item: dict[str, Any], quantity: int) -> Quote:
    """Price one catalogue row at a quantity.

    `list_price` is the base. A promotion only applies once the requested
    quantity reaches its `applies_from_quantity` gate.
    """

    if quantity < 1:
        raise ValueError("quantity must be at least 1")

    list_price = int(item["list_price"])
    promotion = item.get("promotion") or None
    promotion_applied = bool(promotion) and quantity >= int(
        promotion["applies_from_quantity"]
    )
    unit_price = (
        round(list_price * (1 - float(promotion["discount_rate"])))
        if promotion_applied
        else list_price
    )

    original_amount = list_price * quantity
    after_discount = unit_price * quantity
    discount_amount = original_amount - after_discount

    delivery = item["delivery"]
    threshold = int(delivery["free_over"])
    # A free-shipping promotion waives the fee regardless of the threshold;
    # otherwise the order has to reach `free_over` on its own.
    promotion_waives_shipping = promotion_applied and str(
        promotion.get("code")
    ) == FREE_SHIPPING_PROMOTION_CODE
    if promotion_waives_shipping:
        free_shipping_source = "promotion"
    elif after_discount >= threshold:
        free_shipping_source = "threshold"
    else:
        free_shipping_source = None
    shipping_fee = 0 if free_shipping_source else int(delivery["fee"])

    return Quote(
        quantity=quantity,
        list_price=list_price,
        unit_price=unit_price,
        original_amount=original_amount,
        discount_amount=discount_amount,
        shipping_fee_amount=shipping_fee,
        final_amount=after_discount + shipping_fee,
        currency=str(item.get("currency") or "TWD"),
        promotion_applied=promotion_applied,
        promotion_label=str(promotion["label"]) if promotion_applied else None,
        free_shipping_applied=free_shipping_source is not None,
        free_shipping_source=free_shipping_source,
        free_shipping_threshold=threshold,
        delivery_code=str(delivery["code"]),
        delivery_label=str(delivery["label"]),
        estimated_days=int(delivery["estimated_days"]),
        cold_chain=bool(delivery["cold_chain"]),
    )


def _specs_match(actual: dict[str, Any], required: dict[str, str]) -> bool:
    """Every requested spec must be present and compatible.

    Fixture spec values are short strings such as "6L/日", so a substring match
    lets "6L" satisfy "6L/日" without needing the resident to quote the exact
    catalogue wording.
    """

    for name, wanted in required.items():
        value = actual.get(name)
        if not isinstance(value, str):
            return False
        if wanted.casefold() not in value.casefold():
            return False
    return True


def _score(item: dict[str, Any], priced: Quote, *, budget_max: int) -> int:
    budget_fit = (
        _clamp((budget_max - priced.unit_price) / budget_max) if budget_max > 0 else 0.0
    )
    rating = _clamp(float(item["rating"]) / 5)
    speed = _clamp(1 - min(priced.estimated_days, _SLOWEST_DELIVERY_DAYS) / _SLOWEST_DELIVERY_DAYS)
    promotion = (
        _clamp(priced.discount_amount / priced.original_amount)
        if priced.original_amount
        else 0.0
    )
    weighted = (
        budget_fit * _WEIGHT_BUDGET_FIT
        + rating * _WEIGHT_RATING
        + speed * _WEIGHT_SPEED
        + promotion * _WEIGHT_PROMOTION
    )
    return round(weighted * 100)


def _reasons(
    item: dict[str, Any],
    priced: Quote,
    *,
    budget_max: int,
    is_cheapest: bool,
) -> tuple[str, ...]:
    """Rule-generated explanations. No model output reaches this list."""

    reasons: list[str] = []
    if is_cheapest:
        reasons.append("候選中實付金額最低")
    if priced.promotion_applied and priced.promotion_label:
        # A free-shipping promotion saves the delivery fee, not the item price,
        # so claiming "省 0 元" would be misleading.
        if priced.free_shipping_source == "promotion":
            reasons.append(f"促銷：{priced.promotion_label}（免運費）")
        else:
            reasons.append(
                f"促銷：{priced.promotion_label}，省 {priced.discount_amount:,} 元"
            )
    rating = float(item["rating"])
    if rating >= 4.0:
        reasons.append(f"評分 {rating}")
    if priced.free_shipping_source == "promotion":
        reasons.append("本檔促銷免運費")
    elif priced.free_shipping_source == "threshold":
        reasons.append(f"已達免運門檻（{priced.free_shipping_threshold:,} 元）")
    else:
        reasons.append(
            f"未達免運門檻（{priced.free_shipping_threshold:,} 元），"
            f"運費 {priced.shipping_fee_amount:,} 元"
        )
    if priced.estimated_days <= 3:
        reasons.append(f"{priced.delivery_label}，最快 {priced.estimated_days} 個工作天")
    else:
        reasons.append(f"{priced.delivery_label}，預估 {priced.estimated_days} 個工作天")
    if budget_max > 0 and priced.unit_price <= budget_max * 0.6:
        reasons.append("單價明顯低於預算上限")
    return tuple(reasons)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
