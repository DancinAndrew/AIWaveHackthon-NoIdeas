"""Bedrock Converse API 的 tool-use loop。

流程：送出對話 -> 若 stopReason 是 tool_use 就執行工具、把結果回灌 -> 直到模型給純文字。
每次工具呼叫都記進 trace，前端可以畫成「agent 做了什麼」的時間軸。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.config import Config as BotoConfig

from .config import config
from .domain import AgentTraceEntry

logger = logging.getLogger(__name__)

# Bedrock 的 tool loop 一輪可能跑好幾次 API，逾時要放寬
_bedrock = boto3.client(
    "bedrock-runtime",
    region_name=config.region,
    config=BotoConfig(read_timeout=120, connect_timeout=10, retries={"max_attempts": 3}),
)


@dataclass
class AgentTool:
    """一個 agent 可以呼叫的工具。"""

    name: str
    description: str
    schema: dict[str, Any]  # JSON Schema
    run: Callable[[dict[str, Any]], Any]


@dataclass
class RunAgentResult:
    text: str
    trace: list[AgentTraceEntry] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tool_config(tools: list[AgentTool]) -> dict[str, Any] | None:
    if not tools:
        return None
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": {"json": t.schema},
                }
            }
            for t in tools
        ]
    }


def _extract_text(content: list[dict[str, Any]] | None) -> str:
    return "\n".join(b["text"] for b in (content or []) if "text" in b).strip()


def run_agent(
    *,
    agent_name: str,
    system_prompt: str,
    messages: list[dict[str, Any]],
    tools: list[AgentTool],
    max_turns: int = 8,
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> RunAgentResult:
    tool_map = {t.name: t for t in tools}
    convo: list[dict[str, Any]] = list(messages)
    trace: list[AgentTraceEntry] = []

    for _ in range(max_turns):
        kwargs: dict[str, Any] = {
            "modelId": config.model_id,
            "system": [{"text": system_prompt}],
            "messages": convo,
            "inferenceConfig": {"temperature": temperature, "maxTokens": max_tokens},
        }
        tc = _tool_config(tools)
        if tc:
            kwargs["toolConfig"] = tc

        res = _bedrock.converse(**kwargs)

        assistant = res.get("output", {}).get("message")
        if not assistant:
            raise RuntimeError("Bedrock 沒有回傳 message")

        text = _extract_text(assistant.get("content"))
        tool_uses = [b["toolUse"] for b in assistant.get("content", []) if "toolUse" in b]

        # 模型偶爾會在呼叫完工具後就結束，卻不給任何文字內容。
        # 這種空 message 不能放進 convo（下一次 Converse 會 ValidationException：
        # content field is empty），所以直接丟掉它，並把催促文字併進上一則
        # user 訊息 —— 因為 role 必須 user/assistant 交替，不能連續兩則 user。
        if not text and not tool_uses:
            logger.warning("agent %s 回傳空內容，補一次 nudge", agent_name)
            nudge = {"text": "請根據目前掌握的資訊，用繁體中文直接回覆會員。不要再呼叫工具，只要一段話。"}
            if convo and convo[-1]["role"] == "user":
                convo[-1]["content"].append(nudge)
            else:
                convo.append({"role": "user", "content": [nudge]})
            continue

        convo.append(assistant)

        if res.get("stopReason") != "tool_use" or not tool_uses:
            return RunAgentResult(text=text, trace=trace, messages=convo)

        # 執行這一輪所有工具呼叫，結果一次回灌
        results: list[dict[str, Any]] = []
        for use in tool_uses:
            name = use.get("name", "")
            tool = tool_map.get(name)
            ok = True
            if tool is None:
                ok = False
                output: Any = {"error": f"未知的工具: {name}"}
            else:
                try:
                    output = tool.run(use.get("input") or {})
                except Exception as err:  # noqa: BLE001 - 工具錯誤要回灌給模型自救
                    ok = False
                    output = {"error": f"{type(err).__name__}: {err}"}
                    logger.exception("tool %s failed", name)

            trace.append(
                {
                    "agent": agent_name,  # type: ignore[typeddict-item]
                    "tool": name,
                    "input": use.get("input"),
                    "output": output,
                    "at": _now(),
                }
            )
            results.append(
                {
                    "toolResult": {
                        "toolUseId": use.get("toolUseId"),
                        # 用 json.loads(json.dumps(...)) 確保內容一定可序列化
                        "content": [{"json": json.loads(json.dumps(output, default=str))}],
                        "status": "success" if ok else "error",
                    }
                }
            )
        convo.append({"role": "user", "content": results})

    return RunAgentResult(
        text="抱歉，我這邊處理有點卡住了，可以請你再說一次需求嗎？",
        trace=trace,
        messages=convo,
    )
