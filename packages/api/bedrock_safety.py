"""Runtime safety boundary for every direct Amazon Bedrock model request."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Collection, Mapping
from typing import Any, Protocol, TypeVar


APPROVED_TEXT_MODEL_IDS = frozenset({"amazon.nova-2-lite-v1:0"})
DEFAULT_MINIMUM_INTERVAL_SECONDS = 1.05

ResultT = TypeVar("ResultT")


class BedrockSafetyError(ValueError):
    """Raised before an unsafe Bedrock request can reach the SDK client."""


class ConverseClient(Protocol):
    def converse(self, **kwargs: Any) -> Mapping[str, Any]: ...


class BedrockRequestGate:
    """Serialize request starts and keep them strictly below one request/second."""

    def __init__(
        self,
        *,
        minimum_interval_seconds: float = DEFAULT_MINIMUM_INTERVAL_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if (
            not math.isfinite(minimum_interval_seconds)
            or minimum_interval_seconds <= 1.0
        ):
            raise BedrockSafetyError(
                "Bedrock request interval must be greater than 1 second"
            )
        self.minimum_interval_seconds = minimum_interval_seconds
        self._monotonic = monotonic
        self._sleep = sleep
        self._next_allowed_start = 0.0
        self._lock = threading.Lock()

    def invoke(
        self,
        operation: Callable[..., ResultT],
        *args: Any,
        **kwargs: Any,
    ) -> ResultT:
        """Wait for the shared slot, then execute one model operation."""

        with self._lock:
            now = self._monotonic()
            delay = max(0.0, self._next_allowed_start - now)
            if delay:
                self._sleep(delay)
            started_at = self._monotonic()
            self._next_allowed_start = (
                started_at + self.minimum_interval_seconds
            )
            return operation(*args, **kwargs)


DEFAULT_BEDROCK_REQUEST_GATE = BedrockRequestGate()


class GuardedBedrockRuntime:
    """Allowlisted Bedrock Converse client sharing the process request gate."""

    def __init__(
        self,
        client: ConverseClient,
        *,
        gate: BedrockRequestGate = DEFAULT_BEDROCK_REQUEST_GATE,
        approved_model_ids: Collection[str] = APPROVED_TEXT_MODEL_IDS,
    ) -> None:
        self._client = client
        self._gate = gate
        self._approved_model_ids = frozenset(approved_model_ids)

    def converse(self, **kwargs: Any) -> Mapping[str, Any]:
        model_id = kwargs.get("modelId")
        if not isinstance(model_id, str) or model_id not in self._approved_model_ids:
            raise BedrockSafetyError(
                f"Bedrock model {model_id!r} is not approved for this project"
            )
        return self._gate.invoke(self._client.converse, **kwargs)
