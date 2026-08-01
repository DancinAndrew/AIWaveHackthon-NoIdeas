from __future__ import annotations

import logging
import os
from typing import Any
from uuid import uuid4

from flask import Flask, g, jsonify, request

from .errors import ApplicationError, ValidationError
from .orchestration import create_orchestrator_from_environment
from .service import WalkingSkeletonService
from .store import create_store_from_environment


logger = logging.getLogger("aiwave.walking_skeleton")


def create_app(*, testing: bool = False) -> Flask:
    app = Flask(__name__)
    app.config.update(TESTING=testing)
    app.json.ensure_ascii = False
    service = WalkingSkeletonService(
        store=create_store_from_environment(),
        orchestrator=create_orchestrator_from_environment(),
    )
    app.extensions["walking_skeleton_service"] = service

    @app.before_request
    def assign_request_id() -> None:
        g.request_id = request.headers.get("X-Request-Id") or uuid4().hex

    @app.after_request
    def add_response_headers(response):
        response.headers["X-Request-Id"] = g.get("request_id", "")
        allowed_origins = {
            origin.strip()
            for origin in os.getenv(
                "CORS_ALLOWED_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if origin.strip()
        }
        request_origin = request.headers.get("Origin")
        if request_origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = request_origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, Idempotency-Key, X-Demo-Resident-Id, "
                "X-Demo-Provider-Id, X-Demo-Admin-Id, X-Demo-Role"
            )
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

    @app.errorhandler(ApplicationError)
    def handle_application_error(error: ApplicationError):
        return (
            jsonify(
                {
                    "error": {"code": error.code, "message": error.message},
                    "requestId": g.get("request_id"),
                }
            ),
            error.status,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        logger.exception("Unhandled request failure request_id=%s", g.get("request_id"))
        return (
            jsonify(
                {
                    "error": {
                        "code": "internal_error",
                        "message": "系統暫時無法處理，請稍後再試",
                    },
                    "requestId": g.get("request_id"),
                }
            ),
            500,
        )

    @app.get("/health")
    @app.get("/api/v1/health")
    def health():
        return _ok(
            {
                "ok": True,
                "service": "utility-walking-skeleton",
                "orchestrationMode": service.orchestrator.mode,
                "version": "0.1.0",
            }
        )

    @app.post("/api/v1/conversations")
    def create_conversation():
        resident_id = _actor("RESIDENT", "X-Demo-Resident-Id")
        _json_object(optional=True)
        return _ok(service.create_conversation(resident_id), status=201)

    @app.post("/api/v1/conversations/<conversation_id>/messages")
    def add_message(conversation_id: str):
        resident_id = _actor("RESIDENT", "X-Demo-Resident-Id")
        body = _json_object()
        message = body.get("message")
        if not isinstance(message, str):
            raise ValidationError("message 為必填文字")
        return _ok(service.add_resident_message(conversation_id, resident_id, message))

    @app.get("/api/v1/conversations/<conversation_id>/messages")
    def list_messages(conversation_id: str):
        resident_id = _actor("RESIDENT", "X-Demo-Resident-Id")
        return _ok(
            service.list_messages(
                conversation_id, resident_id, after=request.args.get("after")
            )
        )

    @app.get("/api/v1/service-requests")
    def list_service_requests():
        resident_id = _actor("RESIDENT", "X-Demo-Resident-Id")
        return _ok(service.list_service_requests(resident_id))

    @app.get("/api/v1/service-requests/<service_request_id>/progress")
    def progress(service_request_id: str):
        resident_id = _actor("RESIDENT", "X-Demo-Resident-Id")
        return _ok(service.get_progress(service_request_id, resident_id))

    @app.get("/api/v1/reminders")
    def reminders():
        resident_id = _actor("RESIDENT", "X-Demo-Resident-Id")
        return _ok(service.list_reminders(resident_id))

    @app.get("/api/v1/provider-service-requests")
    def provider_tasks():
        provider_id = _actor("PROVIDER", "X-Demo-Provider-Id")
        return _ok(service.list_provider_tasks(provider_id))

    @app.post("/api/v1/provider-service-requests/<task_id>/responses")
    def provider_response(task_id: str):
        provider_id = _actor("PROVIDER", "X-Demo-Provider-Id")
        body = _json_object()
        key = _idempotency_key()
        return _ok(
            service.provider_response(
                task_id=task_id,
                provider_id=provider_id,
                payload=body,
                idempotency_key=key,
            )
        )

    @app.post("/api/v1/admin/workflow-tasks/<task_id>/simulate-timeout")
    def simulate_timeout(task_id: str):
        admin_id = _actor("ADMIN", "X-Demo-Admin-Id")
        body = _json_object()
        reason = body.get("reason")
        if not isinstance(reason, str):
            raise ValidationError("reason 為必填文字")
        return _ok(
            service.simulate_timeout(
                task_id=task_id,
                admin_id=admin_id,
                reason=reason,
                idempotency_key=_idempotency_key(),
            )
        )

    return app


def _ok(data: Any, *, status: int = 200):
    return jsonify({"data": data, "requestId": g.get("request_id")}), status


def _json_object(*, optional: bool = False) -> dict[str, Any]:
    if optional and not request.data:
        return {}
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("request body 必須是 JSON object")
    return body


def _actor(expected_role: str, id_header: str) -> str:
    role = request.headers.get("X-Demo-Role")
    actor_id = request.headers.get(id_header)
    if role != expected_role or not actor_id:
        from .errors import ForbiddenError

        raise ForbiddenError("Demo actor context 不完整或角色不符")
    return actor_id


def _idempotency_key() -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key or len(key) > 128:
        raise ValidationError("Idempotency-Key header 為必填，且不得超過 128 字")
    return key
