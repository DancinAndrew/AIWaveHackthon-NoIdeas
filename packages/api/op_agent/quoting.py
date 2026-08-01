"""報價與評分引擎。

設計取捨：報價與評分用**規則**算，不交給 LLM。
LLM 一旦能自由決定金額就會亂編數字，而報價是這個提案最不能出錯的部分。
LLM 的工作是「排序微調」與「用人話解釋」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .domain import ServiceRequest, UserPreferences, Vendor, VendorProposal
from .ids import iso_date_plus
from .seed import SYMPTOM_TO_ITEMS


# 大額項目：一旦真的要換，金額會是常規維修的數倍。
# 把它從主報價區間拆出來單獨說明，否則「2400~21300 元」這種區間對會員毫無參考價值。
MAJOR_ITEM_CODES = {"AC_COMP"}


@dataclass
class QuoteEstimate:
    inspection_fee: int
    estimated_min: int
    estimated_max: int
    matched_items: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    # 大額風險項目（不含在 estimated_max 內），前端可另外標示
    major_risks: list[dict[str, Any]] = field(default_factory=list)


def estimate_quote(vendor: Vendor, req: ServiceRequest) -> QuoteEstimate:
    """依症狀推估可能的維修項目，再用廠商自己的價目表算報價區間。

    主報價區間只涵蓋「常規維修項目」；壓縮機這類大額更換另外列在 major_risks，
    這樣區間才有參考價值，同時又不會隱瞞最壞情況。
    """
    symptoms = req.get("slots", {}).get("symptoms") or []
    codes: set[str] = set()
    for s in symptoms:
        for keyword, items in SYMPTOM_TO_ITEMS.items():
            if keyword in s:
                codes.update(items)

    pricing = vendor.get("pricing", {})
    inspection_fee = int(pricing.get("inspectionFee", 0))
    priced = [i for i in pricing.get("items", []) if i.get("code") in codes]

    if not priced:
        # 抓不到對應項目就只報到府檢測費，並明確說明
        return QuoteEstimate(
            inspection_fee=inspection_fee,
            estimated_min=inspection_fee,
            estimated_max=inspection_fee,
            matched_items=[],
            assumptions=["症狀需現場判斷，此報價僅含到府檢測費，實際維修項目由技師現場確認後報價"],
        )

    regular = [i for i in priced if i.get("code") not in MAJOR_ITEM_CODES]
    major = [i for i in priced if i.get("code") in MAJOR_ITEM_CODES]

    assumptions: list[str] = []
    age_years = req.get("slots", {}).get("ageYears")
    age_factor = 1.0
    if isinstance(age_years, int) and age_years >= 8:
        age_factor = 1.15
        assumptions.append(f"機齡約 {age_years} 年，零件取得與連帶更換風險較高，上限已含 15% 緩衝")

    if regular:
        low = min(int(i["minPrice"]) for i in regular)
        high = max(int(i["maxPrice"]) for i in regular)
        assumptions.insert(0, "常見處理項目：" + "、".join(str(i["name"]) for i in regular))
    else:
        # 只可能是大額項目時，主區間退回檢測費，避免報一個假的低價
        low = high = 0
        assumptions.insert(0, "此症狀多半需要大額零件更換，主報價僅列到府檢測費")

    major_risks = [
        {
            "code": str(i["code"]),
            "name": str(i["name"]),
            "minPrice": int(i["minPrice"]),
            "maxPrice": round(int(i["maxPrice"]) * age_factor),
        }
        for i in major
    ]
    if major_risks:
        detail = "、".join(
            f"{m['name']} {m['minPrice']:,}~{m['maxPrice']:,} 元" for m in major_risks
        )
        assumptions.append(f"最壞情況：若現場判定需{detail}，此部分不含在上述區間內")

    assumptions.append("報價含到府檢測費；若現場判定不需維修僅收檢測費")

    return QuoteEstimate(
        inspection_fee=inspection_fee,
        estimated_min=inspection_fee + low,
        estimated_max=round(inspection_fee + high * age_factor),
        matched_items=[str(i["code"]) for i in priced],
        assumptions=assumptions,
        major_risks=major_risks,
    )


@dataclass
class ScoreBreakdown:
    price: float
    speed: float
    quality: float
    preference: float
    brand: float
    total: int
    reasons: list[str] = field(default_factory=list)


def score_vendor(
    vendor: Vendor,
    req: ServiceRequest,
    prefs: UserPreferences,
    quote: QuoteEstimate,
    *,
    cheapest: float,
    priciest: float,
) -> ScoreBreakdown:
    """綜合評分。

    權重會依會員的價格敏感度動態調整：
    價格敏感的人，價格權重拉高；不敏感的人，品質權重拉高。
    """
    reasons: list[str] = []
    sensitivity = float(prefs.get("priceSensitivity", 0.5))

    # --- 價格分：在候選中越便宜越高分 ---
    span = max(1.0, priciest - cheapest)
    mid = (quote.estimated_min + quote.estimated_max) / 2
    price = max(0.0, 1 - (mid - cheapest) / span)
    if price > 0.8:
        reasons.append("報價在候選廠商中屬於偏低")

    # --- 速度分 ---
    earliest_days = int(vendor.get("earliestAvailableInDays", 5))
    speed = max(0.0, 1 - earliest_days / 5)
    if earliest_days == 0:
        reasons.append("今天就能到府")
    elif earliest_days <= 1:
        reasons.append("最快明天可到府")

    # --- 品質分：評分 + 案件數 ---
    rating = float(vendor.get("rating", 0))
    completed = int(vendor.get("completedJobs", 0))
    quality = min(1.0, (rating / 5) * 0.8 + min(completed / 3000, 1.0) * 0.2)
    if rating >= 4.7:
        reasons.append(f"評價 {rating} 分（{vendor.get('reviewCount', 0)} 則評論）")

    # --- 偏好分：命中會員偏好標籤 ---
    tags = vendor.get("tags", [])
    wanted = prefs.get("preferredVendorTags") or []
    hit = [t for t in wanted if t in tags]
    preference = 0.5 if not wanted else len(hit) / len(wanted)
    if hit:
        reasons.append("符合你重視的：" + "、".join(hit))

    # --- 品牌專精分 ---
    brand = req.get("slots", {}).get("brand")
    brand_score = 0.5
    if brand and any(brand in t for t in tags):
        brand_score = 1.0
        reasons.append(f"{brand} 品牌專精")

    # --- 時段可服務 ---
    want_period = req.get("preferredContactTime") or prefs.get("preferredContactTime")
    slots = vendor.get("availableSlots", [])
    if want_period and want_period not in slots and "3" not in slots:
        reasons.append("偏好時段不完全符合，需再協調")

    if vendor.get("supportsPoints"):
        reasons.append("可用 OpenPoint 點數折抵")

    w_price = 0.2 + sensitivity * 0.3  # 0.2 ~ 0.5
    w_speed = 0.2
    w_quality = 0.35 - sensitivity * 0.15  # 0.2 ~ 0.35
    w_pref = 0.15
    w_brand = 0.1
    weight_sum = w_price + w_speed + w_quality + w_pref + w_brand

    total = (
        price * w_price
        + speed * w_speed
        + quality * w_quality
        + preference * w_pref
        + brand_score * w_brand
    ) / weight_sum

    return ScoreBreakdown(
        price=round(price, 2),
        speed=round(speed, 2),
        quality=round(quality, 2),
        preference=round(preference, 2),
        brand=round(brand_score, 2),
        total=round(total * 100),
        reasons=reasons,
    )


def build_proposal(
    vendor: Vendor, req: ServiceRequest, quote: QuoteEstimate, score: ScoreBreakdown
) -> VendorProposal:
    """把廠商 + 報價 + 分數組成前端可直接顯示的 proposal。"""
    want_period = req.get("preferredContactTime") or "3"
    slots = vendor.get("availableSlots") or ["3"]
    period = want_period if want_period in slots else slots[0]
    return {
        "vendorId": vendor["vendorId"],
        "vendorName": vendor["name"],
        "rating": float(vendor.get("rating", 0)),
        "tags": list(vendor.get("tags", [])),
        "score": score.total,
        "reasons": score.reasons,
        "quote": {
            "inspectionFee": quote.inspection_fee,
            "estimatedMin": quote.estimated_min,
            "estimatedMax": quote.estimated_max,
            "currency": "TWD",
            "assumptions": quote.assumptions,
            "majorRisks": quote.major_risks,
        },
        "earliestSlot": {
            "date": iso_date_plus(int(vendor.get("earliestAvailableInDays", 0))),
            "period": period,
        },
        "supportsPoints": bool(vendor.get("supportsPoints")),
    }


def price_range(quotes: list[QuoteEstimate]) -> tuple[float, float]:
    """候選報價的中位價區間，用於相對價格評分。"""
    mids: list[float] = [(q.estimated_min + q.estimated_max) / 2 for q in quotes]
    return (min(mids), max(mids)) if mids else (0.0, 0.0)


def to_jsonable(value: Any) -> Any:
    """dataclass -> dict，方便直接塞進 tool 回傳。"""
    if hasattr(value, "__dataclass_fields__"):
        return {k: to_jsonable(getattr(value, k)) for k in value.__dataclass_fields__}
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    return value
