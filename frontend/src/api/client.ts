import type {
  ApiMessage,
  ChatTurn,
  ConversationCreated,
  DemoProvider,
  PointsReward,
  ProviderActiveCase,
  ProviderCompletionRequest,
  ProviderTask,
  ProviderTaskResponse,
  SelectionResult,
  ServiceRequestProjection,
  WorkflowProgress,
} from "./types.ts";


interface ApiEnvelope<T> {
  data: T;
  requestId?: string;
}

interface ApiErrorEnvelope {
  error?: { code?: string; message?: string };
  requestId?: string;
}

interface ClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  residentId?: string;
  providerId?: string;
  adminId?: string;
  idempotencyKey?: () => string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;

  constructor(status: number, code: string, message: string, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

const viteEnv = (
  import.meta as ImportMeta & { env?: Record<string, string | undefined> }
).env;

// Default to the deployed AWS backend (CDK stack AiwaveStaging output
// "ApiBaseUrl"), which runs the Flask API on Lambda behind API Gateway and
// orchestrates through AgentCore Runtime.
// To develop against a local Flask instance instead, set
// VITE_API_BASE_URL=http://127.0.0.1:8000 (the dev server binds IPv4 loopback
// only, and "localhost" resolves to ::1 first on macOS).
const DEFAULT_BASE_URL =
  viteEnv?.VITE_API_BASE_URL ??
  "https://67wcdv3h8b.execute-api.us-west-2.amazonaws.com";

export const DEFAULT_DEMO_RESIDENT_ID = "resident-demo-001";
const DEMO_RESIDENT_STORAGE_KEY = "aiwave.demoResidentId";
// 這個值會被放進 X-Demo-Resident-Id，所以走白名單而不是黑名單：只允許
// 識別碼字元，換行與冒號都無法穿透成額外的 header。
const DEMO_RESIDENT_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

type DemoIdentityStorage = Pick<Storage, "getItem" | "setItem">;

/**
 * 決定這一輪 Demo 要用哪個住戶身分。
 *
 * 換身分就等於換一份乾淨的預約列表（案件按 residentId 隔離），所以
 * `/my-bookings?resident=<id>` 可以在不刪任何資料的前提下重新開始測試。
 * 解析結果會記在 storage，SPA 導覽到其他頁時不會掉回預設身分；帶
 * `?resident=resident-demo-001` 就能切回原本那份資料。
 */
export function resolveDemoResidentId(
  search: string,
  storage?: DemoIdentityStorage | null,
): string {
  const requested = new URLSearchParams(search).get("resident")?.trim();
  if (requested && DEMO_RESIDENT_ID_PATTERN.test(requested)) {
    try {
      storage?.setItem(DEMO_RESIDENT_STORAGE_KEY, requested);
    } catch {
      // 隱私模式下 storage 可能擲錯；記不住不影響這一次的身分。
    }
    return requested;
  }

  let remembered: string | null = null;
  try {
    remembered = storage?.getItem(DEMO_RESIDENT_STORAGE_KEY)?.trim() ?? null;
  } catch {
    remembered = null;
  }
  if (remembered && DEMO_RESIDENT_ID_PATTERN.test(remembered)) {
    return remembered;
  }
  return DEFAULT_DEMO_RESIDENT_ID;
}

function currentDemoResidentId(): string {
  // 在 node 測試環境沒有 location／localStorage，兩者都必須是選用的。
  const scope = globalThis as typeof globalThis & {
    location?: { search?: string };
    localStorage?: DemoIdentityStorage;
  };
  return resolveDemoResidentId(
    scope.location?.search ?? "",
    scope.localStorage ?? null,
  );
}

export function createApiClient(options: ClientOptions = {}) {
  const baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
  const fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const residentId = options.residentId ?? currentDemoResidentId();
  const providerId =
    options.providerId ?? "31324fe0-9899-5382-8211-d0122c20bda0";
  const adminId = options.adminId ?? "admin-demo-001";
  const newIdempotencyKey =
    options.idempotencyKey ?? (() => globalThis.crypto.randomUUID());

  const actorHeaders = (role: "RESIDENT" | "PROVIDER" | "ADMIN") => {
    if (role === "RESIDENT") {
      return {
        "X-Demo-Role": role,
        "X-Demo-Resident-Id": residentId,
      };
    }
    if (role === "PROVIDER") {
      return {
        "X-Demo-Role": role,
        "X-Demo-Provider-Id": providerId,
      };
    }
    return {
      "X-Demo-Role": role,
      "X-Demo-Admin-Id": adminId,
    };
  };

  const requestJson = async <T>(
    path: string,
    role: "RESIDENT" | "PROVIDER" | "ADMIN",
    init: RequestInit = {},
  ): Promise<T> => {
    const headers = new Headers(init.headers);
    headers.set("Content-Type", "application/json");
    Object.entries(actorHeaders(role)).forEach(([name, value]) =>
      headers.set(name, value),
    );
    const response = await fetchImpl(`${baseUrl}${path}`, {
      ...init,
      headers,
    });
    const payload = (await response.json().catch(() => ({}))) as
      | ApiEnvelope<T>
      | ApiErrorEnvelope;
    if (!response.ok || !("data" in payload)) {
      const errorPayload = payload as ApiErrorEnvelope;
      throw new ApiError(
        response.status,
        errorPayload.error?.code ?? "request_failed",
        errorPayload.error?.message ?? "系統暫時無法處理，請稍後再試",
        errorPayload.requestId,
      );
    }
    return payload.data;
  };

  return {
    createConversation: () =>
      requestJson<ConversationCreated>("/api/v1/conversations", "RESIDENT", {
        method: "POST",
        body: JSON.stringify({}),
      }),

    sendMessage: (conversationId: string, message: string) =>
      requestJson<ChatTurn>(
        `/api/v1/conversations/${encodeURIComponent(conversationId)}/messages`,
        "RESIDENT",
        { method: "POST", body: JSON.stringify({ message }) },
      ),

    listMessages: (conversationId: string) =>
      requestJson<{ items: ApiMessage[]; nextCursor?: string }>(
        `/api/v1/conversations/${encodeURIComponent(conversationId)}/messages`,
        "RESIDENT",
      ),

    listServiceRequests: () =>
      requestJson<{ items: ServiceRequestProjection[] }>(
        "/api/v1/service-requests",
        "RESIDENT",
      ),

    getProgress: (serviceRequestId: string) =>
      requestJson<WorkflowProgress>(
        `/api/v1/service-requests/${encodeURIComponent(serviceRequestId)}/progress`,
        "RESIDENT",
      ),

    /**
     * Choose one candidate for a service request.
     *
     * Deliberately accepts no amount: the backend recomputes price, discount
     * and shipping from the catalogue, and ignores any money field a client
     * sends. `expectedVersion` is the candidate list version, so a stale list
     * fails with 409 instead of silently ordering the wrong thing.
     */
    selectProduct: (
      serviceRequestId: string,
      sku: string,
      expectedVersion: number,
    ) =>
      requestJson<SelectionResult>(
        `/api/v1/service-requests/${encodeURIComponent(serviceRequestId)}/selections`,
        "RESIDENT",
        {
          method: "POST",
          body: JSON.stringify({ sku, expectedVersion }),
          headers: { "Idempotency-Key": newIdempotencyKey() },
        },
      ),

    listReminders: () =>
      requestJson<{
        items: Array<{
          reminderId: string;
          serviceRequestId: string;
          label: string;
          actionRequired: boolean;
          updatedAt: string;
        }>;
      }>("/api/v1/reminders", "RESIDENT"),

    /** Demo-only: providers the operator can impersonate in the dashboard. */
    listDemoProviders: () =>
      requestJson<{ items: DemoProvider[] }>(
        "/api/v1/demo/providers",
        "RESIDENT",
      ),

    listProviderTasks: () =>
      requestJson<{ items: ProviderTask[] }>(
        "/api/v1/provider-service-requests",
        "PROVIDER",
      ),

    respondToProviderTask: (
      taskId: string,
      payload: ProviderTaskResponse,
    ) =>
      requestJson<{
        serviceRequestId: string;
        progress: WorkflowProgress;
        providerTask?: ProviderTask;
        pointsReward?: PointsReward | null;
      }>(
        `/api/v1/provider-service-requests/${encodeURIComponent(taskId)}/responses`,
        "PROVIDER",
        {
          method: "POST",
          body: JSON.stringify(payload),
          headers: { "Idempotency-Key": newIdempotencyKey() },
        },
      ),

    listProviderActiveCases: () =>
      requestJson<{ items: ProviderActiveCase[] }>(
        "/api/v1/provider-active-cases",
        "PROVIDER",
      ),

    reportCompletion: (
      serviceRequestId: string,
      payload: ProviderCompletionRequest,
    ) =>
      requestJson<{
        serviceRequestId: string;
        progress: WorkflowProgress;
      }>(
        `/api/v1/provider-active-cases/${encodeURIComponent(serviceRequestId)}/completion`,
        "PROVIDER",
        {
          method: "POST",
          body: JSON.stringify(payload),
          headers: { "Idempotency-Key": newIdempotencyKey() },
        },
      ),

    simulateTimeout: (taskId: string, reason: string) =>
      requestJson<{
        serviceRequestId: string;
        progress: WorkflowProgress;
        providerTask?: ProviderTask;
      }>(
        `/api/v1/admin/workflow-tasks/${encodeURIComponent(taskId)}/simulate-timeout`,
        "ADMIN",
        {
          method: "POST",
          body: JSON.stringify({ reason }),
          headers: { "Idempotency-Key": newIdempotencyKey() },
        },
      ),

    // 畫面需要能說出「現在是哪個 Demo 身分」，否則換了乾淨身分之後的空列表
    // 和「後端掛掉」在視覺上無法區分。
    residentId,
  };
}

export const apiClient = createApiClient();
