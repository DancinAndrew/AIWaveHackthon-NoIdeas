from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Delegation:
    """Supervisor decision consumed by the transport-independent core."""

    service_type: str | None
    target_agent: str | None
    mode: str


class SupervisorOrchestrator(Protocol):
    """Boundary implemented by deterministic local and AgentCore adapters."""

    mode: str

    def delegate(self, message: str) -> Delegation: ...


class DeterministicDemoOrchestrator:
    """Offline fallback with an explicit, non-AgentCore execution label."""

    mode = "deterministic-demo"

    _utility_terms = (
        "水管",
        "漏水",
        "水龍頭",
        "馬桶",
        "排水",
        "插座",
        "跳電",
        "電線",
        "冒煙",
        "火花",
        "熱水器",
        "水電",
    )

    def delegate(self, message: str) -> Delegation:
        if any(term in message for term in self._utility_terms):
            return Delegation(
                service_type="utility_repair",
                target_agent="utility_repair_agent",
                mode=self.mode,
            )
        return Delegation(service_type=None, target_agent=None, mode=self.mode)
