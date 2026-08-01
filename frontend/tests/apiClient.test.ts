import assert from "node:assert/strict";
import test from "node:test";

import { ApiError, createApiClient } from "../src/api/client.ts";


test("resident conversation uses the versioned API and trusted demo headers", async () => {
  const calls: Array<{ input: string; init?: RequestInit }> = [];
  const fakeFetch = async (input: string | URL | Request, init?: RequestInit) => {
    calls.push({ input: String(input), init });
    return new Response(
      JSON.stringify({
        data: {
          conversationId: "conv_123",
          orchestrationMode: "deterministic-demo",
        },
        requestId: "req_123",
      }),
      { status: 201, headers: { "Content-Type": "application/json" } },
    );
  };
  const api = createApiClient({ baseUrl: "https://api.example", fetchImpl: fakeFetch });

  const created = await api.createConversation();

  assert.equal(created.conversationId, "conv_123");
  assert.equal(calls[0].input, "https://api.example/api/v1/conversations");
  assert.equal(calls[0].init?.method, "POST");
  assert.deepEqual(JSON.parse(String(calls[0].init?.body)), {});
  const headers = new Headers(calls[0].init?.headers);
  assert.equal(headers.get("X-Demo-Role"), "RESIDENT");
  assert.equal(headers.get("X-Demo-Resident-Id"), "resident-demo-001");
});

test("provider response adds an idempotency key and does not send provider identity in body", async () => {
  const calls: Array<{ input: string; init?: RequestInit }> = [];
  const fakeFetch = async (input: string | URL | Request, init?: RequestInit) => {
    calls.push({ input: String(input), init });
    return new Response(
      JSON.stringify({ data: { progress: { stage: "provider_confirmed" } } }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  };
  const api = createApiClient({
    baseUrl: "https://api.example/",
    fetchImpl: fakeFetch,
    providerId: "provider-demo",
    idempotencyKey: () => "idem-fixed",
  });

  await api.respondToProviderTask("task_123", {
    action: "accept",
    expectedVersion: 1,
    arrivalWindow: "2026-08-03 14:00-17:00",
    message: "先勘查再施工",
  });

  assert.equal(
    calls[0].input,
    "https://api.example/api/v1/provider-service-requests/task_123/responses",
  );
  const headers = new Headers(calls[0].init?.headers);
  assert.equal(headers.get("Idempotency-Key"), "idem-fixed");
  assert.equal(headers.get("X-Demo-Provider-Id"), "provider-demo");
  const body = JSON.parse(String(calls[0].init?.body));
  assert.equal(body.providerId, undefined);
});

test("API errors expose safe code, status and request id", async () => {
  const fakeFetch = async () =>
    new Response(
      JSON.stringify({
        error: { code: "conflict", message: "任務版本已更新" },
        requestId: "req_conflict",
      }),
      { status: 409, headers: { "Content-Type": "application/json" } },
    );
  const api = createApiClient({ baseUrl: "https://api.example", fetchImpl: fakeFetch });

  await assert.rejects(
    () => api.listServiceRequests(),
    (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 409);
      assert.equal(error.code, "conflict");
      assert.equal(error.requestId, "req_conflict");
      return true;
    },
  );
});
