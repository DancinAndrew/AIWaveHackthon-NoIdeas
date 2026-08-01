"""記憶體版資料層。

程序重啟資料就消失，只用於本地開發 / demo 前的流程驗證。
Flask debug reloader 會重新 import module，所以資料存在 module 級變數即可。
"""

from __future__ import annotations

import copy

from ..domain import (
    Booking,
    ChatSession,
    MatchResult,
    ServiceRequest,
    UserPreferences,
    UserProfile,
    Vendor,
)
from ..seed import SEED_USERS, SEED_VENDORS
from .base import merge_prefs, vendor_covers


class MemoryRepo:
    def __init__(self) -> None:
        self._users: dict[str, UserProfile] = {
            u["inbrAccountId"]: copy.deepcopy(u) for u in SEED_USERS
        }
        self._vendors: dict[str, Vendor] = {
            v["vendorId"]: copy.deepcopy(v) for v in SEED_VENDORS
        }
        self._requests: dict[str, ServiceRequest] = {}
        self._matches: dict[str, MatchResult] = {}
        self._bookings: dict[str, Booking] = {}
        self._sessions: dict[str, ChatSession] = {}

    # ---- 會員 ----
    def get_user(self, inbr_account_id: str) -> UserProfile | None:
        return self._users.get(inbr_account_id)

    def put_user(self, user: UserProfile) -> None:
        self._users[user["inbrAccountId"]] = user

    def merge_preferences(self, inbr_account_id: str, patch: UserPreferences) -> UserPreferences:
        user = self._users.get(inbr_account_id)
        if user is None:
            raise KeyError(f"user not found: {inbr_account_id}")
        user["preferences"] = merge_prefs(user.get("preferences", {}), patch)
        return user["preferences"]

    # ---- 廠商 ----
    def list_vendors(
        self,
        *,
        category: str | None = None,
        county_code: str | None = None,
        district_code: str | None = None,
    ) -> list[Vendor]:
        items = list(self._vendors.values())
        if category:
            items = [v for v in items if category in v.get("categories", [])]
        if county_code:
            items = [v for v in items if vendor_covers(v, county_code, district_code)]
        return items

    def get_vendor(self, vendor_id: str) -> Vendor | None:
        return self._vendors.get(vendor_id)

    def put_vendor(self, vendor: Vendor) -> None:
        self._vendors[vendor["vendorId"]] = vendor

    # ---- 服務單 ----
    def get_request(self, request_id: str) -> ServiceRequest | None:
        return self._requests.get(request_id)

    def put_request(self, req: ServiceRequest) -> None:
        self._requests[req["requestId"]] = req

    def list_requests_by_user(self, inbr_account_id: str) -> list[ServiceRequest]:
        return [r for r in self._requests.values() if r["inbrAccountId"] == inbr_account_id]

    # ---- 媒合結果 ----
    def put_match(self, match: MatchResult) -> None:
        self._matches[match["requestId"]] = match

    def get_match(self, request_id: str) -> MatchResult | None:
        return self._matches.get(request_id)

    # ---- 預約單 ----
    def put_booking(self, booking: Booking) -> None:
        self._bookings[booking["orderNo"]] = booking

    def get_booking(self, order_no: str) -> Booking | None:
        return self._bookings.get(order_no)

    def list_bookings_by_user(self, inbr_account_id: str) -> list[Booking]:
        return [b for b in self._bookings.values() if b["inbrAccountId"] == inbr_account_id]

    # ---- 對話 ----
    def get_session(self, session_id: str) -> ChatSession | None:
        return self._sessions.get(session_id)

    def put_session(self, session: ChatSession) -> None:
        self._sessions[session["sessionId"]] = session
