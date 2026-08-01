"""社區／大樓主檔，以及責任單位（受理範圍、服務時段、SLA、轉介與升級規則）。"""

from __future__ import annotations

import vocab
from common import read_mock, report, rng, stable_uuid, write_json

COMMUNITY_COUNT = 20

ESCALATION_RULES = [
    {
        "trigger": "urgency == emergency",
        "action": "escalate_to_hotline",
        "target": "119 / 縣市 1999 專線",
        "note": "涉及人身安全或立即危險時，先引導撥打緊急專線再建案",
    },
    {
        "trigger": "issue_category == elevator and urgency in (urgent, emergency)",
        "action": "escalate_to_vendor",
        "target": "電梯保養廠商 24 小時派工",
        "note": "受困必須同時通報消防與保養廠商",
    },
    {
        "trigger": "issue_category == leak_dispute",
        "action": "refer",
        "target": "management_committee -> 住戶協調會議",
        "note": "涉及住戶間責任歸屬，管委會僅協調不裁決",
    },
    {
        "trigger": "issue_category == fee_dispute",
        "action": "refer",
        "target": "management_committee -> 區分所有權人會議",
        "note": "管理費爭議依規約與會議決議處理，不由客服判定",
    },
    {
        "trigger": "no_response_after_hours > sla_hours",
        "action": "escalate_to_property_management",
        "target": "物業管理公司區經理",
        "note": "逾期未回應自動升級",
    },
]


def build() -> None:
    districts = read_mock("geo/districts.json")
    providers = [p for p in read_mock("master/providers.json") if p["service_type"] == "community_consultation"]
    areas = read_mock("master/provider_service_areas.json")
    area_by_provider: dict[str, list[dict]] = {}
    for area in areas:
        area_by_provider.setdefault(area["provider_id"], []).append(area)

    random_source = rng("community")
    communities: list[dict] = []
    for index in range(COMMUNITY_COUNT):
        provider = providers[index % len(providers)]
        provider_areas = area_by_provider.get(provider["provider_id"], [])
        area = provider_areas[index % len(provider_areas)] if provider_areas else {}
        district = next(
            (d for d in districts if d["district_code"] == area.get("district_code")), None
        )
        name = (
            vocab.COMMUNITY_NAME_PARTS[index % len(vocab.COMMUNITY_NAME_PARTS)]
            + vocab.COMMUNITY_NAME_SUFFIXES[index % len(vocab.COMMUNITY_NAME_SUFFIXES)]
        )
        communities.append(
            {
                "community_id": stable_uuid("community", index),
                "name": name,
                "county_code": area.get("county_code"),
                "district_code": area.get("district_code"),
                "district_name": district["name"] if district else None,
                "building_count": random_source.randint(1, 6),
                "household_count": random_source.randint(48, 620),
                "has_management_committee": index % 7 != 3,
                "property_management_provider_id": provider["provider_id"],
                "management_office_hours": random_source.choice(
                    ["09:00-18:00", "08:30-17:30", "24h 警衛室"]
                ),
                "facilities": sorted(
                    random_source.sample(
                        ["健身房", "交誼廳", "游泳池", "閱覽室", "訪客停車位", "resident 包裹櫃"],
                        k=random_source.randint(1, 4),
                    )
                ),
                "source": "synthetic",
            }
        )

    units: list[dict] = []
    for index, provider in enumerate(providers):
        unit_type = vocab.RESPONSIBLE_UNIT_TYPES[index % len(vocab.RESPONSIBLE_UNIT_TYPES)]
        scope = sorted(
            random_source.sample(
                [c["code"] for c in vocab.COMMUNITY_ISSUE_CATEGORIES],
                k=random_source.randint(3, 7),
            )
        )
        units.append(
            {
                "unit_id": stable_uuid("responsible_unit", index),
                "provider_id": provider["provider_id"],
                "name": f"{provider['name']}－{unit_type['label']}",
                "unit_type": unit_type["code"],
                "accepts_issue_categories": scope,
                "service_hours": "週一至週五 09:00-17:00"
                if unit_type["code"] != "city_service_1999"
                else "24 小時",
                "sla_first_response_hours": random_source.choice([2, 4, 8, 24, 48]),
                "sla_resolution_days": random_source.choice([1, 3, 5, 7, 14]),
                "requires_pii_consent": True,
                "accepts_anonymous": unit_type["code"] in ("city_service_1999", "environment_bureau"),
                "escalation_rules": random_source.sample(ESCALATION_RULES, k=random_source.randint(2, 4)),
                "source": "synthetic",
            }
        )

    report(write_json("master/communities.json", communities), len(communities))
    report(write_json("master/responsible_units.json", units), len(units))


if __name__ == "__main__":
    build()
