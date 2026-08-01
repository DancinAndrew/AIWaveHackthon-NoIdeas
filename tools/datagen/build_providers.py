"""服務商主檔：providers / service_areas / availability。

刻意保留覆蓋洞（BLANK_COUNTIES 完全無服務商、部分行政區無人服務、
少數服務商滿檔），用來驗證 unmatched 與放寬建議路徑。
"""

from __future__ import annotations

from datetime import timedelta

import vocab
from common import D_DAY, iso, read_mock, report, rng, stable_uuid, write_json

PROVIDER_COUNTS = {
    "restaurant_reservation": 40,
    "product_purchase": 8,
    "housekeeping_service": 16,
    "utility_repair": 22,
    "community_consultation": 10,
}
AVAILABILITY_DAYS = 21
DAY_SLOTS = [
    ("morning", "09:00", "12:00"),
    ("afternoon", "13:00", "17:00"),
    ("evening", "18:00", "21:00"),
]

PROVIDER_BRAND_WORDS = [
    "安心", "宏達", "日新", "友信", "皇家", "green", "誠品家", "百工",
    "速立", "家好", "新旺", "京鑫", "旭光", "順興", "禾豐", "築家",
    "亮潔", "水都", "電通", "雙成", "松果", "民生",
]


def assign_county(service_type: str, index: int) -> str:
    """決定服務商主場縣市：7 成密集縣市、3 成稀疏縣市輪流，離島永不入選。

    dense / sparse 各自獨立輪替，確保每個稀疏縣市至少有一家服務商。
    """
    dense = vocab.DENSE_COUNTIES
    sparse = vocab.SPARSE_COUNTIES
    offset = vocab.SERVICE_TYPES.index(service_type)
    if index % 10 < 7:
        dense_rank = (index // 10) * 7 + (index % 10)
        return dense[(dense_rank + offset) % len(dense)]
    sparse_rank = (index // 10) * 3 + (index % 10 - 7)
    return sparse[(sparse_rank + offset) % len(sparse)]


def _pick_areas(random_source, districts, service_type: str, index: int) -> list[dict]:
    """每個服務商挑一個主場縣市，再挑該縣市的數個行政區。"""
    county = assign_county(service_type, index)
    pool = [d for d in districts if d["county_code"] == county]
    span = {
        "restaurant_reservation": 1,
        "product_purchase": 0,  # 全國配送，不綁行政區
        "housekeeping_service": 6,
        "utility_repair": 5,
        "community_consultation": 4,
    }[service_type]
    if span == 0:
        return []
    picked = random_source.sample(pool, k=min(span, len(pool)))
    return [
        {"county_code": d["county_code"], "district_code": d["district_code"], "district_name": d["name"]}
        for d in picked
    ]


def _capabilities(random_source, service_type: str) -> list[str]:
    if service_type == "utility_repair":
        base = random_source.sample(vocab.REPAIR_CAPABILITIES, k=random_source.randint(2, 5))
        return sorted(set(base))
    if service_type == "housekeeping_service":
        return sorted(random_source.sample(vocab.HOUSEKEEPING_SKILLS, k=random_source.randint(2, 4)))
    if service_type == "restaurant_reservation":
        return sorted(random_source.sample(vocab.SEATING_TYPES, k=random_source.randint(1, 3)))
    if service_type == "product_purchase":
        return sorted(random_source.sample(list(vocab.PRODUCT_CATEGORIES), k=random_source.randint(3, 6)))
    return sorted(random_source.sample([c["code"] for c in vocab.COMMUNITY_ISSUE_CATEGORIES], k=5))


def _pricing(random_source, service_type: str) -> dict:
    if service_type == "utility_repair":
        return {
            "model": "inspection_fee_plus_quote",
            "inspection_fee": random_source.choice([0, 300, 350, 500, 800]),
            "min_charge": random_source.choice([800, 1000, 1200, 1500]),
            "emergency_surcharge": random_source.choice([0, 500, 800, 1200]),
            "currency": "TWD",
        }
    if service_type == "housekeeping_service":
        return {
            "model": "per_item",
            "min_charge": random_source.choice([1200, 1500, 1800, 2000]),
            "travel_fee": random_source.choice([0, 150, 200]),
            "currency": "TWD",
        }
    if service_type == "restaurant_reservation":
        return {
            "model": "minimum_spend",
            "min_spend_per_person": random_source.choice([0, 300, 500, 800, 1200, 2000]),
            "deposit_per_person": random_source.choice([0, 0, 200, 500]),
            "currency": "TWD",
        }
    if service_type == "product_purchase":
        return {"model": "sku_price", "currency": "TWD"}
    return {"model": "free_consultation", "currency": "TWD"}


def build() -> list[dict]:
    districts = read_mock("geo/districts.json")
    providers: list[dict] = []
    areas: list[dict] = []
    availability: list[dict] = []

    for service_type, count in PROVIDER_COUNTS.items():
        random_source = rng(f"provider:{service_type}")
        for index in range(count):
            provider_id = stable_uuid("provider", service_type, index)
            picked_areas = _pick_areas(random_source, districts, service_type, index)
            county = picked_areas[0]["county_code"] if picked_areas else None
            brand = PROVIDER_BRAND_WORDS[(index * 3 + len(service_type)) % len(PROVIDER_BRAND_WORDS)]
            name = _provider_name(service_type, brand, index)

            # 5% 服務商停用；10% 評分偏低，用來測排序
            is_active = not (index % 20 == 19)
            rating = round(random_source.uniform(3.2, 4.9), 1)

            providers.append(
                {
                    "provider_id": provider_id,
                    "service_type": service_type,
                    "name": name,
                    "is_active": is_active,
                    "rating": rating,
                    "review_count": random_source.randint(8, 860),
                    "capabilities": _capabilities(random_source, service_type),
                    "certifications": _certifications(random_source, service_type),
                    "pricing": _pricing(random_source, service_type),
                    "capacity_per_day": random_source.randint(2, 8),
                    "response_sla_hours": random_source.choice([1, 2, 4, 8, 24]),
                    "home_county_code": county,
                    "nationwide": service_type == "product_purchase",
                    "contact_landline": f"0{random_source.randint(2, 8)}-{random_source.randint(2000000, 8999999)}",
                    "source": "synthetic",
                }
            )

            for area in picked_areas:
                areas.append({"provider_id": provider_id, **area})

            if service_type in ("housekeeping_service", "utility_repair", "community_consultation"):
                availability.extend(_availability_rows(random_source, provider_id, service_type, index))

    report(write_json("master/providers.json", providers), len(providers))
    report(write_json("master/provider_service_areas.json", areas), len(areas))
    report(write_json("master/provider_availability.json", availability), len(availability))
    return providers


def _provider_name(service_type: str, brand: str, index: int) -> str:
    suffix = {
        "restaurant_reservation": "訂位服務",
        "product_purchase": "選品商城",
        "housekeeping_service": "家事服務",
        "utility_repair": "水電工程行",
        "community_consultation": "社區服務中心",
    }[service_type]
    return f"{brand}{suffix}" if service_type != "restaurant_reservation" else f"{brand}餐飲集團"


def _certifications(random_source, service_type: str) -> list[dict]:
    if service_type != "utility_repair":
        return []
    picked = random_source.sample(vocab.REPAIR_CERTIFICATIONS, k=random_source.randint(1, 3))
    return [
        {
            "type": cert,
            "number": f"TW-{random_source.randint(100000, 999999)}",
            "valid_until": f"{random_source.choice([2026, 2027, 2028, 2029])}-12-31",
        }
        for cert in picked
    ]


def _availability_rows(random_source, provider_id: str, service_type: str, index: int) -> list[dict]:
    rows = []
    # 每 8 個服務商中有 1 個「全滿檔」，用來測「有服務商但無時段」
    fully_booked = index % 8 == 3
    for day_offset in range(AVAILABILITY_DAYS):
        date = D_DAY + timedelta(days=day_offset)
        weekday = date.weekday()
        for slot_code, start, end in DAY_SLOTS:
            if service_type == "community_consultation" and (weekday >= 5 or slot_code == "evening"):
                continue
            capacity = 0 if fully_booked else random_source.choice([0, 1, 1, 2, 2, 3])
            rows.append(
                {
                    "provider_id": provider_id,
                    "date": date.strftime("%Y-%m-%d"),
                    "slot": slot_code,
                    "start_at": iso(date.replace(hour=int(start[:2]))),
                    "end_at": iso(date.replace(hour=int(end[:2]))),
                    "remaining_capacity": capacity,
                    "is_emergency_slot": service_type == "utility_repair" and slot_code == "evening",
                }
            )
    return rows


if __name__ == "__main__":
    build()
