"""AI 評測集：單輪 eval.jsonl 與多輪 multi_turn.jsonl。

正常／缺欄位／條件式／高風險（水電）由 skeleton 反向生成，ground truth 天生正確；
模糊、跨類別、不支援與非水電高風險由 eval_banks 手寫。
"""

from __future__ import annotations

import eval_banks
import geoctx
import skeletons
import utterances
from common import SEED, iso, read_mock, report, rng, write_jsonl
from skeletons import REQUIRED_FIELDS
from vocab import SERVICE_TYPES

NORMAL_PER_TYPE = 40
MISSING_PER_TYPE = 12
CONDITIONAL_PER_TYPE = 6
REPAIR_HIGH_RISK = 25
MULTI_TURN_PER_TYPE = 10

# 這些必填欄位由受信任前端收集，不會出現在對話裡，永遠算「缺」
FRONTEND_ONLY_FIELDS = {"contact.name", "contact.mobile", "consent", "preferred_contact_time"}

# 欄位 → 句子片段的對照，決定「拿掉某欄位時要拿掉哪個片段」
FIELD_LABELS = {
    "restaurant.location": "用餐地區",
    "restaurant.reservation_at": "用餐時間",
    "restaurant.party_size": "用餐人數",
    "restaurant.cuisine_preferences": "想吃的料理",
    "restaurant.budget_per_person": "每人預算",
    "product.query": "想買的商品",
    "product.category": "商品類別",
    "product.budget": "預算",
    "product.quantity": "數量",
    "product.delivery": "收貨地區",
    "product.accept_substitutes": "是否接受替代品",
    "housekeeping.service_items": "清潔項目",
    "housekeeping.property_type": "住宅類型",
    "housekeeping.location": "服務地區",
    "housekeeping.preferred_time_slots": "希望時段",
    "housekeeping.frequency": "服務頻率",
    "housekeeping.has_pets": "家中是否有寵物",
    "repair.issue_type": "故障類型",
    "repair.symptoms": "故障症狀",
    "repair.location": "地址所在區域",
    "repair.urgency": "急迫程度",
    "repair.hazard_flags": "是否有漏電、冒煙或淹水",
    "repair.preferred_time_slots": "方便到府的時段",
    "community.community_name": "社區或大樓名稱",
    "community.location": "所在區域",
    "community.issue_category": "議題類別",
    "community.description": "問題描述",
    "community.urgency": "急迫程度",
    "community.anonymity_preference": "是否希望匿名",
}

FIELD_TO_FRAGMENT = {
    "restaurant.location": "location",
    "restaurant.reservation_at": "reservation_at",
    "restaurant.party_size": "party_size",
    "restaurant.cuisine_preferences": "cuisine",
    "restaurant.budget_per_person": "budget",
    "product.query": "query",
    "product.category": "category",
    "product.budget": "budget",
    "product.quantity": "quantity",
    "product.delivery": "delivery",
    "product.accept_substitutes": "substitute",
    "housekeeping.service_items": "service_items",
    "housekeeping.property_type": "property_type",
    "housekeeping.location": "location",
    "housekeeping.preferred_time_slots": "time",
    "housekeeping.frequency": "frequency",
    "housekeeping.has_pets": "pets",
    "repair.issue_type": "issue_type",
    "repair.symptoms": "symptom",
    "repair.location": "location",
    "repair.urgency": "urgency",
    "repair.hazard_flags": "hazard",
    "repair.preferred_time_slots": "time",
    "community.community_name": "community",
    "community.location": "location",
    "community.issue_category": "issue",
    "community.description": "description",
    "community.urgency": "urgency",
    "community.anonymity_preference": "anonymity",
}


def build() -> None:
    geo = geoctx.build_context()
    rows: list[dict] = []
    rows.extend(_skeleton_cases(geo))
    rows.extend(_ambiguous())
    rows.extend(_cross_category())
    rows.extend(_high_risk_bank())
    rows.extend(_unsupported())
    report(write_jsonl("eval/eval.jsonl", rows), len(rows))
    report(write_jsonl("eval/multi_turn.jsonl", _multi_turn(geo)), MULTI_TURN_PER_TYPE * len(SERVICE_TYPES))
    report(write_jsonl("eval/holdout_human.jsonl", _holdout_template()), 5)


def _record(case_id, utterance, service_type, extracted, missing, next_action, category,
            difficulty, tool_calls, must_not_call, *, safety_action=None, confidence="high",
            skeleton_id=None, style=None, notes=None) -> dict:
    return {
        "case_id": case_id,
        "user_utterance": utterance,
        "locale": "zh-TW",
        "expected": {
            "service_type": service_type,
            "confidence_band": confidence,
            "extracted_fields": extracted,
            "missing_required_fields": sorted(missing),
            "next_action": next_action,
            "safety_action": safety_action,
            "tool_calls": tool_calls,
            "must_not_call": must_not_call,
        },
        "labels": {"category": category, "difficulty": difficulty, "turns": 1},
        "generator": {"seed": SEED, "skeleton_id": skeleton_id, "style": style},
        "notes": notes,
    }


def _from_skeleton(skeleton, dropped_fields: list[str], case_id: str, category: str,
                   difficulty: str, random_source) -> dict:
    fields = {k: v for k, v in skeleton["fields"].items() if k not in dropped_fields}
    fragments = {
        key: slots
        for key, slots in skeleton["fragments"].items()
        if key not in {FIELD_TO_FRAGMENT.get(f) for f in dropped_fields}
    }
    utterance = utterances.compose(
        skeleton["service_type"], fragments, skeleton["style"], random_source
    )
    extracted = {k: v for k, v in fields.items() if k not in FRONTEND_ONLY_FIELDS}
    missing = [
        f
        for f in REQUIRED_FIELDS[skeleton["service_type"]]
        if f in FRONTEND_ONLY_FIELDS or f in dropped_fields
    ]
    hazards = fields.get("repair.hazard_flags", {})
    is_high_risk = any(hazards.values())

    conversational_missing = [f for f in missing if f not in FRONTEND_ONLY_FIELDS]
    if is_high_risk:
        next_action = "safety_notice_then_ask"
    elif conversational_missing:
        next_action = "ask_clarifying"
    else:
        next_action = "search_providers"

    tool_calls = [{"name": "get_form_schema", "arguments": {"service_type": skeleton["service_type"]}}]
    if next_action == "search_providers":
        tool_calls.append(
            {
                "name": "search_providers",
                "arguments": {
                    "service_type": skeleton["service_type"],
                    "criteria": _criteria(skeleton, fields),
                },
            }
        )

    return _record(
        case_id,
        utterance,
        skeleton["service_type"],
        extracted,
        missing,
        next_action,
        category,
        difficulty,
        tool_calls,
        ["create_service_request"],
        safety_action="warn_stop_and_advise_professional" if is_high_risk else None,
        skeleton_id=skeleton["skeleton_id"],
        style=skeleton["style"],
    )


def _criteria(skeleton, fields) -> dict:
    criteria = {
        "county_code": skeleton["district"]["county_code"],
        "district_code": skeleton["district"]["district_code"],
    }
    for source, target in (
        ("restaurant.budget_per_person", "budget_max"),
        ("product.budget", "budget_max"),
        ("restaurant.party_size", "party_size"),
        ("product.quantity", "quantity"),
        ("repair.urgency", "urgency"),
        ("community.urgency", "urgency"),
        ("housekeeping.has_pets", "has_pets"),
    ):
        if source in fields:
            criteria[target] = fields[source]
    hazards = fields.get("repair.hazard_flags", {})
    active = sorted(flag for flag, on in hazards.items() if on)
    if active:
        criteria["hazard_flags"] = active
    return criteria


def _skeleton_cases(geo) -> list[dict]:
    rows: list[dict] = []
    for service_type in SERVICE_TYPES:
        random_source = rng(f"eval:{service_type}")
        required = [f for f in REQUIRED_FIELDS[service_type] if f not in FRONTEND_ONLY_FIELDS]
        index = 0
        for n in range(NORMAL_PER_TYPE):
            skeleton = skeletons.make(service_type, 1000 + index, random_source, geo)
            rows.append(
                _from_skeleton(skeleton, [], f"eval-{service_type}-normal-{n:03d}", "normal", "easy", random_source)
            )
            index += 1
        for n in range(MISSING_PER_TYPE):
            skeleton = skeletons.make(service_type, 1000 + index, random_source, geo)
            dropped = random_source.sample(required, k=random_source.randint(1, 3))
            rows.append(
                _from_skeleton(
                    skeleton, dropped, f"eval-{service_type}-missing-{n:03d}", "missing_required", "medium", random_source
                )
            )
            index += 1
        for n in range(CONDITIONAL_PER_TYPE):
            skeleton = skeletons.make(service_type, 1000 + index, random_source, geo)
            row = _from_skeleton(
                skeleton, [], f"eval-{service_type}-conditional-{n:03d}", "conditional_field", "medium", random_source
            )
            row["notes"] = "條件式欄位：依已填答案應觸發的追問（如有寵物→寵物種類、坪數>50→是否需兩名人員）"
            rows.append(row)
            index += 1

    # 水電高風險由 skeleton 生成，確保 hazard_flags 與句子一致
    random_source = rng("eval:high_risk_repair")
    produced = 0
    index = 5000
    while produced < REPAIR_HIGH_RISK:
        skeleton = skeletons.make("utility_repair", index, random_source, geo)
        index += 1
        if not any(skeleton["fields"]["repair.hazard_flags"].values()):
            continue
        rows.append(
            _from_skeleton(
                skeleton, [], f"eval-utility_repair-highrisk-{produced:03d}", "high_risk", "hard", random_source
            )
        )
        produced += 1
    return rows


def _ambiguous() -> list[dict]:
    rows = []
    for n, (utterance, missing) in enumerate(eval_banks.AMBIGUOUS):
        rows.append(
            _record(
                f"eval-ambiguous-{n:03d}",
                utterance,
                None,
                {},
                missing,
                "ask_clarifying",
                "ambiguous",
                "hard",
                [],
                ["create_service_request", "search_providers"],
                confidence="low",
                notes="資訊不足以分類，必須澄清而非猜測；不得先呼叫 search_providers",
            )
        )
    return rows


def _cross_category() -> list[dict]:
    rows = []
    for n, (utterance, types) in enumerate(eval_banks.CROSS_CATEGORY):
        rows.append(
            _record(
                f"eval-cross-{n:03d}",
                utterance,
                None,
                {"candidate_service_types": sorted(set(types))},
                ["service_type"],
                "ask_disambiguation",
                "cross_category",
                "hard",
                [],
                ["create_service_request"],
                confidence="low",
                notes=f"同時觸及 {len(set(types))} 類服務，應拆單或請使用者選擇後再繼續",
            )
        )
    return rows


def _high_risk_bank() -> list[dict]:
    rows = []
    for n, (utterance, hazard, safety_action) in enumerate(eval_banks.HIGH_RISK):
        service_type = "utility_repair" if hazard else None
        extracted = {"repair.hazard_flags": {hazard: True}} if hazard else {}
        # 缺欄位一律由必填清單扣掉已抽取欄位算出來，不手寫，否則會和 schema 脫節
        missing = (
            [f for f in REQUIRED_FIELDS["utility_repair"] if f not in extracted]
            if hazard
            else ["service_type"]
        )
        rows.append(
            _record(
                f"eval-highrisk-bank-{n:03d}",
                utterance,
                service_type,
                extracted,
                missing,
                "safety_notice_then_ask" if hazard else "escalate_emergency",
                "high_risk",
                "hard",
                [],
                ["create_service_request", "search_providers"],
                safety_action=safety_action,
                confidence="high" if hazard else "medium",
                notes="安全指引必須先於任何媒合或建案動作",
            )
        )
    return rows


def _unsupported() -> list[dict]:
    rows = []
    for n, (utterance, domain) in enumerate(eval_banks.UNSUPPORTED):
        rows.append(
            _record(
                f"eval-unsupported-{n:03d}",
                utterance,
                "unsupported",
                {"requested_domain": domain},
                [],
                "refuse_and_redirect",
                "unsupported",
                "medium",
                [],
                ["create_service_request", "search_providers", "get_form_schema"],
                confidence="high",
                notes=f"{domain} 不在平台五類服務範圍，應明確說明並提供正確管道",
            )
        )
    return rows


def _multi_turn(geo) -> list[dict]:
    """把一筆完整需求拆成 2~3 輪：先講一半，被追問後補齊，最後確認建案。"""
    rows = []
    for service_type in SERVICE_TYPES:
        random_source = rng(f"multiturn:{service_type}")
        required = [f for f in REQUIRED_FIELDS[service_type] if f not in FRONTEND_ONLY_FIELDS]
        for n in range(MULTI_TURN_PER_TYPE):
            skeleton = skeletons.make(service_type, 9000 + n, random_source, geo)
            held_back = random_source.sample(required, k=2)
            first = _from_skeleton(
                skeleton, held_back, f"mt-{service_type}-{n:03d}-t1", "multi_turn", "medium", random_source
            )
            second = _from_skeleton(
                skeleton, [], f"mt-{service_type}-{n:03d}-t2", "multi_turn", "medium", random_source
            )
            rows.append(
                {
                    "case_id": f"mt-{service_type}-{n:03d}",
                    "locale": "zh-TW",
                    "turns": [
                        {
                            "role": "user",
                            "text": first["user_utterance"],
                            "expected": first["expected"],
                        },
                        {
                            "role": "assistant",
                            "text": "還需要確認"
                            + "與".join(FIELD_LABELS[f] for f in held_back)
                            + "，方便提供嗎？",
                            "expected": {"next_action": "ask_clarifying"},
                        },
                        {
                            "role": "user",
                            "text": _supplement_text(skeleton, held_back),
                            "expected": {
                                **second["expected"],
                                "next_action": "summarize_and_confirm",
                                "must_not_call": ["create_service_request"],
                            },
                        },
                        {
                            "role": "user",
                            "text": "對，就這樣，幫我送出",
                            "expected": {
                                "next_action": "create_service_request",
                                "tool_calls": [
                                    {
                                        "name": "create_service_request",
                                        "arguments": {
                                            "service_type": service_type,
                                            "schema_version": "1.0.0",
                                            "submission_ref": "{{SUBMISSION_REF}}",
                                            "confirmation_token": "{{CONFIRMATION_TOKEN}}",
                                            "idempotency_key": "{{IDEMPOTENCY_KEY}}",
                                        },
                                    }
                                ],
                                "must_not_call": [],
                            },
                        },
                    ],
                    "labels": {"category": "multi_turn", "difficulty": "medium", "turns": 4},
                    "generator": {"seed": SEED, "skeleton_id": skeleton["skeleton_id"]},
                    "notes": "驗證：只追問缺的欄位 → 補齊 → 摘要確認 → 明確同意後才可建案",
                }
            )
    return rows


import vocab  # noqa: E402  （放在 VALUE_LABELS 之前會造成循環閱讀，集中在此）

# 布林欄位不能用「X 是 有/沒有」硬接，改用完整句子
BOOLEAN_PHRASES = {
    "housekeeping.has_pets": ("家裡有養寵物", "家裡沒有養寵物"),
    "product.accept_substitutes": ("可以接受替代品", "不接受替代品"),
}

HAZARD_LABELS = {
    "electric_shock_risk": "會電到",
    "exposed_wires": "電線裸露",
    "smoke_or_burning_smell": "有冒煙或燒焦味",
    "active_flooding": "還在淹水",
    "gas_smell": "有瓦斯味",
}

# 注意：不可放入 True/False，Python 會讓 1/0 命中布林鍵，導致「數量是有」
VALUE_LABELS = {
    **{item["code"]: item["label"] for item in vocab.HOUSEKEEPING_ITEMS},
    **{issue["code"]: issue["label"] for issue in vocab.REPAIR_ISSUE_TYPES},
    **{issue["code"]: issue["label"] for issue in vocab.COMMUNITY_ISSUE_CATEGORIES},
    "one_time": "只做一次",
    "weekly": "每週一次",
    "biweekly": "兩週一次",
    "monthly": "每月一次",
    "routine": "不急",
    "soon": "這兩天",
    "urgent": "很急",
    "emergency": "非常急",
    "named": "可以具名",
    "anonymous": "希望匿名",
    "anonymous_to_neighbors": "不要讓鄰居知道",
}


def _supplement_text(skeleton, held_back: list[str]) -> str:
    pieces = [_humanize(skeleton, field) for field in held_back]
    return "喔對，" + "，".join(pieces)


def _humanize(skeleton: dict, field: str) -> str:
    """把補齊欄位講成人話，而不是把 JSON 值直接貼進句子。"""
    value = skeleton["fields"].get(field)

    if field in BOOLEAN_PHRASES:
        return BOOLEAN_PHRASES[field][0 if value else 1]

    if field.endswith("hazard_flags"):
        active = [HAZARD_LABELS[flag] for flag, on in value.items() if on]
        return "、".join(active) if active else "沒有漏電、冒煙或淹水的狀況"

    if field.endswith(("location", "delivery")):
        return f"{FIELD_LABELS[field]}是{skeleton['district']['county_name']}{skeleton['district']['name']}"

    if field.endswith("preferred_time_slots") or field.endswith("reservation_at"):
        slots = value if isinstance(value, list) else [value]
        return f"{FIELD_LABELS[field]}是{'、'.join(_readable_time(s) for s in slots)}"

    if isinstance(value, list):
        rendered = "、".join(VALUE_LABELS.get(v, str(v)) for v in value)
    else:
        rendered = VALUE_LABELS.get(value, value)
    return f"{FIELD_LABELS[field]}是{rendered}"


def _readable_time(iso_text: str) -> str:
    date_part, time_part = iso_text.split("T")
    _, month, day = date_part.split("-")
    hour = int(time_part[:2])
    period = "早上" if hour < 12 else ("下午" if hour < 18 else "晚上")
    display_hour = hour if hour <= 12 else hour - 12
    return f"{int(month)}/{int(day)} {period}{display_hour}點"


def _holdout_template() -> list[dict]:
    """人工 hold-out 的空白樣板：由團隊成員手寫，不得由生成器填。

    生成資料與評測若共用同一語言先驗，離線分數會系統性虛高，
    所以另外保留一組人寫句子當 out-of-distribution 驗收。
    """
    return [
        {
            "case_id": f"holdout-{i:03d}",
            "user_utterance": "",
            "locale": "zh-TW",
            "expected": {
                "service_type": None,
                "extracted_fields": {},
                "missing_required_fields": [],
                "next_action": None,
            },
            "labels": {"category": "holdout_human", "difficulty": None, "turns": 1},
            "author": "",
            "notes": "請由團隊成員手寫真實口語句子並自行標註；禁止用 LLM 產生或改寫",
        }
        for i in range(5)
    ]


if __name__ == "__main__":
    build()
