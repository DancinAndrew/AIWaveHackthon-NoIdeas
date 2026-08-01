"""把商家與客戶資料灌進 RDS PostgreSQL。

步驟：
  1. 讀 .env 的 PGHOST / PGUSER / PGPASSWORD 連上去
  2. 執行 sql/schema.sql 建表（可重跑，每次會先砍舊表）
  3. 灌 sys_county / sys_district（來自統一資訊資料集）
  4. 灌 mms_vendor + 服務區域 + 價目表（來自 op_agent/seed.py）
  5. 灌 mms_member + 地址 + 家電 + 偏好
  6. 印出每張表的筆數對帳

執行（從 repo 根目錄）：
    .venv\\Scripts\\python.exe packages\\api\\scripts\\rds_load.py

參數：
    --schema-only   只建表不灌資料
    --no-schema     只灌資料不重建表（表已存在時用）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402

from op_agent.geo_generated import COUNTIES, DISTRICTS  # noqa: E402
from op_agent.rds import MAJOR_ITEM_CODES, connect, dsn_summary  # noqa: E402
from op_agent.seed import SEED_USERS, SEED_VENDORS  # noqa: E402

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def sha256_hex(value: str | None) -> str | None:
    """PII 的 hash 索引欄位。真實環境要加 salt/pepper，這裡示範結構。"""
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def run_schema(conn: psycopg.Connection) -> None:
    path = SQL_DIR / "schema.sql"
    print(f"\n[1] 執行 {path.name} 建表")
    conn.execute(path.read_text(encoding="utf-8"))
    conn.commit()
    print("    完成")


def load_geo(conn: psycopg.Connection) -> None:
    """縣市與行政區。用 executemany 一次送多筆，比逐筆 execute 快很多。"""
    print("\n[2] 灌縣市 / 行政區（來源：統一資訊命題數據集）")

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO sys_county (code, name, sort)
            VALUES (%s, %s, %s)
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            """,
            [(c["code"], c["name"], i) for i, c in enumerate(COUNTIES, start=1)],
        )
        cur.executemany(
            """
            INSERT INTO sys_district (code, county_code, name, zip, sort)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            """,
            [
                (d["code"], d["county_code"], d["name"], d.get("zip"), i)
                for i, d in enumerate(DISTRICTS, start=1)
            ],
        )
    conn.commit()
    print(f"    縣市 {len(COUNTIES)} 筆 · 行政區 {len(DISTRICTS)} 筆")


def load_vendors(conn: psycopg.Connection) -> None:
    print("\n[3] 灌商家資料")
    coverage_rows: list[tuple] = []
    pricing_rows: list[tuple] = []

    with conn.cursor() as cur:
        for v in SEED_VENDORS:
            pricing = v.get("pricing", {})
            # 參數化查詢：值一律用 %s 佔位，不要用字串拼接。
            # 這是防 SQL injection 的唯一正確做法。
            cur.execute(
                """
                INSERT INTO mms_vendor (
                    vendor_id, name, service_vendor_id, categories,
                    rating, review_count, completed_jobs,
                    avg_response_minutes, earliest_available_in_days,
                    available_slots, tags, certifications,
                    inspection_fee, supports_points
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (vendor_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    rating = EXCLUDED.rating,
                    upd_time = now()
                """,
                (
                    v["vendorId"],
                    v["name"],
                    v["serviceVendorId"],
                    list(v.get("categories", [])),
                    v.get("rating", 0),
                    v.get("reviewCount", 0),
                    v.get("completedJobs", 0),
                    v.get("avgResponseMinutes", 0),
                    v.get("earliestAvailableInDays", 0),
                    list(v.get("availableSlots", [])),
                    list(v.get("tags", [])),
                    list(v.get("certifications", [])),
                    pricing.get("inspectionFee", 0),
                    bool(v.get("supportsPoints")),
                ),
            )

            for cov in v.get("coverage", []):
                codes = cov["districtCodes"]
                if codes == "ALL":
                    # 全區服務用 district_code = NULL 表示，不要展開成幾十列，
                    # 否則廠商新增行政區時資料會失準
                    coverage_rows.append((v["vendorId"], cov["countyCode"], None))
                else:
                    for code in codes:
                        coverage_rows.append((v["vendorId"], cov["countyCode"], code))

            for item in pricing.get("items", []):
                pricing_rows.append(
                    (
                        v["vendorId"],
                        item["code"],
                        item["name"],
                        item["minPrice"],
                        item["maxPrice"],
                        item.get("unit"),
                        item["code"] in MAJOR_ITEM_CODES,
                    )
                )

        cur.execute("DELETE FROM mms_vendor_coverage")
        cur.executemany(
            "INSERT INTO mms_vendor_coverage (vendor_id, county_code, district_code) VALUES (%s, %s, %s)",
            coverage_rows,
        )
        cur.executemany(
            """
            INSERT INTO mms_vendor_pricing_item
                (vendor_id, item_code, item_name, min_price, max_price, unit, is_major)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (vendor_id, item_code) DO UPDATE SET
                min_price = EXCLUDED.min_price,
                max_price = EXCLUDED.max_price
            """,
            pricing_rows,
        )
    conn.commit()
    print(
        f"    商家 {len(SEED_VENDORS)} 家 · 服務區域 {len(coverage_rows)} 筆 · 價目 {len(pricing_rows)} 筆"
    )


def load_members(conn: psycopg.Connection) -> None:
    print("\n[4] 灌客戶資料")
    addr_n = appl_n = 0

    with conn.cursor() as cur:
        for u in SEED_USERS:
            account_id = u["inbrAccountId"]
            cur.execute(
                """
                INSERT INTO mms_member (
                    inbr_account_id, display_name, mobile, mobile_hash,
                    email, email_hash, points
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (inbr_account_id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    points = EXCLUDED.points,
                    upd_time = now()
                """,
                (
                    account_id,
                    u["displayName"],
                    u.get("mobile"),
                    sha256_hex(u.get("mobile")),
                    u.get("email"),
                    sha256_hex(u.get("email")),
                    u.get("points", 0),
                ),
            )

            cur.execute("DELETE FROM mms_member_address WHERE inbr_account_id = %s", (account_id,))
            for i, a in enumerate(u.get("addresses", [])):
                cur.execute(
                    """
                    INSERT INTO mms_member_address (
                        inbr_account_id, label, county_code, district_code,
                        detail, detail_hash, is_default
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        account_id,
                        "住家" if i == 0 else None,
                        a["countyCode"],
                        a["districtCode"],
                        a.get("detail"),
                        sha256_hex(a.get("detail")),
                        i == 0,
                    ),
                )
                addr_n += 1

            for ap in u.get("appliances", []):
                cur.execute(
                    """
                    INSERT INTO mms_member_appliance (
                        inbr_account_id, appliance_id, kind, brand, model,
                        variant, installed_year, location
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (inbr_account_id, appliance_id) DO UPDATE SET
                        brand = EXCLUDED.brand,
                        installed_year = EXCLUDED.installed_year
                    """,
                    (
                        account_id,
                        ap["applianceId"],
                        ap["kind"],
                        ap.get("brand"),
                        ap.get("model"),
                        ap.get("variant"),
                        ap.get("installedYear"),
                        ap.get("location"),
                    ),
                )
                appl_n += 1

            p = u.get("preferences", {})
            cur.execute(
                """
                INSERT INTO mms_member_preference (
                    inbr_account_id, price_sensitivity, preferred_contact_time,
                    preferred_vendor_tags, blocked_vendor_ids,
                    interested_categories, notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (inbr_account_id) DO UPDATE SET
                    price_sensitivity = EXCLUDED.price_sensitivity,
                    preferred_contact_time = EXCLUDED.preferred_contact_time,
                    preferred_vendor_tags = EXCLUDED.preferred_vendor_tags,
                    notes = EXCLUDED.notes,
                    upd_time = now()
                """,
                (
                    account_id,
                    p.get("priceSensitivity", 0.5),
                    p.get("preferredContactTime"),
                    json.dumps(p.get("preferredVendorTags", []), ensure_ascii=False),
                    json.dumps(p.get("blockedVendorIds", []), ensure_ascii=False),
                    json.dumps(p.get("interestedCategories", []), ensure_ascii=False),
                    json.dumps(p.get("notes", []), ensure_ascii=False),
                ),
            )
    conn.commit()
    print(f"    客戶 {len(SEED_USERS)} 人 · 地址 {addr_n} 筆 · 家電 {appl_n} 筆 · 偏好 {len(SEED_USERS)} 筆")


def reconcile(conn: psycopg.Connection) -> None:
    """對帳：直接問資料庫每張表幾筆，不要相信程式印的數字。"""
    print("\n[5] 資料庫實際筆數")
    tables = [
        "sys_county",
        "sys_district",
        "mms_vendor",
        "mms_vendor_coverage",
        "mms_vendor_pricing_item",
        "mms_member",
        "mms_member_address",
        "mms_member_appliance",
        "mms_member_preference",
    ]
    with conn.cursor() as cur:
        for t in tables:
            # 表名不能參數化（SQL 語法限制），所以用白名單常數，不接受外部輸入
            cur.execute(f"SELECT count(*) FROM {t}")  # noqa: S608
            print(f"    {t:<26} {cur.fetchone()[0]:>5} 筆")


def main() -> int:
    parser = argparse.ArgumentParser(description="把商家與客戶資料灌進 RDS")
    parser.add_argument("--schema-only", action="store_true", help="只建表")
    parser.add_argument("--no-schema", action="store_true", help="不重建表，只灌資料")
    args = parser.parse_args()

    print("=" * 66)
    print("連線目標")
    print("=" * 66)
    print("  " + dsn_summary())

    try:
        conn = connect()
    except Exception as err:  # noqa: BLE001
        print(f"\n連線失敗：{type(err).__name__}: {err}")
        print("\n可能原因：")
        print("  1. RDS 還沒建好 → 跑 rds_create.py --status 看狀態是不是 available")
        print("  2. .env 沒有 PGHOST → 跑 rds_create.py 會自動寫入")
        print("  3. 你的 IP 換了（換 wifi / 重開機）→ 重跑 rds_create.py 會補上新 IP 的規則")
        return 1

    with conn:
        if not args.no_schema:
            run_schema(conn)
        if not args.schema_only:
            load_geo(conn)
            load_vendors(conn)
            load_members(conn)
            reconcile(conn)

    print("\n完成。下一步驗證：")
    print("  .venv\\Scripts\\python.exe packages\\api\\scripts\\rds_query.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
