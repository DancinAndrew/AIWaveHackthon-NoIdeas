"""DynamoDB single-table 實作。

| 實體      | PK                  | SK      | GSI1PK      | GSI1SK              |
|-----------|---------------------|---------|-------------|---------------------|
| 會員      | USER#<accountId>    | PROFILE | -           | -                   |
| 廠商      | VENDOR#<vendorId>   | META    | VENDOR      | <vendorId>          |
| 服務單    | REQ#<requestId>     | META    | USER#<acc>  | REQ#<createdAt>     |
| 媒合結果  | REQ#<requestId>     | MATCH   | -           | -                   |
| 預約單    | BOOKING#<orderNo>   | META    | USER#<acc>  | BOOKING#<createdAt> |
| 對話      | SESSION#<sessionId> | META    | -           | -                   |

DynamoDB 不吃 float，所以寫入前把 float 轉 Decimal、讀出時轉回去。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from ..config import config
from ..domain import (
    Booking,
    ChatSession,
    MatchResult,
    ServiceRequest,
    UserPreferences,
    UserProfile,
    Vendor,
)
from .base import merge_prefs, vendor_covers

GSI1 = "GSI1"


def _to_dynamo(value: Any) -> Any:
    """float -> Decimal，並丟掉 None（DynamoDB 可存 null 但這裡簡化資料）。"""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_dynamo(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_to_dynamo(v) for v in value]
    return value


def _from_dynamo(value: Any) -> Any:
    """Decimal -> int/float。"""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_dynamo(v) for v in value]
    return value


class DynamoRepo:
    def __init__(self) -> None:
        self._table = boto3.resource("dynamodb", region_name=config.region).Table(
            config.table_name
        )

    # ---- 低階讀寫 ----
    def _get(self, pk: str, sk: str) -> Any | None:
        res = self._table.get_item(Key={"PK": pk, "SK": sk})
        item = res.get("Item")
        return _from_dynamo(item["data"]) if item else None

    def _put(
        self, pk: str, sk: str, data: Any, gsi1pk: str | None = None, gsi1sk: str | None = None
    ) -> None:
        item: dict[str, Any] = {"PK": pk, "SK": sk, "data": _to_dynamo(data)}
        if gsi1pk and gsi1sk:
            item["GSI1PK"] = gsi1pk
            item["GSI1SK"] = gsi1sk
        self._table.put_item(Item=item)

    def _query_gsi1(self, pk: str, sk_prefix: str | None = None) -> list[Any]:
        cond = Key("GSI1PK").eq(pk)
        if sk_prefix:
            cond = cond & Key("GSI1SK").begins_with(sk_prefix)
        items: list[Any] = []
        kwargs: dict[str, Any] = {"IndexName": GSI1, "KeyConditionExpression": cond}
        while True:
            res = self._table.query(**kwargs)
            items.extend(_from_dynamo(i["data"]) for i in res.get("Items", []))
            key = res.get("LastEvaluatedKey")
            if not key:
                return items
            kwargs["ExclusiveStartKey"] = key

    # ---- 會員 ----
    def get_user(self, inbr_account_id: str) -> UserProfile | None:
        return self._get(f"USER#{inbr_account_id}", "PROFILE")

    def put_user(self, user: UserProfile) -> None:
        self._put(f"USER#{user['inbrAccountId']}", "PROFILE", user)

    def merge_preferences(self, inbr_account_id: str, patch: UserPreferences) -> UserPreferences:
        user = self.get_user(inbr_account_id)
        if user is None:
            raise KeyError(f"user not found: {inbr_account_id}")
        user["preferences"] = merge_prefs(user.get("preferences", {}), patch)
        self.put_user(user)
        return user["preferences"]

    # ---- 廠商 ----
    def list_vendors(
        self,
        *,
        category: str | None = None,
        county_code: str | None = None,
        district_code: str | None = None,
    ) -> list[Vendor]:
        items: list[Vendor] = self._query_gsi1("VENDOR")
        if category:
            items = [v for v in items if category in v.get("categories", [])]
        if county_code:
            items = [v for v in items if vendor_covers(v, county_code, district_code)]
        return items

    def get_vendor(self, vendor_id: str) -> Vendor | None:
        return self._get(f"VENDOR#{vendor_id}", "META")

    def put_vendor(self, vendor: Vendor) -> None:
        self._put(f"VENDOR#{vendor['vendorId']}", "META", vendor, "VENDOR", vendor["vendorId"])

    # ---- 服務單 ----
    def get_request(self, request_id: str) -> ServiceRequest | None:
        return self._get(f"REQ#{request_id}", "META")

    def put_request(self, req: ServiceRequest) -> None:
        self._put(
            f"REQ#{req['requestId']}",
            "META",
            req,
            f"USER#{req['inbrAccountId']}",
            f"REQ#{req['createdAt']}",
        )

    def list_requests_by_user(self, inbr_account_id: str) -> list[ServiceRequest]:
        return self._query_gsi1(f"USER#{inbr_account_id}", "REQ#")

    # ---- 媒合結果 ----
    def put_match(self, match: MatchResult) -> None:
        self._put(f"REQ#{match['requestId']}", "MATCH", match)

    def get_match(self, request_id: str) -> MatchResult | None:
        return self._get(f"REQ#{request_id}", "MATCH")

    # ---- 預約單 ----
    def put_booking(self, booking: Booking) -> None:
        self._put(
            f"BOOKING#{booking['orderNo']}",
            "META",
            booking,
            f"USER#{booking['inbrAccountId']}",
            f"BOOKING#{booking['createdAt']}",
        )

    def get_booking(self, order_no: str) -> Booking | None:
        return self._get(f"BOOKING#{order_no}", "META")

    def list_bookings_by_user(self, inbr_account_id: str) -> list[Booking]:
        return self._query_gsi1(f"USER#{inbr_account_id}", "BOOKING#")

    # ---- 對話 ----
    def get_session(self, session_id: str) -> ChatSession | None:
        return self._get(f"SESSION#{session_id}", "META")

    def put_session(self, session: ChatSession) -> None:
        self._put(f"SESSION#{session['sessionId']}", "META", session)
