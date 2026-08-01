"""案件資料：service_requests / matches / events / provider_replies / pii_vault。

狀態軌跡嚴格依照 design.md §8 的狀態機；PII 一律以 placeholder 存放，
真值集中在 pii_vault.json（假號段、假地址）。
"""

from __future__ import annotations

from datetime import timedelta

import geoctx
import matching
import skeletons
import utterances
from common import D_DAY, iso, read_mock, report, rng, stable_uuid, write_json
from vocab import SERVICE_TYPES

CASES_PER_TYPE = 100
CONSUMER_COUNT = 60

# 狀態分佈（有候選廠商時）。無候選一律 unmatched。
STATUS_PLAN = (
    ["completed"] * 35
    + ["in_progress"] * 15
    + ["accepted"] * 10
    + ["needs_information"] * 10
    + ["matched"] * 15
    + ["cancelled"] * 10
    + ["submitted"] * 5
)

TRACKS = {
    "submitted": ["submitted"],
    "unmatched": ["submitted", "unmatched"],
    "matched": ["submitted", "matched"],
    "needs_information": ["submitted", "matched", "needs_information"],
    "accepted": ["submitted", "matched", "accepted"],
    "in_progress": ["submitted", "matched", "accepted", "in_progress"],
    "completed": ["submitted", "matched", "accepted", "in_progress", "completed"],
    "cancelled": ["submitted", "matched", "cancelled"],
}

REPLY_TEMPLATES = {
    "accepted": [
        "已收到您的需求，我們可以配合您指定的時段，稍後由專員與您確認細節。",
        "此案本公司可承接，師傅預計於約定時間前 30 分鐘與您聯繫。",
    ],
    "needs_information": [
        "麻煩補充現場照片與樓層資訊，方便我們評估工時與材料。",
        "需要確認坪數與是否有寵物，才能給您正確報價。",
        "請提供社區管委會的施工同意文件，我們才能安排進場。",
    ],
    "in_progress": [
        "師傅已到場，初步判斷需更換零件，將於今日內回報報價。",
        "作業進行中，預計 2 小時內完成。",
    ],
    "completed": [
        "作業已完成並經現場確認，保固三個月，如有問題可再聯繫。",
        "服務完成，感謝您的使用，已寄出電子服務單。",
    ],
    "declined": [
        "很抱歉，該時段人力已滿，建議改約其他時段。",
        "此案超出本公司服務範圍，建議改由專門廠商處理。",
    ],
}

SAFETY_NOTE = (
    "偵測到高風險情境：請先停止使用該設備、必要時關閉總電源或總水閥，"
    "並保持通風。若有立即危險請撥打 119；停電問題可洽台電 1911。"
)


def build() -> None:
    geo = geoctx.build_context()
    providers = read_mock("master/providers.json")
    areas_by_provider: dict[str, set[str]] = {}
    for area in read_mock("master/provider_service_areas.json"):
        areas_by_provider.setdefault(area["provider_id"], set()).add(area["district_code"])

    service_requests: list[dict] = []
    all_matches: list[dict] = []
    all_events: list[dict] = []
    all_replies: list[dict] = []

    consumers = [stable_uuid("consumer", i) for i in range(CONSUMER_COUNT)]

    for service_type in SERVICE_TYPES:
        random_source = rng(f"case:{service_type}")
        for index in range(CASES_PER_TYPE):
            skeleton = skeletons.make(service_type, index, random_source, geo)
            matches = matching.rank(skeleton, providers, areas_by_provider)
            status = "unmatched" if not matches else random_source.choice(STATUS_PLAN)

            service_request_id = stable_uuid("service_request", service_type, index)
            created_at = D_DAY - timedelta(days=random_source.randint(0, 20), hours=random_source.randint(0, 23))
            consumer_id = consumers[(index * 7 + len(service_type)) % CONSUMER_COUNT]
            summary = utterances.compose(
                service_type, skeleton["fragments"], skeleton["style"], random_source
            )
            hazards = skeleton["fields"].get("repair.hazard_flags", {})
            is_high_risk = any(hazards.values())

            track = TRACKS[status]
            events, updated_at = _events_for(
                random_source, service_request_id, track, created_at, consumer_id, matches
            )

            service_requests.append(
                {
                    "service_request_id": service_request_id,
                    "skeleton_id": skeleton["skeleton_id"],
                    "service_type": service_type,
                    "schema_version": "1.0.0",
                    "consumer_id": consumer_id,
                    "status": status,
                    "version": len(events),
                    "request_summary": summary,
                    "form_payload": skeleton["fields"],
                    "county_code": skeleton["district"]["county_code"],
                    "district_code": skeleton["district"]["district_code"],
                    "district_name": skeleton["district"]["name"],
                    "is_high_risk": is_high_risk,
                    "safety_notice": SAFETY_NOTE if is_high_risk else None,
                    "pii_ref": stable_uuid("pii", service_request_id),
                    "idempotency_key": stable_uuid("idem", service_request_id),
                    "created_at": iso(created_at),
                    "updated_at": iso(updated_at),
                    "relaxation_suggestions": matching.relaxation_suggestions(skeleton) if not matches else [],
                    "source": "synthetic",
                }
            )
            all_events.extend(events)
            all_matches.extend(_matches_for(service_request_id, matches, status, created_at))
            all_replies.extend(_replies_for(random_source, service_request_id, matches, status, updated_at))

    report(write_json("cases/service_requests.json", service_requests), len(service_requests))
    report(write_json("cases/service_request_matches.json", all_matches), len(all_matches))
    report(write_json("cases/service_request_events.json", all_events), len(all_events))
    report(write_json("cases/provider_replies.json", all_replies), len(all_replies))
    _build_pii_vault(service_requests)
    _build_conflict_fixtures(service_requests)


def _events_for(random_source, service_request_id, track, created_at, consumer_id, matches):
    events = []
    at = created_at
    previous = None
    for position, status in enumerate(track):
        actor = consumer_id if status in ("submitted", "cancelled") else (
            matches[0]["provider_id"] if matches else consumer_id
        )
        events.append(
            {
                "event_id": stable_uuid("event", service_request_id, position),
                "service_request_id": service_request_id,
                "sequence": position + 1,
                "from_status": previous,
                "to_status": status,
                "actor_id": actor,
                "actor_role": "consumer" if status in ("submitted", "cancelled") else "provider",
                "note": None,
                "occurred_at": iso(at),
            }
        )
        previous = status
        at = at + timedelta(hours=random_source.randint(1, 30))
    return events, at


def _matches_for(service_request_id, matches, status, created_at):
    rows = []
    for rank_position, match in enumerate(matches):
        if status in ("accepted", "in_progress", "completed"):
            match_status = "accepted" if rank_position == 0 else "declined"
        elif status == "cancelled":
            match_status = "expired"
        else:
            match_status = "proposed"
        rows.append(
            {
                "service_request_id": service_request_id,
                "provider_id": match["provider_id"],
                "provider_name": match["provider_name"],
                "rank": rank_position + 1,
                "score": match["score"],
                "reasons": match["reasons"],
                "rule_version": match["rule_version"],
                "match_status": match_status,
                "proposed_at": iso(created_at),
            }
        )
    return rows


def _replies_for(random_source, service_request_id, matches, status, updated_at):
    if not matches or status in ("submitted", "matched", "unmatched"):
        return []
    bucket = status if status in REPLY_TEMPLATES else "accepted"
    rows = [
        {
            "reply_id": stable_uuid("reply", service_request_id, 0),
            "service_request_id": service_request_id,
            "provider_id": matches[0]["provider_id"],
            "body": random_source.choice(REPLY_TEMPLATES[bucket]),
            "created_at": iso(updated_at),
        }
    ]
    if len(matches) > 1 and random_source.random() < 0.4:
        rows.append(
            {
                "reply_id": stable_uuid("reply", service_request_id, 1),
                "service_request_id": service_request_id,
                "provider_id": matches[1]["provider_id"],
                "body": random_source.choice(REPLY_TEMPLATES["declined"]),
                "created_at": iso(updated_at),
            }
        )
    return rows


def _build_pii_vault(service_requests: list[dict]) -> None:
    """PII 只放這裡，且全部使用不會撥通的保留號段與虛構地址。"""
    random_source = rng("pii")
    surnames = "陳林黃張李王吳劉蔡楊許鄭謝洪郭"
    given = ["家豪", "淑芬", "怡君", "志明", "雅婷", "承翰", "宜庭", "冠廷", "詩涵", "柏翰"]
    rows = []
    for service_request in service_requests:
        serial = random_source.randint(0, 999)
        rows.append(
            {
                "pii_ref": service_request["pii_ref"],
                "service_request_id": service_request["service_request_id"],
                "contact_name": f"{random_source.choice(surnames)}{random_source.choice(given)}",
                "contact_mobile": f"0900-000-{serial:03d}",
                "contact_email": f"user{serial:03d}@example.invalid",
                "address_detail": f"{service_request['district_name']}虛構路{random_source.randint(1, 200)}號"
                f"{random_source.randint(1, 20)}樓",
                "note": "全部為虛構資料；0900-000-xxx 為測試保留號段，example.invalid 不可寄送",
            }
        )
    report(write_json("cases/pii_vault.json", rows), len(rows))


def _build_conflict_fixtures(service_requests: list[dict]) -> None:
    """冪等重試與樂觀鎖衝突樣本，給 MCP 工具驗收使用。"""
    random_source = rng("conflicts")
    sample = random_source.sample([i for i in service_requests if i["status"] == "matched"], k=12)
    rows = []
    for service_request in sample[:6]:
        rows.append(
            {
                "fixture_kind": "idempotent_retry",
                "tool": "create_service_request",
                "service_request_id": service_request["service_request_id"],
                "idempotency_key": service_request["idempotency_key"],
                "expected_behavior": "第二次呼叫必須回傳同一 service_request_id，且不得新增案件",
            }
        )
    for service_request in sample[6:]:
        rows.append(
            {
                "fixture_kind": "version_conflict",
                "tool": "update_service_request_status",
                "service_request_id": service_request["service_request_id"],
                "expected_version": service_request["version"],
                "concurrent_expected_version": service_request["version"],
                "expected_behavior": "先到者成功；後到者必須回傳 409 version_conflict",
            }
        )
    report(write_json("cases/conflict_fixtures.json", rows), len(rows))


if __name__ == "__main__":
    build()
