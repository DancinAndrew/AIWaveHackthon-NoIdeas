"""生活管家 -> 媒合代理 的傳輸層。

本地開發：直接 in-process 呼叫，好 debug。
部署後：MATCH_FUNCTION_NAME 有值就走 Lambda invoke（兩個 agent 真的是兩個獨立服務）。
上層程式碼不需要知道差別。
"""

from __future__ import annotations

import json
from typing import Any

from .config import config
from .domain import ServiceRequest, UserPreferences


def call_match_agent(request: ServiceRequest, preferences: UserPreferences) -> dict[str, Any]:
    if not config.match_function_name:
        from .match_agent import run_match_agent

        return run_match_agent(request, preferences)

    import boto3

    lambda_client = boto3.client("lambda", region_name=config.region)
    res = lambda_client.invoke(
        FunctionName=config.match_function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(
            {"request": request, "preferences": preferences}, ensure_ascii=False
        ).encode("utf-8"),
    )

    payload = res["Payload"].read().decode("utf-8")
    if res.get("FunctionError"):
        raise RuntimeError(f"媒合 agent 執行失敗: {res['FunctionError']} {payload}")
    return json.loads(payload)
