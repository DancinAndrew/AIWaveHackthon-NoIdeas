"""ID 與時間工具。"""

from __future__ import annotations

import random
import uuid
from datetime import date, datetime, timedelta, timezone


def new_session_id() -> str:
    return str(uuid.uuid4())


def new_request_id() -> str:
    stamp = format(int(datetime.now(timezone.utc).timestamp() * 1000), "x").upper()
    return f"SR{stamp}{random.randint(100, 999)}"


def new_order_no() -> str:
    """訂單編號：對齊 mms_order_record.order_no 的可讀格式（YYMMDD + 6 碼流水）。"""
    d = date.today()
    return f"{d.year % 100:02d}{d.month:02d}{d.day:02d}{random.randint(0, 999999):06d}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso_date_plus(days: int) -> str:
    """回傳 n 天後的 YYYY-MM-DD。"""
    return (date.today() + timedelta(days=days)).isoformat()


def today_iso() -> str:
    return date.today().isoformat()
