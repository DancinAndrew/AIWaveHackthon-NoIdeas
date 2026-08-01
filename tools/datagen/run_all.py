"""一鍵重建整個 data/mock 資料集，最後跑驗證。

用法：
    .venv/bin/python tools/datagen/run_all.py
"""

from __future__ import annotations

import sys

import build_cases
import build_community
import build_eval
import build_geo
import build_knowledge
import build_manifest
import build_offerings
import build_products
import build_providers
import build_restaurants
import validate

STEPS = [
    ("地理代碼", build_geo.build),
    ("服務商主檔", build_providers.build),
    ("餐廳與時段", build_restaurants.build),
    ("商品 SKU", build_products.build),
    ("服務項目與技師", build_offerings.build),
    ("社區與責任單位", build_community.build),
    ("靜態知識庫", build_knowledge.build),
    ("案件資料", build_cases.build),
    ("AI 評測集", build_eval.build),
]


def main() -> int:
    for label, step in STEPS:
        print(f"[{label}]")
        step()
    print("[manifest]")
    build_manifest.build()
    print()
    return validate.main()


if __name__ == "__main__":
    sys.exit(main())
