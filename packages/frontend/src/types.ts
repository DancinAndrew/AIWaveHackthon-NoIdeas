/**
 * 對應後端 packages/api/op_agent/domain.py 的 wire format。
 * 後端 dict 的 key 就是 camelCase，所以這裡一對一映射，不需要轉換層。
 */

export type PreferredContactTime = '1' | '2' | '3';

export const PERIOD_LABEL: Record<string, string> = {
  '1': '上午',
  '2': '下午',
  '3': '皆可',
};

export interface Address {
  countyCode: string;
  countyName: string;
  districtCode: string;
  districtName: string;
  detail?: string;
}

export interface Appliance {
  applianceId: string;
  kind: 'AC' | 'WASHER' | 'FRIDGE' | 'WATER_HEATER';
  brand?: string;
  model?: string;
  variant?: string;
  installedYear?: number;
  location?: string;
}

export interface UserPreferences {
  priceSensitivity?: number;
  preferredContactTime?: PreferredContactTime;
  preferredVendorTags?: string[];
  blockedVendorIds?: string[];
  interestedCategories?: string[];
  notes?: string[];
}

export interface UserProfile {
  inbrAccountId: string;
  displayName: string;
  mobile?: string;
  email?: string;
  points?: number;
  addresses: Address[];
  appliances: Appliance[];
  preferences: UserPreferences;
}

export type ServiceRequestStatus =
  | 'COLLECTING'
  | 'READY_TO_MATCH'
  | 'MATCHING'
  | 'MATCHED'
  | 'BOOKED'
  | 'CANCELLED';

export interface AcRepairSlots {
  symptoms?: string[];
  variant?: string;
  brand?: string;
  ageYears?: number;
  description?: string;
  selfTried?: string;
}

export interface ServiceRequest {
  requestId: string;
  inbrAccountId: string;
  category: string;
  status: ServiceRequestStatus;
  slots: AcRepairSlots;
  address?: Address;
  preferredContactTime?: PreferredContactTime;
  preferredServiceDate?: string;
  budgetMax?: number;
  createdAt: string;
  updatedAt: string;
}

export interface MajorRisk {
  code: string;
  name: string;
  minPrice: number;
  maxPrice: number;
}

export interface Quote {
  inspectionFee: number;
  estimatedMin: number;
  estimatedMax: number;
  currency: string;
  assumptions: string[];
  majorRisks?: MajorRisk[];
}

export interface VendorProposal {
  vendorId: string;
  vendorName: string;
  rating: number;
  tags: string[];
  score: number;
  reasons: string[];
  quote: Quote;
  earliestSlot: { date: string; period: string };
  supportsPoints: boolean;
}

export interface MatchResult {
  requestId: string;
  matchedAt: string;
  proposals: VendorProposal[];
  summary: string;
  recommendedVendorId?: string;
}

/** 對齊 mms_order_record.order_status（服務訂單流程） */
export type OrderStatus = '11' | '12' | '13' | '14' | '15' | '80' | '90';

export interface Booking {
  orderNo: string;
  requestId: string;
  inbrAccountId: string;
  vendorId: string;
  vendorName: string;
  serviceVendorId: number;
  orderType: string;
  orderStatus: OrderStatus;
  serviceDate: string;
  servicePeriod: string;
  address: Address;
  depositAmount: number;
  estimatedMin: number;
  estimatedMax: number;
  createdAt: string;
}

export interface AgentTraceEntry {
  agent: 'user-agent' | 'match-agent';
  tool: string;
  input: unknown;
  output: unknown;
  at: string;
}

export interface ChatTurnResult {
  sessionId: string;
  reply: string;
  request?: ServiceRequest | null;
  match?: MatchResult | null;
  booking?: Booking | null;
  preferences: UserPreferences;
  trace: AgentTraceEntry[];
}

export interface ContextResponse {
  user: UserProfile;
  requests: ServiceRequest[];
  bookings: Booking[];
  suggestedPrompts: string[];
}

export interface HealthResponse {
  ok: boolean;
  repo: string;
  model: string;
  region: string;
  matchTransport: string;
}

/** 前端自己維護的對話訊息 */
export interface ChatMessage {
  id: string;
  role: 'user' | 'agent';
  text: string;
  /** agent 訊息可以附帶當輪的媒合結果 / 預約單，做成卡片 */
  match?: MatchResult | null;
  booking?: Booking | null;
  trace?: AgentTraceEntry[];
  elapsedMs?: number;
}
