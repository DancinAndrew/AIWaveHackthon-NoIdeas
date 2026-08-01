"""家事服務項目／計價，以及水電技師（專長、證照、勘查費、緊急能力）。"""

from __future__ import annotations

import vocab
from common import read_mock, report, rng, stable_uuid, write_json

TECHNICIANS_PER_VENDOR = (1, 4)


def build() -> None:
    providers = read_mock("master/providers.json")
    _build_housekeeping([p for p in providers if p["service_type"] == "housekeeping_service"])
    _build_technicians([p for p in providers if p["service_type"] == "utility_repair"])


def _build_housekeeping(providers: list[dict]) -> None:
    random_source = rng("housekeeping_offerings")
    rows: list[dict] = []
    for provider in providers:
        picked = random_source.sample(
            vocab.HOUSEKEEPING_ITEMS, k=random_source.randint(4, len(vocab.HOUSEKEEPING_ITEMS))
        )
        for item in picked:
            # 各家在基準價上下 15% 浮動，形成可比價的差異
            price = int(round(item["price"] * random_source.uniform(0.85, 1.15) / 10) * 10)
            rows.append(
                {
                    "offering_id": stable_uuid("hk_offering", provider["provider_id"], item["code"]),
                    "provider_id": provider["provider_id"],
                    "provider_name": provider["name"],
                    "item_code": item["code"],
                    "item_label": item["label"],
                    "pricing_model": item["pricing"],
                    "unit": item["unit"],
                    "unit_price": price,
                    "min_units": 1 if item["pricing"] != "hourly" else 3,
                    "min_charge": provider["pricing"]["min_charge"],
                    "travel_fee": provider["pricing"]["travel_fee"],
                    "property_types": sorted(
                        random_source.sample(vocab.PROPERTY_TYPES, k=random_source.randint(2, 5))
                    ),
                    "frequencies": sorted(
                        random_source.sample(vocab.CLEAN_FREQUENCIES, k=random_source.randint(1, 4))
                    ),
                    "requires_photos": item["code"] in ("deep_clean", "kitchen_clean", "move_in_clean"),
                    "lead_time_days": random_source.choice([1, 2, 3, 5]),
                    "source": "synthetic",
                }
            )
    report(write_json("master/housekeeping_offerings.json", rows), len(rows))


def _build_technicians(providers: list[dict]) -> None:
    random_source = rng("technicians")
    rows: list[dict] = []
    for provider in providers:
        count = random_source.randint(*TECHNICIANS_PER_VENDOR)
        for seat in range(count):
            specialties = random_source.sample(
                [i["code"] for i in vocab.REPAIR_ISSUE_TYPES if i["code"] != "other"],
                k=random_source.randint(2, 4),
            )
            handles_emergency = "emergency_24h" in provider["capabilities"]
            rows.append(
                {
                    "technician_id": stable_uuid("technician", provider["provider_id"], seat),
                    "provider_id": provider["provider_id"],
                    "provider_name": provider["name"],
                    "display_name": f"{random_source.choice('陳林黃張李王吳劉蔡楊')}師傅",
                    "years_experience": random_source.randint(1, 28),
                    "specialties": sorted(specialties),
                    "certifications": provider["certifications"],
                    "handles_emergency": handles_emergency,
                    "night_shift": "night_shift" in provider["capabilities"],
                    "gas_certified": "gas_certified" in provider["capabilities"],
                    "inspection_fee": provider["pricing"]["inspection_fee"],
                    "emergency_surcharge": provider["pricing"]["emergency_surcharge"],
                    "min_charge": provider["pricing"]["min_charge"],
                    "max_jobs_per_day": random_source.randint(2, 6),
                    "rating": round(min(5.0, provider["rating"] + random_source.uniform(-0.3, 0.3)), 1),
                    "source": "synthetic",
                }
            )
    report(write_json("master/repair_technicians.json", rows), len(rows))


if __name__ == "__main__":
    build()
