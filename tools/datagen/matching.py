"""簡化版媒合規則：硬條件過濾 + 軟條件排序，產生可解釋的 reasons。

規則有版本，相同輸入與相同資料快照必須得到相同排序（design.md §7）。
"""

from __future__ import annotations

RULE_VERSION = "match-rules-1.0.0"
MAX_MATCHES = 3


def rank(skeleton: dict, providers: list[dict], areas_by_provider: dict[str, set[str]]) -> list[dict]:
    service_type = skeleton["service_type"]
    district_code = skeleton["district"]["district_code"]
    urgency = _urgency_of(skeleton)
    budget = _budget_of(skeleton)

    scored = []
    for provider in providers:
        if provider["service_type"] != service_type or not provider["is_active"]:
            continue
        serves_area = provider["nationwide"] or district_code in areas_by_provider.get(provider["provider_id"], set())
        if not serves_area:
            continue
        if urgency == "emergency" and service_type == "utility_repair":
            if "emergency_24h" not in provider["capabilities"]:
                continue

        score = 0.0
        reasons: list[str] = []

        reasons.append(f"服務範圍涵蓋{skeleton['district']['county_name']}{skeleton['district']['name']}")
        score += 40

        rating_points = (provider["rating"] - 3.0) / 2.0 * 25
        score += rating_points
        reasons.append(f"平均評分 {provider['rating']}（{provider['review_count']} 則評價）")

        sla_points = {1: 20, 2: 16, 4: 12, 8: 8, 24: 4}[provider["response_sla_hours"]]
        score += sla_points
        reasons.append(f"承諾 {provider['response_sla_hours']} 小時內回應")

        if urgency == "emergency" and "emergency_24h" in provider["capabilities"]:
            score += 15
            reasons.append("具備 24 小時緊急出勤能力")

        if budget is not None:
            min_charge = provider["pricing"].get("min_charge") or provider["pricing"].get("min_spend_per_person")
            if min_charge is None:
                score += 5
            elif budget >= min_charge:
                score += 10
                reasons.append(f"預算 {budget} 元高於最低消費 {min_charge} 元")
            else:
                score -= 20
                reasons.append(f"預算 {budget} 元低於最低消費 {min_charge} 元，需確認是否可調整")

        scored.append(
            {
                "provider_id": provider["provider_id"],
                "provider_name": provider["name"],
                "score": round(score, 2),
                "reasons": reasons,
                "rule_version": RULE_VERSION,
            }
        )

    scored.sort(key=lambda m: (-m["score"], m["provider_id"]))
    return scored[:MAX_MATCHES]


def relaxation_suggestions(skeleton: dict) -> list[str]:
    service_type = skeleton["service_type"]
    district = skeleton["district"]
    suggestions = [f"{district['county_name']}{district['name']}目前沒有可服務的合作廠商，可改選鄰近行政區"]
    if _urgency_of(skeleton) == "emergency":
        suggestions.append("放寬為非緊急時段可增加可媒合廠商")
    if service_type == "restaurant_reservation":
        suggestions.append("調整用餐時段、料理類型或提高每人預算可增加可訂餐廳")
    elif service_type == "product_purchase":
        suggestions.append("提高預算或接受替代品可納入更多商品")
    elif _budget_of(skeleton) is not None:
        suggestions.append("提高預算或接受先勘查後報價，可納入更多廠商")
    return suggestions


def _urgency_of(skeleton: dict):
    fields = skeleton["fields"]
    return fields.get("repair.urgency") or fields.get("community.urgency")


def _budget_of(skeleton: dict):
    fields = skeleton["fields"]
    return fields.get("restaurant.budget_per_person") or fields.get("product.budget")
