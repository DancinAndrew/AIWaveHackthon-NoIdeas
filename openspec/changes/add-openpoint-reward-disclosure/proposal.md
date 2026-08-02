## Why

住戶在廠商承接後只知道「誰會來、什麼時候來」，看不到這筆服務可以換回多少 OPENPOINT。回饋點數是 OPEN POINT 生活圈的核心誘因，也是主辦單位資料集裡已經設計好的欄位：`mms_order_record` 具備 `final_amount`（點數計算基礎）、`earn_points`（由點數計算引擎填入）、`point_status`（01 待發放／02 已發放／03 不發放／04 已取消）與 `point_grant_time`，並有 `idx_order_record_point_process (point_status, order_status, complete_time)` 這條專為批次結算設計的索引。

同時 OPENPOINT 是真實資產系統。`SPEC.md` §2.3 明訂 MVP 不執行不可逆的外部交易，因此揭露必須誠實標示為平台內 Demo 記帳，不能讓住戶或評審誤認為已經對正式帳戶發點。

## What Changes

- 新增回饋點數揭露：廠商回報訂單成立（`accept`）時計算「應獲得點數」，狀態固定為 `01 待發放`，並在原對話的 final message 告知住戶。
- 新增廠商可回報的預估實付金額 `estimatedAmount`（選填）作為計算基礎；未回報時改用服務類別基準金額，並在 UI 明示金額來源。
- 新增「我的預約」卡片的回饋點數區塊，顯示預計點數、計算依據、發放狀態與 Demo 記帳邊界。
- 新增 `points_reward_estimated` 狀態事件，讓進度投影保留揭露時點。
- 點數計算採整數運算（費率以萬分位表示）並套用單筆上限，確保同一筆訂單在任何機器上得到相同結果。

## Capabilities

### New Capabilities

- `openpoint-reward-disclosure`: 定義回饋點數的計算基礎、費率、上限、狀態語意、揭露時機與 Demo 記帳邊界。

### Modified Capabilities

- `service-request-matching-lifecycle`: 廠商承接的回應契約新增選填 `estimatedAmount`，並在承接結果回傳 `pointsReward`。

## Impact

- 後端：新增 `packages/api/walking_skeleton/points.py`（點數計算引擎），`service.py` 在 accept 分支產生並保存 `pointsReward`，案件與進度投影一併帶出。
- 前端：`types.ts` 新增 `PointsReward`，`viewModels.ts` 新增 `pointsRewardPresentation`，`MyBookingsPage` 顯示回饋區塊，`DashboardPage` 讓廠商回報預估金額。
- 資料：本階段不新增資料表；點數只存在案件 aggregate 內。ledger 與實際發放屬後續變更。
- 安全：金額在進入交易前驗證，格式錯誤不得消耗廠商任務或推進版本；揭露文字不含任何個資。

## Out of Scope

- 實際發放（`02 已發放`）、收回（`04 已取消`）與 `mms_point_ledger` 流水帳。
- 點數折抵（`used_points`）與退點（`refund_points`）。
- 服務完成與住戶驗收的生命週期（`completed`），這是實際發放的前提。
- 住戶對商家的評價，以及把評價聚合分數餵回媒合排序。
