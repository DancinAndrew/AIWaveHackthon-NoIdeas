"""媒合 Agent：代表平台去廠商資料庫找最適配的廠商。

設計取捨：報價與評分用規則引擎算（可稽核、不會亂編數字），
LLM 只負責「排序微調 + 用人話解釋」，這是 demo 最穩的組合。
"""

from __future__ import annotations

import json
from typing import Any

from .bedrock import AgentTool, run_agent
from .domain import AgentTraceEntry, MatchResult, ServiceRequest, UserPreferences, VendorProposal
from .geo import describe_address
from .ids import now_iso
from .quoting import build_proposal, estimate_quote, price_range, score_vendor
from .repo import get_repo

SYSTEM_PROMPT = """你是「OpenPoint 廠商媒合代理」，代表平台去替會員找到最適合的服務廠商。

你的職責：
1. 先用 search_candidates 取得可服務該地區的廠商，工具已經幫你算好報價與客觀評分。
2. 檢視候選名單，判斷排序是否合理。你可以調整順序，但不可以修改任何金額或日期。
3. 用 submit_match 送出最終結果，並為每家寫一句「站在會員角度」的推薦理由。

原則：
- 絕對不要自己編造價格、日期、評分。所有數字只能來自 search_candidates 的回傳。
- 最多推薦 3 家，第一名要明確說出為什麼贏過其他家。
- summary 用繁體中文、口語、2~3 句話，講重點取捨（例如「最便宜的是 A，但要等 3 天；急的話選 B」）。
- 如果完全沒有廠商可服務，submit_match 傳空的 vendorIds 並在 summary 說明原因。

務必呼叫 submit_match 結束流程。"""


def run_match_agent(
    request: ServiceRequest, preferences: UserPreferences
) -> dict[str, Any]:
    """回傳 {'match': MatchResult, 'trace': [...]}"""
    repo = get_repo()

    # 候選快取，submit_match 時用來驗證 LLM 沒有亂改數字
    candidates: dict[str, VendorProposal] = {}
    submitted: dict[str, Any] = {}

    def search_candidates(payload: dict[str, Any]) -> dict[str, Any]:
        max_results = int(payload.get("maxResults") or 5)
        address = request.get("address")
        if not address:
            return {"candidates": [], "note": "服務單缺少地址，無法媒合"}

        vendors = repo.list_vendors(
            category=request.get("category"),
            county_code=address.get("countyCode"),
            district_code=address.get("districtCode"),
        )
        blocked = set(preferences.get("blockedVendorIds") or [])
        usable = [v for v in vendors if v["vendorId"] not in blocked]
        if not usable:
            return {
                "candidates": [],
                "note": f"{describe_address(address)} 目前沒有可服務的 {request.get('category')} 廠商",
            }

        quotes = [(v, estimate_quote(v, request)) for v in usable]
        cheapest, priciest = price_range([q for _, q in quotes])

        scored = []
        for vendor, quote in quotes:
            breakdown = score_vendor(
                vendor, request, preferences, quote, cheapest=cheapest, priciest=priciest
            )
            proposal = build_proposal(vendor, request, quote, breakdown)
            candidates[vendor["vendorId"]] = proposal
            scored.append((proposal, breakdown, vendor))

        scored.sort(key=lambda x: x[0]["score"], reverse=True)

        return {
            "serviceArea": describe_address(address),
            "symptoms": request.get("slots", {}).get("symptoms") or [],
            "candidates": [
                {
                    "vendorId": p["vendorId"],
                    "vendorName": p["vendorName"],
                    "rating": p["rating"],
                    "reviewCount": v.get("reviewCount"),
                    "tags": p["tags"],
                    "score": p["score"],
                    "scoreBreakdown": {
                        "price": b.price,
                        "speed": b.speed,
                        "quality": b.quality,
                        "preferenceMatch": b.preference,
                        "brandExpertise": b.brand,
                    },
                    "objectiveReasons": b.reasons,
                    "quote": p["quote"],
                    "earliestSlot": p["earliestSlot"],
                    "supportsPoints": p["supportsPoints"],
                }
                for p, b, v in scored[:max_results]
            ],
        }

    def submit_match(payload: dict[str, Any]) -> dict[str, Any]:
        vendor_ids = payload.get("vendorIds") or []
        reasons = payload.get("reasons") or {}
        summary = payload.get("summary") or ""

        proposals: list[VendorProposal] = []
        rejected: list[str] = []
        for vid in vendor_ids[:3]:
            base = candidates.get(vid)
            if base is None:
                rejected.append(vid)
                continue
            extra = reasons.get(vid)
            merged = dict(base)
            if extra:
                # LLM 的推薦語放最前面，客觀理由保留在後
                merged["reasons"] = [extra, *base.get("reasons", [])]
            proposals.append(merged)  # type: ignore[arg-type]

        submitted["proposals"] = proposals
        submitted["summary"] = summary
        return {
            "accepted": [p["vendorId"] for p in proposals],
            "rejected": rejected,
            "note": "被拒絕的 vendorId 不在候選名單中，已忽略" if rejected else "ok",
        }

    tools = [
        AgentTool(
            name="search_candidates",
            description=(
                "依服務單的地區與症狀，找出可服務的廠商，"
                "並回傳每家的報價區間、最快到府日、客觀評分與評分細項。"
            ),
            schema={
                "type": "object",
                "properties": {
                    "maxResults": {
                        "type": "integer",
                        "description": "最多回傳幾家，預設 5",
                        "default": 5,
                    }
                },
            },
            run=search_candidates,
        ),
        AgentTool(
            name="submit_match",
            description=(
                "送出最終媒合結果。vendorIds 依推薦順序排列（最多 3 個），"
                "只能來自 search_candidates。"
            ),
            schema={
                "type": "object",
                "properties": {
                    "vendorIds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "依推薦順序的 vendorId，最多 3 個",
                    },
                    "reasons": {
                        "type": "object",
                        "description": "vendorId -> 一句話推薦理由（繁體中文，站在會員角度）",
                        "additionalProperties": {"type": "string"},
                    },
                    "summary": {"type": "string", "description": "2~3 句總結，說明取捨建議"},
                },
                "required": ["vendorIds", "summary"],
            },
            run=submit_match,
        ),
    ]

    brief = {
        "category": request.get("category"),
        "address": describe_address(request["address"]) if request.get("address") else None,
        "symptoms": request.get("slots", {}).get("symptoms"),
        "brand": request.get("slots", {}).get("brand"),
        "variant": request.get("slots", {}).get("variant"),
        "ageYears": request.get("slots", {}).get("ageYears"),
        "description": request.get("slots", {}).get("description"),
        "preferredContactTime": request.get("preferredContactTime"),
        "preferredServiceDate": request.get("preferredServiceDate"),
        "budgetMax": request.get("budgetMax"),
    }
    user_text = (
        "請為以下服務單媒合廠商：\n```json\n"
        + json.dumps(brief, ensure_ascii=False, indent=2)
        + "\n```\n會員偏好：\n```json\n"
        + json.dumps(preferences, ensure_ascii=False, indent=2)
        + "\n```"
    )

    result = run_agent(
        agent_name="match-agent",
        system_prompt=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": [{"text": user_text}]}],
        tools=tools,
        temperature=0.2,
    )

    # LLM 沒呼叫 submit_match 就用客觀分數 fallback，保證一定有結果
    fallback = sorted(candidates.values(), key=lambda p: p["score"], reverse=True)[:3]
    final: list[VendorProposal] = submitted.get("proposals") or fallback

    summary = submitted.get("summary") or result.text
    if not summary:
        summary = "已依你的偏好排出建議順序。" if final else "目前這個地區沒有可服務的廠商。"

    match: MatchResult = {
        "requestId": request["requestId"],
        "matchedAt": now_iso(),
        "proposals": final,
        "summary": summary,
    }
    if final:
        match["recommendedVendorId"] = final[0]["vendorId"]

    repo.put_match(match)

    trace: list[AgentTraceEntry] = result.trace
    return {"match": match, "trace": trace}
