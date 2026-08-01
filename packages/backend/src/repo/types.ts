import type {
  Booking,
  ChatSession,
  ServiceRequest,
  UserPreferences,
  UserProfile,
  Vendor,
  MatchResult,
  ServiceCategory,
} from '../domain/types';

/**
 * 資料層介面。
 * 刻意抽象化：本地開發用 memory，上雲用 dynamodb，之後要換成統一的 Postgres
 * 也只要再寫一個實作，agent 與 handler 都不用改。
 */
export interface Repo {
  // ---- 會員 ----
  getUser(inbrAccountId: string): Promise<UserProfile | undefined>;
  putUser(user: UserProfile): Promise<void>;
  mergePreferences(inbrAccountId: string, patch: UserPreferences): Promise<UserPreferences>;

  // ---- 廠商 ----
  listVendors(filter?: {
    category?: ServiceCategory;
    countyCode?: string;
    districtCode?: string;
  }): Promise<Vendor[]>;
  getVendor(vendorId: string): Promise<Vendor | undefined>;
  putVendor(vendor: Vendor): Promise<void>;

  // ---- 服務單 ----
  getRequest(requestId: string): Promise<ServiceRequest | undefined>;
  putRequest(req: ServiceRequest): Promise<void>;
  listRequestsByUser(inbrAccountId: string): Promise<ServiceRequest[]>;

  // ---- 媒合結果 ----
  putMatch(match: MatchResult): Promise<void>;
  getMatch(requestId: string): Promise<MatchResult | undefined>;

  // ---- 預約單 ----
  putBooking(booking: Booking): Promise<void>;
  getBooking(orderNo: string): Promise<Booking | undefined>;
  listBookingsByUser(inbrAccountId: string): Promise<Booking[]>;

  // ---- 對話 ----
  getSession(sessionId: string): Promise<ChatSession | undefined>;
  putSession(session: ChatSession): Promise<void>;
}
