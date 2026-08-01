# AWS MVP 架構圖

> [!CAUTION]
> 本文件已封存。內容採用 FastAPI 與 Aurora，和目前已 Accepted 的 [`ADR-0001`](../../adr/0001-single-orchestrator-flask-mcp-service-platform.md) 不一致；請勿將此圖當成現行實作規格。

這份架構以黑客松可完成、可展示的端到端流程為優先：使用者輸入需求後，由 Bedrock 理解需求與補問欄位，再透過 MCP 工具建立諮詢案件、媒合服務商並供廠商後台追蹤。

## 檔案

- `aws-mvp-architecture.svg`：16:9 向量圖，適合放入簡報。
- `aws-mvp-architecture.png`：1920 x 1080 圖片，方便預覽與貼到文件。
- `aws-mvp-architecture.mmd`：Mermaid 可編輯原始碼。

## 主要決策

- 前端不是 Lambda：React 建置後是靜態檔案，放在 S3，由 CloudFront 發佈；住戶端與廠商後台可共用一個 SPA，以 Cognito role/group 控制畫面與 API 權限。
- 後端可以是 Lambda：API Gateway 接 FastAPI Lambda，負責驗證、對話 session、呼叫 Bedrock 與 MCP client。FastAPI 部署到 Lambda 時需使用 Lambda Web Adapter 或同等 ASGI adapter。
- 一個 Orchestrator：五種服務不拆成五個 Bedrock Agents，而是共用一個編排流程與五類表單／工具設定。
- MCP 是業務動作邊界：AgentCore Gateway 將表單、媒合、建單與狀態查詢公開為 MCP tools；若競賽帳號沒有 AgentCore，可用 API Gateway + Lambda 自行提供相同 MCP contract。
- RDS 儲存結構化資料：圖中採 Aurora Serverless v2 PostgreSQL，透過 RDS Proxy 連線。若沿用目前 README 的 Supabase，應直接替換整個 RDS 節點，不要同時維護兩套交易資料庫。
- S3 有兩個邏輯用途：前端靜態檔案，以及 Knowledge Base 文件／使用者上傳照片；實作時建議分成不同 bucket 與 IAM policy。
- Knowledge Base 只放 FAQ、條款與 SOP；價格、庫存、時段、案件狀態仍由資料庫與 MCP tools 即時查詢。
- OpenSearch Serverless 是 Knowledge Base 的向量索引，並不是交易資料庫。
- Cognito 區分住戶與服務商；案件寫入、接案、狀態更新都必須經 API 權限檢查。Secrets Manager、KMS、CloudWatch 與 CloudTrail 是橫跨各層的安全與營運能力。

## 建議實作順序

1. S3 + CloudFront 部署 React SPA。
2. Cognito 建立住戶與服務商角色。
3. API Gateway + Lambda 跑通 FastAPI health check 與 JWT 驗證。
4. Lambda 呼叫 Bedrock Runtime，完成五類需求分類與欄位抽取。
5. 建立 Aurora／Supabase 資料表及 `get_form_schema`、`create_inquiry`、`search_providers`、`get_or_update_status` 四組核心工具。
6. 將核心工具包成 MCP Server；有 AgentCore 時再接 Gateway。
7. 最後加入 Knowledge Base、OpenSearch、Guardrails、照片上傳與完整監控。

## MVP 可刪減項目

若時間不足，先保留 CloudFront、S3、Cognito、API Gateway、Lambda、Bedrock Runtime、單一 PostgreSQL 與 CloudWatch。Knowledge Base、OpenSearch、WAF、AgentCore 託管 Gateway 可以在核心流程穩定後再加入，但 MCP tool contract 應先固定。
