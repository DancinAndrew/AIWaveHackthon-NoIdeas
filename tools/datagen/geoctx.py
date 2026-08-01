"""地點選取脈絡：讓生成器能刻意挑到「有服務商」或「沒服務商」的行政區。"""

from __future__ import annotations

from common import read_mock

# 每 10 筆有 2 筆刻意落在沒有服務商的行政區，用來產生 unmatched 案例
UNCOVERED_EVERY = 5


def build_context() -> dict:
    districts = read_mock("geo/districts.json")
    providers = {p["provider_id"]: p for p in read_mock("master/providers.json")}
    areas = read_mock("master/provider_service_areas.json")
    communities = read_mock("master/communities.json")

    covered: dict[str, set[str]] = {}
    for area in areas:
        service_type = providers[area["provider_id"]]["service_type"]
        covered.setdefault(service_type, set()).add(area["district_code"])
    # 商品購買全國配送，視同全覆蓋
    covered["product_purchase"] = {d["district_code"] for d in districts}

    by_code = {d["district_code"]: d for d in districts}

    def pick_district(random_source, service_type: str, index: int) -> dict:
        pool_codes = covered.get(service_type, set())
        if index % UNCOVERED_EVERY == 4 and service_type != "product_purchase":
            candidates = [d for d in districts if d["district_code"] not in pool_codes]
        else:
            candidates = [by_code[c] for c in sorted(pool_codes)]
        return random_source.choice(candidates)

    def pick_community(random_source, district: dict) -> dict:
        same = [c for c in communities if c["district_code"] == district["district_code"]]
        return random_source.choice(same or communities)

    # 品項中位價，讓需求端預算貼著真實 SKU 價位帶
    prices: dict[str, list[int]] = {}
    for product in read_mock("master/products.json"):
        prices.setdefault(product["item_type"], []).append(product["sale_price"])
    item_price = {item: sorted(values)[len(values) // 2] for item, values in prices.items()}

    return {
        "districts": districts,
        "by_code": by_code,
        "covered": covered,
        "communities": communities,
        "item_price": item_price,
        "pick_district": pick_district,
        "pick_community": pick_community,
    }
