"""Shared Amazon Bedrock safety boundary for the AgentCore Runtime process.

The gate and the model allowlist are owned by ``packages/api/bedrock_safety.py``
so the Flask Lambda and this Runtime enforce one identical policy instead of two
copies that can drift.  ``infra.aiwave_stack`` stages that module into the
Runtime deployment artifact, which is why the flat import is tried first; the
repository-relative fallback only exists for local tests and local runs.

The gate is per process by construction.  A separate Runtime process therefore
gets its own slot, and the account-level Bedrock budget still has to be managed
by keeping the demo to a single Runtime, as recorded in the README.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:  # deployed artifact: bedrock_safety.py sits beside agent_runtime.py
    from bedrock_safety import (
        APPROVED_TEXT_MODEL_IDS,
        DEFAULT_BEDROCK_REQUEST_GATE,
        BedrockRequestGate,
        BedrockSafetyError,
        GuardedBedrockRuntime,
    )
except ModuleNotFoundError:  # local repository layout
    _SHARED_CORE = Path(__file__).resolve().parents[2] / "packages" / "api"
    if str(_SHARED_CORE) not in sys.path:
        sys.path.insert(0, str(_SHARED_CORE))
    from bedrock_safety import (  # noqa: F401
        APPROVED_TEXT_MODEL_IDS,
        DEFAULT_BEDROCK_REQUEST_GATE,
        BedrockRequestGate,
        BedrockSafetyError,
        GuardedBedrockRuntime,
    )


__all__ = [
    "APPROVED_TEXT_MODEL_IDS",
    "DEFAULT_BEDROCK_REQUEST_GATE",
    "BedrockRequestGate",
    "BedrockSafetyError",
    "GuardedBedrockRuntime",
    "build_guarded_runtime",
]


def build_guarded_runtime(
    client: Any,
    *,
    gate: BedrockRequestGate | None = None,
) -> GuardedBedrockRuntime:
    """Wrap a Bedrock Runtime client in the shared allowlist and request gate."""

    return GuardedBedrockRuntime(
        client,
        gate=gate or DEFAULT_BEDROCK_REQUEST_GATE,
        approved_model_ids=APPROVED_TEXT_MODEL_IDS,
    )
