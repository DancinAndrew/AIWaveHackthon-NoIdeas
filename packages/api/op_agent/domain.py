"""Domain 型別定義。

命名盡量對齊統一資訊提供的資料集，方便後續換成真實 Postgres：
  - inbrAccountId    <-> mms_order_record.inbr_account_id / pms_form_feedback.inbr_account_id
  - countyCode / districtCode <-> 縣市區域檔（2 碼 / 3 碼）
  - serviceVendorId  <-> cms_homepage_service_vendor.id（11 = 修繕服務）
  - orderStatus      <-> mms_order_record.order_status（服務訂單流程）

注意：dict 的 key 刻意用 camelCase。
這些 dict 會直接 json.dumps 回給 React 前端，維持單一 wire format，
省掉 snake_case <-> camelCase 的轉換層與它會帶來的 bug。
"""

from __future__ import annotations

from typing import Literal, TypedDict

# 服務類別：先只做冷氣維修，之後可擴充
ServiceCategory = Literal["AC_REPAIR", "AC_CLEAN", "PLUMBING", "HOME_CLEAN"]

# 對應 cms_homepage_service_vendor.id
SERVICE_VENDOR_ID: dict[str, int] = {
    "AC_REPAIR": 11,
    "AC_CLEAN": 1,
    "PLUMBING": 11,
    "HOME_CLEAN": 1,
}

# 對應 pms_form_feedback.preferred_contact_time：1 上午 / 2 下午 / 3 皆可
PreferredContactTime = Literal["1", "2", "3"]

PERIOD_LABEL: dict[str, str] = {"1": "上午", "2": "下午", "3": "皆可"}

# 服務單狀態
ServiceRequestStatus = Literal[
    "COLLECTING",  # agent 還在問問題
    "READY_TO_MATCH",  # 資訊齊全，可媒合
    "MATCHING",  # 媒合中
    "MATCHED",  # 已有候選廠商
    "BOOKED",  # 已成立預約單
    "CANCELLED",
]

# 對齊 mms_order_record.order_status（服務訂單）
# 11 待訂金支付 / 12 已支付訂金待報價 / 13 已報價待客戶同意
# 14 客戶同意報價 / 15 已驗收待尾款 / 80 已完成 / 90 已取消
OrderStatus = Literal["11", "12", "13", "14", "15", "80", "90"]


class Address(TypedDict, total=False):
    countyCode: str  # '01'
    countyName: str  # '台北市'
    districtCode: str  # '002'
    districtName: str  # '大同區'
    detail: str


class Appliance(TypedDict, total=False):
    applianceId: str
    kind: Literal["AC", "WASHER", "FRIDGE", "WATER_HEATER"]
    brand: str
    model: str
    variant: str  # 分離式 / 窗型 / 吊隱式
    installedYear: int
    location: str  # '主臥' / '客廳'


class UserPreferences(TypedDict, total=False):
    """會員偏好：這是「之後能自動推播喜歡內容」的核心資產。"""

    priceSensitivity: float  # 0(不在意) ~ 1(非常在意)
    preferredContactTime: PreferredContactTime
    preferredVendorTags: list[str]  # '女性技師' / '原廠零件' / '當日到府'
    blockedVendorIds: list[str]
    interestedCategories: list[str]  # 推播依據
    notes: list[str]  # agent 觀察到的長期偏好


class UserProfile(TypedDict, total=False):
    inbrAccountId: str
    displayName: str
    mobile: str  # demo 用途，正式環境需 aes256-gcm 加密（見 pms_form_feedback 做法）
    email: str
    addresses: list[Address]
    appliances: list[Appliance]
    preferences: UserPreferences
    points: int


class VendorCoverage(TypedDict):
    countyCode: str
    districtCodes: list[str] | Literal["ALL"]


class PricingItem(TypedDict, total=False):
    code: str
    name: str
    minPrice: int
    maxPrice: int
    unit: str


class VendorPricing(TypedDict):
    inspectionFee: int  # 基本到府檢測費
    items: list[PricingItem]


class Vendor(TypedDict, total=False):
    vendorId: str
    name: str
    serviceVendorId: int
    categories: list[str]
    coverage: list[VendorCoverage]
    rating: float  # 0~5
    reviewCount: int
    completedJobs: int
    avgResponseMinutes: int
    earliestAvailableInDays: int
    availableSlots: list[str]
    tags: list[str]
    pricing: VendorPricing
    certifications: list[str]
    supportsPoints: bool


class AcRepairSlots(TypedDict, total=False):
    """冷氣維修的槽位（slot filling 目標）。"""

    symptoms: list[str]  # 不冷 / 漏水 / 異音 / 不啟動 / 跳電 / 遙控無反應
    variant: str  # 分離式 / 窗型 / 吊隱式
    brand: str
    ageYears: int
    description: str  # 使用者原話，保留給廠商看
    selfTried: str
    photoUrls: list[str]


class ServiceRequest(TypedDict, total=False):
    requestId: str
    inbrAccountId: str
    category: str
    status: str
    slots: AcRepairSlots
    address: Address
    preferredContactTime: PreferredContactTime
    preferredServiceDate: str  # ISO date
    budgetMax: int
    createdAt: str
    updatedAt: str


class MajorRisk(TypedDict):
    """大額風險項目，不含在 estimatedMax 內，需獨立揭露。"""

    code: str
    name: str
    minPrice: int
    maxPrice: int


class Quote(TypedDict, total=False):
    inspectionFee: int
    estimatedMin: int
    estimatedMax: int
    currency: str
    assumptions: list[str]  # 報價假設，例如「若現場判定需更換壓縮機另計」
    majorRisks: list[MajorRisk]


class EarliestSlot(TypedDict):
    date: str
    period: str


class VendorProposal(TypedDict, total=False):
    """媒合 agent 產出的單一廠商方案。"""

    vendorId: str
    vendorName: str
    rating: float
    tags: list[str]
    score: int  # 綜合分數 0~100
    reasons: list[str]  # 為什麼推薦（給 user agent 轉述）
    quote: Quote
    earliestSlot: EarliestSlot
    supportsPoints: bool


class MatchResult(TypedDict, total=False):
    requestId: str
    matchedAt: str
    proposals: list[VendorProposal]  # 由高到低排序
    summary: str  # 媒合 agent 的總結說明
    recommendedVendorId: str
    # 產生這份結果時服務單的指紋，用來判斷是否需要重新媒合
    requestFingerprint: str


class Booking(TypedDict, total=False):
    orderNo: str
    requestId: str
    inbrAccountId: str
    vendorId: str
    vendorName: str
    serviceVendorId: int
    orderType: str  # '01' 服務訂單
    orderStatus: str
    serviceDate: str
    servicePeriod: str
    address: Address
    depositAmount: int
    estimatedMin: int
    estimatedMax: int
    createdAt: str


class ChatMessage(TypedDict):
    role: Literal["user", "assistant"]
    text: str
    at: str


class ChatSession(TypedDict, total=False):
    sessionId: str
    inbrAccountId: str
    messages: list[ChatMessage]
    activeRequestId: str
    updatedAt: str


class AgentTraceEntry(TypedDict):
    """agent 這一輪做了哪些動作，前端可以做成 timeline。"""

    agent: Literal["user-agent", "match-agent"]
    tool: str
    input: object
    output: object
    at: str


class ChatTurnResult(TypedDict, total=False):
    """前端每次 /chat 拿到的完整畫面狀態。"""

    sessionId: str
    reply: str
    request: ServiceRequest | None
    match: MatchResult | None
    booking: Booking | None
    preferences: UserPreferences
    trace: list[AgentTraceEntry]
