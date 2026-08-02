## Why

`add-openpoint-reward-disclosure` 讓住戶在訂單成立時看到預計回饋，但點數會永遠停在 `01 待發放`，因為 walking skeleton 的終點是 `provider_confirmed`（廠商答應會來），沒有「服務完成」與「住戶驗收」。

這個缺口同時擋住兩件事：點數無法真的入帳（`02 已發放`），住戶也無法評價商家 —— 服務還沒發生就開放評價是錯的。主辦資料集的 `mms_order_record` 用 `complete_time`（註解明示「用於判斷點數發放時機」）與 `comment_status`（`00` 無須評價／`01` 未評價／`02` 已評價）表達同一個順序。

## What Changes

- 新增兩個 stage：`awaiting_resident_acceptance`（廠商已回報完工，待住戶驗收）與 `completed`（服務已完成，點數已入帳）。
- 新增廠商回報完工的介面：`GET /api/v1/provider-active-cases` 列出已承接未完成的案件，`POST /api/v1/provider-active-cases/{service_request_id}/completion` 回報完工並可回報完工金額。
- 住戶在原對話回覆「驗收」才結案並發放點數。廠商單方回報完工不得結案。
- 點數發放依 ADR-0007 以**完工金額重算**，不沿用訂單成立時的預估值；預估值保留在 `estimatedPoints` 與 `estimatedBasisAmount`，差異以 `amountAdjusted` 明示。
- 新增 append-only 點數流水帳 `point_ledger`，作為「是否已發放」的真實來源，重複驗收不得重複入帳。
- `provider_confirmed` 的「我的預約」分頁歸類由「已完成」改為「進行中」，只有 `completed` 才算完成。

## Capabilities

### New Capabilities

- `service-completion-and-point-grant`: 定義完工回報、住戶驗收、點數重算與發放、流水帳與重複發放防護。

### Modified Capabilities

- `openpoint-reward-disclosure`: 回饋投影新增 `grantedPoints`、`estimatedBasisAmount`、`amountAdjusted`、`grantedAt`，狀態可由 `01` 轉 `02`。

## Impact

- 後端：`points.py` 新增 `grant_reward`、`ledger_entry`、`grant_disclosure_sentence`；`service.py` 新增完工與驗收轉移；`store.py` 新增 `point_ledger`，並同步 `rds_store.py` 的 `STATE_FIELDS`（漏加會讓 staging 靜默遺失流水帳）。
- 前端：新增廠商「進行中」區塊與完工回報表單；「我的預約」以綠色區塊區分已入帳。
- 資料：`point_ledger` 以 `ledgerId` 為鍵的 object，因為 `RdsJsonStore._restore_state` 要求每個持久化欄位都是 JSON object。

## Out of Scope

- 點數折抵（`used_points`）、退點（`refund_points`）與 `04 已取消` 的收回轉移。
- `in_service`（施工中）stage 與廠商開工回報。
- 住戶對商家的評價與評價聚合回饋媒合排序。
- 發放冷卻期（主辦訂位類的「7 天後核銷」），目前驗收後即時入帳。
