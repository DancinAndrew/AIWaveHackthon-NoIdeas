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
    # The completion handshake is shared: every category needs the provider to
    # report the work done and the resident to accept before anything closes.
    # Declared here rather than per flow so `set_progress` cannot reject a stage
    # for a category that simply forgot to add the label.
    "awaiting_resident_acceptance": "廠商已回報完工，待住戶驗收",
    "completed": "服務已完成，點數已入帳",
}

# 驗收語句刻意保持明確，避免「好」「可以」這類泛用回覆意外觸發點數發放。
ACCEPTANCE_PHRASES = ("驗收", "確認完工", "確認完成", "施工沒問題")


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

    # ------------------------------------------------------------------
    # Model-backed turn contract
    #
    # The shared skeleton asks the routed agent to understand one turn, but the
    # field vocabulary is per-category: a product request has no `riskScreened`
    # and a utility request has no `budget`. These three methods keep that
    # vocabulary inside the flow so the skeleton never has to know it.
    # ------------------------------------------------------------------

    def known_fields(
        self, request: dict[str, Any] | None, memory: Any = None
    ) -> dict[str, Any]:
        """Non-sensitive fields already collected, sent as context to the agent.

        Remembered member values belong here too, but only in PII-masked form:
        a street address MUST NOT reach the agent or the turn payload.
        """

    def missing_fields(self, request: dict[str, Any] | None) -> tuple[str, ...]:
        """Fields still needed, in the order this flow wants them asked."""

    def turn_goal(
        self, request: dict[str, Any] | None, stage: str | None
    ) -> str | None:
        """What the agent should try to achieve on this turn.

        Returning None declares the stage model-free, and the skeleton then skips
        the model call entirely. A stage whose reply must be fixed wording, such
        as a safety hold, MUST return None.
        """

    def merge_agent_extraction(
        self, request: dict[str, Any], turn: Any
    ) -> dict[str, Any]:
        """Apply validated model output and report what still needs a Flask answer.

        Implementations MUST treat every key as untrusted: only allowlisted keys
        with contract-valid values may reach `request`, and a value that fails
        this flow's own reference-data check MUST be reported rather than stored.
        """

    def start(
        self,
        svc: Any,
        conversation: dict[str, Any],
        request: dict[str, Any],
        *,
        turn: Any = None,
        memory: Any = None,
    ) -> dict[str, Any]:
        """Produce the first assistant turn after the supervisor delegated.

        `turn` is the routed agent's understanding of the same sentence. It is
        optional so a flow stays usable without a model, but when present its
        extraction MUST go through `merge_agent_extraction` rather than being
        written to `request` directly.
        """

    def continue_turn(
        self,
        svc: Any,
        conversation: dict[str, Any],
        request: dict[str, Any],
        content: str,
        *,
        turn: Any = None,
        memory: Any = None,
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

    def rank_candidates(
        self, request: dict[str, Any], memory: Any = None
    ) -> list[dict[str, Any]]:
        """Deterministic hard-condition filter plus ordering for dispatch.

        A member preference MAY influence the ordering and MAY exclude a blocked
        vendor, but MUST NOT relax a hard condition such as the service area.
        """

    def validate_accept(self, payload: dict[str, Any]) -> None:
        """Raise ValidationError when an accept is missing required fields."""

    def reward_basis(
        self, request: dict[str, Any], payload: dict[str, Any]
    ) -> tuple[int, str] | None:
        """Amount the points estimate is calculated from, and where it came from.

        Per category because the honest basis differs: a repair has no price
        until a technician quotes it, so the provider reports an estimate or the
        platform falls back to a category baseline. A product order already has
        a server-computed amount, so estimating one would invent a number the
        platform can already state exactly.

        Return None to disclose no reward for this category.
        """

        return None

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
