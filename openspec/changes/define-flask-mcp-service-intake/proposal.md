## Why

目前專案只有技術棧與五類服務名稱，尚未定義可驗收的彈性表單、MCP 工具和案件媒合契約。競賽交付需要一條能展示需求理解、留資、Agent 自動委派及服務商追蹤的完整流程；競賽同時要求只使用 AWS 服務，因此必須固定 AgentCore、RDS 與跨類別共用契約。

## What Changes

- 新增五類版本化服務表單：餐廳訂位、商品購買、家事服務、水電修繕、社區服務諮詢。
- 新增共用 MCP 工具契約，涵蓋表單取得、服務商搜尋、案件建立、案件查詢及服務商狀態更新。
- 新增案件媒合、狀態歷程、寫入確認、冪等性及個資保護規則。
- 新增 Step Functions Standard 非同步 workflow，涵蓋需求文件、等待廠商 callback、補件往返、自動改派、提醒與最終 Agent 結論。
- 採用一個 AgentCore Runtime，內含 Supervisor 與五個邏輯領域 Agent；Agent 理解需求，Flask 以確定性規則完成商家排序與委派。
- 採用 Amazon RDS for PostgreSQL、Amazon Cognito、AWS Amplify Hosting 與 AgentCore Gateway Lambda targets，移除 Supabase 部署依賴。
- 採用一個 Amazon Bedrock Managed Knowledge Base，以 `service_type` metadata 隔離五類靜態內容。
- 固定 `us-west-2`、Nova 2 Lite baseline、Titan Text Embeddings V2＋S3 Vectors，以及無 NAT 的 private-subnet Demo 網路。
- **BREAKING**：HTTP 後端由 FastAPI／Uvicorn 改為 Flask；現有或後續 FastAPI 啟動方式與路由實作不得繼續作為正式介面。

## Capabilities

### New Capabilities

- `service-intake-forms`: 定義五類服務的共用欄位、類別專屬欄位、條件式必填、安全分流與版本規則。
- `mcp-service-tools`: 定義供 Orchestrator 使用的 MCP tools、輸入輸出、授權、錯誤與冪等契約。
- `service-request-matching-lifecycle`: 定義服務需求建立、服務商媒合、角色可見性、合法狀態轉移與歷程追蹤。
- `agentcore-domain-orchestration`: 定義 Supervisor、五個領域 Agent、工具 allowlist、KB filter 與商家委派邊界。
- `async-agent-provider-workflow`: 定義 Agent、住戶與廠商的長流程、callback、文件、訊息及進度投影。

### Modified Capabilities

無；目前沒有既有 OpenSpec capabilities。

## Impact

- 專案規格：新增 `SPEC.md`、ADR、OpenSpec proposal/specs/design/tasks 及機器可讀 contracts。
- Python 依賴：移除 `fastapi`、`uvicorn` 與 Supabase 客戶端，加入 Flask、AgentCore／Strands 與 PostgreSQL 存取依賴；實際套件需在實作前另行確認。
- 後端設計：採 Flask application factory、Blueprint、service、repository 與統一錯誤處理。
- API／MCP：AgentCore Gateway 以受控 Lambda targets 暴露 MCP tools；Flask Lambda 與工具 Lambda 建置自同一 Python application core，模型不得直接查寫資料庫。
- 資料與安全：RDS PostgreSQL 保存服務商、表單版本、交易、媒合與狀態歷程；Cognito、API Gateway 與 Flask 共同執行身分及資源授權。
- 非同步流程：Step Functions Standard 保存等待與分支；RDS 保存可供產品頁面讀取的 workflow、task、artifact 與 conversation projection。
