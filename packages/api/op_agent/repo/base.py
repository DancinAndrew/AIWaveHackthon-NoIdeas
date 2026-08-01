"""Repo 介面與共用邏輯。"""

from __future__ import annotations

from typing import Protocol

from ..domain import (
    Booking,
    ChatSession,
    MatchResult,
    ServiceRequest,
    UserPreferences,
    UserProfile,
    Vendor,
)


class Repo(Protocol):
    # ---- 會員 ----
    def get_user(self, inbr_account_id: str) -> UserProfile | None: ...
    def put_user(self, user: UserProfile) -> None: ...
    def merge_preferences(
        self, inbr_account_id: str, patch: UserPreferences
    ) -> UserPreferences: ...

    # ---- 廠商 ----
    def list_vendors(
        self,
        *,
        category: str | None = None,
        county_code: str | None = None,
        district_code: str | None = None,
    ) -> list[Vendor]: ...
    def get_vendor(self, vendor_id: str) -> Vendor | None: ...
    def put_vendor(self, vendor: Vendor) -> None: ...

    # ---- 服務單 ----
    def get_request(self, request_id: str) -> ServiceRequest | None: ...
    def put_request(self, req: ServiceRequest) -> None: ...
    def list_requests_by_user(self, inbr_account_id: str) -> list[ServiceRequest]: ...

    # ---- 媒合結果 ----
    def put_match(self, match: MatchResult) -> None: ...
    def get_match(self, request_id: str) -> MatchResult | None: ...

    # ---- 預約單 ----
    def put_booking(self, booking: Booking) -> None: ...
    def get_booking(self, order_no: str) -> Booking | None: ...
    def list_bookings_by_user(self, inbr_account_id: str) -> list[Booking]: ...

    # ---- 對話 ----
    def get_session(self, session_id: str) -> ChatSession | None: ...
    def put_session(self, session: ChatSession) -> None: ...


def vendor_covers(vendor: Vendor, county_code: str, district_code: str | None = None) -> bool:
    """判斷廠商是否服務該縣市／行政區。"""
    for cov in vendor.get("coverage", []):
        if cov["countyCode"] != county_code:
            continue
        codes = cov["districtCodes"]
        if codes == "ALL":
            return True
        if district_code is None:
            return True
        return district_code in codes
    return False


def merge_prefs(base: UserPreferences, patch: UserPreferences) -> UserPreferences:
    """偏好合併規則：陣列做去重聯集、數值直接覆寫、notes 累加後只留最近 20 筆。"""

    def uniq(a: list | None, b: list | None) -> list:
        out: list = []
        for item in (a or []) + (b or []):
            if item not in out:
                out.append(item)
        return out

    merged: UserPreferences = {
        "preferredVendorTags": uniq(
            base.get("preferredVendorTags"), patch.get("preferredVendorTags")
        ),
        "blockedVendorIds": uniq(base.get("blockedVendorIds"), patch.get("blockedVendorIds")),
        "interestedCategories": uniq(
            base.get("interestedCategories"), patch.get("interestedCategories")
        ),
        "notes": uniq(base.get("notes"), patch.get("notes"))[-20:],
    }
    price = patch.get("priceSensitivity", base.get("priceSensitivity"))
    if price is not None:
        merged["priceSensitivity"] = price
    period = patch.get("preferredContactTime", base.get("preferredContactTime"))
    if period is not None:
        merged["preferredContactTime"] = period
    return merged
