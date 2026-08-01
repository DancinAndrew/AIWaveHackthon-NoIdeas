"""RDS PostgreSQL 連線設定。

連線資訊從環境變數讀（`rds_create.py` 會自動寫進 repo 根目錄的 .env）：
    PGHOST / PGPORT / PGDATABASE / PGUSER / PGPASSWORD

這些變數名沿用 PostgreSQL 官方慣例，所以 psql、DBeaver 等工具也認得，
你在終端機 `psql` 不用打一長串參數。
"""

from __future__ import annotations

import os

import psycopg

# 大額項目：真的要換就是常規維修的數倍，報價要獨立揭露而不是混進區間。
# 與 quoting.py 的 MAJOR_ITEM_CODES 同一份定義，灌資料時寫進 is_major 欄位。
MAJOR_ITEM_CODES = {"AC_COMP"}


def pg_settings() -> dict[str, str]:
    return {
        "host": os.environ.get("PGHOST", ""),
        "port": os.environ.get("PGPORT", "5432"),
        "dbname": os.environ.get("PGDATABASE", "oplifeagent"),
        "user": os.environ.get("PGUSER", "opadmin"),
        "password": os.environ.get("PGPASSWORD", ""),
    }


def dsn_summary() -> str:
    """給人看的連線描述，刻意不印密碼。"""
    s = pg_settings()
    host = s["host"] or "(未設定 PGHOST)"
    return f"{s['user']}@{host}:{s['port']}/{s['dbname']}"


def connect(*, autocommit: bool = False) -> psycopg.Connection:
    s = pg_settings()
    if not s["host"]:
        raise RuntimeError("環境變數 PGHOST 沒有設定，請先執行 scripts/rds_create.py")
    return psycopg.connect(
        host=s["host"],
        port=int(s["port"]),
        dbname=s["dbname"],
        user=s["user"],
        password=s["password"],
        # RDS 預設支援 TLS。require 表示一定要加密，但不驗證憑證鏈；
        # 正式環境應該用 verify-full 並帶上 AWS 的 CA bundle。
        sslmode="require",
        connect_timeout=15,
        autocommit=autocommit,
    )
