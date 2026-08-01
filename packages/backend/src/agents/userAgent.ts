import type {
  AgentTraceEntry,
  Booking,
  ChatMessage,
  ChatSession,
  ChatTurnResult,
  MatchResult,
  PreferredContactTime,
  ServiceCategory,
  ServiceRequest,
  UserPreferences,
} from '../domain/types';
import { SERVICE_VENDOR_ID } from '../domain/types';
import { describeAddress, listDistricts, resolveAddress } from '../data/geo';
import { getRepo } from '../repo';
import { runAgent, type AgentTool, type Message } from '../lib/bedrock';
import { isoDatePlus, newOrderNo, newRequestId, newSessionId, nowIso } from '../lib/ids';
import { callMatchAgent } from './matchClient';

const SYSTEM_PROMPT = `你是 OpenPoint 的「生活管家」，一個代表會員的 AI 代理人。

## 你存在的理由
現在會員要修冷氣，得自己在 App 裡找分類、填一長串表單、再跟好幾家廠商來回問價。
你的任務是把這一切變成「一段對話」：會員只要說「冷氣不冷」，剩下的你處理。

## 行為準則
1. **先看資料再問問題。** 開場一定先呼叫 get_member_context，會員的地址、家裡有哪些冷氣、偏好時段都在裡面。
   已經知道的事情不要問，改成確認：「幫你修主臥那台 2018 年的大金分離式，對嗎？」
2. **一次只問一件事。** 不要一口氣丟五個問題，那就跟填表單沒兩樣。
3. **問到能媒合就停。** 冷氣維修最少需要：症狀、地址、方便時段。品牌/機齡如果資料裡有就直接用。
4. 每問到新資訊就呼叫 update_request 存起來。
5. 資訊夠了就呼叫 dispatch_matching。這會叫醒「廠商媒合代理」，牠會回來給你 2~3 家帶報價的方案。
6. 拿到方案後，用**口語**幫會員做重點比較，主動講出取捨（誰便宜、誰快、誰有保固），並問他要選哪一家。
7. 會員明確選定後呼叫 create_booking。
8. 觀察到長期偏好（在意價格、討厭推銷、只要女師傅、偏好某品牌…）就呼叫 remember_preference。
   這是平台之後能精準推播的基礎，但**不要為了記錄而追問**，只記錄自然聊出來的。

## 語氣
繁體中文、像個熟悉他家狀況的鄰居，不是客服機器人。
不要用「親愛的顧客您好」這種話。不要用 emoji 開頭每一句。回覆控制在 4 句以內。

## 絕對不要
- 不要自己編造報價、廠商名稱、到府時間。這些只能來自 dispatch_matching 的結果。
- 不要一次列出所有廠商的所有細節，挑重點講。
- 不要在資訊不足時就 dispatch_matching。`;

const REQUIRED_HINT = ['症狀', '地址', '方便時段'];

export interface ChatTurnInput {
  sessionId?: string;
  inbrAccountId: string;
  message: string;
}

/** 依序把 Bedrock 對話記錄壓縮成純文字歷史，避免 session 無限膨脹 */
function toBedrockMessages(history: ChatMessage[], userText: string): Message[] {
  const recent = history.slice(-12);
  const msgs: Message[] = recent.map((m) => ({
    role: m.role,
    content: [{ text: m.text }],
  }));
  msgs.push({ role: 'user', content: [{ text: userText }] });
  return msgs;
}

export async function runUserAgentTurn(input: ChatTurnInput): Promise<ChatTurnResult> {
  const repo = getRepo();
  const sessionId = input.sessionId ?? newSessionId();

  const session: ChatSession =
    (await repo.getSession(sessionId)) ?? {
      sessionId,
      inbrAccountId: input.inbrAccountId,
      messages: [],
      updatedAt: nowIso(),
    };

  const user = await repo.getUser(input.inbrAccountId);
  if (!user) throw new Error(`找不到會員: ${input.inbrAccountId}`);

  let request: ServiceRequest | undefined = session.activeRequestId
    ? await repo.getRequest(session.activeRequestId)
    : undefined;
  let match: MatchResult | undefined = request ? await repo.getMatch(request.requestId) : undefined;
  let booking: Booking | undefined;
  let preferences: UserPreferences = user.preferences;
  const extraTrace: AgentTraceEntry[] = [];

  /** 取得（或建立）當前服務單 */
  async function ensureRequest(category: ServiceCategory = 'AC_REPAIR'): Promise<ServiceRequest> {
    if (request) return request;
    request = {
      requestId: newRequestId(),
      inbrAccountId: user!.inbrAccountId,
      category,
      status: 'COLLECTING',
      slots: {},
      preferredContactTime: user!.preferences.preferredContactTime,
      createdAt: nowIso(),
      updatedAt: nowIso(),
    };
    // 只有一個地址就直接帶入，少問一題
    if (user!.addresses.length === 1) request.address = user!.addresses[0];
    session.activeRequestId = request.requestId;
    await repo.putRequest(request);
    return request;
  }

  // ---------------- Tools ----------------

  const getMemberContext: AgentTool = {
    name: 'get_member_context',
    description:
      '取得會員的完整背景：姓名、常用地址、家中家電清單（品牌/機型/年份/位置）、偏好、點數，以及目前服務單狀態。開場必先呼叫。',
    schema: { type: 'object', properties: {} },
    run: async () => {
      const req = request;
      return {
        member: {
          displayName: user!.displayName,
          points: user!.points,
          addresses: user!.addresses.map((a) => ({
            label: describeAddress(a),
            countyName: a.countyName,
            districtName: a.districtName,
          })),
          appliances: user!.appliances.filter((a) => a.kind === 'AC'),
          allAppliances: user!.appliances,
          preferences: user!.preferences,
        },
        currentRequest: req
          ? {
              requestId: req.requestId,
              category: req.category,
              status: req.status,
              slots: req.slots,
              address: req.address ? describeAddress(req.address) : null,
              preferredContactTime: req.preferredContactTime,
              preferredServiceDate: req.preferredServiceDate,
              missing: missingFields(req),
            }
          : null,
        hint: `冷氣維修媒合最少需要：${REQUIRED_HINT.join('、')}`,
        today: new Date().toISOString().slice(0, 10),
      };
    },
  };

  const updateRequest: AgentTool = {
    name: 'update_request',
    description:
      '把這一輪問到的資訊寫進服務單。只傳有變動的欄位。地址可以傳完整口語字串（如「台北市大安區復興南路一段100號」）。',
    schema: {
      type: 'object',
      properties: {
        category: {
          type: 'string',
          enum: ['AC_REPAIR', 'AC_CLEAN', 'PLUMBING', 'HOME_CLEAN'],
          description: '服務類別，冷氣不冷/漏水/異音等維修問題用 AC_REPAIR',
        },
        symptoms: {
          type: 'array',
          items: { type: 'string' },
          description: '症狀關鍵詞，例如 ["不冷","漏水"]',
        },
        brand: { type: 'string', description: '品牌，如 大金、日立' },
        variant: { type: 'string', description: '機型：分離式 / 窗型 / 吊隱式' },
        ageYears: { type: 'integer', description: '使用年數' },
        description: { type: 'string', description: '會員原話描述，給廠商參考' },
        selfTried: { type: 'string', description: '會員自己已經試過什麼' },
        addressText: { type: 'string', description: '完整地址口語字串' },
        preferredContactTime: {
          type: 'string',
          enum: ['1', '2', '3'],
          description: '1=上午 2=下午 3=皆可',
        },
        preferredServiceDate: { type: 'string', description: '期望到府日 YYYY-MM-DD' },
        budgetMax: { type: 'integer', description: '預算上限（元）' },
      },
    },
    run: async (patch: {
      category?: ServiceCategory;
      symptoms?: string[];
      brand?: string;
      variant?: string;
      ageYears?: number;
      description?: string;
      selfTried?: string;
      addressText?: string;
      preferredContactTime?: PreferredContactTime;
      preferredServiceDate?: string;
      budgetMax?: number;
    }) => {
      const req = await ensureRequest(patch.category ?? 'AC_REPAIR');
      if (patch.category) req.category = patch.category;

      if (patch.symptoms?.length) {
        req.slots.symptoms = [...new Set([...(req.slots.symptoms ?? []), ...patch.symptoms])];
      }
      if (patch.brand) req.slots.brand = patch.brand;
      if (patch.variant) req.slots.variant = patch.variant;
      if (typeof patch.ageYears === 'number') req.slots.ageYears = patch.ageYears;
      if (patch.description) req.slots.description = patch.description;
      if (patch.selfTried) req.slots.selfTried = patch.selfTried;
      if (patch.preferredContactTime) req.preferredContactTime = patch.preferredContactTime;
      if (patch.preferredServiceDate) req.preferredServiceDate = patch.preferredServiceDate;
      if (typeof patch.budgetMax === 'number') req.budgetMax = patch.budgetMax;

      let addressWarning: string | undefined;
      if (patch.addressText) {
        // 先看是不是會員已存的地址
        const known = user!.addresses.find((a) =>
          describeAddress(a).includes(patch.addressText!.replace(/\s/g, '')),
        );
        const resolved = known ?? resolveAddress({ freeText: patch.addressText });
        if (resolved) {
          req.address = resolved;
        } else {
          addressWarning = '這個地址無法對應到縣市/行政區，請向會員確認縣市與行政區';
        }
      }

      req.updatedAt = nowIso();
      const missing = missingFields(req);
      req.status = missing.length === 0 ? 'READY_TO_MATCH' : 'COLLECTING';
      await repo.putRequest(req);

      return {
        requestId: req.requestId,
        status: req.status,
        slots: req.slots,
        address: req.address ? describeAddress(req.address) : null,
        preferredContactTime: req.preferredContactTime,
        missing,
        addressWarning,
        canDispatch: missing.length === 0,
      };
    },
  };

  const listAreaOptions: AgentTool = {
    name: 'list_districts',
    description: '會員只講縣市、沒講行政區時，用這個列出該縣市可選的行政區。',
    schema: {
      type: 'object',
      properties: { countyName: { type: 'string', description: '縣市名稱，如 台北市' } },
      required: ['countyName'],
    },
    run: async ({ countyName }: { countyName: string }) => {
      const resolved = resolveAddress({ county: countyName, district: '中正' });
      const code = resolved?.countyCode ?? '';
      const districts = code ? listDistricts(code) : [];
      return { countyName, districts, note: districts.length ? 'ok' : '找不到該縣市' };
    },
  };

  const dispatchMatching: AgentTool = {
    name: 'dispatch_matching',
    description:
      '把服務單交給「廠商媒合代理」，牠會從廠商資料庫挑出最適配的 2~3 家並附上報價與最快到府日。資訊不齊全時會被拒絕。',
    schema: { type: 'object', properties: {} },
    run: async () => {
      const req = request;
      if (!req) return { ok: false, error: '還沒有服務單，請先呼叫 update_request' };
      const missing = missingFields(req);
      if (missing.length > 0) {
        return { ok: false, error: `資訊還不齊，缺少：${missing.join('、')}`, missing };
      }

      req.status = 'MATCHING';
      await repo.putRequest(req);

      const out = await callMatchAgent({ request: req, preferences });
      extraTrace.push(...out.trace);
      match = out.match;

      req.status = out.match.proposals.length > 0 ? 'MATCHED' : 'COLLECTING';
      req.updatedAt = nowIso();
      await repo.putRequest(req);

      return {
        ok: true,
        matchSummary: out.match.summary,
        proposals: out.match.proposals.map((p) => ({
          vendorId: p.vendorId,
          vendorName: p.vendorName,
          rating: p.rating,
          score: p.score,
          priceRange: `${p.quote.estimatedMin}~${p.quote.estimatedMax} 元`,
          inspectionFee: p.quote.inspectionFee,
          earliestDate: p.earliestSlot.date,
          tags: p.tags,
          reasons: p.reasons,
          assumptions: p.quote.assumptions,
          supportsPoints: p.supportsPoints,
        })),
      };
    },
  };

  const createBooking: AgentTool = {
    name: 'create_booking',
    description: '會員明確選定廠商後，建立預約單。vendorId 必須來自 dispatch_matching 的結果。',
    schema: {
      type: 'object',
      properties: {
        vendorId: { type: 'string' },
        serviceDate: { type: 'string', description: '到府日 YYYY-MM-DD，沒指定就用該廠商最快日' },
      },
      required: ['vendorId'],
    },
    run: async ({ vendorId, serviceDate }: { vendorId: string; serviceDate?: string }) => {
      const req = request;
      if (!req || !match) return { ok: false, error: '還沒有媒合結果' };
      const proposal = match.proposals.find((p) => p.vendorId === vendorId);
      if (!proposal) {
        return {
          ok: false,
          error: `vendorId ${vendorId} 不在媒合結果中`,
          available: match.proposals.map((p) => p.vendorId),
        };
      }
      if (!req.address) return { ok: false, error: '服務單缺少地址' };

      const b: Booking = {
        orderNo: newOrderNo(),
        requestId: req.requestId,
        inbrAccountId: user!.inbrAccountId,
        vendorId: proposal.vendorId,
        vendorName: proposal.vendorName,
        serviceVendorId: SERVICE_VENDOR_ID[req.category],
        orderType: '01',
        // 到府檢測後才報價，對齊 mms_order_record 的「12 已支付訂金，待報價」
        orderStatus: '11',
        serviceDate: serviceDate ?? proposal.earliestSlot.date,
        servicePeriod: proposal.earliestSlot.period,
        address: req.address,
        depositAmount: proposal.quote.inspectionFee,
        estimatedMin: proposal.quote.estimatedMin,
        estimatedMax: proposal.quote.estimatedMax,
        createdAt: nowIso(),
      };
      await repo.putBooking(b);
      booking = b;

      req.status = 'BOOKED';
      req.updatedAt = nowIso();
      await repo.putRequest(req);

      // 成交即視為對該廠商特質的正向訊號
      preferences = await repo.mergePreferences(user!.inbrAccountId, {
        interestedCategories: [req.category],
        preferredVendorTags: proposal.tags.slice(0, 2),
      });

      return {
        ok: true,
        orderNo: b.orderNo,
        vendorName: b.vendorName,
        serviceDate: b.serviceDate,
        servicePeriod: b.servicePeriod === '1' ? '上午' : b.servicePeriod === '2' ? '下午' : '皆可',
        depositAmount: b.depositAmount,
        estimatedRange: `${b.estimatedMin}~${b.estimatedMax} 元`,
        orderStatus: '11 待訂金支付',
      };
    },
  };

  const rememberPreference: AgentTool = {
    name: 'remember_preference',
    description:
      '記錄會員的長期偏好，之後用於自動推播與媒合加權。只記錄自然聊出來的，不要為此追問。',
    schema: {
      type: 'object',
      properties: {
        priceSensitivity: {
          type: 'number',
          description: '價格敏感度 0~1，會員明顯在意價格時給 0.8 以上',
        },
        preferredContactTime: { type: 'string', enum: ['1', '2', '3'] },
        preferredVendorTags: {
          type: 'array',
          items: { type: 'string' },
          description: '例如 ["女性技師","原廠零件","當日到府"]',
        },
        blockedVendorIds: { type: 'array', items: { type: 'string' }, description: '會員排除的廠商' },
        interestedCategories: {
          type: 'array',
          items: { type: 'string', enum: ['AC_REPAIR', 'AC_CLEAN', 'PLUMBING', 'HOME_CLEAN'] },
        },
        note: { type: 'string', description: '一句話描述觀察到的偏好' },
      },
    },
    run: async (patch: UserPreferences & { note?: string }) => {
      const { note, ...rest } = patch;
      preferences = await repo.mergePreferences(user!.inbrAccountId, {
        ...rest,
        notes: note ? [note] : undefined,
      });
      return { ok: true, preferences };
    },
  };

  // ---------------- 執行 ----------------

  const result = await runAgent({
    agentName: 'user-agent',
    systemPrompt: SYSTEM_PROMPT,
    tools: [
      getMemberContext,
      updateRequest,
      listAreaOptions,
      dispatchMatching,
      createBooking,
      rememberPreference,
    ],
    temperature: 0.4,
    maxTurns: 10,
    messages: toBedrockMessages(session.messages, input.message),
  });

  session.messages.push({ role: 'user', text: input.message, at: nowIso() });
  session.messages.push({ role: 'assistant', text: result.text, at: nowIso() });
  session.updatedAt = nowIso();
  await repo.putSession(session);

  return {
    sessionId,
    reply: result.text,
    request: request ? await repo.getRequest(request.requestId) : undefined,
    match,
    booking,
    preferences,
    trace: [...result.trace, ...extraTrace].sort((a, b) => a.at.localeCompare(b.at)),
  };
}

/** 判斷服務單還缺什麼才能媒合 */
export function missingFields(req: ServiceRequest): string[] {
  const missing: string[] = [];
  if (!req.slots.symptoms?.length) missing.push('症狀');
  if (!req.address) missing.push('服務地址');
  if (!req.preferredContactTime) missing.push('方便時段');
  return missing;
}

/** 給前端的「建議開場話術」，讓 demo 有起點 */
export function suggestedPrompts(): string[] {
  return [
    '我家冷氣不冷了',
    '主臥的冷氣在滴水，越來越嚴重',
    '冷氣開了會有很大的異音',
    `我想約 ${isoDatePlus(2)} 下午請人來看冷氣`,
  ];
}
