"""Shared service-area vocabulary for the walking skeleton.

Scope note: this is deliberately the same nine Taipei districts the utility
walking skeleton already supported, not the full `data/mock/geo/districts.json`
set. Widening it would let a resident name a district no demo provider covers,
which changes existing utility behaviour, so it belongs to its own change.

Codes match the competition `sys_county` / `sys_district` fixtures: two digits
for a county, three for a district.
"""

from __future__ import annotations

COUNTY_NAME = "台北市"
COUNTY_CODE = "01"

DISTRICTS: dict[str, tuple[str, str]] = {
    "大安區": ("01", "007"),
    "內湖區": ("01", "010"),
    "南港區": ("01", "008"),
    "中山區": ("01", "003"),
    "士林區": ("01", "011"),
    "信義區": ("01", "005"),
    "松山區": ("01", "006"),
    "大同區": ("01", "002"),
    "北投區": ("01", "009"),
}


def resolve_district(text: str) -> tuple[str, str, str] | None:
    """Return `(county_code, district_code, district_name)` named in free text."""

    for district_name, (county_code, district_code) in DISTRICTS.items():
        if district_name in text:
            return county_code, district_code, district_name
    return None


def describe(district_name: str | None) -> str:
    return f"{COUNTY_NAME}{district_name}" if district_name else "（未指定地區）"
