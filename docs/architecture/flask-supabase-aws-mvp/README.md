# Flask + AWS + Supabase MVP 架構圖

這是依 `SPEC.md`、Accepted `ADR-0001` 與 active OpenSpec change 繪製的現行架構圖。舊的 FastAPI＋Aurora 圖保留在 `docs/archive/`，只供決策追溯。

## 檔案

- `aws-mvp-architecture.png`：1920 x 1080，適合簡報。
- `aws-mvp-architecture.svg`：可縮放向量圖。
- `aws-mvp-architecture.mmd`：Mermaid 可編輯原始碼。

## 現行決策

- 前端：React build 放 Amazon S3，由 CloudFront 發佈；住戶端與服務商後台可共用 SPA。
- HTTP 後端：API Gateway 連接 AWS Lambda 上的 Flask application。部署時使用 Lambda Web Adapter 或等價的 WSGI adapter。
- Flask 內部分層：REST Blueprints 與 MCP adapter 都呼叫同一 application services；授權、驗證、媒合、冪等與狀態機不得重複實作。
- AI：單一 Orchestrator 呼叫 Amazon Bedrock Runtime；五類服務由 JSON Schema、規則與資料設定擴充，不建立五個 Agent。
- MCP：外部 Agent 可直接呼叫 `/mcp`；AgentCore Gateway 是可選的託管 front door，不改變 MCP tool contract。
- 資料庫：現行決策是 Supabase PostgreSQL + RLS，不使用 Aurora／RDS 作為交易資料庫。
- S3：保存 Knowledge Base 文件、照片及附件；前端靜態檔案應使用不同 bucket 與 IAM policy。
- Knowledge Base：只保存 FAQ、條款、服務說明與 SOP；價格、庫存、時段與案件狀態只能來自 Supabase 或合作廠商 API。
- 身分供應商尚未決定；圖中保留 Amazon Cognito 或 Supabase Auth 兩個候選，不將任一方案畫成已定案。

## Flask Lambda 邊界

Flask Lambda 負責 transport 與應用編排，但不在函式記憶體保存交易狀態。核心模組包括：

- REST Blueprints：HTTP status、headers、serialization、actor context。
- MCP adapter/server：MCP tool schema 與工具呼叫轉接。
- Orchestrator adapter：Bedrock prompt、tool-use loop、回應組裝。
- Application services：驗證、授權、confirmation、idempotency、媒合與狀態機。
- Repositories／vendor adapters：Supabase 與合作廠商 API 存取。

## MVP 優先順序

1. S3 + CloudFront 發佈 React。
2. API Gateway + Flask Lambda 跑通 health check 與 REST error contract。
3. Flask repository 接 Supabase，完成 RLS 與 deterministic fixtures。
4. Flask 呼叫 Bedrock Runtime，完成五類分類、欄位抽取與確認流程。
5. REST 與 MCP 共用 application services，跑通建案、媒合與狀態更新。
6. 加入 S3 附件、Knowledge Base、OpenSearch、CloudWatch 與 KMS。
7. 需要託管 MCP 入口時，再加入 AgentCore Gateway。

