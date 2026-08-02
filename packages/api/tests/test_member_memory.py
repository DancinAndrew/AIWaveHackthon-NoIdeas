"""Contract tests for member long-term memory.

Three things must hold, and each one has failed in a real system before:
the street address must never reach a projection, one observation must not blank
the rest of the preference row, and several registered addresses must not be
silently guessed between.
"""

from __future__ import annotations

import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from walking_skeleton.member_memory import (  # noqa: E402
    MAX_NOTES,
    InMemoryMemberMemoryStore,
    MemberAddress,
    MemberAppliance,
    MemberMemory,
    MemberPreference,
    NullMemberMemoryStore,
    PostgresMemberMemoryStore,
    create_member_memory_store_from_environment,
    demo_memories,
    merge_preference_fields,
)

HOME = MemberAddress(
    county_code="01",
    district_code="010",
    district_name="內湖區",
    label="住家",
    is_default=True,
)
PARENTS = MemberAddress(
    county_code="01",
    district_code="005",
    district_name="信義區",
    label="爸媽家",
)
WATER_HEATER = MemberAppliance(
    appliance_id="A1",
    kind="WATER_HEATER",
    brand="櫻花",
    variant="數位恆溫",
    installed_year=2019,
    location="陽台",
)


class MemoryProjectionTests(unittest.TestCase):
    def test_registered_address_has_no_place_to_hold_a_street_detail(self) -> None:
        self.assertNotIn("detail", MemberAddress.__slots__)
        self.assertNotIn(
            "detail", PostgresMemberMemoryStore.ADDRESS_SQL.replace("is_default", "")
        )

    def test_single_default_address_is_usable_without_asking(self) -> None:
        memory = MemberMemory(addresses=(HOME,))

        self.assertEqual(memory.default_address, HOME)
        self.assertEqual(memory.to_known_fields()["rememberedDistrictName"], "內湖區")

    def test_two_defaults_are_treated_as_ambiguous(self) -> None:
        memory = MemberMemory(
            addresses=(HOME, replace(PARENTS, is_default=True))
        )

        self.assertIsNone(memory.default_address)

    def test_two_addresses_without_a_default_must_be_disambiguated(self) -> None:
        memory = MemberMemory(
            addresses=(
                MemberAddress("01", "010", "內湖區", "住家"),
                MemberAddress("01", "005", "信義區", "爸媽家"),
            )
        )

        known = memory.to_known_fields()
        self.assertIsNone(memory.default_address)
        self.assertNotIn("rememberedDistrictName", known)
        self.assertEqual(known["rememberedDistrictChoices"], ["內湖區", "信義區"])

    def test_appliance_is_described_so_the_agent_can_confirm_it(self) -> None:
        memory = MemberMemory(appliances=(WATER_HEATER,))

        self.assertEqual(
            memory.to_known_fields()["rememberedAppliance"],
            "陽台2019 年櫻花數位恆溫熱水器",
        )

    def test_empty_memory_projects_nothing(self) -> None:
        self.assertEqual(MemberMemory().to_known_fields(), {})
        self.assertTrue(MemberMemory().is_empty)


class PreferenceMergeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = MemberPreference(
            price_sensitivity=0.4,
            preferred_contact_time="1",
            preferred_vendor_tags=("原廠零件",),
            blocked_vendor_ids=("V009",),
            notes=("偏好先報價再施工",),
        )

    def test_scalar_update_leaves_arrays_untouched(self) -> None:
        merged = merge_preference_fields(self.base, {"priceSensitivity": 0.9})

        self.assertEqual(merged.price_sensitivity, 0.9)
        self.assertEqual(merged.preferred_vendor_tags, ("原廠零件",))
        self.assertEqual(merged.blocked_vendor_ids, ("V009",))
        self.assertEqual(merged.notes, ("偏好先報價再施工",))

    def test_arrays_union_without_duplicates(self) -> None:
        merged = merge_preference_fields(
            self.base,
            {"preferredVendorTags": ["原廠零件", "當日到府"]},
        )

        self.assertEqual(merged.preferred_vendor_tags, ("原廠零件", "當日到府"))

    def test_blocked_vendors_accumulate(self) -> None:
        merged = merge_preference_fields(self.base, {"blockedVendorIds": ["V010"]})

        self.assertEqual(merged.blocked_vendor_ids, ("V009", "V010"))

    def test_a_single_note_is_appended_and_capped(self) -> None:
        merged = merge_preference_fields(
            self.base, {"notes": [f"note-{index}" for index in range(MAX_NOTES + 5)]}
        )

        self.assertEqual(len(merged.notes), MAX_NOTES)
        self.assertEqual(merged.notes[-1], f"note-{MAX_NOTES + 4}")

    def test_price_sensitivity_is_clamped(self) -> None:
        self.assertEqual(
            merge_preference_fields(self.base, {"priceSensitivity": 7}).price_sensitivity,
            1.0,
        )
        self.assertEqual(
            merge_preference_fields(self.base, {"priceSensitivity": -3}).price_sensitivity,
            0.0,
        )

    def test_unknown_and_ill_typed_keys_change_nothing(self) -> None:
        merged = merge_preference_fields(
            self.base,
            {
                "priceSensitivity": "very",
                "preferredContactTime": "9",
                "blockedVendorIds": "V010",
                "residentMobile": "0912345678",
            },
        )

        self.assertEqual(merged.price_sensitivity, 0.4)
        self.assertEqual(merged.preferred_contact_time, "1")
        self.assertEqual(merged.blocked_vendor_ids, ("V009", "V010"))

    def test_empty_patch_returns_the_same_preference(self) -> None:
        self.assertIs(merge_preference_fields(self.base, {}), self.base)


class StoreBehaviourTests(unittest.TestCase):
    def test_in_memory_store_persists_a_merge_across_calls(self) -> None:
        store = InMemoryMemberMemoryStore(
            {"resident-1": MemberMemory(addresses=(HOME,))}
        )

        store.merge_preference("resident-1", {"blockedVendorIds": ["V009"]})
        store.merge_preference("resident-1", {"priceSensitivity": 0.9})
        memory = store.load("resident-1")

        self.assertEqual(memory.preference.blocked_vendor_ids, ("V009",))
        self.assertEqual(memory.preference.price_sensitivity, 0.9)
        self.assertEqual(memory.addresses, (HOME,))

    def test_null_store_never_reports_memory(self) -> None:
        store = NullMemberMemoryStore()

        self.assertTrue(store.load("resident-1").is_empty)
        self.assertEqual(store.load("resident-1").to_known_fields(), {})

    def test_environment_default_keeps_memory_switched_off(self) -> None:
        self.assertEqual(
            create_member_memory_store_from_environment().backend, "none"
        )

    def test_demo_fixture_does_not_block_any_mock_provider(self) -> None:
        memory = demo_memories()["resident-demo-001"]

        self.assertEqual(memory.preference.blocked_vendor_ids, ())
        self.assertEqual(memory.default_address.district_name, "內湖區")


class FakeCursor:
    def __init__(self, database: "FakeDatabase") -> None:
        self.database = database
        self._rows: list[tuple[Any, ...]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str, parameters: tuple[Any, ...] = ()) -> None:
        normalized = " ".join(statement.split()).upper()
        self.database.statements.append(normalized)
        if "FROM MMS_MEMBER_ADDRESS" in normalized:
            self._rows = list(self.database.addresses)
        elif "FROM MMS_MEMBER_APPLIANCE" in normalized:
            self._rows = list(self.database.appliances)
        elif "FROM MMS_MEMBER_PREFERENCE" in normalized:
            self._rows = [self.database.preference] if self.database.preference else []
        elif normalized.startswith("INSERT INTO MMS_MEMBER_PREFERENCE"):
            self.database.written = parameters
            self.database.preference = (
                parameters[1],
                parameters[2],
                json.loads(parameters[3]),
                json.loads(parameters[4]),
                json.loads(parameters[5]),
                json.loads(parameters[6]),
            )
            self._rows = []

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._rows[0] if self._rows else None


class FakeConnection:
    def __init__(self, database: "FakeDatabase") -> None:
        self.database = database
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.database)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class FakeDatabase:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.connections: list[FakeConnection] = []
        self.written: tuple[Any, ...] | None = None
        self.addresses: list[tuple[Any, ...]] = [
            ("住家", "01", "010", "內湖區", True)
        ]
        self.appliances: list[tuple[Any, ...]] = [
            ("A1", "WATER_HEATER", "櫻花", "SH-9105", "數位恆溫", 2019, "陽台")
        ]
        self.preference: tuple[Any, ...] | None = (
            0.4,
            "1",
            ["原廠零件"],
            ["V009"],
            [],
            ["偏好先報價再施工"],
        )

    def connect(self) -> FakeConnection:
        connection = FakeConnection(self)
        self.connections.append(connection)
        return connection


class PostgresStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = FakeDatabase()
        self.store = PostgresMemberMemoryStore(
            connection_factory=self.database.connect
        )

    def test_load_projects_all_three_tables(self) -> None:
        memory = self.store.load("resident-1")

        self.assertEqual(memory.default_address.district_name, "內湖區")
        self.assertEqual(memory.appliances[0].brand, "櫻花")
        self.assertEqual(memory.preference.blocked_vendor_ids, ("V009",))
        self.assertTrue(self.database.connections[0].closed)

    def test_load_never_selects_the_street_detail(self) -> None:
        self.store.load("resident-1")

        address_statement = next(
            statement
            for statement in self.database.statements
            if "MMS_MEMBER_ADDRESS" in statement
        )
        self.assertNotIn("DETAIL", address_statement)

    def test_merge_locks_the_row_and_writes_a_field_level_merge(self) -> None:
        merged = self.store.merge_preference("resident-1", {"priceSensitivity": 0.9})

        self.assertTrue(
            any("FOR UPDATE" in statement for statement in self.database.statements)
        )
        self.assertEqual(merged.price_sensitivity, 0.9)
        self.assertEqual(merged.blocked_vendor_ids, ("V009",))
        self.assertEqual(json.loads(self.database.written[4]), ["V009"])
        self.assertEqual(
            json.loads(self.database.written[6]), ["偏好先報價再施工"]
        )
        self.assertTrue(self.database.connections[0].committed)

    def test_missing_preference_row_starts_from_defaults(self) -> None:
        self.database.preference = None

        merged = self.store.merge_preference("resident-1", {"blockedVendorIds": ["V1"]})

        self.assertEqual(merged.blocked_vendor_ids, ("V1",))
        self.assertEqual(merged.price_sensitivity, 0.5)


if __name__ == "__main__":
    unittest.main()
