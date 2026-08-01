from __future__ import annotations

import base64
import json
import sys
import unittest
from pathlib import Path
from typing import Any


API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from lambda_handler import handler  # noqa: E402


def http_api_event(
    method: str,
    path: str,
    *,
    body: str | None = None,
    headers: dict[str, str] | None = None,
    raw_query_string: str = "",
    is_base64_encoded: bool = False,
) -> dict[str, Any]:
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": raw_query_string,
        "headers": headers or {},
        "requestContext": {
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
            },
            "requestId": "api-gateway-request-001",
        },
        "body": body,
        "isBase64Encoded": is_base64_encoded,
    }


class LambdaHandlerTests(unittest.TestCase):
    def test_health_request_reaches_current_flask_app(self) -> None:
        response = handler(
            http_api_event(
                "GET",
                "/api/v1/health",
                headers={"x-request-id": "lambda-health-001"},
            ),
            None,
        )

        self.assertEqual(response["statusCode"], 200)
        self.assertFalse(response["isBase64Encoded"])
        payload = json.loads(response["body"])
        self.assertTrue(payload["data"]["ok"])
        self.assertEqual(
            payload["data"]["orchestrationMode"],
            "deterministic-demo",
        )
        self.assertEqual(response["headers"]["x-request-id"], "lambda-health-001")

    def test_base64_json_request_preserves_actor_headers(self) -> None:
        encoded_body = base64.b64encode(b"{}").decode("ascii")
        response = handler(
            http_api_event(
                "POST",
                "/api/v1/conversations",
                body=encoded_body,
                headers={
                    "content-type": "application/json",
                    "x-demo-role": "RESIDENT",
                    "x-demo-resident-id": "resident-lambda-001",
                },
                is_base64_encoded=True,
            ),
            None,
        )

        self.assertEqual(response["statusCode"], 201)
        payload = json.loads(response["body"])
        self.assertTrue(payload["data"]["conversationId"].startswith("conv-"))

    def test_cors_response_is_returned_without_wildcard_origin(self) -> None:
        response = handler(
            http_api_event(
                "OPTIONS",
                "/api/v1/conversations",
                headers={"origin": "http://localhost:5173"},
            ),
            None,
        )

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(
            response["headers"]["access-control-allow-origin"],
            "http://localhost:5173",
        )
        self.assertNotEqual(
            response["headers"]["access-control-allow-origin"],
            "*",
        )

    def test_non_http_api_v2_event_fails_closed(self) -> None:
        response = handler({"version": "1.0"}, None)

        self.assertEqual(response["statusCode"], 400)
        self.assertEqual(
            json.loads(response["body"])["error"]["code"],
            "invalid_lambda_event",
        )


if __name__ == "__main__":
    unittest.main()
