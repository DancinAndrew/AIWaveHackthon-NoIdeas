"""Cross-category flow boundary for the walking skeleton.

`WalkingSkeletonService` owns everything that is identical across service
types: conversations, messages, artifacts versioning, provider tasks,
rematching, idempotency, authorization and the progress projection. Everything
that differs per service type lives behind `ServiceFlow`.

The protocol is intentionally transport-independent. Implementations receive the
service instance as an explicit context argument instead of importing Flask, so
the same flow objects can be driven by the Flask app or by an AgentCore Gateway
tool Lambda without duplicating business logic.
"""

from __future__ import annotations

from typing import Any, Protocol


# Stages shared by every service type. A flow MAY override a label to use
# domain wording and MAY add stages that only exist in its own lifecycle, but it
# MUST NOT rename a shared stage, because reminders and the progress projection
# branch on these names across categories.
BASE_STAGE_LABELS: dict[str, str] = {
    "collecting_details": "Agent 正在確認需求",
    "awaiting_resident_confirmation": "需求文件待住戶確認",
    "waiting_provider_response": "已媒合廠商，等待回覆",
    "waiting_resident_information": "廠商需要住戶補充資訊",
    "rematching": "正在改派下一位廠商",
    "provider_confirmed": "廠商已確認，可依約到場",
}


class UnsupportedServiceTypeError(RuntimeError):
    """A stored request references a service type with no registered flow.

    This is a server-side inconsistency, not client input, so it is deliberately
    not an `ApplicationError`: the transport layer maps it to a redacted 500
    instead of silently falling back to another category's flow.
    """

    def __init__(self, service_type: object) -> None:
        super().__init__(f"no registered service flow for {service_type!r}")
        self.service_type = service_type


class ServiceFlow(Protocol):
    """Per-service-type behaviour required by the shared skeleton."""

    service_type: str
    agent_name: str
    service_name: str
    schema_version: str
    stage_labels: dict[str, str]
    # Short, resident-facing hint describing what this flow can handle. The
    # supervisor composes greetings and "unsupported request" replies from the
    # registered flows so wording never has to be duplicated in the skeleton.
    routing_hint: str
    # True only for flows where the resident picks one option out of several.
    # The selection endpoint refuses any request whose flow does not declare it,
    # so a utility case can never be driven through a product-only route.
    supports_selection: bool

    def init_request(self, request: dict[str, Any], content: str) -> None:
        """Add category-specific fields to a freshly created service request."""

    def start(
        self, svc: Any, conversation: dict[str, Any], request: dict[str, Any]
    ) -> dict[str, Any]:
        """Produce the first assistant turn after the supervisor delegated."""

    def continue_turn(
        self,
        svc: Any,
        conversation: dict[str, Any],
        request: dict[str, Any],
        content: str,
    ) -> dict[str, Any]:
        """Advance an existing request with a new resident message."""

    def build_summary(self, request: dict[str, Any]) -> str:
        """Human-readable, non-sensitive artifact summary.

        Only called once every field required by the artifact is present.
        """

    def fallback_summary(self, request: dict[str, Any]) -> str:
        """Summary shown before an artifact exists, while fields are still missing."""

    def build_canonical(self, request: dict[str, Any]) -> dict[str, Any]:
        """Canonical artifact payload stored for audit and provider rendering."""

    def projection_fields(self, request: dict[str, Any]) -> dict[str, Any]:
        """Category-specific fields merged into the service request projection."""

    def list_providers(self) -> tuple[dict[str, Any], ...]:
        """Every provider this flow can dispatch to."""

    def rank_candidates(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        """Deterministic hard-condition filter plus ordering for dispatch."""

    def validate_accept(self, payload: dict[str, Any]) -> None:
        """Raise ValidationError when an accept is missing required fields."""

    def apply_accept(
        self, request: dict[str, Any], provider: dict[str, Any], payload: dict[str, Any]
    ) -> str:
        """Record accept details on the request and return the final message."""

    def selection_version(self, request: dict[str, Any]) -> int:
        """Optimistic-lock value a resident must echo back when selecting.

        Only meaningful when `supports_selection` is True.
        """

    def select(
        self, svc: Any, request: dict[str, Any], *, sku: str, expected_version: int
    ) -> dict[str, Any]:
        """Record the resident's choice and produce the confirmable artifact."""
