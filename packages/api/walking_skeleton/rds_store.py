"""Transactionally persist the demo aggregate in private RDS PostgreSQL.

The water-repair walking skeleton intentionally uses one small JSONB aggregate
row.  ``SELECT ... FOR UPDATE`` serializes writers across separate Flask and
Gateway Lambda containers, while the application service keeps its existing
typed state-transition rules.  This is a demo persistence adapter, not the
future normalized reporting schema.
"""

from __future__ import annotations

import copy
import json
import os
import threading
from collections.abc import Callable, Mapping
from typing import Any

from .errors import ApplicationError
from .store import InMemoryStore


SCHEMA_VERSION = 1
STATE_FIELDS = (
    "conversations",
    "messages",
    "service_requests",
    "artifacts",
    "artifact_versions",
    "progress",
    "tasks",
    "events",
    "point_ledger",
)


class RdsJsonStore(InMemoryStore):
    """Use the existing store contract with an RDS transaction per operation."""

    def __init__(self, *, connection_factory: Callable[[], Any] | None = None) -> None:
        super().__init__()
        self.lock = _TransactionLock(
            self,
            connection_factory or _connect_from_environment,
        )

    def _load_from_connection(self, connection: Any) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS aiwave_demo_state (
                    aggregate_id smallint PRIMARY KEY CHECK (aggregate_id = 1),
                    schema_version integer NOT NULL,
                    state jsonb NOT NULL,
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            cursor.execute(
                """
                INSERT INTO aiwave_demo_state (aggregate_id, schema_version, state)
                VALUES (1, %s, %s::jsonb)
                ON CONFLICT (aggregate_id) DO NOTHING
                """,
                (SCHEMA_VERSION, "{}"),
            )
            cursor.execute(
                """
                SELECT state
                FROM aiwave_demo_state
                WHERE aggregate_id = 1
                FOR UPDATE
                """
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("RDS demo state row was not created")
        raw_state = row[0]
        if isinstance(raw_state, str):
            raw_state = json.loads(raw_state)
        if not isinstance(raw_state, Mapping):
            raise RuntimeError("RDS demo state must be a JSON object")
        self._restore_state(raw_state)

    def _save_to_connection(self, connection: Any) -> None:
        encoded = json.dumps(
            self._snapshot_state(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE aiwave_demo_state
                SET state = %s::jsonb,
                    schema_version = %s,
                    updated_at = now()
                WHERE aggregate_id = 1
                """,
                (encoded, SCHEMA_VERSION),
            )

    def _snapshot_state(self) -> dict[str, Any]:
        snapshot = {
            "schemaVersion": SCHEMA_VERSION,
            **{
                field: copy.deepcopy(getattr(self, field))
                for field in STATE_FIELDS
            },
            "idempotency": [
                {
                    "lookup": list(lookup),
                    "entry": copy.deepcopy(entry),
                }
                for lookup, entry in sorted(self.idempotency.items())
            ],
        }
        return snapshot

    def _restore_state(self, snapshot: Mapping[str, Any]) -> None:
        schema_version = snapshot.get("schemaVersion", SCHEMA_VERSION)
        if schema_version != SCHEMA_VERSION:
            raise RuntimeError(
                f"unsupported RDS demo state schema version: {schema_version!r}"
            )
        for field in STATE_FIELDS:
            value = snapshot.get(field, {})
            if not isinstance(value, Mapping):
                raise RuntimeError(f"RDS demo state field {field} must be an object")
            setattr(self, field, copy.deepcopy(dict(value)))

        restored_idempotency: dict[tuple[str, str, str], dict[str, Any]] = {}
        raw_idempotency = snapshot.get("idempotency", [])
        if not isinstance(raw_idempotency, list):
            raise RuntimeError("RDS demo idempotency state must be an array")
        for item in raw_idempotency:
            if not isinstance(item, Mapping):
                raise RuntimeError("RDS demo idempotency item must be an object")
            lookup = item.get("lookup")
            entry = item.get("entry")
            if (
                not isinstance(lookup, list)
                or len(lookup) != 3
                or not all(isinstance(part, str) for part in lookup)
                or not isinstance(entry, Mapping)
            ):
                raise RuntimeError("RDS demo idempotency item is malformed")
            restored_idempotency[tuple(lookup)] = copy.deepcopy(dict(entry))
        self.idempotency = restored_idempotency


class _TransactionLock:
    """Reentrant process lock backed by one outer PostgreSQL transaction."""

    def __init__(
        self,
        store: RdsJsonStore,
        connection_factory: Callable[[], Any],
    ) -> None:
        self._store = store
        self._connection_factory = connection_factory
        self._mutex = threading.RLock()
        self._depth = 0
        self._connection: Any | None = None

    def __enter__(self) -> "_TransactionLock":
        self._mutex.acquire()
        try:
            if self._depth == 0:
                self._connection = self._connection_factory()
                self._store._load_from_connection(self._connection)
            self._depth += 1
            return self
        except Exception:
            if self._connection is not None:
                try:
                    self._connection.rollback()
                finally:
                    self._connection.close()
                    self._connection = None
            self._mutex.release()
            raise

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: Any,
    ) -> bool:
        self._depth -= 1
        try:
            if self._depth > 0:
                return False
            if self._connection is None:
                raise RuntimeError("RDS transaction connection is missing")
            should_commit = exception_type is None or issubclass(
                exception_type,
                ApplicationError,
            )
            if should_commit:
                self._store._save_to_connection(self._connection)
                self._connection.commit()
            else:
                self._connection.rollback()
            return False
        finally:
            if self._depth == 0 and self._connection is not None:
                self._connection.close()
                self._connection = None
            self._mutex.release()


def _connect_from_environment() -> Any:
    secret_arn = os.getenv("DATABASE_SECRET_ARN", "").strip()
    if not secret_arn:
        raise RuntimeError("DATABASE_SECRET_ARN is required for the RDS store")

    import boto3
    import psycopg

    secret_response = boto3.client(
        "secretsmanager",
        region_name=os.getenv("AWS_REGION", "us-west-2"),
    ).get_secret_value(SecretId=secret_arn)
    secret_text = secret_response.get("SecretString")
    if not isinstance(secret_text, str):
        raise RuntimeError("database secret must contain a SecretString")
    secret = json.loads(secret_text)
    if not isinstance(secret, Mapping):
        raise RuntimeError("database secret must contain a JSON object")

    required = ("username", "password")
    missing = [name for name in required if not isinstance(secret.get(name), str)]
    if missing:
        raise RuntimeError("database secret is missing required connection fields")
    host = secret.get("host") or os.getenv("DATABASE_HOST")
    database_name = secret.get("dbname") or os.getenv("DATABASE_NAME", "aiwave")
    port = secret.get("port", 5432)
    if not isinstance(host, str) or not host:
        raise RuntimeError("database host is missing")

    return psycopg.connect(
        host=host,
        port=int(port),
        dbname=str(database_name),
        user=secret["username"],
        password=secret["password"],
        sslmode="require",
        connect_timeout=10,
        autocommit=False,
    )
