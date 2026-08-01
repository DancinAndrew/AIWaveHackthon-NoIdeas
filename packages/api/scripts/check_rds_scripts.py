"""在還沒建 RDS 之前，先檢查 RDS 相關腳本的語法與 SQL 是否合理。

檢查項目：
  1. 三支腳本能不能 import（語法錯誤會在這裡爆）
  2. schema.sql 讀得到、且 CREATE TABLE 數量符合預期
  3. seed 資料轉成 DB 列的邏輯正確（不連線，純算）
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)


def main() -> int:
    print("\n--- 1) 模組能否 import ---")
    try:
        import importlib

        for mod in ("op_agent.rds", "psycopg"):
            importlib.import_module(mod)
        check("op_agent.rds / psycopg 可 import", True)
    except Exception as err:  # noqa: BLE001
        check("op_agent.rds / psycopg 可 import", False, f"{type(err).__name__}: {err}")
        return 1

    from op_agent.rds import MAJOR_ITEM_CODES, dsn_summary

    check("dsn_summary 不會印出密碼", "password" not in dsn_summary().lower(), dsn_summary())

    print("\n--- 2) schema.sql ---")
    sql_path = Path(__file__).resolve().parents[1] / "sql" / "schema.sql"
    check("schema.sql 存在", sql_path.exists(), str(sql_path))
    sql = sql_path.read_text(encoding="utf-8")
    tables = re.findall(r"CREATE TABLE (\w+)", sql)
    expected = {
        "sys_county",
        "sys_district",
        "mms_vendor",
        "mms_vendor_coverage",
        "mms_vendor_pricing_item",
        "mms_member",
        "mms_member_address",
        "mms_member_appliance",
        "mms_member_preference",
    }
    check("建了 9 張表", set(tables) == expected, f"{len(tables)} 張：{sorted(set(tables) ^ expected) or '完全符合'}")
    check("每張表都有 DROP（可重跑）", sql.count("DROP TABLE IF EXISTS") == len(expected))
    check("有建 view", "CREATE OR REPLACE VIEW v_vendor_service_area" in sql)
    # 只有 mms_vendor_coverage 與 mms_member_address 需要指到行政區
    n_district_fk = sql.count("REFERENCES sys_district")
    check("行政區外鍵有 2 個（商家服務區 + 客戶地址）", n_district_fk == 2, f"{n_district_fk} 個")
    n_county_fk = sql.count("REFERENCES sys_county")
    check("縣市外鍵有 3 個（行政區 + 商家服務區 + 客戶地址）", n_county_fk == 3, f"{n_county_fk} 個")

    print("\n--- 3) seed 資料 → DB 列的換算 ---")
    from op_agent.seed import SEED_USERS, SEED_VENDORS

    coverage_rows = 0
    all_district_rows = 0
    pricing_rows = 0
    major_rows = 0
    for v in SEED_VENDORS:
        for cov in v.get("coverage", []):
            if cov["districtCodes"] == "ALL":
                coverage_rows += 1
                all_district_rows += 1
            else:
                coverage_rows += len(cov["districtCodes"])
        for item in v.get("pricing", {}).get("items", []):
            pricing_rows += 1
            if item["code"] in MAJOR_ITEM_CODES:
                major_rows += 1

    check("商家 6 家", len(SEED_VENDORS) == 6, str(len(SEED_VENDORS)))
    check("服務區域列數 > 0", coverage_rows > 0, f"{coverage_rows} 列（其中 {all_district_rows} 列為全區 NULL）")
    check("價目列數 > 0", pricing_rows > 0, f"{pricing_rows} 列")
    check("有標記大額項目", major_rows > 0, f"{major_rows} 列 is_major=true")

    addr = sum(len(u.get("addresses", [])) for u in SEED_USERS)
    appl = sum(len(u.get("appliances", [])) for u in SEED_USERS)
    check("客戶 1 人", len(SEED_USERS) == 1, str(len(SEED_USERS)))
    check("地址 2 筆", addr == 2, str(addr))
    check("家電 3 筆", appl == 3, str(appl))

    print("\n--- 4) 縣市資料齊全（外鍵會用到）---")
    from op_agent.geo_generated import COUNTIES, DISTRICTS

    county_codes = {c["code"] for c in COUNTIES}
    orphan = [d["code"] for d in DISTRICTS if d["county_code"] not in county_codes]
    check("行政區都有對應縣市（不會違反外鍵）", not orphan, f"孤兒 {orphan[:5]}" if orphan else "全部有對應")

    # 商家 coverage 引用的行政區代碼必須存在，否則灌資料會外鍵失敗
    district_codes = {d["code"] for d in DISTRICTS}
    bad: list[str] = []
    for v in SEED_VENDORS:
        for cov in v.get("coverage", []):
            if cov["districtCodes"] == "ALL":
                if cov["countyCode"] not in county_codes:
                    bad.append(f"{v['vendorId']}:county {cov['countyCode']}")
                continue
            for code in cov["districtCodes"]:
                if code not in district_codes:
                    bad.append(f"{v['vendorId']}:district {code}")
    check("商家服務區域代碼都有效", not bad, ", ".join(bad[:6]) if bad else "全部有效")

    # 會員地址同理
    bad_addr: list[str] = []
    for u in SEED_USERS:
        for a in u.get("addresses", []):
            if a["countyCode"] not in county_codes:
                bad_addr.append(f"county {a['countyCode']}")
            if a["districtCode"] not in district_codes:
                bad_addr.append(f"district {a['districtCode']}")
    check("客戶地址代碼都有效", not bad_addr, ", ".join(bad_addr) if bad_addr else "全部有效")

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"失敗 {len(FAILURES)} 項：{FAILURES}")
        return 1
    print("RDS 腳本靜態檢查全部通過（尚未連線）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
