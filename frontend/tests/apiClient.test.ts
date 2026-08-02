import assert from "node:assert/strict";
import test from "node:test";

import {
  ApiError,
  DEFAULT_DEMO_RESIDENT_ID,
  createApiClient,
  resolveDemoResidentId,
} from "../src/api/client.ts";


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


test("a resident id from the URL is used and remembered for later navigation", () => {
  const store = new Map<string, string>();
  const storage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
  };

  const resolved = resolveDemoResidentId("?resident=resident-demo-clean-01", storage);

  assert.equal(resolved, "resident-demo-clean-01");
  // 換頁後（SPA 導覽不會重新解析 query）仍要記得同一個身分。
  assert.equal(resolveDemoResidentId("", storage), "resident-demo-clean-01");
});

test("an unsafe resident id is rejected instead of reaching a request header", () => {
  const store = new Map<string, string>();
  const storage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
  };

  // 這個值會被放進 X-Demo-Resident-Id，換行字元不得穿透。
  const resolved = resolveDemoResidentId(
    "?resident=" + encodeURIComponent("bad\r\nX-Demo-Role: ADMIN"),
    storage,
  );

  assert.equal(resolved, DEFAULT_DEMO_RESIDENT_ID);
  assert.equal(store.size, 0);
});

test("without a URL param or a remembered value the default demo resident applies", () => {
  assert.equal(resolveDemoResidentId("", null), DEFAULT_DEMO_RESIDENT_ID);
});

test("an explicit default in the URL switches back from a remembered resident", () => {
  const store = new Map<string, string>([
    ["aiwave.demoResidentId", "resident-demo-clean-01"],
  ]);
  const storage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
  };

  const resolved = resolveDemoResidentId(
    `?resident=${DEFAULT_DEMO_RESIDENT_ID}`,
    storage,
  );

  assert.equal(resolved, DEFAULT_DEMO_RESIDENT_ID);
});

test("resident headers follow the resolved demo identity", async () => {
  const calls: Array<{ init?: RequestInit }> = [];
  const fakeFetch = async (_input: string | URL | Request, init?: RequestInit) => {
    calls.push({ init });
    return new Response(JSON.stringify({ data: { items: [] } }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const api = createApiClient({
    baseUrl: "https://api.example",
    fetchImpl: fakeFetch,
    residentId: "resident-demo-clean-01",
  });

  await api.listServiceRequests();

  const headers = new Headers(calls[0].init?.headers);
  assert.equal(headers.get("X-Demo-Resident-Id"), "resident-demo-clean-01");
  assert.equal(headers.get("X-Demo-Role"), "RESIDENT");
});
