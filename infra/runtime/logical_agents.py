"""The five logical domain agents hosted inside one AgentCore Runtime.

Each agent carries its own routing keywords, required fields, MCP tool
allowlist, model instructions and closed extraction schema.  Only
``utility_repair`` has a model extraction schema in this increment; the other
four keep their deterministic contract until their domain lands, and the runtime
reports that honestly instead of pretending a model produced the turn.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

UTILITY_ISSUE_TYPES = (
    "electrical",
    "toilet",
    "drain",
    "water_heater",
    "leak",
    "other",
)
URGENCY_LEVELS = ("routine", "soon", "urgent", "emergency")
HAZARD_FLAG_KEYS = (
    "electricShockRisk",
    "exposedWires",
    "smokeOrBurningSmell",
    "activeFlooding",
)

# Field name used by Flask -> key produced by the model extraction schema.
FIELD_ALIASES: dict[str, str] = {
    "riskScreening": "riskScreenAnswered",
    "district": "districtName",
    "preferredTime": "preferredTime",
    "issueType": "issueType",
    "urgency": "urgency",
}

UTILITY_REPAIR_EXTRACTED_FIELDS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "issueType": {
            "type": "string",
            "enum": list(UTILITY_ISSUE_TYPES),
            "description": "問題類型；無法判斷時省略此欄位。",
        },
        "districtName": {
            "type": "string",
            "description": (
                "住戶說出的行政區完整名稱，例如「內湖區」「板橋區」。"
                "只在住戶明確提到地區時填入，不要推測；不要填入詳細門牌。"
            ),
        },
        "areaOutOfScope": {
            "type": "boolean",
            "description": (
                "住戶已給出地區，但該地區不在提供的示範服務範圍清單內時設為 true。"
            ),
        },
        "preferredTime": {
            "type": "string",
            "description": (
                "住戶希望廠商到場的日期與時段，保留住戶原本說法，"
                "例如「禮拜六白天」「明天下午兩點到五點」。"
            ),
        },
        "urgency": {
            "type": "string",
            "enum": list(URGENCY_LEVELS),
            "description": "由住戶描述判斷的急迫程度。",
        },
        "riskScreenAnswered": {
            "type": "boolean",
            "description": (
                "住戶已明確回答安全篩檢問題（漏電、裸線、冒煙焦味、大量積水）時設為 true。"
            ),
        },
        "hazardFlags": {
            "type": "object",
            "properties": {key: {"type": "boolean"} for key in HAZARD_FLAG_KEYS},
            "required": list(HAZARD_FLAG_KEYS),
            "description": "四項危險徵兆的判斷；要填就必須四項都填。",
        },
        "confirmsBrief": {
            "type": "boolean",
            "description": "住戶對目前版本的需求文件表示明確確認時設為 true。",
        },
        "observedPreference": {
            "type": "object",
            "description": (
                "住戶自然聊出來的長期偏好。只在住戶真的表達了才填，不要為了記錄而追問。"
                "只會做欄位層合併，不會覆蓋其他既有偏好。"
            ),
            "properties": {
                "priceSensitivity": {
                    "type": "number",
                    "description": "價格敏感度 0~1；住戶明顯在意價格時給 0.8 以上。",
                },
                "preferredContactTime": {
                    "type": "string",
                    "enum": ["1", "2", "3"],
                    "description": "1 上午 2 下午 3 皆可。",
                },
                "preferredVendorTags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": '例如 ["原廠零件", "當日到府"]。',
                },
                "blockedVendorIds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "住戶明確表示不要的廠商 ID。",
                },
                "note": {
                    "type": "string",
                    "description": "一句話描述觀察到的偏好，不得包含姓名、電話或地址。",
                },
            },
        },
    },
}

UTILITY_REPAIR_INSTRUCTIONS = (
    "你是台灣社區生活管家平台的水電修繕領域 Agent，使用繁體中文與住戶對話。\n"
    "你的任務只有兩件：一是從住戶訊息抽取結構化欄位，二是針對『本輪待補欄位』的"
    "第一項提出一個簡短、具體的問題。\n"
    "規則：\n"
    "1. 一次只問一件事，句子不超過兩句，語氣自然、不用敬語堆疊。\n"
    "2. 不要重複詢問『目前已知欄位』裡已經有值的項目。\n"
    "3. 住戶用口語說法（例如「禮拜六白天」「板橋」）也要抽取，不要因為格式不標準就當作沒說。\n"
    "4. 只在住戶明確提到地區時填 districtName；若該地區不在示範服務範圍清單內，"
    "同時把 areaOutOfScope 設為 true，並在回覆中誠實說明目前服務範圍。\n"
    "5. 不要索取姓名、電話、Email 或詳細門牌，這些由表單流程處理。\n"
    "6. 不要提供自行拆修的操作步驟，也不要承諾價格、到場時間、庫存或廠商可用時段；"
    "這些一律由平台的結構化工具決定。\n"
    "7. 若住戶描述出現漏電、裸線、冒煙焦味、觸電感或大量積水，把 riskLevel 設為 high。\n"
    "8. 只能透過提供的工具輸出結果，不要輸出工具以外的文字。\n"
)

GENERIC_DOMAIN_INSTRUCTIONS = (
    "你是台灣社區生活管家平台的領域 Agent，使用繁體中文與住戶對話，"
    "一次只詢問一項缺少的欄位，不承諾價格、庫存或到場時間。"
)


@dataclass(frozen=True, slots=True)
class LogicalAgent:
    """In-process domain agent exposed to the Supervisor as a typed tool."""

    name: str
    service_type: str
    keywords: tuple[str, ...]
    assistant_message: str
    required_fields: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    instructions: str = GENERIC_DOMAIN_INSTRUCTIONS
    extracted_fields_schema: dict[str, Any] | None = None

    @property
    def supports_model_extraction(self) -> bool:
        return self.extracted_fields_schema is not None


LOGICAL_AGENT_REGISTRY: dict[str, LogicalAgent] = {
    "restaurant_agent": LogicalAgent(
        name="restaurant_agent",
        service_type="restaurant_reservation",
        keywords=("餐廳", "訂位", "訂桌", "用餐", "聚餐"),
        assistant_message=(
            "我已接手餐廳訂位需求。請先告訴我日期、時段、人數與偏好的地區或料理。"
        ),
        required_fields=("date", "timeWindow", "partySize", "area", "cuisine"),
        allowed_tools=("knowledge_base_search", "service_request"),
    ),
    "product_agent": LogicalAgent(
        name="product_agent",
        service_type="product_purchase",
        keywords=("購買", "買", "商品", "下單", "餐券", "採買"),
        assistant_message=(
            "我已接手商品購買需求。請告訴我商品、數量、預算與希望收到的時間。"
        ),
        required_fields=("product", "quantity", "budget", "deliveryWindow"),
        allowed_tools=("knowledge_base_search", "service_request"),
    ),
    "housekeeping_agent": LogicalAgent(
        name="housekeeping_agent",
        service_type="housekeeping_service",
        keywords=("家事", "打掃", "清潔", "居家整理", "收納"),
        assistant_message=(
            "我已接手家事服務需求。請告訴我服務地區、空間大小、項目與希望時段。"
        ),
        required_fields=("district", "spaceSize", "tasks", "preferredTime"),
        allowed_tools=("knowledge_base_search", "service_request"),
    ),
    "utility_repair_agent": LogicalAgent(
        name="utility_repair_agent",
        service_type="utility_repair",
        keywords=(
            "水電",
            "水管",
            "漏水",
            "水龍頭",
            "馬桶",
            "排水",
            "插座",
            "跳電",
            "電線",
            "冒煙",
            "火花",
            "熱水器",
        ),
        assistant_message=(
            "我已接手水電修繕需求。先確認安全：現場是否有漏電、裸線、冒煙焦味，"
            "或水已接近插座、形成大量積水？"
        ),
        required_fields=(
            "riskScreening",
            "issueType",
            "symptoms",
            "district",
            "preferredTime",
        ),
        allowed_tools=(
            "knowledge_base_search",
            "service_request",
            "provider_matching",
        ),
        instructions=UTILITY_REPAIR_INSTRUCTIONS,
        extracted_fields_schema=UTILITY_REPAIR_EXTRACTED_FIELDS_SCHEMA,
    ),
    "community_service_agent": LogicalAgent(
        name="community_service_agent",
        service_type="community_consultation",
        keywords=("社區", "管委會", "規約", "管理費", "公設", "管理中心"),
        assistant_message=(
            "我已接手社區服務諮詢。請告訴我想詢問的主題、社區範圍與希望處理的期限。"
        ),
        required_fields=("topic", "communityScope", "desiredResolutionDate"),
        allowed_tools=("knowledge_base_search", "service_request"),
    ),
}
