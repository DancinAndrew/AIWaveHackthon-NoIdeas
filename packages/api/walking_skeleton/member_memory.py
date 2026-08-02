"""Member long-term memory: registered addresses, appliances and preferences.

This is the cross-session half of "the assistant already knows your home". The
tables (``mms_member_address`` / ``mms_member_appliance`` /
``mms_member_preference``) and the merge semantics originate from the earlier
dual-agent prototype under ``op_agent/``; this module brings them onto the
walking skeleton execution path with three boundaries made explicit:

* PII never enters the projection. ``mms_member_address.detail`` is not even
  selected, so the street address cannot reach a prompt, a trace or a log.
* Preference writes are field level. Arrays union, scalars overwrite, notes keep
  the most recent entries. A single observation never blanks the rest of the row.
* Memory is a default, not an authority. The application service still validates
  a remembered district against the controlled district table before using it.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

MAX_NOTES = 20
MAX_APPLIANCES = 20
MAX_ADDRESSES = 10
MAX_TAGS = 20
MAX_NOTE_LENGTH = 200
DEFAULT_PRICE_SENSITIVITY = 0.5

APPLIANCE_KIND_LABELS = {
    "AC": "冷氣",
    "WASHER": "洗衣機",
    "FRIDGE": "冰箱",
    "WATER_HEATER": "熱水器",
}
# Appliance kinds a utility repair case can plausibly be about.
UTILITY_APPLIANCE_KINDS = ("WATER_HEATER", "AC", "WASHER")


@dataclass(frozen=True, slots=True)
class MemberAddress:
    """A registered address, reduced to what matching actually needs.

    The street detail is intentionally not represented. County and district are
    enough to match a provider, and anything more would be PII in a prompt.
    """

    county_code: str
    district_code: str
    district_name: str
    label: str | None = None
    is_default: bool = False


@dataclass(frozen=True, slots=True)
class MemberAppliance:
    appliance_id: str
    kind: str
    brand: str | None = None
    model: str | None = None
    variant: str | None = None
    installed_year: int | None = None
    location: str | None = None

    def describe(self) -> str:
        """A short human phrase the agent can confirm instead of re-asking."""

        parts = [
            self.location,
            f"{self.installed_year} 年" if self.installed_year else None,
            self.brand,
            self.variant,
            APPLIANCE_KIND_LABELS.get(self.kind, self.kind),
        ]
        return "".join(part for part in parts if part)


@dataclass(frozen=True, slots=True)
class MemberPreference:
    price_sensitivity: float = DEFAULT_PRICE_SENSITIVITY
    preferred_contact_time: str | None = None
    preferred_vendor_tags: tuple[str, ...] = ()
    blocked_vendor_ids: tuple[str, ...] = ()
    interested_categories: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def is_unset(self) -> bool:
        """True when nothing has been learned yet.

        Matching keeps its plain deterministic ordering in that case, so enabling
        the memory backend cannot silently reorder candidates for a member the
        platform knows nothing about.
        """

        return self == MemberPreference()

    def to_payload(self) -> dict[str, Any]:
        return {
            "priceSensitivity": self.price_sensitivity,
            "preferredContactTime": self.preferred_contact_time,
            "preferredVendorTags": list(self.preferred_vendor_tags),
            "blockedVendorIds": list(self.blocked_vendor_ids),
            "interestedCategories": list(self.interested_categories),
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class MemberMemory:
    addresses: tuple[MemberAddress, ...] = ()
    appliances: tuple[MemberAppliance, ...] = ()
    preference: MemberPreference = field(default_factory=MemberPreference)

    @property
    def is_empty(self) -> bool:
        return not self.addresses and not self.appliances

    @property
    def default_address(self) -> MemberAddress | None:
        """The address usable without asking.

        With several registered addresses the resident has to say which one, so
        only an unambiguous default counts. Guessing would silently dispatch a
        technician to the wrong home.
        """

        defaults = [address for address in self.addresses if address.is_default]
        if len(defaults) == 1:
            return defaults[0]
        if len(self.addresses) == 1:
            return self.addresses[0]
        return None

    def appliance_for(self, kinds: Sequence[str] = UTILITY_APPLIANCE_KINDS) -> MemberAppliance | None:
        for kind in kinds:
            for appliance in self.appliances:
                if appliance.kind == kind:
                    return appliance
        return None

    def to_known_fields(self) -> dict[str, Any]:
        """PII-masked projection safe to send to the model and MCP tools."""

        fields: dict[str, Any] = {}
        default_address = self.default_address
        if default_address is not None:
            fields["rememberedDistrictName"] = default_address.district_name
        elif len(self.addresses) > 1:
            fields["rememberedDistrictChoices"] = [
                address.district_name for address in self.addresses
            ]
        appliance = self.appliance_for()
        if appliance is not None:
            fields["rememberedAppliance"] = appliance.describe()
        if self.preference.preferred_contact_time:
            fields["rememberedContactTime"] = self.preference.preferred_contact_time
        return fields


EMPTY_MEMORY = MemberMemory()


def merge_preference_fields(
    base: MemberPreference,
    patch: Mapping[str, Any],
) -> MemberPreference:
    """Field-level merge, mirroring ``op_agent.repo.base.merge_prefs``.

    Arrays union with de-duplication, scalars overwrite, notes keep the most
    recent entries. Keys absent from the patch are left untouched, so recording
    one observation cannot blank the rest of the row.
    """

    updates: dict[str, Any] = {}

    price = patch.get("priceSensitivity")
    if isinstance(price, (int, float)) and not isinstance(price, bool):
        updates["price_sensitivity"] = max(0.0, min(float(price), 1.0))

    contact_time = patch.get("preferredContactTime")
    if isinstance(contact_time, str) and contact_time in {"1", "2", "3"}:
        updates["preferred_contact_time"] = contact_time

    for patch_key, field_name in (
        ("preferredVendorTags", "preferred_vendor_tags"),
        ("blockedVendorIds", "blocked_vendor_ids"),
        ("interestedCategories", "interested_categories"),
    ):
        added = _clean_strings(patch.get(patch_key))
        if added:
            updates[field_name] = _union(getattr(base, field_name), added)[:MAX_TAGS]

    note = patch.get("note")
    added_notes = _clean_strings(patch.get("notes"))
    if isinstance(note, str) and note.strip():
        added_notes = (*added_notes, note.strip()[:MAX_NOTE_LENGTH])
    if added_notes:
        updates["notes"] = _union(base.notes, added_notes)[-MAX_NOTES:]

    if not updates:
        return base
    return replace(base, **updates)


class MemberMemoryStore(Protocol):
    """Boundary implemented by the demo fixture store and the RDS adapter."""

    backend: str

    def load(self, resident_id: str) -> MemberMemory: ...

    def merge_preference(
        self,
        resident_id: str,
        patch: Mapping[str, Any],
    ) -> MemberPreference: ...


class NullMemberMemoryStore:
    """No memory configured. Every turn behaves as a first-time resident."""

    backend = "none"

    def load(self, resident_id: str) -> MemberMemory:
        return EMPTY_MEMORY

    def merge_preference(
        self,
        resident_id: str,
        patch: Mapping[str, Any],
    ) -> MemberPreference:
        return MemberPreference()


class InMemoryMemberMemoryStore:
    """Local demo and test store with the same merge semantics as RDS."""

    backend = "in-memory"

    def __init__(self, memories: Mapping[str, MemberMemory] | None = None) -> None:
        self._memories: dict[str, MemberMemory] = dict(memories or {})

    def load(self, resident_id: str) -> MemberMemory:
        return self._memories.get(resident_id, EMPTY_MEMORY)

    def merge_preference(
        self,
        resident_id: str,
        patch: Mapping[str, Any],
    ) -> MemberPreference:
        memory = self._memories.get(resident_id, EMPTY_MEMORY)
        merged = merge_preference_fields(memory.preference, patch)
        self._memories[resident_id] = replace(memory, preference=merged)
        return merged


class PostgresMemberMemoryStore:
    """Read the member tables and merge preferences in one transaction.

    ``mms_member_address.detail`` is deliberately absent from the SELECT list:
    the street address is never loaded, so it cannot be leaked downstream.
    """

    backend = "rds"

    ADDRESS_SQL = """
        SELECT a.label, a.county_code, a.district_code, d.name, a.is_default
        FROM mms_member_address a
        JOIN sys_district d ON d.code = a.district_code
        WHERE a.inbr_account_id = %s
        ORDER BY a.is_default DESC, a.id
        LIMIT %s
    """
    APPLIANCE_SQL = """
        SELECT appliance_id, kind, brand, model, variant, installed_year, location
        FROM mms_member_appliance
        WHERE inbr_account_id = %s
        ORDER BY id
        LIMIT %s
    """
    PREFERENCE_SQL = """
        SELECT price_sensitivity, preferred_contact_time, preferred_vendor_tags,
               blocked_vendor_ids, interested_categories, notes
        FROM mms_member_preference
        WHERE inbr_account_id = %s
    """
    UPSERT_PREFERENCE_SQL = """
        INSERT INTO mms_member_preference (
            inbr_account_id, price_sensitivity, preferred_contact_time,
            preferred_vendor_tags, blocked_vendor_ids, interested_categories,
            notes, upd_time
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (inbr_account_id) DO UPDATE SET
            price_sensitivity = EXCLUDED.price_sensitivity,
            preferred_contact_time = EXCLUDED.preferred_contact_time,
            preferred_vendor_tags = EXCLUDED.preferred_vendor_tags,
            blocked_vendor_ids = EXCLUDED.blocked_vendor_ids,
            interested_categories = EXCLUDED.interested_categories,
            notes = EXCLUDED.notes,
            upd_time = now()
    """

    def __init__(self, *, connection_factory: Callable[[], Any]) -> None:
        self._connection_factory = connection_factory

    def load(self, resident_id: str) -> MemberMemory:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(self.ADDRESS_SQL, (resident_id, MAX_ADDRESSES))
                addresses = tuple(
                    MemberAddress(
                        label=_optional_text(row[0]),
                        county_code=str(row[1]),
                        district_code=str(row[2]),
                        district_name=str(row[3]),
                        is_default=bool(row[4]),
                    )
                    for row in cursor.fetchall() or ()
                )
                cursor.execute(self.APPLIANCE_SQL, (resident_id, MAX_APPLIANCES))
                appliances = tuple(
                    MemberAppliance(
                        appliance_id=str(row[0]),
                        kind=str(row[1]),
                        brand=_optional_text(row[2]),
                        model=_optional_text(row[3]),
                        variant=_optional_text(row[4]),
                        installed_year=int(row[5]) if row[5] is not None else None,
                        location=_optional_text(row[6]),
                    )
                    for row in cursor.fetchall() or ()
                )
                cursor.execute(self.PREFERENCE_SQL, (resident_id,))
                preference = _preference_from_row(cursor.fetchone())
            connection.commit()
        finally:
            connection.close()
        return MemberMemory(
            addresses=addresses,
            appliances=appliances,
            preference=preference,
        )

    def merge_preference(
        self,
        resident_id: str,
        patch: Mapping[str, Any],
    ) -> MemberPreference:
        import json

        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                # Read the current row inside the same transaction so a
                # concurrent turn cannot make this write clobber its fields.
                cursor.execute(self.PREFERENCE_SQL + " FOR UPDATE", (resident_id,))
                current = _preference_from_row(cursor.fetchone())
                merged = merge_preference_fields(current, patch)
                cursor.execute(
                    self.UPSERT_PREFERENCE_SQL,
                    (
                        resident_id,
                        merged.price_sensitivity,
                        merged.preferred_contact_time,
                        json.dumps(list(merged.preferred_vendor_tags)),
                        json.dumps(list(merged.blocked_vendor_ids)),
                        json.dumps(list(merged.interested_categories)),
                        json.dumps(list(merged.notes), ensure_ascii=False),
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return merged


def create_member_memory_store_from_environment() -> MemberMemoryStore:
    """Select the memory backend without turning it on implicitly.

    The default is ``none`` so the existing deterministic demo flow, its contract
    tests and the browser E2E keep their current turn-by-turn behaviour. The
    personalisation demo is opted into explicitly.
    """

    backend = os.getenv("MEMBER_MEMORY_BACKEND", "none").strip().lower()
    if backend in {"", "none"}:
        return NullMemberMemoryStore()
    if backend == "demo":
        return InMemoryMemberMemoryStore(demo_memories())
    if backend == "rds":
        from .rds_store import _connect_from_environment

        return PostgresMemberMemoryStore(
            connection_factory=_connect_from_environment
        )
    raise ValueError(f"unsupported MEMBER_MEMORY_BACKEND: {backend!r}")


def demo_memories() -> dict[str, MemberMemory]:
    """Fixture memory for the demo resident.

    The district matches the two mock utility providers in
    ``data/mock/master/provider_service_areas.json`` so the rematch path stays
    demonstrable, and no vendor is blocked by default.
    """

    return {
        "resident-demo-001": MemberMemory(
            addresses=(
                MemberAddress(
                    county_code="01",
                    district_code="010",
                    district_name="內湖區",
                    label="住家",
                    is_default=True,
                ),
            ),
            appliances=(
                MemberAppliance(
                    appliance_id="A1",
                    kind="WATER_HEATER",
                    brand="櫻花",
                    model="SH-9105",
                    variant="數位恆溫",
                    installed_year=2019,
                    location="陽台",
                ),
                MemberAppliance(
                    appliance_id="A2",
                    kind="AC",
                    brand="大金",
                    variant="分離式",
                    installed_year=2018,
                    location="主臥",
                ),
            ),
            preference=MemberPreference(
                price_sensitivity=0.8,
                preferred_contact_time="2",
                preferred_vendor_tags=("原廠零件",),
                notes=("偏好先報價再施工",),
            ),
        )
    }


def _preference_from_row(row: Any) -> MemberPreference:
    if not row:
        return MemberPreference()
    price = row[0]
    return MemberPreference(
        price_sensitivity=(
            max(0.0, min(float(price), 1.0))
            if price is not None
            else DEFAULT_PRICE_SENSITIVITY
        ),
        preferred_contact_time=_optional_text(row[1]),
        preferred_vendor_tags=_clean_strings(row[2]),
        blocked_vendor_ids=_clean_strings(row[3]),
        interested_categories=_clean_strings(row[4]),
        notes=_clean_strings(row[5])[-MAX_NOTES:],
    )


def _clean_strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip()[:MAX_NOTE_LENGTH],) if value.strip() else ()
    if not isinstance(value, Iterable):
        return ()
    cleaned: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            cleaned.append(item.strip()[:MAX_NOTE_LENGTH])
    return tuple(cleaned)


def _union(base: Sequence[str], added: Sequence[str]) -> tuple[str, ...]:
    out: list[str] = []
    for item in (*base, *added):
        if item not in out:
            out.append(item)
    return tuple(out)


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()[:MAX_NOTE_LENGTH]
    return None
