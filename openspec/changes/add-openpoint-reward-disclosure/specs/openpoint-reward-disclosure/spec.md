## ADDED Requirements

### Requirement: 揭露時機綁定訂單成立
系統 SHALL 只在廠商回報訂單成立（`accept`）成功後才產生並揭露回饋點數。案件在 `waiting_provider_response`、`waiting_resident_information`、`awaiting_resident_confirmation` 或 `safety_hold` 期間 MUST NOT 出現回饋點數，避免住戶把尚未成立的案件誤認為已可獲得回饋。

#### Scenario: 廠商承接後揭露
- **WHEN** 廠商對指派給自己的任務成功回報 `accept`
- **THEN** 承接結果回傳 `pointsReward`，且原對話的 final message 同時告知預計點數、計算依據與發放狀態

#### Scenario: 尚未承接不揭露
- **WHEN** 案件已建立並委派廠商但廠商尚未回應
- **THEN** 案件投影的 `pointsReward` 為 null，「我的預約」不顯示任何回饋金額

#### Scenario: 婉拒與補件不揭露
- **WHEN** 廠商回報 `decline` 或 `needs_information`
- **THEN** 系統不產生回饋點數，改派或補件流程不受影響

### Requirement: 點數狀態沿用主辦資料語意
系統 SHALL 使用 `mms_order_record.point_status` 的代碼語意：`01` 待發放、`02` 已發放、`03` 不發放、`04` 已取消。訂單成立時的揭露 MUST 固定為 `01 待發放`，且 MUST 一併說明發放條件為服務完成並經住戶驗收後。

#### Scenario: 訂單成立時的狀態
- **WHEN** 回饋點數在廠商承接後產生
- **THEN** `status` 為 `01`、`statusLabel` 為「待發放」，且揭露文字包含發放條件

#### Scenario: 不得在此階段標示已發放
- **WHEN** 案件仍停在 `provider_confirmed`
- **THEN** 系統 MUST NOT 將任何點數標示為 `02 已發放`

### Requirement: 計算基礎與金額來源可辨識
系統 SHALL 以實付金額為點數計算基礎。廠商回報 `estimatedAmount` 時採用該金額並標示來源為 `provider_reported`；未回報時採用服務類別基準金額並標示為 `issue_type_baseline`。投影 MUST 讓前端能向住戶說明金額來源，不得讓平台估算值看起來像廠商正式報價。

#### Scenario: 廠商回報金額
- **WHEN** 廠商承接時回報 `estimatedAmount` 為 5000
- **THEN** `basisAmount` 為 5000、`amountSource` 為 `provider_reported`，回饋為 50 點

#### Scenario: 廠商未回報金額
- **WHEN** 廠商承接時未提供 `estimatedAmount`，且案件 `issueType` 為 `leak`
- **THEN** `basisAmount` 採類別基準 2800、`amountSource` 為 `issue_type_baseline`，回饋為 28 點

### Requirement: 確定性整數計算與單筆上限
系統 SHALL 以整數運算計算點數，費率以萬分位表示，結果向下取整，並套用單筆訂單上限。相同輸入 MUST 在任何執行環境得到相同點數；套用上限時 MUST 明示，不得靜默截斷。

#### Scenario: 相同輸入結果穩定
- **WHEN** 以相同服務類別、相同基礎金額重複計算
- **THEN** 得到完全相同的點數，不因浮點誤差產生差異

#### Scenario: 超過單筆上限
- **WHEN** 基礎金額為 1000000 且費率為 1%
- **THEN** 點數為上限 500 點，且 `capped` 為 true 讓 UI 明示已套用上限

### Requirement: 金額驗證不得消耗廠商任務
系統 SHALL 在進入交易前驗證 `estimatedAmount`：MUST 為 1 至 1000000 的整數，MUST 拒絕布林值、非數字字串與非整數值。驗證失敗 MUST 回傳 422，且 MUST NOT 改變任務狀態或版本。

#### Scenario: 不合法金額被拒絕
- **WHEN** 廠商以 `estimatedAmount` 為 0、負數、非數字字串或超過上限的值承接
- **THEN** 系統回傳 422，任務仍為 `pending` 且版本不變，廠商可用正確金額重試

### Requirement: Demo 記帳邊界必須明示
OPENPOINT 為真實資產系統，系統 MUST NOT 在 MVP 對外部帳戶發點。所有揭露 SHALL 標示為平台內 Demo 記帳，並在住戶可見的對話與「我的預約」同時呈現此邊界。

#### Scenario: 對話與預約頁一致揭露
- **WHEN** 住戶在對話或「我的預約」看到回饋點數
- **THEN** 兩處都顯示尚未連動 OPENPOINT 正式帳戶的說明，`isDemoLedger` 為 true

### Requirement: 揭露內容不得包含個資
回饋點數的投影、揭露文字與狀態事件 MUST NOT 包含姓名、電話、Email、詳細地址或附件內容。

#### Scenario: 事件與投影僅含金額與點數
- **WHEN** 系統寫入 `points_reward_estimated` 事件並回傳投影
- **THEN** 內容只含服務類別、金額、費率、點數與狀態，不含任何聯絡資料
