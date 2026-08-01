"""從統一資訊提供的「縣市區域範例資料.json」產生 Python 常數檔。

該檔案是多個 JSON 物件串接（{"sys_county":[...]} 後面接 {"sys_district":[...]}），
不是合法的單一 JSON，所以用大括號配對切開後逐段 parse。

用法：python scripts/gen_geo.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "packages" / "api" / "op_agent" / "geo_generated.py"


def find_dataset_dir() -> Path:
    for p in ROOT.iterdir():
        if p.is_dir() and "命題數據集" in p.name:
            return p
    raise SystemExit("找不到命題數據集資料夾")


def split_json_objects(text: str) -> list[str]:
    """用大括號配對，把串接的多個 JSON 物件切出來。"""
    out: list[str] = []
    depth = 0
    start = -1
    in_str = False
    esc = False
    for i, c in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                out.append(text[start : i + 1])
                start = -1
    return out


def main() -> None:
    src = find_dataset_dir() / "縣市區域範例資料.json"
    raw = src.read_text(encoding="utf-8")

    counties: list[dict] = []
    districts: list[dict] = []
    for chunk in split_json_objects(raw):
        try:
            obj = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if isinstance(obj.get("sys_county"), list):
            counties.extend(obj["sys_county"])
        if isinstance(obj.get("sys_district"), list):
            districts.extend(obj["sys_district"])

    active_counties = [
        {"code": c["code"], "name": c["name"]}
        for c in sorted(
            (c for c in counties if c.get("is_deleted") == "0"),
            key=lambda c: c["sort"],
        )
    ]
    active_districts = [
        {
            "code": d["code"],
            "county_code": d["county_code"],
            "name": d["name"],
            "zip": d["zip"],
        }
        for d in sorted(
            (d for d in districts if d.get("is_deleted") == "0"),
            key=lambda d: (d["county_code"], d["sort"]),
        )
    ]

    body = f'''"""自動產生，請勿手改。

來源：{src.relative_to(ROOT).as_posix()}
重新產生：python scripts/gen_geo.py
對應 sys_county / sys_district（縣市代碼 2 碼、行政區代碼 3 碼）
"""

from __future__ import annotations

from typing import TypedDict


class CountyRow(TypedDict):
    code: str
    name: str


class DistrictRow(TypedDict):
    code: str
    county_code: str
    name: str
    zip: str


COUNTIES: list[CountyRow] = {json.dumps(active_counties, ensure_ascii=False, indent=4)}

DISTRICTS: list[DistrictRow] = {json.dumps(active_districts, ensure_ascii=False, indent=4)}
'''

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8")
    print(f"counties={len(active_counties)} districts={len(active_districts)} -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
