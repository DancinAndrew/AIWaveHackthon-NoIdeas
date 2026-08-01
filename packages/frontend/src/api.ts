import type { ChatTurnResult, ContextResponse, HealthResponse } from './types';

/**
 * 後端位址。
 * 開發時走 vite proxy（/api → http://127.0.0.1:3001），
 * 部署時可用 VITE_API_BASE 覆寫成 API Gateway 的網址。
 */
const BASE = import.meta.env.VITE_API_BASE ?? '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  const text = await res.text();
  let body: unknown;
  try {
    body = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(`後端回傳非 JSON（${res.status}）：${text.slice(0, 120)}`);
  }
  if (!res.ok) {
    const message = (body as { error?: string }).error ?? `HTTP ${res.status}`;
    throw new Error(message);
  }
  return body as T;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

export function getContext(inbrAccountId?: string): Promise<ContextResponse> {
  const qs = inbrAccountId ? `?inbrAccountId=${encodeURIComponent(inbrAccountId)}` : '';
  return request<ContextResponse>(`/context${qs}`);
}

export function postChat(payload: {
  message: string;
  sessionId?: string;
  inbrAccountId?: string;
}): Promise<ChatTurnResult> {
  return request<ChatTurnResult>('/chat', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
