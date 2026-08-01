from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
from collections.abc import Callable
from typing import Any, TypeVar

from .errors import ConflictError


T = TypeVar("T")


class InMemoryStore:
    """Thread-safe local projection store.

    It mirrors the RDS repository boundary used in staging. Keeping the state
    mutation behind this object lets the Flask and AgentCore transports share
    one application service without importing either transport into the core.
    """

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.conversations: dict[str, dict[str, Any]] = {}
        self.messages: dict[str, list[dict[str, Any]]] = {}
        self.service_requests: dict[str, dict[str, Any]] = {}
        self.artifacts: dict[str, dict[str, Any]] = {}
        self.artifact_versions: dict[str, list[dict[str, Any]]] = {}
        self.progress: dict[str, dict[str, Any]] = {}
        self.tasks: dict[str, dict[str, Any]] = {}
        self.events: dict[str, list[dict[str, Any]]] = {}
        self.idempotency: dict[tuple[str, str, str], dict[str, Any]] = {}

    def idempotent(
        self,
        *,
        actor_id: str,
        operation: str,
        key: str,
        payload: dict[str, Any],
        command: Callable[[], T],
    ) -> T:
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        lookup = (actor_id, operation, key)
        with self.lock:
            prior = self.idempotency.get(lookup)
            if prior:
                if prior["fingerprint"] != fingerprint:
                    raise ConflictError("相同 Idempotency-Key 不可搭配不同內容")
                return copy.deepcopy(prior["result"])
            result = command()
            self.idempotency[lookup] = {
                "fingerprint": fingerprint,
                "result": copy.deepcopy(result),
            }
            return result


def create_store_from_environment() -> InMemoryStore:
    """Select explicit staging persistence while keeping tests local by default."""

    backend = os.getenv("STORE_BACKEND", "memory").strip().lower()
    if backend == "memory":
        return InMemoryStore()
    if backend == "rds":
        from .rds_store import RdsJsonStore

        return RdsJsonStore()
    raise RuntimeError(f"unsupported STORE_BACKEND: {backend!r}")
