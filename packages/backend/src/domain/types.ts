/**
 * Domain 型別定義
 *
 * 命名盡量對齊統一資訊提供的資料集，方便後續換成真實 Postgres：
 *  - inbrAccountId  <-> mms_order_record.inbr_account_id / pms_form_feedback.inbr_account_id
 *  - countyCode / districtCode <-> 縣市區域檔（2 碼 / 3 碼）
 *  - serviceVendorId <-> cms_homepage_service_vendor.id（11 = 修繕服務）
 *  - orderStatus <-> mms_order_record.order_status（服務訂單流程）
 */

/** 服務類別：先只做冷氣維修，之後可擴充 */
export type ServiceCategory =
  | 'AC_REPAIR' // 冷氣維修
  | 'AC_CLEAN' // 冷氣清洗
  | 'PLUMBING' // 水電修繕
  | 'HOME_CLEAN'; // 居家清潔

/** 對應 cms_homepage_service_vendor.id */
export const SERVICE_VENDOR_ID: Record<ServiceCategory, number> = {
  AC_REPAIR: 11,
  AC_CLEAN: 1,
  PLUMBING: 11,
  HOME_CLEAN: 1,
};

/** 對應 pms_form_feedback.preferred_contact_time */
export type PreferredContactTime = '1' | '2' | '3'; // 1 上午 / 2 下午 / 3 皆可

export interface Address {
  countyCode: string; // '01'
  countyName: string; // '台北市'
  districtCode: string; // '002'
  districtName: string; // '大同區'
  detail?: string;
}

/** 會員擁有的家電，讓 agent 不用每次重問品牌/機型 */
export interface Appliance {
  applianceId: string;
  kind: 'AC' | 'WASHER' | 'FRIDGE' | 'WATER_HEATER';
  brand?: string;
  model?: string;
  /** 分離式 / 窗型 / 吊隱式 */
  variant?: string;
  installedYear?: number;
  location?: string; // '主臥' / '客廳'
}

/** 會員偏好：這是「之後能自動推播喜歡內容」的核心資產 */
export interface UserPreferences {
  /** 價格敏感度 0(不在意) ~ 1(非常在意) */
  priceSensitivity?: number;
  /** 偏好時段 */
  preferredContactTime?: PreferredContactTime;
  /** 偏好廠商特質，例如 '女性技師' / '當日到府' / '原廠零件' */
  preferredVendorTags?: string[];
  /** 排除過的廠商 */
  blockedVendorIds?: string[];
  /** 常用服務類別（推播依據） */
  interestedCategories?: ServiceCategory[];
  /** 自由文字備註，agent 觀察到的長期偏好 */
  notes?: string[];
}

export interface UserProfile {
  inbrAccountId: string;
  displayName: string;
  /** demo 用途，正式環境需 aes256-gcm 加密（見 pms_form_feedback 做法） */
  mobile?: string;
  email?: string;
  addresses: Address[];
  appliances: Appliance[];
  preferences: UserPreferences;
  /** 會員等級 / 點數，用於報價折抵敘事 */
  points?: number;
}

/** 廠商可服務的區域 */
export interface VendorCoverage {
  countyCode: string;
  districtCodes: string[] | 'ALL';
}

export interface VendorPricing {
  /** 基本到府檢測費 */
  inspectionFee: number;
  /** 常見維修項目報價區間 */
  items: Array<{
    code: string;
    name: string;
    minPrice: number;
    maxPrice: number;
    unit?: string;
  }>;
}

export interface Vendor {
  vendorId: string;
  name: string;
  serviceVendorId: number;
  categories: ServiceCategory[];
  coverage: VendorCoverage[];
  rating: number; // 0~5
  reviewCount: number;
  completedJobs: number;
  /** 平均回應時間（分鐘） */
  avgResponseMinutes: number;
  /** 最快可到府天數 */
  earliestAvailableInDays: number;
  /** 可服務時段 */
  availableSlots: PreferredContactTime[];
  tags: string[]; // '原廠零件' / '當日到府' / '女性技師' / '保固一年'
  pricing: VendorPricing;
  certifications?: string[];
  /** 是否支援 OpenPoint 點數折抵 */
  supportsPoints: boolean;
}

/** 冷氣維修的槽位（slot filling 目標） */
export interface AcRepairSlots {
  /** 症狀：不冷 / 漏水 / 異音 / 不啟動 / 跳電 / 遙控無反應 */
  symptoms?: string[];
  variant?: string; // 分離式 / 窗型 / 吊隱式
  brand?: string;
  ageYears?: number;
  /** 使用者描述的原始文字，保留給廠商看 */
  description?: string;
  /** 是否已經自行處理過 */
  selfTried?: string;
  photoUrls?: string[];
}

export type ServiceRequestStatus =
  | 'COLLECTING' // agent 還在問問題
  | 'READY_TO_MATCH' // 資訊齊全，可媒合
  | 'MATCHING' // 媒合中
  | 'MATCHED' // 已有候選廠商
  | 'BOOKED' // 已成立預約單
  | 'CANCELLED';

export interface ServiceRequest {
  requestId: string;
  inbrAccountId: string;
  category: ServiceCategory;
  status: ServiceRequestStatus;
  slots: AcRepairSlots;
  address?: Address;
  preferredContactTime?: PreferredContactTime;
  /** 期望到府日（ISO date） */
  preferredServiceDate?: string;
  budgetMax?: number;
  createdAt: string;
  updatedAt: string;
}

/** 媒合 agent 產出的單一廠商方案 */
export interface VendorProposal {
  vendorId: string;
  vendorName: string;
  rating: number;
  tags: string[];
  /** 綜合分數 0~100 */
  score: number;
  /** 為什麼推薦（給 user agent 轉述） */
  reasons: string[];
  quote: {
    inspectionFee: number;
    estimatedMin: number;
    estimatedMax: number;
    currency: 'TWD';
    /** 報價假設，例如「若需更換壓縮機另計」 */
    assumptions: string[];
  };
  earliestSlot: {
    date: string;
    period: PreferredContactTime;
  };
  supportsPoints: boolean;
}

export interface MatchResult {
  requestId: string;
  matchedAt: string;
  /** 由高到低排序 */
  proposals: VendorProposal[];
  /** 媒合 agent 的總結說明 */
  summary: string;
  recommendedVendorId?: string;
}

/** 對齊 mms_order_record.order_status（服務訂單） */
export type OrderStatus =
  | '11' // 待訂金支付
  | '12' // 已支付訂金，待報價
  | '13' // 已報價，待客戶同意
  | '14' // 客戶同意報價
  | '15' // 已驗收，待尾款支付
  | '80' // 已完成
  | '90'; // 已取消

export interface Booking {
  orderNo: string;
  requestId: string;
  inbrAccountId: string;
  vendorId: string;
  vendorName: string;
  serviceVendorId: number;
  orderType: '01'; // 服務訂單
  orderStatus: OrderStatus;
  serviceDate: string;
  servicePeriod: PreferredContactTime;
  address: Address;
  depositAmount: number;
  estimatedMin: number;
  estimatedMax: number;
  createdAt: string;
}

/** 對話訊息（存進 DB 讓 agent 有記憶） */
export interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
  at: string;
}

export interface ChatSession {
  sessionId: string;
  inbrAccountId: string;
  messages: ChatMessage[];
  activeRequestId?: string;
  updatedAt: string;
}

/** 前端每次 /chat 拿到的完整畫面狀態 */
export interface ChatTurnResult {
  sessionId: string;
  reply: string;
  request?: ServiceRequest;
  match?: MatchResult;
  booking?: Booking;
  preferences: UserPreferences;
  /** agent 這一輪做了哪些動作，前端可以做成 timeline，demo 很好看 */
  trace: AgentTraceEntry[];
}

export interface AgentTraceEntry {
  agent: 'user-agent' | 'match-agent';
  tool: string;
  input: unknown;
  output: unknown;
  at: string;
}
