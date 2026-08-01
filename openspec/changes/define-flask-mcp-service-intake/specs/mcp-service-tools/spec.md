## ADDED Requirements

### Requirement: MCP 工具清單與 Schema
MCP Server SHALL 公開且僅公開 `get_form_schema`、`search_providers`、`create_service_request`、`get_service_request_status`、`list_provider_service_requests` 與 `update_service_request_status` 六項 MVP 工具；每項工具 MUST 提供封閉的 JSON `inputSchema` 與 `outputSchema`，未宣告欄位不得直接進入 service layer。

#### Scenario: 列出工具
- **WHEN** 已授權的 MCP client 呼叫 `tools/list`
- **THEN** 回傳六項 MVP 工具、用途描述及其輸入 Schema

#### Scenario: 未知輸入欄位
- **WHEN** 工具輸入含 Schema 未宣告欄位
- **THEN** 呼叫失敗並回傳 `validation_error`，未知欄位不得傳至資料庫查詢

### Requirement: 取得表單 Schema 工具
`get_form_schema` SHALL 接受支援的 `service_type` 與可選版本，回傳對應的啟用 JSON Schema、實際版本與快取識別；若版本省略則 MUST 回傳最新啟用版本。

#### Scenario: 取得指定類別最新表單
- **WHEN** client 以 `restaurant_reservation` 且未指定版本呼叫工具
- **THEN** 回傳餐廳訂位最新啟用 Schema 與明確 `schema_version`

#### Scenario: 指定版本不存在
- **WHEN** client 要求不存在或已撤銷的版本
- **THEN** 回傳 `form_schema_not_found`，不得默默改用其他版本

### Requirement: 搜尋服務商工具
`search_providers` SHALL 只使用 Amazon RDS for PostgreSQL 或受控 mock／合作廠商 adapter 的即時結構化資料進行硬條件過濾與排序，回傳服務商、服務項目、分數、可解釋理由及資料新鮮度；MUST NOT 以 Knowledge Base 內容宣稱價格、庫存或可用時段。

#### Scenario: 有符合條件的服務商
- **WHEN** 類別、地區、時段及類別專屬硬條件均有效
- **THEN** 工具依確定性規則排序並對每個結果回傳非空 `reasons`

#### Scenario: 無符合結果
- **WHEN** 沒有服務商同時符合必要地區與能力條件
- **THEN** 回傳空的 `matches` 與可用的放寬建議，不得臆造服務商

#### Scenario: 即時來源失效
- **WHEN** 服務商或商品資料來源逾時且沒有仍在允許新鮮度內的快取
- **THEN** 回傳 `live_data_unavailable`，不得以 Knowledge Base 結果替代

### Requirement: 建立案件工具的確認與冪等性
`create_service_request` MUST 要求伺服器簽發的 `submission_ref`、`confirmation_token` 與 `idempotency_key`；伺服器 SHALL 驗證提交版本、個資同意與確認內容後，以單一資料庫交易建立案件及第一筆狀態事件，再以案件 ID 作為冪等 execution name 啟動 Step Functions workflow。模型不得在 tool arguments 中傳送原始 PII。

#### Scenario: 首次建立案件
- **WHEN** submission 有效、使用者已確認、同意仍有效且 idempotency key 尚未使用
- **THEN** 系統建立一筆案件與 `submitted` 事件，啟動一個 workflow execution，並回傳 `201` 語意的案件識別及 workflow projection

#### Scenario: 相同請求重試
- **WHEN** 相同 actor 與相同 idempotency key 重複呼叫且 payload 雜湊相同
- **THEN** 回傳原案件並將 `deduplicated` 設為真，不得建立第二筆案件

#### Scenario: 同一 key 對應不同內容
- **WHEN** 相同 idempotency key 被用於不同 payload 雜湊
- **THEN** 回傳 `idempotency_conflict`，不得覆蓋或建立案件

#### Scenario: 缺少明確確認
- **WHEN** submission 完整但 confirmation token 不存在、過期或與摘要不一致
- **THEN** 回傳 `confirmation_required`，且資料庫不得新增案件

### Requirement: 案件讀取授權
`get_service_request_status` SHALL 從已驗證身分推導 actor，不接受由模型自行指定 actor；只有案件消費者、已獲授權的候選服務商成員及管理員可讀取相應資料，回傳內容 MUST 依角色遮蔽 PII，並包含來自 RDS 的 workflow stage、waiting role、公開標籤與更新時間，不得直接讀 Step Functions history。

#### Scenario: 消費者查詢自己的案件
- **WHEN** 已驗證消費者查詢自己建立的案件
- **THEN** 回傳案件狀態、workflow projection、媒合摘要與可見回覆

#### Scenario: 查詢他人案件
- **WHEN** 消費者查詢不屬於自己的案件
- **THEN** 回傳 `forbidden` 或不洩漏存在性的 `not_found`，且不回傳任何案件資料

#### Scenario: 尚未承接的服務商
- **WHEN** 候選服務商查詢標示為承接後才公開的聯絡資料
- **THEN** 回傳遮蔽後需求摘要，完整聯絡資料不得出現在 tool result 或日誌

### Requirement: 服務商案件列表
`list_provider_service_requests` SHALL 從驗證身分推導服務商組織，支援狀態篩選、游標分頁與固定排序，且 MUST 只回傳該組織有權查看的案件。

#### Scenario: 分頁列出候選案件
- **WHEN** 已驗證服務商成員以有效狀態與 limit 查詢
- **THEN** 回傳授權範圍內的案件、`next_cursor` 與穩定排序

#### Scenario: 消費者呼叫服務商列表
- **WHEN** 只有消費者角色的 actor 呼叫此工具
- **THEN** 回傳 `forbidden`，不得以傳入 provider ID 繞過

### Requirement: 案件狀態更新
`update_service_request_status` MUST 要求目標狀態、`expected_version`、非空 idempotency key 與可選非敏感備註；系統 SHALL 驗證角色、合法狀態轉移及樂觀鎖後，在同一交易更新案件與新增事件。

#### Scenario: 合法狀態更新
- **WHEN** 有權限的服務商以目前版本執行合法轉移
- **THEN** 案件版本加一、狀態更新且新增不可變狀態事件

#### Scenario: 非法狀態轉移
- **WHEN** actor 嘗試從終止狀態轉回處理中，或執行角色不允許的轉移
- **THEN** 回傳 `invalid_state_transition`，案件與歷程均不改變

#### Scenario: 並行更新衝突
- **WHEN** `expected_version` 與目前案件版本不一致
- **THEN** 回傳 `version_conflict` 及目前非敏感版本資訊，呼叫方必須重新讀取後再決定

### Requirement: 一致錯誤契約與可觀測性
所有 MCP 工具失敗 MUST 回傳穩定錯誤碼、對使用者安全的訊息、可選欄位錯誤及 `request_id`；伺服器日誌 SHALL 使用相同 `request_id`，但 MUST NOT 記錄原始 PII、token、附件內容或完整 tool arguments。

#### Scenario: 輸入驗證失敗
- **WHEN** 任一工具輸入未通過 JSON Schema
- **THEN** 回傳 `validation_error`、欄位路徑與 `request_id`，不包含堆疊、SQL 或機密設定

#### Scenario: 非預期相依服務錯誤
- **WHEN** RDS、mock adapter 或合作廠商 API 發生非預期錯誤
- **THEN** client 收到 `dependency_unavailable` 與可重試資訊，詳細錯誤只寫入已遮蔽的伺服器日誌
