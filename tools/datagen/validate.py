"""資料集驗證 gate：不過就不出貨。

檢查外鍵、狀態機、評測欄位合法性、缺欄位計算一致性、PII 洩漏與配額分佈。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from common import OUT_DIR, read_mock
from skeletons import REQUIRED_FIELDS
from vocab import SERVICE_TYPES

# design.md §8 的合法狀態轉移
LEGAL_TRANSITIONS = {
    None: {"submitted"},
    "submitted": {"matched", "unmatched", "cancelled"},
    "matched": {"accepted", "needs_information", "unmatched", "cancelled"},
    "accepted": {"in_progress", "needs_information", "cancelled"},
    "needs_information": {"submitted", "cancelled"},
    "in_progress": {"completed", "needs_information", "cancelled"},
    "completed": set(),
    "unmatched": set(),
    "cancelled": set(),
}

# 允許出現在句子裡的假 PII：測試保留號段與不可寄送網域
ALLOWED_MOBILE = re.compile(r"0900-000-\d{3}")
MOBILE_PATTERN = re.compile(r"09\d{2}[-\s]?\d{3}[-\s]?\d{3}")
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
ID_PATTERN = re.compile(r"[A-Z][12]\d{8}")

EXPECTED_EVAL_QUOTA = {
    "normal": 200,
    "missing_required": 60,
    "conditional_field": 30,
    "ambiguous": 39,
    "cross_category": 30,
    "high_risk": 40,
    "unsupported": 29,
}


def main() -> int:
    failures: list[str] = []
    failures += _check_geo()
    failures += _check_master_fks()
    failures += _check_state_machine()
    failures += _check_eval_fields()
    failures += _check_pii()
    failures += _check_knowledge_base_metadata()
    failures += _check_quota()

    if failures:
        print(f"✗ 驗證失敗，共 {len(failures)} 項：")
        for item in failures[:40]:
            print(f"  - {item}")
        if len(failures) > 40:
            print(f"  ...另有 {len(failures) - 40} 項")
        return 1
    print("✓ 全部檢查通過")
    return 0


def _check_geo() -> list[str]:
    districts = read_mock("geo/districts.json")
    counties = {c["county_code"] for c in read_mock("geo/counties.json")}
    problems = []
    if len(districts) != 368:
        problems.append(f"行政區數量應為 368，實際 {len(districts)}")
    for district in districts:
        if district["county_code"] not in counties:
            problems.append(f"行政區 {district['district_code']} 的縣市代碼不存在")
    return problems


def _check_master_fks() -> list[str]:
    provider_ids = {p["provider_id"] for p in read_mock("master/providers.json")}
    district_codes = {d["district_code"] for d in read_mock("geo/districts.json")}
    skus = {p["sku"] for p in read_mock("master/products.json")}
    problems = []

    for area in read_mock("master/provider_service_areas.json"):
        if area["provider_id"] not in provider_ids:
            problems.append(f"service_area 指向不存在的服務商 {area['provider_id']}")
        if area["district_code"] not in district_codes:
            problems.append(f"service_area 指向不存在的行政區 {area['district_code']}")

    for name in ("restaurants", "housekeeping_offerings", "repair_technicians", "responsible_units"):
        for row in read_mock(f"master/{name}.json"):
            if row["provider_id"] not in provider_ids:
                problems.append(f"{name} 指向不存在的服務商 {row['provider_id']}")

    for row in read_mock("master/product_inventory.json"):
        if row["sku"] not in skus:
            problems.append(f"庫存指向不存在的 SKU {row['sku']}")
    return problems


def _check_state_machine() -> list[str]:
    service_requests = {i["service_request_id"]: i for i in read_mock("cases/service_requests.json")}
    events = read_mock("cases/service_request_events.json")
    by_service_request: dict[str, list[dict]] = {}
    for event in events:
        by_service_request.setdefault(event["service_request_id"], []).append(event)

    problems = []
    for service_request_id, rows in by_service_request.items():
        if service_request_id not in service_requests:
            problems.append(f"事件指向不存在的案件 {service_request_id}")
            continue
        rows.sort(key=lambda r: r["sequence"])
        previous = None
        for event in rows:
            if event["to_status"] not in LEGAL_TRANSITIONS[previous]:
                problems.append(
                    f"案件 {service_request_id} 非法轉移 {previous} -> {event['to_status']}"
                )
                break
            previous = event["to_status"]
        if previous != service_requests[service_request_id]["status"]:
            problems.append(f"案件 {service_request_id} 最終事件狀態與 status 不一致")

    for service_request in service_requests.values():
        if service_request["status"] == "unmatched" and not service_request["relaxation_suggestions"]:
            problems.append(f"案件 {service_request['service_request_id']} 為 unmatched 卻沒有放寬建議")
    return problems


def _check_eval_fields() -> list[str]:
    """評測集抽取欄位必須是該類表單真的有的欄位，缺欄位必須是算出來的。"""
    allowed = {
        service_type: {f.split(".")[0] for f in REQUIRED_FIELDS[service_type]}
        for service_type in SERVICE_TYPES
    }
    problems = []
    for row in _read_jsonl("eval/eval.jsonl"):
        expected = row["expected"]
        service_type = expected["service_type"]
        if service_type in (None, "unsupported"):
            continue
        for key in expected["extracted_fields"]:
            if key.split(".")[0] not in allowed[service_type]:
                problems.append(f"{row['case_id']} 抽取了不存在的欄位群 {key}")
        overlap = set(expected["extracted_fields"]) & set(expected["missing_required_fields"])
        if overlap:
            problems.append(f"{row['case_id']} 同一欄位同時被標為已抽取與缺少：{sorted(overlap)}")
        required = set(REQUIRED_FIELDS[service_type])
        still_required_missing = required - set(expected["extracted_fields"])
        if set(expected["missing_required_fields"]) != still_required_missing:
            problems.append(f"{row['case_id']} missing_required_fields 與必填清單推算結果不符")
        if expected["next_action"] == "search_providers" and "create_service_request" not in expected["must_not_call"]:
            problems.append(f"{row['case_id']} 尚未確認就允許呼叫 create_service_request")
    return problems


def _check_pii() -> list[str]:
    """句子與知識庫不得出現真實格式的手機、Email 或身分證字號。"""
    problems = []
    targets: list[tuple[str, str]] = []
    for path in sorted((OUT_DIR / "eval").glob("*.jsonl")):
        targets.append((path.name, path.read_text(encoding="utf-8")))
    for path in sorted((OUT_DIR / "knowledge").glob("*.md")):
        targets.append((path.name, path.read_text(encoding="utf-8")))
    for path in sorted((OUT_DIR / "knowledge_base").rglob("*.md")):
        targets.append((str(path.relative_to(OUT_DIR)), path.read_text(encoding="utf-8")))
    for service_request in read_mock("cases/service_requests.json"):
        targets.append((service_request["service_request_id"], service_request["request_summary"]))

    for name, text in targets:
        for match in MOBILE_PATTERN.findall(text):
            if not ALLOWED_MOBILE.fullmatch(match):
                problems.append(f"{name} 出現非保留號段手機 {match}")
        for match in EMAIL_PATTERN.findall(text):
            if not match.endswith("example.invalid"):
                problems.append(f"{name} 出現可寄送的 Email {match}")
        for match in ID_PATTERN.findall(text):
            problems.append(f"{name} 出現身分證格式字串 {match}")
    return problems


def _check_knowledge_base_metadata() -> list[str]:
    problems = []
    documents = sorted((OUT_DIR / "knowledge_base").rglob("*.md"))
    if not documents:
        return ["knowledge_base 沒有可上傳的 Markdown 文件"]

    seen_service_types: set[str] = set()
    allowed_kinds = {"faq", "notice", "terms", "sop", "safety"}
    for document in documents:
        sidecar = document.with_name(f"{document.name}.metadata.json")
        if not sidecar.exists():
            problems.append(f"{document.relative_to(OUT_DIR)} 缺少 metadata sidecar")
            continue
        try:
            attributes = json.loads(sidecar.read_text(encoding="utf-8"))["metadataAttributes"]
        except (json.JSONDecodeError, KeyError, TypeError):
            problems.append(f"{sidecar.relative_to(OUT_DIR)} 格式無效")
            continue
        service_type = attributes.get("service_type")
        if service_type not in SERVICE_TYPES:
            problems.append(f"{sidecar.relative_to(OUT_DIR)} service_type 無效")
        else:
            seen_service_types.add(service_type)
        if attributes.get("doc_kind") not in allowed_kinds:
            problems.append(f"{sidecar.relative_to(OUT_DIR)} doc_kind 無效")
        if attributes.get("authoritative_scope") != "static_only":
            problems.append(f"{sidecar.relative_to(OUT_DIR)} 未限制為 static_only")

    missing = set(SERVICE_TYPES) - seen_service_types
    if missing:
        problems.append(f"knowledge_base 缺少服務類別：{sorted(missing)}")
    return problems


def _check_quota() -> list[str]:
    counts: dict[str, int] = {}
    for row in _read_jsonl("eval/eval.jsonl"):
        category = row["labels"]["category"]
        counts[category] = counts.get(category, 0) + 1
    problems = []
    for category, expected in EXPECTED_EVAL_QUOTA.items():
        actual = counts.get(category, 0)
        if abs(actual - expected) > max(2, expected * 0.1):
            problems.append(f"評測配額 {category} 期望約 {expected}，實際 {actual}")
    return problems


def _read_jsonl(relative_path: str) -> list[dict]:
    path: Path = OUT_DIR / relative_path
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


if __name__ == "__main__":
    sys.exit(main())
