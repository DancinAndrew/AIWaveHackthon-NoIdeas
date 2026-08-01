"""餐廳目錄與可訂時段。

每家餐廳綁定一個 restaurant_reservation 服務商，位於該服務商的服務行政區。
時段涵蓋 D 日起 21 天，午晚餐各 3 個時段。
"""

from __future__ import annotations

from datetime import timedelta

import vocab
from common import D_DAY, iso, read_mock, report, rng, stable_uuid, write_json

SLOT_DAYS = 21
LUNCH_TIMES = [(11, 30), (12, 0), (13, 0)]
DINNER_TIMES = [(17, 30), (18, 30), (19, 30)]
STREET_NAMES = ["中山路", "中正路", "民生路", "光復路", "和平路", "成功路", "自由路", "文化街"]
TABLE_TYPES = [
    {"code": "two_seat", "label": "2 人桌", "capacity": 2},
    {"code": "four_seat", "label": "4 人桌", "capacity": 4},
    {"code": "six_seat", "label": "6 人桌", "capacity": 6},
    {"code": "private_room", "label": "包廂", "capacity": 12},
]


def build() -> None:
    providers = [p for p in read_mock("master/providers.json") if p["service_type"] == "restaurant_reservation"]
    areas = read_mock("master/provider_service_areas.json")
    area_by_provider = {}
    for area in areas:
        area_by_provider.setdefault(area["provider_id"], []).append(area)

    random_source = rng("restaurants")
    restaurants: list[dict] = []
    slots: list[dict] = []

    for index, provider in enumerate(providers):
        cuisine = vocab.CUISINES[index % len(vocab.CUISINES)]
        area = area_by_provider.get(provider["provider_id"], [{}])[0]
        restaurant_id = stable_uuid("restaurant", index)
        name_part = vocab.RESTAURANT_NAME_PARTS[cuisine][index % 5]
        name = f"{name_part}{random_source.choice(vocab.RESTAURANT_SUFFIXES)}"

        open_hour, close_hour = random_source.choice([(11, 21), (11, 22), (17, 23), (11, 14)])
        closed_weekday = random_source.choice([None, 0, 1, 2])
        seating = random_source.sample(TABLE_TYPES, k=random_source.randint(2, 4))

        # 價位互相一致：price_level 由 avg_price 推導，低消不得高於平均客單價
        avg_price = random_source.choice([250, 400, 600, 850, 1200, 1800, 2800])
        price_level = next(i for i, ceiling in enumerate([400, 850, 1800, 99999], start=1) if avg_price <= ceiling)
        min_spend = min(provider["pricing"]["min_spend_per_person"], avg_price)

        restaurant = {
            "restaurant_id": restaurant_id,
            "provider_id": provider["provider_id"],
            "name": name,
            "cuisine": cuisine,
            "county_code": area.get("county_code"),
            "district_code": area.get("district_code"),
            "address_masked": f"{area.get('district_name', '')}{random_source.choice(STREET_NAMES)}{random_source.randint(1, 320)}號",
            "phone": f"0{random_source.randint(2, 8)}-{random_source.randint(2000000, 8999999)}",
            "price_level": price_level,
            "avg_price_per_person": avg_price,
            "min_spend_per_person": min_spend,
            "deposit_per_person": provider["pricing"]["deposit_per_person"],
            "opening_hours": {
                "open": f"{open_hour:02d}:00",
                "close": f"{close_hour:02d}:00",
                "closed_weekday": closed_weekday,
                "last_order_minutes_before_close": 60,
            },
            "max_party_size": max(t["capacity"] for t in seating),
            "table_types": seating,
            "dietary_support": sorted(
                random_source.sample(vocab.DIETARY_SUPPORTS, k=random_source.randint(0, 3))
            ),
            "features": sorted(
                random_source.sample(
                    ["兒童座椅", "無障礙入口", "有停車場", "可帶寵物", "包廂投影", "禁菸"],
                    k=random_source.randint(1, 4),
                )
            ),
            "cancellation_rule": random_source.choice(vocab.RESERVATION_CANCEL_RULES),
            "accepts_online_booking": index % 12 != 5,
            "rating": provider["rating"],
            "source": "synthetic",
        }
        restaurants.append(restaurant)

        if restaurant["accepts_online_booking"]:
            slots.extend(_slots_for(random_source, restaurant, closed_weekday, open_hour, close_hour))

    report(write_json("master/restaurants.json", restaurants), len(restaurants))
    report(write_json("master/restaurant_slots.json", slots), len(slots))


def _slots_for(random_source, restaurant: dict, closed_weekday, open_hour: int, close_hour: int) -> list[dict]:
    rows = []
    for day_offset in range(SLOT_DAYS):
        date = D_DAY + timedelta(days=day_offset)
        if closed_weekday is not None and date.weekday() == closed_weekday:
            continue
        is_weekend = date.weekday() >= 5
        for hour, minute in LUNCH_TIMES + DINNER_TIMES:
            if hour < open_hour or hour >= close_hour:
                continue
            for table in restaurant["table_types"]:
                # 週末與晚餐時段刻意收緊，製造「熱門時段訂不到」
                base = 3 if not is_weekend else 1
                if hour >= 17:
                    base -= 1
                seats = max(0, base + random_source.choice([-1, 0, 0, 1]))
                rows.append(
                    {
                        "restaurant_id": restaurant["restaurant_id"],
                        "start_at": iso(date.replace(hour=hour, minute=minute)),
                        "table_type": table["code"],
                        "party_size_max": table["capacity"],
                        "tables_available": seats,
                    }
                )
    return rows


if __name__ == "__main__":
    build()
