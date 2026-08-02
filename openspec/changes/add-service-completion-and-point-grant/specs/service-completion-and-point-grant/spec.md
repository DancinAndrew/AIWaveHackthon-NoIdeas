## ADDED Requirements

### Requirement: 完工回報只能由指派廠商在已確認案件上進行
系統 SHALL 只允許案件目前指派的廠商回報完工，且案件 MUST 已處於 `provider_confirmed`。授權檢查 MUST 先於 payload 驗證，避免未指派的廠商利用驗證差異探測案件是否存在。

#### Scenario: 指派廠商回報完工
- **WHEN** 已承接的廠商對其案件回報完工
- **THEN** 案件轉為 `awaiting_resident_acceptance`、`waitingFor` 為 `resident`，並在原對話新增請住戶驗收的訊息

#### Scenario: 案件尚未確認
- **WHEN** 廠商在案件仍為 `waiting_provider_response` 時回報完工
- **THEN** 系統回傳衝突錯誤，案件狀態不變

#### Scenario: 非指派廠商
- **WHEN** 未被指派的廠商嘗試回報完工
- **THEN** 系統回傳未授權錯誤，且不洩漏案件是否存在

### Requirement: 只有住戶明確驗收才結案並發放點數
系統 MUST NOT 因廠商回報完工就結案或發放點數。案件 SHALL 只在住戶於原對話明確表達驗收後才轉為 `completed` 並發放點數。住戶回報問題時 MUST 維持 `awaiting_resident_acceptance`。

#### Scenario: 住戶驗收
- **WHEN** 住戶在 `awaiting_resident_acceptance` 回覆驗收
- **THEN** 案件轉為 `completed`、`waitingFor` 為 null，點數狀態由 `01` 轉為 `02`，並寫入 `resident_accepted_completion` 與 `points_granted` 事件

#### Scenario: 住戶回報施工問題
- **WHEN** 住戶在 `awaiting_resident_acceptance` 描述施工仍有問題
- **THEN** 案件維持 `awaiting_resident_acceptance`、點數維持 `01 待發放`，且流水帳不得產生任何項目

#### Scenario: 完工回報後尚未驗收
- **WHEN** 廠商已回報完工但住戶尚未回覆
- **THEN** 案件投影的點數 `status` 仍為 `01`、`grantedPoints` 為 null

### Requirement: 發放點數以完工金額重算
系統 SHALL 在發放時以廠商回報的完工金額重算點數，MUST NOT 沿用訂單成立時的預估值。廠商未回報完工金額時 SHALL 沿用訂單成立時的計算基礎與金額來源。預估值 MUST 保留於 `estimatedPoints` 與 `estimatedBasisAmount`，且金額造成點數不同時 MUST 以 `amountAdjusted` 明示，不得靜默替換數字。

#### Scenario: 完工金額高於預估
- **WHEN** 訂單成立時預估 5000 元、廠商回報完工金額 6200 元，費率為 1%
- **THEN** `grantedPoints` 為 62、`basisAmount` 為 6200、`estimatedPoints` 仍為 50、`amountAdjusted` 為 true，且揭露文字說明原預估點數

#### Scenario: 未回報完工金額
- **WHEN** 廠商回報完工但未提供金額，訂單成立時基礎為 5000 元
- **THEN** `grantedPoints` 為 50、`basisAmount` 為 5000、`amountAdjusted` 為 false

#### Scenario: 完工金額格式不合法
- **WHEN** 廠商以 0、負數、非數字字串、布林值或超過上限的金額回報完工
- **THEN** 系統回傳 422，案件維持 `provider_confirmed`，廠商可用正確金額重試

### Requirement: 流水帳是發放的真實來源且不得重複入帳
系統 SHALL 以 append-only 流水帳記錄每次發放，並以流水帳而非案件欄位判斷是否已發放。同一案件 MUST NOT 產生多於一筆 `earn` 項目，即使住戶重複表達驗收。

#### Scenario: 重複驗收
- **WHEN** 住戶在案件已 `completed` 後再次回覆驗收
- **THEN** 系統回覆該案件已完成且點數已入帳，流水帳中該案件的 `earn` 項目仍只有一筆

#### Scenario: 流水帳項目內容
- **WHEN** 點數發放完成
- **THEN** 流水帳項目包含案件、住戶、方向 `earn`、點數、狀態 `02`、計算基礎與發放時間，且不含姓名、電話、Email 或地址

### Requirement: 完成前不得歸類為已完成
系統 SHALL 只把 `completed` 視為完成。`provider_confirmed` 與 `awaiting_resident_acceptance` MUST 呈現為進行中，讓住戶不會誤認為服務已結束。

#### Scenario: 廠商已確認到場
- **WHEN** 廠商已確認到場但尚未回報完工
- **THEN** 該案件在住戶的預約列表歸類為進行中，而非已完成
