"""OPENPOINT 回饋點數的確定性計算規則。

主辦單位的 ``data/competition/mms_order_record.sql`` 已經定義好點數語意，這個
模組沿用同一套代碼與欄位意義，不自創第二套：

* ``final_amount``  — 實付金額，作為點數計算基礎
* ``earn_points``   — 應獲得點數，由「點數計算引擎」填入（就是這個模組）
* ``point_status``  — 01 待發放 / 02 已發放 / 03 不發放 / 04 已取消
* ``complete_time`` — 完成時間，用於判斷點數發放時機

範圍邊界：這裡只計算並揭露「應獲得點數」，狀態一律停在 ``01 待發放``。
實際發放、收回與折抵都不在這個模組，也不呼叫任何外部帳務系統。OPENPOINT 是
真實資產系統，依 ``SPEC.md`` §2.3 不得執行不可逆外部交易，因此 Demo 只在平台
內記帳並對住戶明示。

實作採整數運算：費率以萬分位（basis points）表示，避免浮點誤差讓同一筆訂單在
不同機器上算出不同點數。
"""

from __future__ import annotations

from typing import Any

from .errors import ValidationError


PROGRAM = "OPENPOINT"

# 對應 mms_order_record.point_status
STATUS_PENDING = "01"
STATUS_GRANTED = "02"
STATUS_WITHHELD = "03"
STATUS_CANCELLED = "04"

STATUS_LABELS = {
    STATUS_PENDING: "待發放",
    STATUS_GRANTED: "已發放",
    STATUS_WITHHELD: "不發放",
    STATUS_CANCELLED: "已取消",
}

# 每個服務類別的回饋費率，單位為萬分位。100 = 1%。
EARN_RATE_BASIS_POINTS: dict[str, int] = {
    "utility_repair": 100,
}
DEFAULT_EARN_RATE_BASIS_POINTS = 50

# 單筆訂單回饋上限，避免大額修繕一次給出不合理的點數。
MAX_POINTS_PER_ORDER = 500

MIN_BASIS_AMOUNT = 1
MAX_BASIS_AMOUNT = 1_000_000

# 廠商未回報金額時的類別基準金額（新台幣元）。這是平台估算值，不是報價。
BASELINE_AMOUNT_BY_ISSUE_TYPE: dict[str, int] = {
    "leak": 2800,
    "drain": 2200,
    "toilet": 2000,
    "water_heater": 4500,
    "electrical": 3200,
    "other": 2500,
}

GRANT_CONDITION = "服務完成並經住戶驗收後發放"
LEDGER_DISCLOSURE = "Demo 平台內記帳，尚未連動 OPENPOINT 正式帳戶"

AMOUNT_SOURCE_PROVIDER = "provider_reported"
AMOUNT_SOURCE_BASELINE = "issue_type_baseline"

_AMOUNT_SOURCE_LABELS = {
    AMOUNT_SOURCE_PROVIDER: "廠商回報預估金額",
    AMOUNT_SOURCE_BASELINE: "平台類別估算金額",
}


def normalize_reported_amount(value: Any) -> int | None:
    """驗證廠商回報的預估金額；``None`` 表示未提供，改用類別基準金額。

    在進入交易前呼叫，讓不合法的金額不會消耗廠商任務或推進版本。
    """

    if value is None or value == "":
        return None
    # bool 是 int 的子類別，必須先擋掉，否則 True 會被當成 1 元。
    if isinstance(value, bool):
        raise ValidationError("estimatedAmount 必須是新台幣整數金額")
    if isinstance(value, int):
        amount = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValidationError("estimatedAmount 必須是新台幣整數金額")
        amount = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        amount = int(value.strip())
    else:
        raise ValidationError("estimatedAmount 必須是新台幣整數金額")
    if amount < MIN_BASIS_AMOUNT or amount > MAX_BASIS_AMOUNT:
        raise ValidationError(
            f"estimatedAmount 必須介於 {MIN_BASIS_AMOUNT} 與 {MAX_BASIS_AMOUNT} 之間"
        )
    return amount


def earn_rate_basis_points(service_type: str) -> int:
    return EARN_RATE_BASIS_POINTS.get(service_type, DEFAULT_EARN_RATE_BASIS_POINTS)


def resolve_basis_amount(
    *, issue_type: str, reported_amount: int | None
) -> tuple[int, str]:
    if reported_amount is not None:
        return reported_amount, AMOUNT_SOURCE_PROVIDER
    baseline = BASELINE_AMOUNT_BY_ISSUE_TYPE.get(
        issue_type, BASELINE_AMOUNT_BY_ISSUE_TYPE["other"]
    )
    return baseline, AMOUNT_SOURCE_BASELINE


def calculate_points(basis_amount: int, rate_basis_points: int) -> int:
    """向下取整的整數運算，並套用單筆上限。"""

    raw = basis_amount * rate_basis_points // 10_000
    return min(raw, MAX_POINTS_PER_ORDER)


def format_rate(rate_basis_points: int) -> str:
    percent = rate_basis_points / 100
    if percent.is_integer():
        return f"{int(percent)}%"
    return f"{percent:g}%"


def format_amount(amount: int) -> str:
    return f"NT${amount:,}"


def estimate_reward(
    *,
    service_type: str,
    issue_type: str,
    reported_amount: int | None,
    estimated_at: str,
) -> dict[str, Any]:
    """產生訂單成立時揭露給住戶的預計回饋點數投影。"""

    rate_basis_points = earn_rate_basis_points(service_type)
    basis_amount, amount_source = resolve_basis_amount(
        issue_type=issue_type, reported_amount=reported_amount
    )
    estimated_points = calculate_points(basis_amount, rate_basis_points)
    uncapped = basis_amount * rate_basis_points // 10_000
    return {
        "program": PROGRAM,
        "status": STATUS_PENDING,
        "statusLabel": STATUS_LABELS[STATUS_PENDING],
        "estimatedPoints": estimated_points,
        "earnRate": format_rate(rate_basis_points),
        "earnRateBasisPoints": rate_basis_points,
        "basisAmount": basis_amount,
        "amountSource": amount_source,
        "amountSourceLabel": _AMOUNT_SOURCE_LABELS[amount_source],
        "capped": uncapped > MAX_POINTS_PER_ORDER,
        "maxPointsPerOrder": MAX_POINTS_PER_ORDER,
        "grantCondition": GRANT_CONDITION,
        "isDemoLedger": True,
        "disclosure": LEDGER_DISCLOSURE,
        "estimatedAt": estimated_at,
    }


def reward_disclosure_sentence(reward: dict[str, Any]) -> str:
    """住戶在對話中看到的揭露句；金額來源與 Demo 邊界都要講清楚。"""

    basis = (
        f"以{reward['amountSourceLabel']} {format_amount(reward['basisAmount'])}"
        f" × {reward['earnRate']} 計算"
    )
    capped = (
        f"（已套用單筆上限 {reward['maxPointsPerOrder']} 點）" if reward["capped"] else ""
    )
    return (
        f"{reward['grantCondition']}，預計回饋 {reward['estimatedPoints']} 點 "
        f"{reward['program']}{capped}：{basis}。"
        f"目前狀態為「{reward['statusLabel']}」，{reward['disclosure']}。"
    )
