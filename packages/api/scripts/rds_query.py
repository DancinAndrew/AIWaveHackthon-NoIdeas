"""驗證 RDS 裡的資料 —— 跑幾個「真的會用到」的查詢。

這支的價值在於：它證明資料不只是「灌進去了」，而是「查得出有意義的結果」。
每個查詢都對應 agent 實際會問資料庫的問題。

執行（從 repo 根目錄）：
    .venv\\Scripts\\python.exe packages\\api\\scripts\\rds_query.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from op_agent.rds import connect, dsn_summary  # noqa: E402


def show(title: str, question: str, cur, sql: str, params: tuple = ()) -> None:
    print()
    print("=" * 72)
    print(title)
    print(f"  對應的實際問題：{question}")
    print("=" * 72)
    cur.execute(sql, params)
    rows = cur.fetchall()
    if not rows:
        print("  （沒有結果）")
        return
    headers = [d.name for d in cur.description]
    widths = [
        max(len(h), max((len(str(r[i])) for r in rows), default=0)) for i, h in enumerate(headers)
    ]
    print("  " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("  " + "-+-".join("-" * w for w in widths))
    for r in rows:
        print("  " + " | ".join(str(v).ljust(widths[i]) for i, v in enumerate(r)))
    print(f"  ({len(rows)} 筆)")


def main() -> int:
    print(f"連線：{dsn_summary()}")
    try:
        conn = connect()
    except Exception as err:  # noqa: BLE001
        print(f"連線失敗：{type(err).__name__}: {err}")
        return 1

    with conn, conn.cursor() as cur:
        show(
            "① 台北市大安區可服務的廠商",
            "會員說「我在大安區」，媒合代理要撈出候選名單",
            cur,
            """
            SELECT v.vendor_id, v.name, v.rating, v.inspection_fee,
                   v.earliest_available_in_days AS days
            FROM mms_vendor v
            JOIN mms_vendor_coverage cv ON cv.vendor_id = v.vendor_id
            WHERE cv.county_code = %s
              AND (cv.district_code = %s OR cv.district_code IS NULL)
              AND 'AC_REPAIR' = ANY(v.categories)
              AND v.is_deleted = '0' AND v.is_enable = '1'
            ORDER BY v.rating DESC
            """,
            ("01", "007"),
        )

        show(
            "② 冷媒填充的價格帶（跨廠商比較）",
            "報價引擎要知道同一項維修在市場上的價格區間",
            cur,
            """
            SELECT p.item_name, v.name AS vendor, p.min_price, p.max_price
            FROM mms_vendor_pricing_item p
            JOIN mms_vendor v ON v.vendor_id = p.vendor_id
            WHERE p.item_code = %s
            ORDER BY p.min_price
            """,
            ("AC_GAS",),
        )

        show(
            "③ 大額風險項目（不計入主報價區間）",
            "報價要誠實揭露最壞情況，這些項目靠 is_major 標記",
            cur,
            """
            SELECT v.name AS vendor, p.item_name, p.min_price, p.max_price
            FROM mms_vendor_pricing_item p
            JOIN mms_vendor v ON v.vendor_id = p.vendor_id
            WHERE p.is_major = true
            ORDER BY p.max_price DESC
            """,
        )

        show(
            "④ 會員完整背景（agent 開場讀的資料）",
            "get_member_context 要一次拿到姓名、點數、偏好",
            cur,
            """
            SELECT m.display_name, m.points,
                   pr.price_sensitivity, pr.preferred_contact_time,
                   pr.preferred_vendor_tags
            FROM mms_member m
            LEFT JOIN mms_member_preference pr USING (inbr_account_id)
            """,
        )

        show(
            "⑤ 會員的地址（含縣市行政區名稱）",
            "agent 要問「這次是哪個地址」時列給會員選",
            cur,
            """
            SELECT a.label, c.name AS county, d.name AS district, a.detail, a.is_default
            FROM mms_member_address a
            JOIN sys_county c   ON c.code = a.county_code
            JOIN sys_district d ON d.code = a.district_code
            ORDER BY a.is_default DESC
            """,
        )

        show(
            "⑥ 會員家裡的冷氣（含推算機齡）",
            "免除「你冷氣什麼牌子、幾年了」這種重複詢問",
            cur,
            """
            SELECT ap.location, ap.brand, ap.variant, ap.installed_year,
                   EXTRACT(YEAR FROM now())::int - ap.installed_year AS age_years
            FROM mms_member_appliance ap
            WHERE ap.kind = 'AC'
            ORDER BY ap.installed_year
            """,
        )

        show(
            "⑦ 每個廠商服務幾個行政區",
            "資料健檢：確認 coverage 沒灌錯（NULL 代表全區）",
            cur,
            """
            SELECT v.vendor_id, v.name,
                   count(*) FILTER (WHERE cv.district_code IS NOT NULL) AS 指定行政區數,
                   count(*) FILTER (WHERE cv.district_code IS NULL)     AS 全區縣市數
            FROM mms_vendor v
            LEFT JOIN mms_vendor_coverage cv ON cv.vendor_id = v.vendor_id
            GROUP BY v.vendor_id, v.name
            ORDER BY v.vendor_id
            """,
        )

        show(
            "⑧ 用 view 看攤平後的服務區域",
            "人工核對資料時最直覺的視角",
            cur,
            "SELECT * FROM v_vendor_service_area WHERE county_name = %s ORDER BY vendor_id LIMIT 15",
            ("台北市",),
        )

    print("\n全部查詢完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
