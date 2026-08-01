"""AgentCore Gateway Lambda target for resident-side service request tools.

AgentCore passes the tool arguments directly as ``event`` and Gateway metadata
through ``context.client_context.custom``.  This adapter deliberately exposes
only resident conversation operations; provider and administrator transitions
remain behind their separately authorized Flask routes.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from walking_skeleton.errors import ApplicationError
from walking_skeleton.service import WalkingSkeletonService


logger = logging.getLogger("aiwave.agentcore_gateway_tool")
TOOL_NAME = "utility_service_request"
TOOL_NAME_DELIMITER = "___"
MESSAGE_VERSION = "1.0"
ALLOWED_OPERATIONS = frozenset(
    {
        "create_conversation",
        "add_resident_message",
        "get_progress",
    }
)
SERVICE = WalkingSkeletonService()


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entrypoint used by the AgentCore Gateway target."""

    return handle_tool(event, context, service=SERVICE)


def handle_tool(
    event: object,
    context: Any,
    *,
    service: WalkingSkeletonService,
) -> dict[str, Any]:
    """Validate Gateway metadata and invoke the shared application service."""

    gateway_metadata = _gateway_metadata(context)
    if gateway_metadata is None:
        return _error(
            "invalid_gateway_context",
            "request must come from the configured AgentCore Gateway tool",
        )
    if not isinstance(event, Mapping):
        return _error("invalid_tool_input", "event must be an object")

    operation = event.get("operation")
    if not isinstance(operation, str) or not operation:
        return _error("invalid_tool_input", "operation must be a non-empty string")
    if operation not in ALLOWED_OPERATIONS:
        return _error(
            "tool_operation_not_allowed",
            "operation is not available to the resident agent",
        )
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return _error("invalid_tool_input", "payload must be an object")

    try:
        data = _dispatch(operation, payload, service)
    except ApplicationError as error:
        return _error(error.code, error.message)
    except ValueError as error:
        return _error("invalid_tool_input", str(error))
    except Exception:
        logger.exception(
            "Unhandled AgentCore tool failure request_id=%s operation=%s",
            gateway_metadata["awsRequestId"],
            operation,
        )
        return _error("internal_tool_error", "tool execution failed")

    return {
        "ok": True,
        "data": data,
        "meta": gateway_metadata,
    }


def _dispatch(
    operation: str,
    payload: Mapping[str, Any],
    service: WalkingSkeletonService,
) -> dict[str, Any]:
    resident_id = _required_string(payload, "residentId")
    if operation == "create_conversation":
        return service.create_conversation(resident_id)
    if operation == "add_resident_message":
        return service.add_resident_message(
            _required_string(payload, "conversationId"),
            resident_id,
            _required_string(payload, "message", maximum_length=2_000),
        )
    if operation == "get_progress":
        return service.get_progress(
            _required_string(payload, "serviceRequestId"),
            resident_id,
        )
    raise ValueError("unsupported operation")


def _gateway_metadata(context: Any) -> dict[str, str] | None:
    client_context = getattr(context, "client_context", None)
    custom = getattr(client_context, "custom", None)
    if not isinstance(custom, Mapping):
        return None
    if custom.get("bedrockAgentCoreMessageVersion") != MESSAGE_VERSION:
        return None
    original_tool_name = custom.get("bedrockAgentCoreToolName")
    if not isinstance(original_tool_name, str):
        return None
    target_prefix, delimiter, tool_name = original_tool_name.partition(
        TOOL_NAME_DELIMITER
    )
    if not target_prefix or delimiter != TOOL_NAME_DELIMITER or tool_name != TOOL_NAME:
        return None
    aws_request_id = custom.get("bedrockAgentCoreAwsRequestId")
    mcp_message_id = custom.get("bedrockAgentCoreMcpMessageId")
    if not isinstance(aws_request_id, str) or not isinstance(mcp_message_id, str):
        return None
    return {
        "toolName": tool_name,
        "awsRequestId": aws_request_id,
        "mcpMessageId": mcp_message_id,
    }


def _required_string(
    payload: Mapping[str, Any],
    name: str,
    *,
    maximum_length: int = 128,
) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    value = value.strip()
    if len(value) > maximum_length:
        raise ValueError(f"{name} must not exceed {maximum_length} characters")
    return value


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}
