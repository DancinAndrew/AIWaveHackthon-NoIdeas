"""生成器共用工具：固定 seed、路徑、JSON 讀寫、命題檔解析。"""

from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SEED = 20260801
TZ = timezone(timedelta(hours=8))
# 所有相對時間以此為 D 日；改這裡即可整批平移時段資料
D_DAY = datetime(2026, 8, 1, 0, 0, 0, tzinfo=TZ)

ROOT = Path(__file__).resolve().parents[2]
COMPETITION_DIR = ROOT / "data" / "competition"
OUT_DIR = ROOT / "data" / "mock"

# 固定 namespace，讓 uuid5 在同 seed 下可重現
UUID_NS = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def rng(stream: str) -> random.Random:
    """每個資料流一個獨立 Random，避免新增資料時打亂既有輸出。"""
    return random.Random(f"{SEED}:{stream}")


def stable_uuid(*parts: Any) -> str:
    return str(uuid.uuid5(UUID_NS, ":".join(str(p) for p in parts)))


def iso(dt: datetime) -> str:
    return dt.astimezone(TZ).isoformat(timespec="seconds")


def load_multi_doc_json(path: Path) -> dict[str, list[dict]]:
    """命題的三個 JSON 檔都是多個頂層文件並排，逐份解析後合併。

    非 JSON 的純文字行（如主檔檔案第 36 行的 type 對照表）會被跳過並回報。
    """
    text = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    merged: dict[str, list[dict]] = {}
    index = 0
    while index < len(text):
        while index < len(text) and text[index] in " \t\r\n":
            index += 1
        if index >= len(text):
            break
        try:
            doc, index = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            newline = text.find("\n", index)
            index = newline + 1 if newline > 0 else len(text)
            continue
        if not isinstance(doc, dict):
            continue
        for key, value in doc.items():
            merged.setdefault(key, []).extend(value)
    return merged


def write_json(relative_path: str, payload: Any) -> Path:
    target = OUT_DIR / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target


def write_jsonl(relative_path: str, rows: list[dict]) -> Path:
    target = OUT_DIR / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def read_mock(relative_path: str) -> Any:
    return json.loads((OUT_DIR / relative_path).read_text(encoding="utf-8"))


def report(target: Path, count: int) -> None:
    print(f"  {target.relative_to(ROOT)}  ({count} 筆)")
