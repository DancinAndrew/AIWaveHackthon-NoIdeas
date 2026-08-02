import type {
  ApiMessage,
  ChatTurn,
  ConversationCreated,
  PointsReward,
  ProviderActiveCase,
  ProviderCompletionRequest,
  ProviderTask,
  ProviderTaskResponse,
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

const DEFAULT_BASE_URL = viteEnv?.VITE_API_BASE_URL ?? "http://localhost:8000";

export function createApiClient(options: ClientOptions = {}) {
  const baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
  const fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const residentId = options.residentId ?? "resident-demo-001";
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
  };
}

export const apiClient = createApiClient();
