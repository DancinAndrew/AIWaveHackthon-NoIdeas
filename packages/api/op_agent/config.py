"""集中讀環境變數，避免各處散落 os.environ。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 往上找 repo 根目錄的 .env（packages/api/op_agent -> packages/api -> packages -> repo root）
_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / ".env")


@dataclass(frozen=True)
class Config:
    region: str
    model_id: str
    repo_driver: str  # 'memory' | 'dynamodb'
    table_name: str
    # 有值就用 Lambda invoke 呼叫媒合 agent，沒值就 in-process 呼叫
    match_function_name: str | None
    port: int


def _get_config() -> Config:
    return Config(
        region=os.environ.get("AWS_REGION") or "us-west-2",
        model_id=os.environ.get("BEDROCK_MODEL_ID")
        or "amazon.nova-2-lite-v1:0",
        repo_driver=(os.environ.get("REPO_DRIVER") or "memory").lower(),
        table_name=os.environ.get("TABLE_NAME") or "op-life-agent",
        match_function_name=os.environ.get("MATCH_FUNCTION_NAME") or None,
        port=int(os.environ.get("PORT") or 3001),
    )


config = _get_config()
