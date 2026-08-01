"""合併命題的 200 筆行政區 + 補齊的 168 筆 → 全國 368 筆。"""

from __future__ import annotations

from common import COMPETITION_DIR, load_multi_doc_json, report, write_json
from geo_missing import MISSING_DISTRICTS

GEO_SRC = COMPETITION_DIR / "縣市區域範例資料.json"
FIRST_MISSING_CODE = 70


def build() -> None:
    source = load_multi_doc_json(GEO_SRC)
    counties = [
        {
            "county_code": row["code"],
            "name": row["name"],
            "sort": row["sort"],
            "source": "competition",
        }
        for row in sorted(source["sys_county"], key=lambda r: r["sort"])
    ]
    county_names = {c["county_code"]: c["name"] for c in counties}

    districts = [
        {
            "district_code": row["code"],
            "county_code": row["county_code"],
            "county_name": county_names[row["county_code"]],
            "name": row["name"],
            "zip": row["zip"],
            "source": "competition",
        }
        for row in source["sys_district"]
    ]

    for offset, (county_code, name, zip_code) in enumerate(MISSING_DISTRICTS):
        districts.append(
            {
                "district_code": f"{FIRST_MISSING_CODE + offset:03d}",
                "county_code": county_code,
                "county_name": county_names[county_code],
                "name": name,
                "zip": zip_code,
                "source": "filled",
            }
        )

    districts.sort(key=lambda d: int(d["district_code"]))

    codes = [int(d["district_code"]) for d in districts]
    assert codes == list(range(1, 369)), "行政區代碼必須是 001~368 連號"
    assert len({(d["county_code"], d["name"]) for d in districts}) == 368

    report(write_json("geo/counties.json", counties), len(counties))
    report(write_json("geo/districts.json", districts), len(districts))


if __name__ == "__main__":
    build()
