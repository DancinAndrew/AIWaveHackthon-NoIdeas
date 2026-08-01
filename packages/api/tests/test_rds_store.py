from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from typing import Any


API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from walking_skeleton.errors import ConflictError  # noqa: E402
from walking_skeleton.rds_store import RdsJsonStore  # noqa: E402


class FakeDatabase:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.connection_count = 0

    def connect(self) -> "FakeConnection":
        self.connection_count += 1
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, database: FakeDatabase) -> None:
        self.database = database
        self.working = copy.deepcopy(database.state)
        self.selected: tuple[dict[str, Any]] | None = None
        self.closed = False

    def cursor(self) -> "FakeConnection":
        return self

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str, parameters: tuple[Any, ...] = ()) -> None:
        normalized = " ".join(statement.split()).upper()
        if normalized.startswith("CREATE TABLE"):
            return
        if normalized.startswith("INSERT INTO"):
            return
        if normalized.startswith("SELECT"):
            self.selected = (copy.deepcopy(self.working),)
            return
        if normalized.startswith("UPDATE"):
            self.working = json.loads(parameters[0])
            return
        raise AssertionError(f"unexpected SQL: {statement}")

    def fetchone(self) -> tuple[dict[str, Any]] | None:
        return self.selected

    def commit(self) -> None:
        self.database.state = copy.deepcopy(self.working)

    def rollback(self) -> None:
        self.working = copy.deepcopy(self.database.state)

    def close(self) -> None:
        self.closed = True


class RdsJsonStoreTests(unittest.TestCase):
    def test_state_survives_across_store_instances(self) -> None:
        database = FakeDatabase()
        first = RdsJsonStore(connection_factory=database.connect)
        with first.lock:
            first.conversations["conv-1"] = {"residentId": "resident-1"}
            first.messages["conv-1"] = [{"content": "漏水"}]

        second = RdsJsonStore(connection_factory=database.connect)
        with second.lock:
            self.assertEqual(
                second.conversations["conv-1"]["residentId"],
                "resident-1",
            )
            self.assertEqual(second.messages["conv-1"][0]["content"], "漏水")

    def test_nested_application_operations_share_one_database_transaction(self) -> None:
        database = FakeDatabase()
        store = RdsJsonStore(connection_factory=database.connect)

        with store.lock:
            result = store.idempotent(
                actor_id="provider-1",
                operation="accept",
                key="key-1",
                payload={"version": 1},
                command=lambda: {"accepted": True},
            )

        self.assertEqual(result, {"accepted": True})
        self.assertEqual(database.connection_count, 1)

        reloaded = RdsJsonStore(connection_factory=database.connect)
        replay = reloaded.idempotent(
            actor_id="provider-1",
            operation="accept",
            key="key-1",
            payload={"version": 1},
            command=lambda: self.fail("idempotent command must not repeat"),
        )
        self.assertEqual(replay, {"accepted": True})

    def test_expected_application_error_keeps_intentional_progress_projection(self) -> None:
        database = FakeDatabase()
        store = RdsJsonStore(connection_factory=database.connect)

        with self.assertRaises(ConflictError):
            with store.lock:
                store.progress["request-1"] = {"stage": "rematching"}
                raise ConflictError("needs admin")

        reloaded = RdsJsonStore(connection_factory=database.connect)
        with reloaded.lock:
            self.assertEqual(
                reloaded.progress["request-1"]["stage"],
                "rematching",
            )

    def test_unexpected_error_rolls_back_partial_state(self) -> None:
        database = FakeDatabase()
        store = RdsJsonStore(connection_factory=database.connect)

        with self.assertRaises(RuntimeError):
            with store.lock:
                store.tasks["partial"] = {"status": "invalid"}
                raise RuntimeError("unexpected")

        reloaded = RdsJsonStore(connection_factory=database.connect)
        with reloaded.lock:
            self.assertNotIn("partial", reloaded.tasks)


if __name__ == "__main__":
    unittest.main()
