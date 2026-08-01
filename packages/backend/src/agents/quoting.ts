import type { ServiceRequest, UserPreferences, Vendor, VendorProposal } from '../domain/types';
import { SYMPTOM_TO_ITEMS } from '../data/vendors';
import { isoDatePlus } from '../lib/ids';

/**
 * 依症狀推估可能的維修項目 -> 用廠商自己的價目表算報價區間。
 * 這一段刻意用規則而非 LLM：報價不能讓模型自由發揮，會亂編數字。
 * LLM 的工作是「解釋」與「排序」，不是「定價」。
 */
export function estimateQuote(
  vendor: Vendor,
  req: ServiceRequest,
): {
  inspectionFee: number;
  estimatedMin: number;
  estimatedMax: number;
  matchedItems: string[];
  assumptions: string[];
} {
  const symptoms = req.slots.symptoms ?? [];
  const codes = new Set<string>();
  for (const s of symptoms) {
    for (const [keyword, items] of Object.entries(SYMPTOM_TO_ITEMS)) {
      if (s.includes(keyword)) items.forEach((i) => codes.add(i));
    }
  }

  const priced = vendor.pricing.items.filter((i) => codes.has(i.code));
  const assumptions: string[] = [];

  if (priced.length === 0) {
    // 抓不到對應項目就只報到府檢測費，並明確說明
    assumptions.push('症狀需現場判斷，此報價僅含到府檢測費，實際維修項目由技師現場確認後報價');
    return {
      inspectionFee: vendor.pricing.inspectionFee,
      estimatedMin: vendor.pricing.inspectionFee,
      estimatedMax: vendor.pricing.inspectionFee,
      matchedItems: [],
      assumptions,
    };
  }

  // 最樂觀：只需最便宜的一項；最保守：最貴的一項
  const min = Math.min(...priced.map((i) => i.minPrice));
  const max = Math.max(...priced.map((i) => i.maxPrice));

  const ageYears = req.slots.ageYears;
  let ageFactorMax = 1;
  if (typeof ageYears === 'number' && ageYears >= 8) {
    ageFactorMax = 1.15;
    assumptions.push(`機齡約 ${ageYears} 年，零件取得與連帶更換風險較高，上限已含 15% 緩衝`);
  }

  assumptions.push(`可能項目：${priced.map((i) => i.name).join('、')}`);
  assumptions.push('報價含到府檢測費；若現場判定不需維修僅收檢測費');

  return {
    inspectionFee: vendor.pricing.inspectionFee,
    estimatedMin: vendor.pricing.inspectionFee + min,
    estimatedMax: Math.round(vendor.pricing.inspectionFee + max * ageFactorMax),
    matchedItems: priced.map((i) => i.code),
    assumptions,
  };
}

export interface ScoreBreakdown {
  price: number;
  speed: number;
  quality: number;
  preference: number;
  brand: number;
  total: number;
  reasons: string[];
}

/**
 * 綜合評分。權重會依會員的價格敏感度動態調整：
 * 價格敏感的人，價格權重拉高；不敏感的人，品質與速度權重拉高。
 */
export function scoreVendor(
  vendor: Vendor,
  req: ServiceRequest,
  prefs: UserPreferences,
  quote: { estimatedMin: number; estimatedMax: number },
  priceRange: { cheapest: number; priciest: number },
): ScoreBreakdown {
  const reasons: string[] = [];
  const sensitivity = prefs.priceSensitivity ?? 0.5;

  // --- 價格分：在候選中越便宜越高分 ---
  const span = Math.max(1, priceRange.priciest - priceRange.cheapest);
  const mid = (quote.estimatedMin + quote.estimatedMax) / 2;
  const price = Math.max(0, 1 - (mid - priceRange.cheapest) / span);
  if (price > 0.8) reasons.push('報價在候選廠商中屬於偏低');

  // --- 速度分 ---
  const speed = Math.max(0, 1 - vendor.earliestAvailableInDays / 5);
  if (vendor.earliestAvailableInDays === 0) reasons.push('今天就能到府');
  else if (vendor.earliestAvailableInDays <= 1) reasons.push('最快明天可到府');

  // --- 品質分：評分 + 案件數 ---
  const quality = Math.min(1, (vendor.rating / 5) * 0.8 + Math.min(vendor.completedJobs / 3000, 1) * 0.2);
  if (vendor.rating >= 4.7) reasons.push(`評價 ${vendor.rating} 分（${vendor.reviewCount} 則評論）`);

  // --- 偏好分：命中會員偏好標籤 ---
  const wanted = prefs.preferredVendorTags ?? [];
  const hit = wanted.filter((t) => vendor.tags.includes(t));
  const preference = wanted.length === 0 ? 0.5 : hit.length / wanted.length;
  if (hit.length > 0) reasons.push(`符合你重視的：${hit.join('、')}`);

  // --- 品牌專精分 ---
  const brand = req.slots.brand;
  let brandScore = 0.5;
  if (brand && vendor.tags.some((t) => t.includes(brand))) {
    brandScore = 1;
    reasons.push(`${brand} 品牌專精`);
  }

  // --- 時段可服務 ---
  const wantPeriod = req.preferredContactTime ?? prefs.preferredContactTime;
  if (wantPeriod && !vendor.availableSlots.includes(wantPeriod) && !vendor.availableSlots.includes('3')) {
    reasons.push('偏好時段不完全符合，需再協調');
  }

  if (vendor.supportsPoints) reasons.push('可用 OpenPoint 點數折抵');

  const wPrice = 0.2 + sensitivity * 0.3; // 0.2 ~ 0.5
  const wSpeed = 0.2;
  const wQuality = 0.35 - sensitivity * 0.15; // 0.2 ~ 0.35
  const wPref = 0.15;
  const wBrand = 0.1;

  const total =
    (price * wPrice + speed * wSpeed + quality * wQuality + preference * wPref + brandScore * wBrand) /
    (wPrice + wSpeed + wQuality + wPref + wBrand);

  return {
    price: round2(price),
    speed: round2(speed),
    quality: round2(quality),
    preference: round2(preference),
    brand: round2(brandScore),
    total: Math.round(total * 100),
    reasons,
  };
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

/** 把廠商 + 報價 + 分數組成前端可直接顯示的 proposal */
export function buildProposal(
  vendor: Vendor,
  req: ServiceRequest,
  quote: ReturnType<typeof estimateQuote>,
  score: ScoreBreakdown,
): VendorProposal {
  const wantPeriod = req.preferredContactTime ?? '3';
  const period = vendor.availableSlots.includes(wantPeriod) ? wantPeriod : vendor.availableSlots[0];
  return {
    vendorId: vendor.vendorId,
    vendorName: vendor.name,
    rating: vendor.rating,
    tags: vendor.tags,
    score: score.total,
    reasons: score.reasons,
    quote: {
      inspectionFee: quote.inspectionFee,
      estimatedMin: quote.estimatedMin,
      estimatedMax: quote.estimatedMax,
      currency: 'TWD',
      assumptions: quote.assumptions,
    },
    earliestSlot: {
      date: isoDatePlus(vendor.earliestAvailableInDays),
      period,
    },
    supportsPoints: vendor.supportsPoints,
  };
}
