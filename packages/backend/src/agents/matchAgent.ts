import type {
  AgentTraceEntry,
  MatchResult,
  ServiceRequest,
  UserPreferences,
  VendorProposal,
} from '../domain/types';
import { getRepo } from '../repo';
import { runAgent, type AgentTool } from '../lib/bedrock';
import { buildProposal, estimateQuote, scoreVendor } from './quoting';
import { describeAddress } from '../data/geo';
import { nowIso } from '../lib/ids';

export interface MatchAgentInput {
  request: ServiceRequest;
  preferences: UserPreferences;
}

export interface MatchAgentOutput {
  match: MatchResult;
  trace: AgentTraceEntry[];
}

const SYSTEM_PROMPT = `你是「OpenPoint 廠商媒合代理」，代表平台去替會員找到最適合的服務廠商。

你的職責：
1. 先用 search_candidates 取得可服務該地區的廠商，工具已經幫你算好報價與客觀評分。
2. 檢視候選名單，判斷排序是否合理。你可以調整順序，但不可以修改任何金額或日期。
3. 用 submit_match 送出最終結果，並為每家寫一句「站在會員角度」的推薦理由。

原則：
- 絕對不要自己編造價格、日期、評分。所有數字只能來自 search_candidates 的回傳。
- 最多推薦 3 家，第一名要明確說出為什麼贏過其他家。
- summary 要用繁體中文、口語、2~3 句話，講重點取捨（例如「最便宜的是 A，但要等 3 天；急的話選 B」）。
- 如果完全沒有廠商可服務，submit_match 傳空的 proposals 並在 summary 說明原因。

務必呼叫 submit_match 結束流程。`;

/**
 * 媒合 Agent。
 *
 * 設計取捨：報價與評分用規則引擎算（可稽核、不會亂編數字），
 * LLM 只負責「排序微調 + 用人話解釋」，這是 hackathon demo 最穩的組合。
 */
export async function runMatchAgent(input: MatchAgentInput): Promise<MatchAgentOutput> {
  const { request, preferences } = input;
  const repo = getRepo();

  // 候選快取，submit_match 時用來驗證 LLM 沒有亂改數字
  const candidateMap = new Map<string, VendorProposal>();
  let submitted: { proposals: VendorProposal[]; summary: string } | undefined;

  const searchCandidates: AgentTool = {
    name: 'search_candidates',
    description:
      '依服務單的地區與症狀，找出可服務的廠商，並回傳每家的報價區間、最快到府日、客觀評分與評分細項。',
    schema: {
      type: 'object',
      properties: {
        maxResults: { type: 'integer', description: '最多回傳幾家，預設 5', default: 5 },
      },
    },
    run: async ({ maxResults = 5 }: { maxResults?: number }) => {
      if (!request.address) {
        return { candidates: [], note: '服務單缺少地址，無法媒合' };
      }
      const vendors = await repo.listVendors({
        category: request.category,
        countyCode: request.address.countyCode,
        districtCode: request.address.districtCode,
      });

      const blocked = new Set(preferences.blockedVendorIds ?? []);
      const usable = vendors.filter((v) => !blocked.has(v.vendorId));
      if (usable.length === 0) {
        return {
          candidates: [],
          note: `${describeAddress(request.address)} 目前沒有可服務的 ${request.category} 廠商`,
        };
      }

      const quotes = usable.map((v) => ({ vendor: v, quote: estimateQuote(v, request) }));
      const mids = quotes.map((q) => (q.quote.estimatedMin + q.quote.estimatedMax) / 2);
      const priceRange = { cheapest: Math.min(...mids), priciest: Math.max(...mids) };

      const scored = quotes
        .map(({ vendor, quote }) => {
          const score = scoreVendor(vendor, request, preferences, quote, priceRange);
          const proposal = buildProposal(vendor, request, quote, score);
          candidateMap.set(vendor.vendorId, proposal);
          return { proposal, breakdown: score, vendor };
        })
        .sort((a, b) => b.proposal.score - a.proposal.score)
        .slice(0, maxResults);

      return {
        serviceArea: describeAddress(request.address),
        symptoms: request.slots.symptoms ?? [],
        candidates: scored.map(({ proposal, breakdown, vendor }) => ({
          vendorId: proposal.vendorId,
          vendorName: proposal.vendorName,
          rating: proposal.rating,
          reviewCount: vendor.reviewCount,
          tags: proposal.tags,
          score: proposal.score,
          scoreBreakdown: {
            price: breakdown.price,
            speed: breakdown.speed,
            quality: breakdown.quality,
            preferenceMatch: breakdown.preference,
            brandExpertise: breakdown.brand,
          },
          objectiveReasons: breakdown.reasons,
          quote: proposal.quote,
          earliestSlot: proposal.earliestSlot,
          supportsPoints: proposal.supportsPoints,
        })),
      };
    },
  };

  const submitMatch: AgentTool = {
    name: 'submit_match',
    description: '送出最終媒合結果。vendorIds 依推薦順序排列（最多 3 個），只能來自 search_candidates。',
    schema: {
      type: 'object',
      properties: {
        vendorIds: {
          type: 'array',
          items: { type: 'string' },
          description: '依推薦順序的 vendorId，最多 3 個',
        },
        reasons: {
          type: 'object',
          description: 'vendorId -> 一句話推薦理由（繁體中文，站在會員角度）',
          additionalProperties: { type: 'string' },
        },
        summary: { type: 'string', description: '2~3 句總結，說明取捨建議' },
      },
      required: ['vendorIds', 'summary'],
    },
    run: async ({
      vendorIds,
      reasons = {},
      summary,
    }: {
      vendorIds: string[];
      reasons?: Record<string, string>;
      summary: string;
    }) => {
      const proposals: VendorProposal[] = [];
      const rejected: string[] = [];
      for (const id of vendorIds.slice(0, 3)) {
        const base = candidateMap.get(id);
        if (!base) {
          rejected.push(id);
          continue;
        }
        const extra = reasons[id];
        proposals.push({
          ...base,
          // 客觀理由保留，LLM 的推薦語放最前面
          reasons: extra ? [extra, ...base.reasons] : base.reasons,
        });
      }
      submitted = { proposals, summary };
      return {
        accepted: proposals.map((p) => p.vendorId),
        rejected,
        note: rejected.length ? '被拒絕的 vendorId 不在候選名單中，已忽略' : 'ok',
      };
    },
  };

  const result = await runAgent({
    agentName: 'match-agent',
    systemPrompt: SYSTEM_PROMPT,
    tools: [searchCandidates, submitMatch],
    temperature: 0.2,
    messages: [
      {
        role: 'user',
        content: [
          {
            text: [
              '請為以下服務單媒合廠商：',
              '```json',
              JSON.stringify(
                {
                  requestId: request.category,
                  category: request.category,
                  address: request.address ? describeAddress(request.address) : null,
                  symptoms: request.slots.symptoms,
                  brand: request.slots.brand,
                  variant: request.slots.variant,
                  ageYears: request.slots.ageYears,
                  description: request.slots.description,
                  preferredContactTime: request.preferredContactTime,
                  preferredServiceDate: request.preferredServiceDate,
                  budgetMax: request.budgetMax,
                },
                null,
                2,
              ),
              '```',
              '會員偏好：',
              '```json',
              JSON.stringify(preferences, null, 2),
              '```',
            ].join('\n'),
          },
        ],
      },
    ],
  });

  // LLM 沒呼叫 submit_match 就用客觀分數 fallback，保證一定有結果
  const fallbackProposals = [...candidateMap.values()].sort((a, b) => b.score - a.score).slice(0, 3);
  const finalProposals = submitted?.proposals.length ? submitted.proposals : fallbackProposals;

  const match: MatchResult = {
    requestId: request.requestId,
    matchedAt: nowIso(),
    proposals: finalProposals,
    summary:
      submitted?.summary ??
      result.text ??
      (finalProposals.length ? '已依你的偏好排出建議順序。' : '目前這個地區沒有可服務的廠商。'),
    recommendedVendorId: finalProposals[0]?.vendorId,
  };

  await repo.putMatch(match);
  return { match, trace: result.trace };
}
