import type {
  Booking,
  ChatSession,
  MatchResult,
  ServiceCategory,
  ServiceRequest,
  UserPreferences,
  UserProfile,
  Vendor,
} from '../domain/types';
import { SEED_USERS } from '../data/users';
import { SEED_VENDORS } from '../data/vendors';
import type { Repo } from './types';
import { vendorCovers } from './coverage';

/**
 * 記憶體版資料層。程序重啟資料就消失，只用於本地開發 / demo 前的流程驗證。
 * 用 globalThis 存，這樣 tsx watch 熱重載時對話不會被清掉。
 */
interface Store {
  users: Map<string, UserProfile>;
  vendors: Map<string, Vendor>;
  requests: Map<string, ServiceRequest>;
  matches: Map<string, MatchResult>;
  bookings: Map<string, Booking>;
  sessions: Map<string, ChatSession>;
}

const g = globalThis as unknown as { __opStore?: Store };

function store(): Store {
  if (!g.__opStore) {
    g.__opStore = {
      users: new Map(SEED_USERS.map((u) => [u.inbrAccountId, structuredClone(u)])),
      vendors: new Map(SEED_VENDORS.map((v) => [v.vendorId, structuredClone(v)])),
      requests: new Map(),
      matches: new Map(),
      bookings: new Map(),
      sessions: new Map(),
    };
  }
  return g.__opStore;
}

export class MemoryRepo implements Repo {
  async getUser(id: string) {
    return store().users.get(id);
  }

  async putUser(user: UserProfile) {
    store().users.set(user.inbrAccountId, user);
  }

  async mergePreferences(id: string, patch: UserPreferences): Promise<UserPreferences> {
    const user = store().users.get(id);
    if (!user) throw new Error(`user not found: ${id}`);
    user.preferences = mergePrefs(user.preferences, patch);
    return user.preferences;
  }

  async listVendors(filter?: {
    category?: ServiceCategory;
    countyCode?: string;
    districtCode?: string;
  }) {
    let list = [...store().vendors.values()];
    if (filter?.category) list = list.filter((v) => v.categories.includes(filter.category!));
    if (filter?.countyCode) {
      list = list.filter((v) => vendorCovers(v, filter.countyCode!, filter.districtCode));
    }
    return list;
  }

  async getVendor(vendorId: string) {
    return store().vendors.get(vendorId);
  }

  async putVendor(vendor: Vendor) {
    store().vendors.set(vendor.vendorId, vendor);
  }

  async getRequest(requestId: string) {
    return store().requests.get(requestId);
  }

  async putRequest(req: ServiceRequest) {
    store().requests.set(req.requestId, req);
  }

  async listRequestsByUser(id: string) {
    return [...store().requests.values()].filter((r) => r.inbrAccountId === id);
  }

  async putMatch(match: MatchResult) {
    store().matches.set(match.requestId, match);
  }

  async getMatch(requestId: string) {
    return store().matches.get(requestId);
  }

  async putBooking(booking: Booking) {
    store().bookings.set(booking.orderNo, booking);
  }

  async getBooking(orderNo: string) {
    return store().bookings.get(orderNo);
  }

  async listBookingsByUser(id: string) {
    return [...store().bookings.values()].filter((b) => b.inbrAccountId === id);
  }

  async getSession(sessionId: string) {
    return store().sessions.get(sessionId);
  }

  async putSession(session: ChatSession) {
    store().sessions.set(session.sessionId, session);
  }
}

/** 偏好合併規則：陣列做去重聯集、數值直接覆寫、notes 累加 */
export function mergePrefs(base: UserPreferences, patch: UserPreferences): UserPreferences {
  const uniq = <T>(a: T[] = [], b: T[] = []) => [...new Set([...a, ...b])];
  return {
    priceSensitivity: patch.priceSensitivity ?? base.priceSensitivity,
    preferredContactTime: patch.preferredContactTime ?? base.preferredContactTime,
    preferredVendorTags: uniq(base.preferredVendorTags, patch.preferredVendorTags),
    blockedVendorIds: uniq(base.blockedVendorIds, patch.blockedVendorIds),
    interestedCategories: uniq(base.interestedCategories, patch.interestedCategories),
    notes: uniq(base.notes, patch.notes).slice(-20),
  };
}
