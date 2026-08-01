import { randomUUID } from 'node:crypto';

export function newSessionId(): string {
  return randomUUID();
}

export function newRequestId(): string {
  return `SR${Date.now().toString(36).toUpperCase()}${Math.floor(Math.random() * 900 + 100)}`;
}

/**
 * 訂單編號：對齊 mms_order_record.order_no 的可讀格式（YYMMDD + 流水）
 * 例：260801000123
 */
export function newOrderNo(): string {
  const d = new Date();
  const yy = String(d.getFullYear()).slice(2);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const seq = String(Math.floor(Math.random() * 1_000_000)).padStart(6, '0');
  return `${yy}${mm}${dd}${seq}`;
}

export function nowIso(): string {
  return new Date().toISOString();
}

/** 回傳 n 天後的 YYYY-MM-DD */
export function isoDatePlus(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}
