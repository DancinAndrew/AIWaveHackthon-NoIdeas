"""端到端煙霧測試：不開 HTTP，直接跑多輪對話。

驗證 slot filling -> 媒合代理 -> 報價 -> 建立預約單 -> 偏好記錄 都真的會發生。

執行（從 repo 根目錄）：
    .venv\\Scripts\\python.exe packages\\api\\scripts\\smoke.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from op_agent.domain import PERIOD_LABEL  # noqa: E402
from op_agent.seed import DEMO_USER_ID  # noqa: E402
from op_agent.user_agent import run_user_agent_turn  # noqa: E402

TURNS = [
    "我家冷氣不冷了，主臥那台",
    "台北市大安區復興南路一段100號5樓，下午方便",
    "預算不要太高，幫我看有哪些選擇",
    "那就約冷研家電",
]


def main() -> int:
    session_id: str | None = None

    for i, message in enumerate(TURNS, start=1):
        print("\n" + "=" * 72)
        print(f"[第 {i} 輪] 會員：{message}")
        print("=" * 72)

        started = time.monotonic()
        try:
            r = run_user_agent_turn(
                session_id=session_id, inbr_account_id=DEMO_USER_ID, message=message
            )
        except Exception as err:  # noqa: BLE001
            print(f"  !! 失敗：{type(err).__name__}: {err}")
            return 1

        session_id = r["sessionId"]

        for t in r.get("trace", []):
            print(f"  · [{t['agent']}] {t['tool']}")

        print(f"\n管家：{r['reply']}\n")

        req = r.get("request")
        if req:
            addr = req.get("address")
            print(
                f"  服務單 {req['requestId']}  狀態={req.get('status')}"
                f"  症狀={'/'.join(req.get('slots', {}).get('symptoms') or []) or '-'}"
                f"  地址={(addr.get('countyName', '') + addr.get('districtName', '')) if addr else '-'}"
                f"  時段={PERIOD_LABEL.get(req.get('preferredContactTime', ''), '-')}"
            )

        match = r.get("match")
        if match:
            print(f"  媒合結果（{len(match.get('proposals', []))} 家）：")
            for p in match.get("proposals", []):
                q = p["quote"]
                print(
                    f"    - {p['vendorName']}  分數 {p['score']}"
                    f"  {q['estimatedMin']}~{q['estimatedMax']} 元"
                    f"  最快 {p['earliestSlot']['date']}"
                )
            print(f"  媒合總結：{match.get('summary')}")

        booking = r.get("booking")
        if booking:
            print(
                f"  預約單 {booking['orderNo']}  {booking['vendorName']}"
                f"  {booking['serviceDate']} {PERIOD_LABEL.get(booking['servicePeriod'], '')}"
                f"  訂金 {booking['depositAmount']} 元  狀態 {booking['orderStatus']}"
            )

        print(f"  偏好：{r.get('preferences')}")
        print(f"  ({int((time.monotonic() - started) * 1000)}ms)")

    print("\n煙霧測試結束")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
