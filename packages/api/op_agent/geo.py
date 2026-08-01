"""縣市／行政區解析。

把使用者的口語地址轉成統一資訊資料集裡的 county_code / district_code，
這樣服務單、廠商服務區、諮詢單就能對得起來。
"""

from __future__ import annotations

from .domain import Address
from .geo_generated import COUNTIES, DISTRICTS

_COUNTY_BY_CODE = {c["code"]: c for c in COUNTIES}
_DISTRICT_BY_CODE = {d["code"]: d for d in DISTRICTS}


def _normalize(name: str) -> str:
    """台北/臺北、台中/臺中 等異體字正規化。"""
    return name.strip().replace("臺", "台").replace(" ", "")


def find_county(text: str) -> dict | None:
    q = _normalize(text)
    if not q:
        return None
    for c in COUNTIES:
        if _normalize(c["name"]) == q:
            return {"code": c["code"], "name": c["name"]}
    # 「台北」→「台北市」
    for c in COUNTIES:
        n = _normalize(c["name"])
        if n.startswith(q) or q.startswith(n):
            return {"code": c["code"], "name": c["name"]}
    return None


def find_district(county_code: str, text: str) -> dict | None:
    q = _normalize(text)
    if not q:
        return None
    pool = [d for d in DISTRICTS if d["county_code"] == county_code]
    for d in pool:
        if _normalize(d["name"]) == q:
            return {"code": d["code"], "name": d["name"]}
    for d in pool:
        n = _normalize(d["name"])
        if n.startswith(q) or q.startswith(n):
            return {"code": d["code"], "name": d["name"]}
    return None


def list_districts(county_code: str) -> list[str]:
    return [d["name"] for d in DISTRICTS if d["county_code"] == county_code]


def resolve_address(
    *,
    county: str | None = None,
    district: str | None = None,
    detail: str | None = None,
    free_text: str | None = None,
) -> Address | None:
    """把使用者口語地址解析成 Address（含 county/district code）。

    例：「台北市大安區復興南路一段100號5樓」
    """
    county_raw = county
    district_raw = district

    if free_text and (not county_raw or not district_raw):
        text = _normalize(free_text)
        hit = next((c for c in COUNTIES if _normalize(c["name"]) in text), None)
        if hit:
            county_raw = hit["name"]
            idx = text.index(_normalize(hit["name"])) + len(_normalize(hit["name"]))
            rest = text[idx:]
            d_hit = next(
                (
                    d
                    for d in DISTRICTS
                    if d["county_code"] == hit["code"] and rest.startswith(_normalize(d["name"]))
                ),
                None,
            )
            if d_hit:
                district_raw = d_hit["name"]
                if detail is None:
                    detail = rest[len(_normalize(d_hit["name"])) :]
            elif detail is None:
                detail = rest

    if not county_raw:
        return None
    c = find_county(county_raw)
    if not c:
        return None
    d = find_district(c["code"], district_raw) if district_raw else None
    if not d:
        return None

    addr: Address = {
        "countyCode": c["code"],
        "countyName": c["name"],
        "districtCode": d["code"],
        "districtName": d["name"],
    }
    cleaned = (detail or "").strip()
    if cleaned:
        addr["detail"] = cleaned
    return addr


def describe_address(a: Address) -> str:
    return f"{a.get('countyName', '')}{a.get('districtName', '')}{a.get('detail', '')}"


def county_name(code: str) -> str:
    row = _COUNTY_BY_CODE.get(code)
    return row["name"] if row else code


def district_name(code: str) -> str:
    row = _DISTRICT_BY_CODE.get(code)
    return row["name"] if row else code
