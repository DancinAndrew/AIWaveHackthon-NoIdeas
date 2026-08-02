# ADR-0007：OPENPOINT 回饋以平台內 Demo 記帳揭露，不對正式帳戶發點

- 狀態：Accepted
- 日期：2026-08-02
- 決策者：AIWaveHackthon-NoIdeas 團隊
- 關聯規格：`SPEC.md`、`openspec/changes/add-openpoint-reward-disclosure/`

## Context

住戶完成生活服務後獲得 OPENPOINT 回饋是 OPEN POINT 生活圈的核心誘因，也是主辦單位資料集已經內建的能力。`data/competition/mms_order_record.sql` 具備 `final_amount`（註解明示為點數計算基礎）、`earn_points`（註解明示由點數計算引擎填入）、`used_points`、`refund_points`、`point_status`（01 待發放／02 已發放／03 不發放／04 已取消）、`point_grant_time`，以及 `idx_order_record_point_process (point_status, order_status, complete_time)` 這條專為批次結算掃描設計的索引。

問題在於 OPENPOINT 是真實存在的會員資產系統。對它發點是不可逆的外部交易，而 `SPEC.md` §2.3 明訂 MVP 不直接執行付款、退款或其他不可逆外部交易，外部系統一律使用明確標示的 mock adapter。

同時，我們沒有正式的點數 API 憑證，也沒有可用的沙箱帳戶。Demo 若讓畫面看起來像已經發點，等於對評審做出無法驗證的宣稱。

## Decision

### 1. 只計算與揭露，不發放

平台計算「應獲得點數」並向住戶揭露，狀態固定為 `01 待發放`。實際發放（`02`）、不發放（`03`）與取消（`04`）的轉移不在本階段實作。所有點數都只存在自家資料，不呼叫任何外部帳務介面。

### 2. 揭露時機綁在訂單成立

廠商回報訂單成立（`accept`）時才產生回饋揭露。案件尚未被廠商承接時不顯示任何金額，避免住戶把「已委派」誤認為「已成立」。發放條件（服務完成並經住戶驗收後）必須與點數一起呈現。

### 3. 計算基礎以廠商回報為主，平台估算為輔

廠商承接時可回報預估實付金額，對應 `final_amount` 由服務商提供的原始設計。未回報時使用服務類別基準金額，但投影必須帶 `amountSource` 讓前端明示是平台估算，不得讓估算值看起來像正式報價。

### 4. 確定性整數運算

費率以萬分位（basis points）整數表示，`basis_amount * rate_bp // 10_000` 全程整數運算並套用單筆上限。點數是對住戶的承諾，不接受浮點誤差讓 Flask Lambda 與 AgentCore Runtime 對同一筆訂單算出不同結果。

### 5. Demo 邊界在住戶可見處明示

對話 final message 與「我的預約」都必須顯示尚未連動 OPENPOINT 正式帳戶。投影帶 `isDemoLedger` 旗標，讓前端無法「不小心」漏掉這個揭露。

## Alternatives Considered

### 直接接 OPENPOINT 正式 API

最有說服力，但違反 `SPEC.md` 的不可逆交易邊界，且沒有憑證與沙箱。錯誤的發點在真實資產系統上難以回收，風險與收益完全不成比例。

### 畫面呈現成已發點，實際不發

Demo 效果最好，成本最低，但這是對評審的不實陳述，也違反專案自己訂的「不把 mock 說成真實整合」原則。明確拒絕。

### 不看金額，每案固定回饋點數

實作最簡單，但會讓 `final_amount` 與 `earn_points` 兩個主辦欄位失去意義，也無法展示點數計算引擎的存在。

### 現在就建 `mms_point_ledger`

append-only 流水帳是實際發放的正確設計，但在只有「待發放」一種狀態時，ledger 僅有單一寫入方向，無法驗證它真正要解決的對帳問題。等服務完成流程進來時一併設計。

## Consequences

### 正面

- 住戶在訂單成立時就看到回饋誘因，補上了原本缺失的價值閉環。
- 沿用主辦資料的欄位與狀態語意，未來要接真實結算時不需要重新設計代碼。
- 整數運算讓點數在任何執行環境都可重現，可直接寫成自動化測試。
- 誠實標示 Demo 邊界，維持專案「不誇大實作狀態」的一致性。

### 負面與風險

- 住戶可能把「預計」當成保證。金額來自廠商預估，實際完工金額可能不同；實際發放時必須以完工金額重算，不可沿用揭露時的預估值。
- 費率與單筆上限目前是程式常數。活動檔期或分級費率進來時需要外部化設定。
- 「待發放」會一直停在待發放，直到服務完成生命週期實作完成。這是已知且刻意的缺口，記錄在 OpenSpec 的 Out of Scope。

## Follow-up

1. 服務完成與住戶驗收生命週期（`in_service` → `awaiting_resident_acceptance` → `completed`），這是 `02 已發放` 的前提。
2. `mms_point_ledger` append-only 流水帳，含發放、收回與退點方向。
3. 住戶評價與聚合分數回饋媒合排序；評價文字有 prompt injection 與個資風險，只有聚合數值可進入排序邏輯。
