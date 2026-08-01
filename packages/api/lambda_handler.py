"""AWS Lambda adapter for API Gateway HTTP API payload version 2.0.

This module intentionally has no adapter dependency: Flask remains the HTTP
application and this small boundary translates the managed API Gateway event
into a WSGI request through Flask's test client.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
from collections.abc import Mapping
from typing import Any

from app import app


logger = logging.getLogger("aiwave.lambda_transport")


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """Translate an API Gateway HTTP API v2 event into the current Flask app."""

    try:
        request = _parse_event(event)
    except ValueError:
        return _error_response(
            status=400,
            code="invalid_lambda_event",
            message="Request event is not a valid API Gateway HTTP API v2 event",
        )

    try:
        with app.test_client() as client:
            response = client.open(
                path=request["path"],
                method=request["method"],
                headers=request["headers"],
                data=request["body"],
                environ_overrides={"QUERY_STRING": request["query_string"]},
            )
    except Exception:
        logger.exception("Unhandled Lambda transport failure")
        return _error_response(
            status=500,
            code="lambda_transport_error",
            message="系統暫時無法處理，請稍後再試",
        )

    response_headers: dict[str, str] = {}
    cookies: list[str] = []
    for name, value in response.headers.to_wsgi_list():
        normalized_name = name.lower()
        if normalized_name == "set-cookie":
            cookies.append(value)
        elif normalized_name in response_headers:
            response_headers[normalized_name] = (
                f"{response_headers[normalized_name]}, {value}"
            )
        else:
            response_headers[normalized_name] = value

    response_bytes = response.get_data()
    try:
        response_body = response_bytes.decode("utf-8")
        is_base64_encoded = False
    except UnicodeDecodeError:
        response_body = base64.b64encode(response_bytes).decode("ascii")
        is_base64_encoded = True

    result: dict[str, Any] = {
        "statusCode": response.status_code,
        "headers": response_headers,
        "body": response_body,
        "isBase64Encoded": is_base64_encoded,
    }
    if cookies:
        result["cookies"] = cookies
    return result


def _parse_event(event: Mapping[str, Any]) -> dict[str, Any]:
    if event.get("version") != "2.0":
        raise ValueError("unsupported payload version")
    request_context = event.get("requestContext")
    if not isinstance(request_context, Mapping):
        raise ValueError("missing request context")
    http = request_context.get("http")
    if not isinstance(http, Mapping):
        raise ValueError("missing HTTP context")
    method = http.get("method")
    path = event.get("rawPath")
    if not isinstance(method, str) or not method:
        raise ValueError("missing HTTP method")
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("invalid HTTP path")

    raw_headers = event.get("headers") or {}
    if not isinstance(raw_headers, Mapping) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in raw_headers.items()
    ):
        raise ValueError("invalid headers")
    headers = dict(raw_headers)
    cookies = event.get("cookies") or []
    if not isinstance(cookies, list) or not all(
        isinstance(cookie, str) for cookie in cookies
    ):
        raise ValueError("invalid cookies")
    if cookies:
        headers["cookie"] = "; ".join(cookies)

    query_string = event.get("rawQueryString") or ""
    if not isinstance(query_string, str):
        raise ValueError("invalid query string")

    raw_body = event.get("body")
    if raw_body is None:
        body = b""
    elif not isinstance(raw_body, str):
        raise ValueError("invalid request body")
    elif event.get("isBase64Encoded") is True:
        try:
            body = base64.b64decode(raw_body, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("invalid base64 request body") from error
    else:
        body = raw_body.encode("utf-8")

    return {
        "method": method,
        "path": path,
        "headers": headers,
        "query_string": query_string,
        "body": body,
    }


def _error_response(*, status: int, code: str, message: str) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json; charset=utf-8"},
        "body": json.dumps(
            {"error": {"code": code, "message": message}},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "isBase64Encoded": False,
    }


# Temporary compatibility alias for any existing Lambda configuration.  New
# infrastructure must use ``lambda_handler.handler``.
chat_handler = handler
