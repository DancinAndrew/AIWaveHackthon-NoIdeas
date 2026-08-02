"""Product purchase (商品購買) service flow.

Slot filling collects only what is needed to price and deliver an order:
item type (or category), budget ceiling, quantity and the delivery district.

There is deliberately **no** field for a name, phone, email or street address.
`SPEC.md` requires contact data to stay out of the AI conversation, and the
strongest way to satisfy that is to have nowhere to put it, rather than masking
it after the fact. `_strip_contact_details()` additionally scrubs volunteered
contact strings so they never reach a stored summary or artifact.

Every amount shown to the resident comes from `product_catalog`, which prices
from `list_price` using versioned rules. No amount is ever produced by a model.
"""

from __future__ import annotations

import re
from typing import Any

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from .errors import ConflictError, ValidationError
from .flows import BASE_STAGE_LABELS
from .geo import COUNTY_NAME, resolve_district
from .product_catalog import ProductCatalog

SERVICE_TYPE = "product_purchase"
AGENT_NAME = "product_agent"
SERVICE_NAME = "商品購買"
SCHEMA_VERSION = "1.0.0"

CANDIDATE_LIMIT = 3
DEFAULT_QUANTITY = 1

# Competition `mms_order_record.order_type`: 05 is a product order.
ORDER_TYPE = "05"

# Competition `order_status` values for order_type 05. The MVP acceptance end
# point is 03; 04/80/99 are declared so an illegal jump is rejected rather than
# silently accepted, but nothing in this change triggers them.
ORDER_STATUS_LABELS: dict[str, str] = {
    "01": "待付款",
    "02": "待確認",
    "03": "已確認",
    "04": "進行中",
    "80": "已完成",
    "90": "已取消",
    "99": "已退款",
}

_ALLOWED_ORDER_TRANSITIONS: dict[str, frozenset[str]] = {
    "01": frozenset({"02", "90"}),
    "02": frozenset({"03", "90"}),
    "03": frozenset({"04", "90"}),
    "04": frozenset({"80", "90"}),
    "80": frozenset({"99"}),
    "90": frozenset(),
    "99": frozenset(),
}

CONFIRM_PHRASES = ("確認送出", "確認建立", "內容正確", "可以送出", "確認下單")

STAGE_LABELS: dict[str, str] = {
    **BASE_STAGE_LABELS,
    "collecting_details": "商品 Agent 正在確認需求",
    "awaiting_resident_selection": "請從候選商品中選擇一項",
    "authorizing_payment": "正在進行 Demo 模擬付款授權",
    "out_of_stock": "候選商品目前缺貨",
    "waiting_provider_response": "已委派供應商，等待回覆",
    "provider_confirmed": "供應商已確認，將依約出貨",
}

# Budget expressions. Chinese numerals are limited to the common "N 千/萬"
# shorthand a resident actually types; anything else must be digits.
_BUDGET_PATTERNS = (
    re.compile(r"預算[^\d]{0,6}(\d[\d,]*)\s*(萬|千)?"),
    re.compile(r"(\d[\d,]*)\s*(萬|千)?\s*(?:元|塊)?\s*(?:以內|以下|之內|內)"),
    re.compile(r"不(?:要)?超過\s*(\d[\d,]*)\s*(萬|千)?"),
)
_CHINESE_BUDGET_PATTERN = re.compile(
    r"(?:預算)?[^\d]{0,4}([一二三四五六七八九十兩])\s*(萬|千)\s*(?:元|塊)?\s*(?:以內|以下|之內|內)?"
)
_CHINESE_DIGITS = {
    "一": 1,
    "二": 2,
    "兩": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

_QUANTITY_PATTERNS = (
    re.compile(r"(\d+)\s*(?:台|個|支|件|組|入|包|瓶|盒|隻|副|雙)"),
    re.compile(r"([一二三四五六七八九十兩])\s*(?:台|個|支|件|組|入|包|瓶|盒|隻|副|雙)"),
    re.compile(r"數量\s*[:：]?\s*(\d+)"),
    re.compile(r"[xX×]\s*(\d+)"),
)

# Volunteered contact data is removed rather than stored. Kept deliberately
# narrow so ordinary product text is never mangled.
_CONTACT_PATTERNS = (
    re.compile(r"09\d{2}[\s-]?\d{3}[\s-]?\d{3}"),
    re.compile(r"0\d{1,2}[\s-]?\d{6,8}"),
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    # Street-level address fragments; district names are kept because delivery
    # needs them.
    re.compile(r"[\u4e00-\u9fff]{1,10}(?:路|街|大道)[\u4e00-\u9fff\d]{0,10}\d+號[\d樓之\-]*"),
)
_CONTACT_PLACEHOLDER = "［已省略聯絡資訊］"

_ACCEPT_SUBSTITUTE_DECLINED = ("不接受", "不要替代", "只要這個牌子", "指定品牌")


def _strip_contact_details(text: str) -> str:
    cleaned = text
    for pattern in _CONTACT_PATTERNS:
        cleaned = pattern.sub(_CONTACT_PLACEHOLDER, cleaned)
    return cleaned


def _order_number() -> str:
    """Readable order number shaped like the competition samples (ORD + date)."""

    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return f"ORD{stamp}{uuid4().hex[:6].upper()}"


def _to_amount(digits: str, scale: str | None) -> int:
    amount = int(digits.replace(",", ""))
    if scale == "萬":
        return amount * 10_000
    if scale == "千":
        return amount * 1_000
    return amount


def extract_budget(text: str) -> int | None:
    """Highest-confidence budget ceiling stated in the message, if any."""

    for pattern in _BUDGET_PATTERNS:
        match = pattern.search(text)
        if match:
            return _to_amount(match.group(1), match.group(2) if match.lastindex else None)
    match = _CHINESE_BUDGET_PATTERN.search(text)
    if match:
        return _CHINESE_DIGITS[match.group(1)] * (
            10_000 if match.group(2) == "萬" else 1_000
        )
    return None


def extract_quantity(text: str) -> int | None:
    for pattern in _QUANTITY_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        token = match.group(1)
        value = _CHINESE_DIGITS.get(token) if token in _CHINESE_DIGITS else int(token)
        if value and 1 <= value <= 999:
            return value
    return None


class ProductPurchaseFlow:
    """Deterministic product purchase conversation rules."""

    service_type = SERVICE_TYPE
    agent_name = AGENT_NAME
    service_name = SERVICE_NAME
    schema_version = SCHEMA_VERSION
    stage_labels = STAGE_LABELS
    routing_hint = "想買什麼商品、預算與收貨地區"

    supports_selection = True
    # Product accepts move the order state machine, which needs the guarded
    # transition helper on the service.
    accept_needs_service = True

    def __init__(
        self,
        catalog: ProductCatalog | None = None,
        payment_authorizer: Callable[[dict[str, Any]], bool] | None = None,
    ) -> None:
        # Loaded once per process; the fixtures are read-only.
        self.catalog = catalog or ProductCatalog.load()
        # Explicitly labelled mock. It never contacts a payment provider and
        # never moves real money; it exists so the `authorizing_payment` stage is
        # a real, observable step that can also fail.
        self.authorize_payment = payment_authorizer or (lambda order: True)

    # ------------------------------------------------------------------
    # Slot filling
    # ------------------------------------------------------------------

    def init_request(self, request: dict[str, Any], content: str) -> None:
        request.update(
            {
                "itemType": None,
                "category": None,
                "budgetMax": None,
                "quantity": DEFAULT_QUANTITY,
                "quantityStated": False,
                "countyCode": None,
                "districtCode": None,
                "districtName": None,
                "acceptSubstitutes": True,
                "requestText": _strip_contact_details(content),
                "candidates": [],
                "candidatesVersion": 0,
                "selectedSku": None,
                "orderNo": None,
                "orderType": None,
                "orderStatus": None,
                "orderAmounts": None,
                "estimatedShipDate": None,
                "paymentAuthorized": False,
                "providerQuestion": None,
                "providerAnswer": None,
            }
        )
        self._apply_extractors(request, content)

    def _apply_extractors(self, request: dict[str, Any], content: str) -> None:
        if not request.get("itemType"):
            item_type = self.catalog.resolve_item_type(content)
            if item_type:
                request["itemType"] = item_type
        if not request.get("itemType") and not request.get("category"):
            category = self.catalog.resolve_category(content)
            if category:
                request["category"] = category

        budget = extract_budget(content)
        if budget:
            request["budgetMax"] = budget

        quantity = extract_quantity(content)
        if quantity:
            request["quantity"] = quantity
            request["quantityStated"] = True

        located = resolve_district(content)
        if located:
            (
                request["countyCode"],
                request["districtCode"],
                request["districtName"],
            ) = located

        if any(phrase in content for phrase in _ACCEPT_SUBSTITUTE_DECLINED):
            request["acceptSubstitutes"] = False

    def _missing_slot_prompt(self, request: dict[str, Any]) -> str | None:
        """Ask for exactly one missing slot, never one already known."""

        if not request.get("itemType") and not request.get("category"):
            return (
                "請告訴我想買什麼商品，例如「藍牙耳機」、「除濕機」或「機械鍵盤」。"
                f"目前可查的品項有 {len(self.catalog.item_types())} 種。"
            )
        if not request.get("budgetMax"):
            target = request.get("itemType") or request.get("category")
            return f"{target}的預算上限大約多少？例如「預算 3000 以內」。"
        if not request.get("districtName"):
            return (
                f"要送到哪一區？請給{COUNTY_NAME}的行政區，例如「內湖區」。"
                "詳細門牌不需要在 AI 對話中提供。"
            )
        return None

    # ------------------------------------------------------------------
    # Model-backed turn contract
    #
    # This flow has no model extraction schema in the Runtime yet, so it takes
    # routing from the agent turn and nothing else. Every slot below is either a
    # catalogue lookup or a price, and letting unschema'd model output write those
    # is exactly how a demo ends up quoting a number no supplier agreed to.
    # ------------------------------------------------------------------

    def known_fields(
        self, request: dict[str, Any] | None, memory: Any = None
    ) -> dict[str, Any]:
        if not request:
            return {}
        return {
            "itemType": request["itemType"],
            "category": request["category"],
            "budgetMax": request["budgetMax"],
            "quantity": request["quantity"],
            "districtName": request["districtName"],
        }

    def missing_fields(self, request: dict[str, Any] | None) -> tuple[str, ...]:
        if not request:
            return ("product", "budget", "district")
        missing: list[str] = []
        if not request.get("itemType") and not request.get("category"):
            missing.append("product")
        if not request.get("budgetMax"):
            missing.append("budget")
        if not request.get("districtName"):
            missing.append("district")
        return tuple(missing)

    def turn_goal(
        self, request: dict[str, Any] | None, stage: str | None
    ) -> str | None:
        if request is None:
            return "route_new_request"
        if stage == "awaiting_resident_confirmation":
            return "confirm_brief"
        if stage == "waiting_resident_information":
            return "answer_provider_question"
        if stage in {"collecting_details", "awaiting_resident_selection", "out_of_stock"}:
            return "collect_missing_fields"
        return "answer_progress_question"

    def merge_agent_extraction(
        self, request: dict[str, Any], turn: Any
    ) -> dict[str, Any]:
        """No-op until this domain has a closed extraction schema.

        Returning empty notes keeps the caller honest: nothing was applied, so
        nothing may be reported as understood by a model.
        """

        return {}

    # ------------------------------------------------------------------
    # Turns
    # ------------------------------------------------------------------

    def start(
        self,
        svc: Any,
        conversation: dict[str, Any],
        request: dict[str, Any],
        *,
        turn: Any = None,
        memory: Any = None,
    ) -> dict[str, Any]:
        svc.set_progress(request, "collecting_details", waiting_for="resident")
        prompt = self._missing_slot_prompt(request)
        if prompt is None:
            return self._present_candidates(
                svc, conversation, request, opening=True, turn=turn
            )
        assistant = svc.append_assistant(
            conversation["conversationId"],
            f"我已交給商品 Agent。{prompt}",
            agent=AGENT_NAME,
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
        memory: Any = None,
    ) -> dict[str, Any]:
        stage = svc.current_stage(request)

        if stage in {"collecting_details", "awaiting_resident_selection", "out_of_stock"}:
            self._apply_extractors(request, content)
            svc.touch(request)
            prompt = self._missing_slot_prompt(request)
            if prompt is not None:
                assistant = svc.append_assistant(
                    conversation["conversationId"], prompt, agent=AGENT_NAME
                )
                return svc.turn_payload(conversation, assistant, turn=turn)
            return self._present_candidates(svc, conversation, request, turn=turn)

        if stage == "awaiting_resident_confirmation":
            if any(phrase in content for phrase in CONFIRM_PHRASES):
                return self._confirm_and_dispatch(svc, conversation, request, turn=turn)
            before = self._slot_fingerprint(request)
            self._apply_extractors(request, content)
            svc.touch(request)
            if self._slot_fingerprint(request) != before:
                # Requirements changed, so the priced artifact no longer matches
                # what the resident asked for. Re-search instead of letting a
                # stale confirmation create an order.
                return self._present_candidates(svc, conversation, request, turn=turn)
            assistant = svc.append_assistant(
                conversation["conversationId"],
                "訂單摘要還沒送出。內容正確請回覆「確認送出」；想換商品或改數量，直接告訴我即可。",
                agent=AGENT_NAME,
            )
            return svc.turn_payload(
                conversation,
                assistant,
                artifact=svc.current_artifact(request),
                turn=turn,
            )

        if stage == "authorizing_payment":
            return self._confirm_and_dispatch(
                svc, conversation, request, retry=True, turn=turn
            )

        if stage == "waiting_resident_information":
            return svc.accept_resident_information(
                conversation,
                request,
                content,
                agent=AGENT_NAME,
                reply="收到，我已把補充內容回傳給供應商，現在等待供應商確認。",
                turn=turn,
            )

        assistant = svc.append_assistant(
            conversation["conversationId"],
            "訂單已送出，你可以在「我的預約」查看供應商確認與出貨進度。",
            agent=AGENT_NAME,
        )
        return svc.turn_payload(conversation, assistant, turn=turn)

    def _present_candidates(
        self,
        svc: Any,
        conversation: dict[str, Any],
        request: dict[str, Any],
        *,
        opening: bool = False,
        turn: Any = None,
    ) -> dict[str, Any]:
        candidates = self.catalog.search(
            item_type=request.get("itemType"),
            category=request.get("category"),
            budget_max=int(request["budgetMax"]),
            quantity=int(request["quantity"]),
            limit=CANDIDATE_LIMIT,
        )
        request["candidates"] = [candidate.as_dict() for candidate in candidates]
        request["selectedSku"] = None
        # Bumped on every re-search so a resident cannot select from a list that
        # has since been recomputed under different requirements.
        request["candidatesVersion"] = self.selection_version(request) + 1
        svc.touch(request)

        if not candidates:
            svc.set_progress(request, "out_of_stock", waiting_for="resident")
            text = self._no_candidate_text(request)
        else:
            svc.set_progress(
                request, "awaiting_resident_selection", waiting_for="resident"
            )
            text = self._candidate_text(request, candidates, opening=opening)

        assistant = svc.append_assistant(
            conversation["conversationId"], text, agent=AGENT_NAME
        )
        return svc.turn_payload(
            conversation,
            assistant,
            trace_agent="supervisor" if opening else None,
            turn=turn,
        )

    def _candidate_text(
        self, request: dict[str, Any], candidates: list[Any], *, opening: bool
    ) -> str:
        target = request.get("itemType") or request.get("category")
        quantity = int(request["quantity"])
        head = "我已交給商品 Agent。" if opening else ""
        lines = [
            f"{head}依「{target}、預算 {int(request['budgetMax']):,} 元以內、"
            f"數量 {quantity}、送{COUNTY_NAME}{request['districtName']}」"
            f"找到 {len(candidates)} 個選項："
        ]
        for index, candidate in enumerate(candidates, 1):
            quote = candidate.quote
            shipping = (
                "促銷免運"
                if quote.free_shipping_source == "promotion"
                else "免運"
                if quote.free_shipping_applied
                else f"運費 {quote.shipping_fee_amount:,}"
            )
            lines.append(
                f"\n{index}. {candidate.name}（{candidate.brand}，評分 {candidate.rating}）"
                f"\n   單價 {quote.unit_price:,}｜{shipping}｜實付 {quote.final_amount:,} 元"
                f"\n   {candidate.supplier_name}｜{quote.delivery_label} 約 {quote.estimated_days} 個工作天"
                f"｜可售 {candidate.available}"
                f"\n   {'、'.join(candidate.reasons[:2])}"
            )
        if not request["quantityStated"]:
            lines.append(f"\n數量預設為 {quantity}，需要調整請直接告訴我。")
        lines.append("\n請點選你要的商品，我會產生訂單摘要給你確認。")
        return "".join(lines)

    def _no_candidate_text(self, request: dict[str, Any]) -> str:
        target = request.get("itemType") or request.get("category")
        budget = int(request["budgetMax"])
        etas = [
            eta
            for eta in (
                self.catalog.restock_eta(sku)
                for sku in self.catalog.skus_for(
                    item_type=request.get("itemType"), category=request.get("category")
                )
            )
            if eta
        ]
        if etas:
            return (
                f"目前沒有符合「{target}、預算 {budget:,} 元以內、數量 {request['quantity']}」"
                f"且有現貨的商品。最快的補貨時間是 {min(etas)}。"
                "你可以調整預算或數量，我再重新查一次。"
            )
        return (
            f"目前沒有符合「{target}、預算 {budget:,} 元以內、數量 {request['quantity']}」"
            "且有現貨的商品，補貨時間供應商尚未提供。"
            "你可以調整預算或數量，我再重新查一次。"
        )

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def selection_version(self, request: dict[str, Any]) -> int:
        return int(request.get("candidatesVersion") or 0)

    def select(
        self, svc: Any, request: dict[str, Any], *, sku: str, expected_version: int
    ) -> dict[str, Any]:
        """Record the chosen SKU and render the confirmable order summary.

        Amounts are always recomputed from the catalogue here. Anything a client
        sent about price or shipping is irrelevant by construction, because this
        method never reads it.
        """

        stage = svc.current_stage(request)
        if stage not in {"awaiting_resident_selection", "awaiting_resident_confirmation"}:
            raise ConflictError("目前不是可以選擇商品的階段")
        if expected_version != self.selection_version(request):
            raise ConflictError("候選清單已更新，請重新查看後再選擇")

        candidates = {
            candidate["sku"]: candidate for candidate in request.get("candidates") or []
        }
        if sku not in candidates:
            raise ValidationError("所選商品不在目前的候選清單中")

        already_selected = request.get("selectedSku")
        request["selectedSku"] = sku
        svc.touch(request)
        # A different choice supersedes the previous summary so an older version
        # can never be the one that gets confirmed.
        artifact = svc.render_artifact(
            request, supersede=bool(already_selected and already_selected != sku)
        )
        svc.set_progress(request, "awaiting_resident_confirmation", waiting_for="resident")
        svc.event(request, "product_selected", f"住戶選擇 {candidates[sku]['name']}")
        return {
            "serviceRequestId": request["serviceRequestId"],
            "progress": svc.progress_projection(request),
            "serviceRequest": svc.service_request_projection(request),
            "artifact": artifact,
            "assistantMessage": svc.append_assistant(
                request["conversationId"],
                self._selection_text(request, artifact),
                agent=AGENT_NAME,
            ),
        }

    def _selection_text(self, request: dict[str, Any], artifact: dict[str, Any]) -> str:
        sku = request["selectedSku"]
        item = self.catalog.products[sku]
        quote = self.catalog.quote(sku, int(request["quantity"]))
        if quote.free_shipping_source == "promotion":
            shipping_note = "本檔促銷免運"
        elif quote.free_shipping_source == "threshold":
            shipping_note = f"已達免運門檻 {quote.free_shipping_threshold:,} 元"
        else:
            shipping_note = f"未達免運門檻 {quote.free_shipping_threshold:,} 元"
        quantity = int(request["quantity"])
        # Lines are ordered so the resident can add them up:
        #   定價 − 折扣 = 小計；小計 + 運費 = 實付
        # The base line is the catalogue list price, never the already-discounted
        # unit price, otherwise the discount row looks like it was not applied.
        base = (
            f"定價　：{quote.list_price:,} 元 × {quantity} ＝ {quote.original_amount:,} 元"
            if quantity > 1
            else f"定價　：{quote.list_price:,} 元"
        )
        lines = [base]
        if quote.discount_amount:
            lines.append(
                f"折扣　：-{quote.discount_amount:,} 元（{quote.promotion_label}）"
            )
            lines.append(
                f"小計　：{quote.original_amount - quote.discount_amount:,} 元"
            )
        elif quote.promotion_applied and quote.free_shipping_source == "promotion":
            # Waives the delivery fee rather than reducing the item price.
            lines.append(f"促銷　：{quote.promotion_label}（免運費）")
        lines.append(
            f"運費　：{quote.shipping_fee_amount:,} 元（{shipping_note}）"
        )
        lines.append(f"實付　：{quote.final_amount:,} 元")

        return (
            f"已為你整理第 {artifact['version']} 版訂單摘要：\n\n"
            f"商品　：{item['name']}（{item['brand']}）\n"
            f"規格　：{'、'.join(f'{k} {v}' for k, v in (item.get('specs') or {}).items())}\n"
            f"數量　：{quantity}\n"
            + "\n".join(lines)
            + f"\n配送　：{quote.delivery_label}，約 {quote.estimated_days} 個工作天，"
            f"送{COUNTY_NAME}{request['districtName']}\n"
            f"供應商：{item['supplier_name']}\n"
            f"退換貨：{item['return_policy']['label']}\n\n"
            "內容正確請回覆「確認送出」。確認後才會建立訂單，"
            "付款為 Demo 模擬授權，不會產生真實扣款。"
        )

    # ------------------------------------------------------------------
    # Order creation and mock payment authorization
    # ------------------------------------------------------------------

    def _confirm_and_dispatch(
        self,
        svc: Any,
        conversation: dict[str, Any],
        request: dict[str, Any],
        *,
        retry: bool = False,
        turn: Any = None,
    ) -> dict[str, Any]:
        if not request.get("selectedSku"):
            raise ConflictError("尚未選擇商品，無法建立訂單")

        artifact = svc.current_artifact(request)
        if not retry:
            artifact = svc.confirm_artifact(request)
            self._create_order(svc, request)

        svc.set_progress(request, "authorizing_payment", waiting_for=None)

        if not self.authorize_payment(self._order_snapshot(request)):
            svc.event(request, "payment_authorization_failed", "Demo 模擬授權未通過")
            assistant = svc.append_assistant(
                conversation["conversationId"],
                f"訂單 {request['orderNo']} 已建立（狀態：{ORDER_STATUS_LABELS['01']}），"
                "但 Demo 模擬授權未通過，因此還沒委派供應商。"
                "回覆任何訊息我可以再試一次。",
                agent=AGENT_NAME,
            )
            return svc.turn_payload(
                conversation, assistant, artifact=artifact, turn=turn
            )

        request["paymentAuthorized"] = True
        self._transition_order(svc, request, "02")
        svc.event(request, "payment_authorized", "Demo 模擬授權完成，未產生真實扣款")

        suppliers = self.rank_candidates(request)
        if not suppliers:
            raise ConflictError("找不到這項商品的供應商")
        task = svc.dispatch_first_candidate(
            request,
            suppliers,
            reason="initial_match",
            event_type="supplier_matched",
            event_label="已依所選商品委派其供應商",
        )
        assistant = svc.append_assistant(
            conversation["conversationId"],
            f"訂單 {request['orderNo']} 已建立。\n"
            f"1. {ORDER_STATUS_LABELS['01']} → 已完成 Demo 模擬付款授權"
            "（未產生真實扣款）\n"
            f"2. 目前狀態：{ORDER_STATUS_LABELS['02']}\n"
            f"3. 已委派供應商 {task['provider']['name']}，等待確認出貨；"
            "目前不需要你操作。\n\n"
            "你可以在「我的預約」查看最新進度。",
            agent=AGENT_NAME,
        )
        return svc.turn_payload(
            conversation, assistant, artifact=artifact, provider_task=task, turn=turn
        )

    def _create_order(self, svc: Any, request: dict[str, Any]) -> None:
        sku = request["selectedSku"]
        quote = self.catalog.quote(sku, int(request["quantity"]))
        request["orderNo"] = _order_number()
        request["orderType"] = ORDER_TYPE
        request["orderStatus"] = "01"
        request["orderVersion"] = 1
        # Snapshot so the order and the confirmed artifact can never drift.
        request["orderAmounts"] = quote.as_dict()
        svc.touch(request)
        svc.event(
            request,
            "product_order_created",
            f"已建立商品訂單 {request['orderNo']}（{ORDER_STATUS_LABELS['01']}）",
        )

    def _order_snapshot(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "orderNo": request.get("orderNo"),
            "orderType": request.get("orderType"),
            "orderStatus": request.get("orderStatus"),
            "sku": request.get("selectedSku"),
            "quantity": request.get("quantity"),
            "amounts": request.get("orderAmounts"),
        }

    def _transition_order(self, svc: Any, request: dict[str, Any], to_status: str) -> None:
        current = str(request.get("orderStatus") or "")
        allowed = _ALLOWED_ORDER_TRANSITIONS.get(current)
        if allowed is None:
            raise ConflictError(f"訂單狀態 {current or '（未建立）'} 無法轉移")
        if to_status not in allowed:
            raise ConflictError(
                f"訂單狀態不可由 {ORDER_STATUS_LABELS.get(current, current)} "
                f"轉為 {ORDER_STATUS_LABELS.get(to_status, to_status)}"
            )
        request["orderStatus"] = to_status
        request["orderVersion"] = int(request.get("orderVersion") or 1) + 1
        svc.touch(request)

    def _slot_fingerprint(self, request: dict[str, Any]) -> tuple[Any, ...]:
        return (
            request.get("itemType"),
            request.get("category"),
            request.get("budgetMax"),
            request.get("quantity"),
            request.get("districtName"),
        )

    # ------------------------------------------------------------------
    # Artifact and projection
    # ------------------------------------------------------------------

    def build_summary(self, request: dict[str, Any]) -> str:
        sku = request.get("selectedSku")
        if not sku:
            return self.fallback_summary(request)
        item = self.catalog.products[sku]
        quote = self.catalog.quote(sku, int(request["quantity"]))
        return (
            f"{item['name']} × {request['quantity']}｜"
            f"實付 {quote.final_amount:,} 元（含運費 {quote.shipping_fee_amount:,}）｜"
            f"送{COUNTY_NAME}{request['districtName']}｜"
            f"{quote.delivery_label}約 {quote.estimated_days} 個工作天"
        )

    def fallback_summary(self, request: dict[str, Any]) -> str:
        target = request.get("itemType") or request.get("category") or "商品"
        budget = request.get("budgetMax")
        parts = [target]
        if budget:
            parts.append(f"預算 {int(budget):,} 元以內")
        if request.get("districtName"):
            parts.append(f"送{COUNTY_NAME}{request['districtName']}")
        return "｜".join(parts)

    def build_canonical(self, request: dict[str, Any]) -> dict[str, Any]:
        """Canonical artifact payload. Contains no contact data by construction."""

        sku = request.get("selectedSku")
        canonical: dict[str, Any] = {
            "itemType": request.get("itemType"),
            "category": request.get("category"),
            "budgetMax": request.get("budgetMax"),
            "quantity": request.get("quantity"),
            "delivery": {
                "countyCode": request.get("countyCode"),
                "districtCode": request.get("districtCode"),
                "districtName": request.get("districtName"),
            },
            "acceptSubstitutes": request.get("acceptSubstitutes"),
        }
        if sku:
            item = self.catalog.products[sku]
            quote = self.catalog.quote(sku, int(request["quantity"]))
            canonical["product"] = {
                "sku": sku,
                "name": item["name"],
                "brand": item["brand"],
                "specs": dict(item.get("specs") or {}),
                "supplierId": item["supplier_id"],
                "supplierName": item["supplier_name"],
                "returnPolicyLabel": item["return_policy"]["label"],
                "warrantyMonths": item["warranty_months"],
            }
            canonical["amounts"] = quote.as_dict()
        return canonical

    def projection_fields(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "itemType": request.get("itemType"),
            "category": request.get("category"),
            "quantity": request.get("quantity"),
            "districtName": request.get("districtName"),
            "selectedSku": request.get("selectedSku"),
            "orderNo": request.get("orderNo"),
            "orderStatus": request.get("orderStatus"),
            "candidates": list(request.get("candidates") or []),
            # The client must echo this back when selecting, so it has to be
            # part of the projection rather than internal-only state.
            "candidatesVersion": self.selection_version(request),
            # Product purchase has no safety hold; declared so the shared
            # projection shape stays uniform across service types.
            "safetyHold": False,
        }

    # ------------------------------------------------------------------
    # Supplier side (completed in stage 4)
    # ------------------------------------------------------------------

    def list_providers(self) -> tuple[dict[str, Any], ...]:
        return self.catalog.suppliers()

    def rank_candidates(
        self, request: dict[str, Any], memory: Any = None
    ) -> list[dict[str, Any]]:
        """The supplier of the chosen SKU is the only hard-condition match."""

        sku = request.get("selectedSku")
        if not sku:
            return []
        supplier_id = self.catalog.products[sku]["supplier_id"]
        return [
            supplier
            for supplier in self.catalog.suppliers()
            if supplier["providerId"] == supplier_id
        ]

    def validate_accept(self, payload: dict[str, Any]) -> None:
        from .errors import ValidationError

        if not str(payload.get("estimatedShipDate") or "").strip():
            raise ValidationError("供應商接受時 estimatedShipDate 為必填")

    def reward_basis(
        self, request: dict[str, Any], payload: dict[str, Any]
    ) -> tuple[int, str] | None:
        """The order already has a server-computed amount, so use it.

        A supplier-reported figure is deliberately ignored: the platform priced
        this order from the catalogue, so estimating it would replace a known
        number with a guess.
        """

        from . import points

        quote = self.catalog.quote(request["selectedSku"], int(request["quantity"]))
        return quote.final_amount, points.AMOUNT_SOURCE_ORDER_FINAL

    def apply_accept(
        self,
        request: dict[str, Any],
        provider: dict[str, Any],
        payload: dict[str, Any],
        svc: Any = None,
    ) -> str:
        ship_date = str(payload.get("estimatedShipDate") or "").strip()
        message = str(payload.get("message") or "").strip()
        request["estimatedShipDate"] = ship_date
        if svc is not None:
            self._transition_order(svc, request, "03")
        else:  # pragma: no cover - the skeleton always passes svc
            request["orderStatus"] = "03"
        sku = request["selectedSku"]
        item = self.catalog.products[sku]
        quote = self.catalog.quote(sku, int(request["quantity"]))
        note = message or "出貨後可在「我的預約」查看進度"
        return (
            f"{provider['name']} 已在平台內確認出貨，預計出貨日 {ship_date}。\n"
            f"商品：{item['name']} × {request['quantity']}\n"
            f"實付：{quote.final_amount:,} 元（含運費 {quote.shipping_fee_amount:,} 元）\n"
            f"退換貨政策：{item['return_policy']['label']}\n"
            f"備註：{note.rstrip('。')}。\n\n"
            "這是 Demo 的平台內確認與模擬授權，未產生真實扣款或不可逆外部交易。"
        )
