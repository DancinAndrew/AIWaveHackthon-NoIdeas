"""確認 PostgreSQL driver 裝好了。"""

from __future__ import annotations

try:
    import psycopg

    print(f"psycopg OK version={psycopg.__version__}")
except Exception as err:  # noqa: BLE001
    print(f"psycopg 不可用：{type(err).__name__}: {err}")

try:
    import pg8000.native  # noqa: F401

    print("pg8000 OK（純 Python 備援 driver）")
except Exception as err:  # noqa: BLE001
    print(f"pg8000 不可用：{type(err).__name__}: {err}")
