"""Flask 應用。

API 契約（前端只認這三個）：
    GET  /health
    GET  /context?inbrAccountId=...
    POST /chat      { "sessionId"?: str, "inbrAccountId"?: str, "message": str }

同一個 app 物件既能本地 `python app.py` 跑，也能被 lambda_handler.py 包成 Lambda。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from op_agent.config import config
from op_agent.repo import get_repo
from op_agent.seed import DEMO_USER_ID
from op_agent.user_agent import run_user_agent_turn, suggested_prompts

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("op.api")

# React 前端 build 產物。存在的話 `/` 直接吐 App，
# 這樣單一個 Flask 程序就能 demo 全部功能，不需要另外開 vite。
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    # 中文直接輸出，不要被轉成 \uXXXX，方便 curl / 前端 debug
    app.json.ensure_ascii = False

    # Demo 階段開放所有來源；正式環境要收斂成 OpenPoint 的網域白名單。
    # 目前 /chat 沒有任何身分驗證，靠 inbrAccountId 直接指定會員 —
    # 上線前必須改成驗證 OpenPoint SSO token 後由 token 解出會員身分。
    CORS(app, resources={r"/*": {"origins": "*"}})

    # ---------------- 前端 ----------------

    @app.get("/")
    def index():
        """有 build 過的 React 就吐它，否則退回開發控制台並提示怎麼 build。"""
        if (FRONTEND_DIST / "index.html").exists():
            return send_from_directory(FRONTEND_DIST, "index.html")
        return app.send_static_file("index.html")

    @app.get("/assets/<path:filename>")
    def frontend_assets(filename: str):
        """Vite build 出來的 index.html 引用 /assets/xxx.js 這種絕對路徑。"""
        return send_from_directory(FRONTEND_DIST / "assets", filename)

    @app.get("/console")
    def console():
        """開發用可視化控制台（零依賴 HTML，不需要 npm build）。

        把 agent 的內部狀態全部攤開：slot filling、媒合結果、
        每個工具的輸入輸出。除錯時比看 App 快得多。
        """
        return app.send_static_file("index.html")

    # ---------------- API ----------------
    #
    # 每個 API 都註冊兩條路徑：
    #   /chat      給 Flask 自己 serve 前端時用（同源，前端打 /api/chat 會走下面那條）
    #   /api/chat  給前端統一使用 —— vite dev 時 proxy 會把 /api 前綴拿掉，
    #              Flask 直接 serve 時則由這裡的別名接住。
    # 這樣同一份前端 build 在兩種情境都能跑，不用改 base url。

    @app.get("/health")
    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "repo": config.repo_driver,
                "model": config.model_id,
                "region": config.region,
                "matchTransport": "lambda" if config.match_function_name else "in-process",
            }
        )

    @app.get("/context")
    @app.get("/api/context")
    def context():
        """給前端開場用：會員資訊 + 歷史單 + 建議話術。"""
        repo = get_repo()
        account_id = request.args.get("inbrAccountId") or DEMO_USER_ID
        user = repo.get_user(account_id)
        if user is None:
            return jsonify({"error": "會員不存在"}), 404
        return jsonify(
            {
                "user": user,
                "requests": repo.list_requests_by_user(account_id),
                "bookings": repo.list_bookings_by_user(account_id),
                "suggestedPrompts": suggested_prompts(),
            }
        )

    @app.post("/chat")
    @app.post("/api/chat")
    def chat():
        body = request.get_json(silent=True) or {}
        message = body.get("message")
        if not isinstance(message, str) or not message.strip():
            return jsonify({"error": "message 為必填"}), 400

        started = time.monotonic()
        try:
            result = run_user_agent_turn(
                session_id=body.get("sessionId"),
                # demo 階段沒有登入，預設用種子會員
                inbr_account_id=body.get("inbrAccountId") or DEMO_USER_ID,
                message=message,
            )
        except KeyError as err:
            return jsonify({"error": str(err)}), 404
        except Exception as err:  # noqa: BLE001 - 回一個可讀的錯誤給前端
            logger.exception("chat failed")
            return jsonify({"error": f"{type(err).__name__}: {err}"}), 500

        elapsed = int((time.monotonic() - started) * 1000)
        logger.info(
            "chat ok %dms tools=%s",
            elapsed,
            ",".join(t["tool"] for t in result.get("trace", [])) or "-",
        )
        return jsonify(result)

    return app


app = create_app()


if __name__ == "__main__":
    has_build = (FRONTEND_DIST / "index.html").exists()
    print(
        f"\n生活管家已啟動\n"
        f"\n  >> App：      http://127.0.0.1:{config.port}/"
        + ("" if has_build else "   (尚未 build，目前顯示開發控制台)")
        + f"\n  >> 開發控制台：http://127.0.0.1:{config.port}/console"
        f"\n"
        f"\n  資料層: {config.repo_driver}   模型: {config.model_id}   區域: {config.region}"
        + (
            ""
            if has_build
            else "\n\n  要看 App 請先執行： npm run build -w @op/frontend"
        )
        + "\n"
    )
    # debug=False：Flask reloader 會讓 MemoryRepo 的資料在重載時被清掉，demo 時很困擾
    app.run(host="127.0.0.1", port=config.port, debug=False)
