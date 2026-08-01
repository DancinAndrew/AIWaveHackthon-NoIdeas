"""生活管家 Agent：代表會員的 AI 代理人。

這是整個提案的核心：把「找分類 -> 填長表單 -> 跟多家廠商來回問價」
壓縮成一段對話。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .bedrock import AgentTool, run_agent
from .domain import (
    PERIOD_LABEL,
    SERVICE_VENDOR_ID,
    AgentTraceEntry,
    Booking,
    ChatSession,
    ChatTurnResult,
    ServiceRequest,
)
from .geo import describe_address, find_county, list_districts, resolve_address
from .ids import (
    iso_date_plus,
    new_order_no,
    new_request_id,
    new_session_id,
    now_iso,
    today_iso,
)
from .match_client import call_match_agent
from .repo import get_repo

SYSTEM_PROMPT = """你是 OpenPoint 的「生活管家」，一個代表會員的 AI 代理人。

## 你存在的理由
現在會員要修冷氣，得自己在 App 裡找分類、填一長串表單、再跟好幾家廠商來回問價。
你的任務是把這一切變成「一段對話」：會員只要說「冷氣不冷」，剩下的你處理。

## 每一輪的固定動作順序（非常重要）
1. 呼叫 get_member_context 看目前狀況（會員資料、服務單已有什麼、還缺什麼）。
2. **只要會員這一輪講了任何新資訊，就必須先呼叫 update_request 存起來，然後才回話。**
   包含症狀、地址、時段、品牌、機型、機齡、預算、期望日期。
   會員資料裡查到的東西（例如主臥那台是 2018 年大金分離式）也要一起寫進去，不要只放在心裡。
3. 看 update_request 回傳的 missing：
   - 還有缺 -> 針對「缺的第一項」問一個問題就好。
   - canDispatch 是 true -> 立刻呼叫 dispatch_matching，不要再多問。
4. 有媒合結果後，會員表示選定某一家就呼叫 create_booking。

絕對不要出現「呼叫了 get_member_context 就直接回話問問題」這種情況 ——
只要有新資訊沒存，下一輪你就會忘記，會員得重講一次。

## 其他準則
- **已經知道的事情不要問，改成確認。** 例如「幫你修主臥那台 2018 年的大金分離式，對嗎？」
- **會員有多個地址時，一定要先問這次是哪一個，不可以自己挑一個就去媒合。**
  只有一個地址才可以直接用。
- **一次只問一件事。** 不要一口氣丟五個問題，那就跟填表單沒兩樣。
- 冷氣維修媒合最少只需要：症狀、地址、方便時段。品牌／機齡從會員資料帶入就好，不要追問。
- 會員只要透露對價格的態度（「預算不要太高」「貴一點沒關係」），
  就呼叫 remember_preference 更新 priceSensitivity。
- 拿到方案後，用**口語**幫會員做重點比較，主動講出取捨（誰便宜、誰快、誰有保固），
  並問他要選哪一家。報價區間之外若有 majorRisks（例如壓縮機），要誠實提一句。
- 觀察到長期偏好（在意價格、討厭推銷、只要女師傅、偏好某品牌…）就呼叫 remember_preference。
  這是平台之後能精準推播的基礎，但**不要為了記錄而追問**，只記錄自然聊出來的。

## 語氣
繁體中文、像個熟悉他家狀況的鄰居，不是客服機器人。
不要用「親愛的顧客您好」這種話。不要每句都用 emoji 開頭。回覆控制在 4 句以內。

**人稱要正確。** 你是代理人，不是會員本人。
會員的家、會員的冷氣一律說「你家」「你那台」，
絕對不要說成「我家」「我的冷氣」—— 那會讓會員以為你搞錯對象。
提到自己時說「我幫你…」。

## 絕對不要
- 不要自己編造報價、廠商名稱、到府時間。這些只能來自 dispatch_matching 的結果。
- 不要一次列出所有廠商的所有細節，挑重點講。
- 不要在資訊不足時就 dispatch_matching。"""

REQUIRED_HINT = ["症狀", "地址", "方便時段"]


def missing_fields(req: ServiceRequest) -> list[str]:
    """判斷服務單還缺什麼才能媒合。"""
    missing: list[str] = []
    if not (req.get("slots", {}).get("symptoms")):
        missing.append("症狀")
    if not req.get("address"):
        missing.append("服務地址")
    if not req.get("preferredContactTime"):
        missing.append("方便時段")
    return missing


def request_fingerprint(req: ServiceRequest) -> str:
    """服務單中會影響媒合結果的欄位指紋。

    LLM 有時會在資訊沒變的情況下重複呼叫 dispatch_matching，
    那是一次沒必要的 Bedrock 往返（實測 20 秒以上）。
    用指紋比對就能直接回上次的結果，不必靠 prompt 拜託模型別重複。
    """
    slots = req.get("slots", {})
    payload = {
        "category": req.get("category"),
        "symptoms": sorted(slots.get("symptoms") or []),
        "brand": slots.get("brand"),
        "variant": slots.get("variant"),
        "ageYears": slots.get("ageYears"),
        "address": req.get("address"),
        "preferredContactTime": req.get("preferredContactTime"),
        "preferredServiceDate": req.get("preferredServiceDate"),
        "budgetMax": req.get("budgetMax"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def suggested_prompts() -> list[str]:
    """給前端的「建議開場話術」，讓 demo 有起點。"""
    return [
        "我家冷氣不冷了",
        "主臥的冷氣在滴水，越來越嚴重",
        "冷氣開了會有很大的異音",
        f"我想約 {iso_date_plus(2)} 下午請人來看冷氣",
    ]


FALLBACK_REPLY = "抱歉，我剛剛沒接上。可以再說一次你的需求嗎？"


def _resolve_proposal(
    proposals: list[dict[str, Any]], vendor_id: str | None, vendor_name: str | None
) -> dict[str, Any] | None:
    """用 vendorId 或（模糊的）廠商名稱找出對應方案。"""
    if vendor_id:
        hit = next((p for p in proposals if p["vendorId"] == vendor_id), None)
        if hit:
            return hit
        # 模型有時會把名稱塞進 vendorId 欄位
        vendor_name = vendor_name or vendor_id

    if not vendor_name:
        return None

    needle = vendor_name.strip().replace(" ", "")
    exact = next((p for p in proposals if p["vendorName"].replace(" ", "") == needle), None)
    if exact:
        return exact

    partial = [
        p
        for p in proposals
        if needle in p["vendorName"].replace(" ", "") or p["vendorName"].replace(" ", "") in needle
    ]
    # 只有唯一命中才敢認，避免把訂單開給錯的廠商
    return partial[0] if len(partial) == 1 else None


def _to_bedrock_messages(history: list[dict], user_text: str) -> list[dict[str, Any]]:
    """把對話記錄壓縮成純文字歷史，避免 session 無限膨脹。

    Bedrock 不接受空的 text block，且 role 必須 user/assistant 交替出現，
    所以這裡過濾空訊息並合併連續同 role 的訊息。
    """
    msgs: list[dict[str, Any]] = []
    for m in history[-12:]:
        text = (m.get("text") or "").strip()
        if not text:
            continue
        if msgs and msgs[-1]["role"] == m["role"]:
            msgs[-1]["content"][0]["text"] += f"\n{text}"
            continue
        msgs.append({"role": m["role"], "content": [{"text": text}]})

    if msgs and msgs[-1]["role"] == "user":
        msgs[-1]["content"][0]["text"] += f"\n{user_text}"
    else:
        msgs.append({"role": "user", "content": [{"text": user_text}]})
    return msgs


def run_user_agent_turn(
    *, session_id: str | None, inbr_account_id: str, message: str
) -> ChatTurnResult:
    repo = get_repo()
    sid = session_id or new_session_id()

    session: ChatSession = repo.get_session(sid) or {
        "sessionId": sid,
        "inbrAccountId": inbr_account_id,
        "messages": [],
        "updatedAt": now_iso(),
    }

    user = repo.get_user(inbr_account_id)
    if user is None:
        raise KeyError(f"找不到會員: {inbr_account_id}")

    # 這些用 dict 包起來，讓內層 closure 可以改（避免 nonlocal 一長串）
    state: dict[str, Any] = {
        "request": repo.get_request(session["activeRequestId"])
        if session.get("activeRequestId")
        else None,
        "match": None,
        "booking": None,
        "preferences": user.get("preferences", {}),
    }
    if state["request"]:
        state["match"] = repo.get_match(state["request"]["requestId"])
    extra_trace: list[AgentTraceEntry] = []

    def ensure_request(category: str = "AC_REPAIR") -> ServiceRequest:
        if state["request"]:
            return state["request"]
        req: ServiceRequest = {
            "requestId": new_request_id(),
            "inbrAccountId": inbr_account_id,
            "category": category,
            "status": "COLLECTING",
            "slots": {},
            "createdAt": now_iso(),
            "updatedAt": now_iso(),
        }
        period = user.get("preferences", {}).get("preferredContactTime")
        if period:
            req["preferredContactTime"] = period
        # 只有一個地址就直接帶入，少問一題
        addresses = user.get("addresses") or []
        if len(addresses) == 1:
            req["address"] = addresses[0]
        state["request"] = req
        session["activeRequestId"] = req["requestId"]
        repo.put_request(req)
        return req

    # ---------------- Tools ----------------

    def get_member_context(_: dict[str, Any]) -> dict[str, Any]:
        req = state["request"]
        return {
            "member": {
                "displayName": user.get("displayName"),
                "points": user.get("points"),
                "addresses": [
                    {
                        "label": describe_address(a),
                        "countyName": a.get("countyName"),
                        "districtName": a.get("districtName"),
                    }
                    for a in user.get("addresses", [])
                ],
                "airConditioners": [
                    a for a in user.get("appliances", []) if a.get("kind") == "AC"
                ],
                "allAppliances": user.get("appliances", []),
                "preferences": user.get("preferences", {}),
            },
            "currentRequest": (
                {
                    "requestId": req["requestId"],
                    "category": req.get("category"),
                    "status": req.get("status"),
                    "slots": req.get("slots", {}),
                    "address": describe_address(req["address"]) if req.get("address") else None,
                    "preferredContactTime": req.get("preferredContactTime"),
                    "preferredServiceDate": req.get("preferredServiceDate"),
                    "missing": missing_fields(req),
                }
                if req
                else None
            ),
            "hint": "冷氣維修媒合最少需要：" + "、".join(REQUIRED_HINT),
            "today": today_iso(),
        }

    def update_request(patch: dict[str, Any]) -> dict[str, Any]:
        req = ensure_request(patch.get("category") or "AC_REPAIR")
        if patch.get("category"):
            req["category"] = patch["category"]

        slots = req.setdefault("slots", {})
        if patch.get("symptoms"):
            existing = slots.get("symptoms") or []
            for s in patch["symptoms"]:
                if s not in existing:
                    existing.append(s)
            slots["symptoms"] = existing
        for key in ("brand", "variant", "description", "selfTried"):
            if patch.get(key):
                slots[key] = patch[key]
        if isinstance(patch.get("ageYears"), int):
            slots["ageYears"] = patch["ageYears"]

        if patch.get("preferredContactTime"):
            req["preferredContactTime"] = patch["preferredContactTime"]
        if patch.get("preferredServiceDate"):
            req["preferredServiceDate"] = patch["preferredServiceDate"]
        if isinstance(patch.get("budgetMax"), int):
            req["budgetMax"] = patch["budgetMax"]

        address_warning: str | None = None
        if patch.get("addressText"):
            text = str(patch["addressText"])
            compact = text.replace(" ", "")
            # 先看是不是會員已存的地址
            known = next(
                (a for a in user.get("addresses", []) if compact in describe_address(a).replace(" ", "")),
                None,
            )
            resolved = known or resolve_address(free_text=text)
            if resolved:
                req["address"] = resolved
            else:
                address_warning = "這個地址無法對應到縣市/行政區，請向會員確認縣市與行政區"

        req["updatedAt"] = now_iso()
        missing = missing_fields(req)
        req["status"] = "READY_TO_MATCH" if not missing else "COLLECTING"
        repo.put_request(req)

        out: dict[str, Any] = {
            "requestId": req["requestId"],
            "status": req["status"],
            "slots": req.get("slots", {}),
            "address": describe_address(req["address"]) if req.get("address") else None,
            "preferredContactTime": req.get("preferredContactTime"),
            "missing": missing,
            "canDispatch": not missing,
        }
        if address_warning:
            out["addressWarning"] = address_warning
        return out

    def list_area_options(payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("countyName") or "")
        county = find_county(name)
        districts = list_districts(county["code"]) if county else []
        return {
            "countyName": county["name"] if county else name,
            "districts": districts,
            "note": "ok" if districts else "找不到該縣市",
        }

    def dispatch_matching(_: dict[str, Any]) -> dict[str, Any]:
        req = state["request"]
        if not req:
            return {"ok": False, "error": "還沒有服務單，請先呼叫 update_request"}
        missing = missing_fields(req)
        if missing:
            return {
                "ok": False,
                "error": "資訊還不齊，缺少：" + "、".join(missing),
                "missing": missing,
            }

        fingerprint = request_fingerprint(req)
        cached = state["match"]
        reused = bool(cached) and cached.get("requestFingerprint") == fingerprint

        if reused:
            match = cached
        else:
            req["status"] = "MATCHING"
            repo.put_request(req)

            out = call_match_agent(req, state["preferences"])
            extra_trace.extend(out.get("trace") or [])
            match = out["match"]
            match["requestFingerprint"] = fingerprint
            repo.put_match(match)
            state["match"] = match

            req["status"] = "MATCHED" if match.get("proposals") else "COLLECTING"
            req["updatedAt"] = now_iso()
            repo.put_request(req)

        return {
            "ok": True,
            "reusedPreviousMatch": reused,
            "note": "服務單內容沒有變更，直接沿用上次的媒合結果" if reused else "已重新媒合",
            "matchSummary": match.get("summary"),
            "proposals": [
                {
                    "vendorId": p["vendorId"],
                    "vendorName": p["vendorName"],
                    "rating": p["rating"],
                    "score": p["score"],
                    "priceRange": f"{p['quote']['estimatedMin']}~{p['quote']['estimatedMax']} 元",
                    "inspectionFee": p["quote"]["inspectionFee"],
                    "earliestDate": p["earliestSlot"]["date"],
                    "tags": p["tags"],
                    "reasons": p["reasons"],
                    "assumptions": p["quote"]["assumptions"],
                    "majorRisks": p["quote"].get("majorRisks") or [],
                    "supportsPoints": p["supportsPoints"],
                }
                for p in match.get("proposals", [])
            ],
        }

    def create_booking(payload: dict[str, Any]) -> dict[str, Any]:
        req = state["request"]
        match = state["match"]
        if not req or not match:
            return {"ok": False, "error": "還沒有媒合結果"}

        proposals = match.get("proposals", [])
        # 模型手上通常只記得廠商「名字」，硬要求精確 vendorId 會逼它回頭問會員
        # 「你要 V001 還是 V003」，那是很糟的體驗。所以這裡用名稱也能認。
        proposal = _resolve_proposal(
            proposals, payload.get("vendorId"), payload.get("vendorName")
        )
        if proposal is None:
            return {
                "ok": False,
                "error": "認不出是哪一家，請用媒合結果中的廠商名稱或 vendorId 再試一次",
                "available": [
                    {"vendorId": p["vendorId"], "vendorName": p["vendorName"]} for p in proposals
                ],
            }
        if not req.get("address"):
            return {"ok": False, "error": "服務單缺少地址"}

        booking: Booking = {
            "orderNo": new_order_no(),
            "requestId": req["requestId"],
            "inbrAccountId": inbr_account_id,
            "vendorId": proposal["vendorId"],
            "vendorName": proposal["vendorName"],
            "serviceVendorId": SERVICE_VENDOR_ID.get(req.get("category", ""), 11),
            "orderType": "01",  # 服務訂單
            # 到府檢測後才報價，對齊 mms_order_record 的 11 待訂金支付
            "orderStatus": "11",
            "serviceDate": payload.get("serviceDate") or proposal["earliestSlot"]["date"],
            "servicePeriod": proposal["earliestSlot"]["period"],
            "address": req["address"],
            "depositAmount": proposal["quote"]["inspectionFee"],
            "estimatedMin": proposal["quote"]["estimatedMin"],
            "estimatedMax": proposal["quote"]["estimatedMax"],
            "createdAt": now_iso(),
        }
        repo.put_booking(booking)
        state["booking"] = booking

        req["status"] = "BOOKED"
        req["updatedAt"] = now_iso()
        repo.put_request(req)

        # 成交即視為對該廠商特質的正向訊號
        state["preferences"] = repo.merge_preferences(
            inbr_account_id,
            {
                "interestedCategories": [req.get("category", "")],
                "preferredVendorTags": list(proposal.get("tags", []))[:2],
            },
        )

        return {
            "ok": True,
            "orderNo": booking["orderNo"],
            "vendorName": booking["vendorName"],
            "serviceDate": booking["serviceDate"],
            "servicePeriod": PERIOD_LABEL.get(booking["servicePeriod"], booking["servicePeriod"]),
            "depositAmount": booking["depositAmount"],
            "estimatedRange": f"{booking['estimatedMin']}~{booking['estimatedMax']} 元",
            "orderStatus": "11 待訂金支付",
        }

    def remember_preference(patch: dict[str, Any]) -> dict[str, Any]:
        note = patch.pop("note", None)
        if note:
            patch["notes"] = [note]
        state["preferences"] = repo.merge_preferences(inbr_account_id, patch)
        return {"ok": True, "preferences": state["preferences"]}

    tools = [
        AgentTool(
            name="get_member_context",
            description=(
                "取得會員的完整背景：姓名、常用地址、家中家電清單（品牌/機型/年份/位置）、"
                "偏好、點數，以及目前服務單狀態。開場必先呼叫。"
            ),
            schema={"type": "object", "properties": {}},
            run=get_member_context,
        ),
        AgentTool(
            name="update_request",
            description=(
                "把這一輪問到的資訊寫進服務單。只傳有變動的欄位。"
                "地址可以傳完整口語字串（如「台北市大安區復興南路一段100號」）。"
            ),
            schema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["AC_REPAIR", "AC_CLEAN", "PLUMBING", "HOME_CLEAN"],
                        "description": "服務類別，冷氣不冷/漏水/異音等維修問題用 AC_REPAIR",
                    },
                    "symptoms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": '症狀關鍵詞，例如 ["不冷","漏水"]',
                    },
                    "brand": {"type": "string", "description": "品牌，如 大金、日立"},
                    "variant": {"type": "string", "description": "機型：分離式 / 窗型 / 吊隱式"},
                    "ageYears": {"type": "integer", "description": "使用年數"},
                    "description": {"type": "string", "description": "會員原話描述，給廠商參考"},
                    "selfTried": {"type": "string", "description": "會員自己已經試過什麼"},
                    "addressText": {"type": "string", "description": "完整地址口語字串"},
                    "preferredContactTime": {
                        "type": "string",
                        "enum": ["1", "2", "3"],
                        "description": "1=上午 2=下午 3=皆可",
                    },
                    "preferredServiceDate": {
                        "type": "string",
                        "description": "期望到府日 YYYY-MM-DD",
                    },
                    "budgetMax": {"type": "integer", "description": "預算上限（元）"},
                },
            },
            run=update_request,
        ),
        AgentTool(
            name="list_districts",
            description="會員只講縣市、沒講行政區時，用這個列出該縣市可選的行政區。",
            schema={
                "type": "object",
                "properties": {
                    "countyName": {"type": "string", "description": "縣市名稱，如 台北市"}
                },
                "required": ["countyName"],
            },
            run=list_area_options,
        ),
        AgentTool(
            name="dispatch_matching",
            description=(
                "把服務單交給「廠商媒合代理」，牠會從廠商資料庫挑出最適配的 2~3 家"
                "並附上報價與最快到府日。資訊不齊全時會被拒絕。"
            ),
            schema={"type": "object", "properties": {}},
            run=dispatch_matching,
        ),
        AgentTool(
            name="create_booking",
            description=(
                "會員明確選定廠商後，建立預約單。"
                "vendorId 或 vendorName 給一個就好，都必須來自 dispatch_matching 的結果。"
            ),
            schema={
                "type": "object",
                "properties": {
                    "vendorId": {"type": "string", "description": "如 V001"},
                    "vendorName": {
                        "type": "string",
                        "description": "廠商名稱，如 冷研家電維修工作室（記不得 vendorId 時用這個）",
                    },
                    "serviceDate": {
                        "type": "string",
                        "description": "到府日 YYYY-MM-DD，沒指定就用該廠商最快日",
                    },
                },
            },
            run=create_booking,
        ),
        AgentTool(
            name="remember_preference",
            description=(
                "記錄會員的長期偏好，之後用於自動推播與媒合加權。"
                "只記錄自然聊出來的，不要為此追問。"
            ),
            schema={
                "type": "object",
                "properties": {
                    "priceSensitivity": {
                        "type": "number",
                        "description": "價格敏感度 0~1，會員明顯在意價格時給 0.8 以上",
                    },
                    "preferredContactTime": {"type": "string", "enum": ["1", "2", "3"]},
                    "preferredVendorTags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": '例如 ["女性技師","原廠零件","當日到府"]',
                    },
                    "blockedVendorIds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "會員排除的廠商",
                    },
                    "interestedCategories": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["AC_REPAIR", "AC_CLEAN", "PLUMBING", "HOME_CLEAN"],
                        },
                    },
                    "note": {"type": "string", "description": "一句話描述觀察到的偏好"},
                },
            },
            run=remember_preference,
        ),
    ]

    result = run_agent(
        agent_name="user-agent",
        system_prompt=SYSTEM_PROMPT,
        messages=_to_bedrock_messages(session.get("messages", []), message),
        tools=tools,
        temperature=0.4,
        max_turns=10,
    )

    # 永遠不要把空回覆存進歷史，否則下一輪送回 Bedrock 會 ValidationException
    reply = (result.text or "").strip() or FALLBACK_REPLY

    session.setdefault("messages", []).append(
        {"role": "user", "text": message, "at": now_iso()}
    )
    session["messages"].append({"role": "assistant", "text": reply, "at": now_iso()})
    session["updatedAt"] = now_iso()
    repo.put_session(session)

    req_out = repo.get_request(state["request"]["requestId"]) if state["request"] else None
    trace = sorted([*result.trace, *extra_trace], key=lambda t: t["at"])

    return {
        "sessionId": sid,
        "reply": reply,
        "request": req_out,
        "match": state["match"],
        "booking": state["booking"],
        "preferences": state["preferences"],
        "trace": trace,
    }
