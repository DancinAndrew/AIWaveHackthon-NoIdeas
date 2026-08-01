"""Lambda 入口。

兩個 handler 對應兩個 agent：

  chat_handler   -> API Gateway HTTP API (payload v2) 包 Flask app，對外提供 /chat /context /health
  match_handler  -> 不對外開放，由 chat_handler 用 Lambda invoke 呼叫（媒合代理是平台端內部服務）

Flask 是 WSGI，API Gateway 給的是 event dict，中間用 apig-wsgi 轉接。
"""

from __future__ import annotations

from typing import Any

from apig_wsgi import make_lambda_handler

from app import app
from op_agent.match_agent import run_match_agent

# API Gateway HTTP API 用 payload format 2.0
_wsgi_handler = make_lambda_handler(app, binary_support=False)


def chat_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return _wsgi_handler(event, context)


def match_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """直接吃 {"request": ..., "preferences": ...} 的 payload。"""
    req = event.get("request")
    if not req:
        raise ValueError("payload 缺少 request")
    return run_match_agent(req, event.get("preferences") or {})
