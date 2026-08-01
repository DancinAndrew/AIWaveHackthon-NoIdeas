"""診斷：確認 Flask 路由、靜態檔位置、以及本機 3001 埠是否有人在聽。

執行（從 repo 根目錄）：
    .venv\\Scripts\\python.exe packages\\api\\scripts\\diagnose.py
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app  # noqa: E402
from op_agent.config import config  # noqa: E402


def main() -> int:
    print("=" * 64)
    print("1) Flask 註冊的路由")
    print("=" * 64)
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: str(r)):
        methods = ",".join(sorted(rule.methods - {"HEAD", "OPTIONS"}))
        print(f"  {str(rule):24} [{methods}]  -> {rule.endpoint}")

    print()
    print("=" * 64)
    print("2) 靜態檔設定")
    print("=" * 64)
    print(f"  app.root_path      = {app.root_path}")
    print(f"  app.static_folder  = {app.static_folder}")
    index = Path(app.static_folder or "") / "index.html"
    print(f"  index.html 路徑    = {index}")
    print(f"  index.html 存在？  = {index.exists()}")
    if index.exists():
        print(f"  index.html 大小    = {index.stat().st_size} bytes")

    print()
    print("=" * 64)
    print("3) 用 test client 實際請求 /")
    print("=" * 64)
    res = app.test_client().get("/")
    print(f"  狀態碼   = {res.status_code}")
    print(f"  Content-Type = {res.headers.get('Content-Type')}")
    body = res.get_data(as_text=True)
    print(f"  回傳長度 = {len(body)} 字元")
    print(f"  開頭     = {body[:60]!r}")

    print()
    print("=" * 64)
    print(f"4) 本機 127.0.0.1:{config.port} 有人在聽嗎？")
    print("=" * 64)
    sock = socket.socket()
    sock.settimeout(1.5)
    try:
        sock.connect(("127.0.0.1", config.port))
        print(f"  有 —— 已經有進程佔用 {config.port} 埠")
        print("  如果瀏覽器 404，很可能那是「加 / 路由之前」啟動的舊進程，請先關掉再重啟。")
    except OSError as err:
        print(f"  沒有 —— 目前沒人在聽（{err}）")
        print("  瀏覽器如果顯示 404 而不是「無法連線」，那你連的可能不是這個 port。")
    finally:
        sock.close()

    print()
    print("結論：若上面第 3 步是 200，程式碼沒問題，問題在「跑的是舊進程」或「連錯 port」。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
