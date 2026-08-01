# ADR-0001：採用單一 Orchestrator、Flask 與 MCP 工具邊界

- 狀態：Superseded by [ADR-0003](0003-adopt-aws-native-agentcore-rds-platform.md)
- 日期：2026-08-01
- 決策者：AIWaveHackthon-NoIdeas 團隊
- 關聯規格：`openspec/changes/define-flask-mcp-service-intake/`

## Context

命題要求系統理解自然語言生活需求，針對餐廳訂位、商品購買、家事服務、水電修繕及社區服務諮詢產生彈性留資表單，媒合服務商，並讓服務商從後台承接與追蹤案件。命題也要求團隊自行設計 API，並將服務包裝成標準 MCP Server 供外部 Agent 使用。

早期方案考慮為冷氣、食物等領域各建一個 Amazon Bedrock Collaborator Agent，各自配置 Action Groups 與 Knowledge Base。此切分有四個問題：

1. 五類服務共用分類、欄位蒐集、留資、媒合與案件狀態流程，類別 Agent 會重複大部分邏輯。
2. 「冷氣」同時可能屬於家電清洗與水電修繕，「食物」則可能是餐廳訂位或外送，邊界不穩定。
3. 價格、庫存、時段與案件狀態是即時結構化資料，不適合作為 Knowledge Base 的事實來源。
4. Amazon Bedrock Agents 已改稱 Agents Classic，且 AWS 文件說明自 2026-07-30 起不再開放新客戶，因此新專案不應依賴其 Collaborator Agent 功能。

專案原先宣告 FastAPI／Uvicorn；團隊決定後端改用 Flask。

## Decision

### 1. 使用單一 Orchestrator

使用 Amazon Bedrock Runtime 上的一個 Orchestrator 負責：

- 需求分類；
- 結構化欄位抽取；
- 只追問缺少欄位；
- 選擇 MCP tool；
- 將工具結果轉成使用者可理解的回應。

五類服務以版本化 JSON Schema、服務規則與媒合設定表示，不建立五個常駐領域 Agent。只有當未來出現獨立安全、權限或推理邊界時，才新增專責 Agent。

### 2. 使用 Flask 作為 HTTP 後端

Flask 採 application factory、Blueprint、service、repository 分層：

- Blueprint 處理 HTTP transport 與序列化；
- service layer 執行驗證、授權、狀態機、冪等與交易規則；
- repository 封裝 Supabase 資料存取；
- MCP adapter 直接呼叫同一 service layer，不複製業務規則，也不繞經 HTTP loopback。

由於 Flask 不會自動提供完整的型別與 OpenAPI 契約，專案以版本化 JSON Schema、MCP tool schemas 及明確的 REST error contract 作為介面真實來源。

### 3. MCP 是 Agent 的唯一動作邊界

MVP 公開六項工具：

- `get_form_schema`
- `search_providers`
- `create_inquiry`
- `get_inquiry_status`
- `list_provider_inquiries`
- `update_inquiry_status`

模型不得直接執行 SQL、解密 PII 或呼叫未登錄的廠商操作。`create_inquiry` 與 `update_inquiry_status` 必須驗證明確確認、角色、冪等鍵與狀態版本。

### 4. Knowledge Base 與即時資料分離

Knowledge Base 只保存 FAQ、條款、服務說明與 SOP。服務商、服務區域、價格、庫存、時段、案件及狀態由 Supabase 或合作廠商 API 提供。當即時來源不可用時，系統回報不可驗證，不得以 Knowledge Base 推測。

### 5. 共用案件生命週期

五類服務共用案件、媒合及狀態事件模型。類別差異保留在表單資料與媒合條件，不建立五套資料表或狀態機。

## Alternatives Considered

### 五個 Bedrock Collaborator Agents 與五套 Knowledge Base

未採用。優點是展示多 Agent；缺點是重複邏輯、路由與資料邊界模糊、延遲與除錯成本較高，且依賴 Agents Classic 可用性。

### 一個 Agent 搭配六個 Bedrock Action Groups

未作為主要方案。若既有帳號已能使用 Agents Classic，技術上可行；但競賽明確要求標準 MCP Server，Action Groups 也會增加另一套工具契約與 Lambda 事件格式。

### 完全不使用 LLM 的固定表單流程

未採用。此方案最可預測，但無法充分展示自然語言需求理解、跨句欄位抽取與自適應追問；確定性表單驗證仍保留在 LLM 之外。

### FastAPI

未採用。FastAPI 的自動 OpenAPI 與型別驗證較完整，但團隊已選擇 Flask；代價由明確 JSON Schema、分層、測試與契約驗證補足。

## Consequences

### Positive

- 新增服務類別主要是新增 Schema、規則與資料，不必複製 Agent。
- REST 與 MCP 共用 service layer，可維持一致授權、冪等與狀態機。
- 即時資料與靜態知識責任清楚，降低錯誤價格、庫存或狀態的風險。
- Flask 架構輕量，適合黑客松快速完成端到端流程。

### Negative

- 團隊必須自行維護 request／response Schema、OpenAPI 文件及驗證整合。
- 單一 Orchestrator 需要良好的分類與工具評測，否則可能選錯服務類型。
- MCP Server、HTTP API 與 Supabase RLS 三層權限需一致測試。
- 既有 FastAPI／Uvicorn 依賴與啟動說明需要遷移；此變更為 breaking change。

### Risks and Mitigations

- 模型分類錯誤 → 在建案前顯示類別與摘要，模糊或跨類別輸入先要求澄清。
- MCP 重複寫入 → confirmation token、idempotency key、payload hash 與樂觀鎖。
- PII 出現在 prompt／trace → 聯絡資料先轉為 server-side reference，集中遮蔽日誌。
- 供應商資料過期 → 結果包含新鮮度；來源失效時回報不可驗證。
- Flask handler 累積業務邏輯 → Blueprint 只處理 transport，所有規則集中在 service layer。

## Follow-up

- 依 OpenSpec tasks 建立 Flask application factory 與 service／repository 邊界。
- 決定 MCP 直接部署或 AgentCore Gateway 轉接；此決定不改變工具契約。
- 決定正式登入供應商與 token 驗證方式。
- 合作廠商提供 API 後，另立 ADR 評估真實訂位、購買、派工及付款工具。

## References

- [Amazon Bedrock Agents multi-agent collaboration](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-multi-agent-collaboration.html)
- [Amazon Bedrock AgentCore Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)
- `SPEC.md`
- `openspec/changes/define-flask-mcp-service-intake/`
