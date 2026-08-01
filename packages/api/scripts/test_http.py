"""用 Flask test client 驗證 HTTP 層（路由、CORS、JSON 序列化）。

不需要真的開 port，但走的是跟正式一樣的 Flask 請求流程。

執行（從 repo 根目錄）：
    .venv\\Scripts\\python.exe packages\\api\\scripts\\test_http.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def main() -> int:
    client = app.test_client()

    print("\n--- GET / (可視化控制台) ---")
    res = client.get("/")
    html = res.get_data(as_text=True)
    check("狀態碼 200", res.status_code == 200, str(res.status_code))
    check("是 HTML", "text/html" in res.headers.get("Content-Type", ""))
    check("有掛上 /chat 呼叫", "/chat" in html)
    check("有服務單面板", "slot filling" in html)
    check("有 Agent 動作紀錄面板", "Agent 動作紀錄" in html)

    print("\n--- GET /health ---")
    res = client.get("/health")
    body = res.get_json()
    check("狀態碼 200", res.status_code == 200, str(res.status_code))
    check("ok=True", body.get("ok") is True)
    check("有回報 model", bool(body.get("model")), body.get("model", ""))
    check(
        "媒合傳輸方式為 in-process",
        body.get("matchTransport") == "in-process",
        str(body.get("matchTransport")),
    )

    print("\n--- GET /context ---")
    res = client.get("/context")
    body = res.get_json()
    check("狀態碼 200", res.status_code == 200, str(res.status_code))
    check("有會員資料", bool(body.get("user", {}).get("displayName")), body.get("user", {}).get("displayName", ""))
    check("有兩個地址", len(body.get("user", {}).get("addresses", [])) == 2)
    check("有建議話術", len(body.get("suggestedPrompts", [])) >= 3)
    check(
        "中文沒有被轉成 unicode escape",
        "陳小美" in res.get_data(as_text=True),
    )

    print("\n--- GET /context 不存在的會員 ---")
    res = client.get("/context?inbrAccountId=not-a-real-user")
    check("狀態碼 404", res.status_code == 404, str(res.status_code))

    print("\n--- POST /chat 缺 message ---")
    res = client.post("/chat", json={})
    check("狀態碼 400", res.status_code == 400, str(res.status_code))

    print("\n--- OPTIONS /chat (CORS preflight) ---")
    res = client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    check("狀態碼 200/204", res.status_code in (200, 204), str(res.status_code))
    check(
        "有 Access-Control-Allow-Origin",
        "Access-Control-Allow-Origin" in res.headers,
        res.headers.get("Access-Control-Allow-Origin", ""),
    )

    print("\n--- POST /chat 真實對話（會打 Bedrock）---")
    res = client.post("/chat", json={"message": "我家冷氣不冷了，主臥那台"})
    check("狀態碼 200", res.status_code == 200, str(res.status_code))
    body = res.get_json() or {}
    check("有 sessionId", bool(body.get("sessionId")))
    check("reply 非空", bool((body.get("reply") or "").strip()))
    check("有建立服務單", bool(body.get("request")))
    tools = [t["tool"] for t in body.get("trace", [])]
    check("呼叫過 get_member_context", "get_member_context" in tools, ",".join(tools))
    print(f"\n  管家回覆：{body.get('reply')}")
    req = body.get("request") or {}
    print(f"  服務單：{json.dumps(req.get('slots'), ensure_ascii=False)} status={req.get('status')}")

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"失敗 {len(FAILURES)} 項：{FAILURES}")
        return 1
    print("HTTP 層全部通過")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
