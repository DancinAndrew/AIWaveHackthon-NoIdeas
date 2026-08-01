# ADR-0003：採用 AWS 原生 AgentCore、RDS 與多領域 Agent 平台

- 狀態：Accepted
- 日期：2026-08-01
- 決策者：AIWaveHackthon-NoIdeas 團隊
- 取代：[ADR-0001](0001-single-orchestrator-flask-mcp-service-platform.md) 的單一 Orchestrator、Supabase 與待定部署決策
- 關聯規格：`SPEC.md`、`openspec/changes/define-flask-mcp-service-intake/`

## Context

競賽限制要求平台只使用 AWS 服務，Supabase Cloud 因此不符合部署邊界。Amazon Bedrock Agents 已進入 Classic 維護模式且不再開放新客戶；平台同時需要依餐廳、商品、家事、水電與社區諮詢的不同條件理解需求，再以可驗證規則自動委派商家。

Demo 要保存真實的內部訂位、訂單、預約、報修與諮詢交易，但付款、餐廳、供應商與派工等外部系統只使用模擬 adapter，不產生真實扣款或不可逆外部操作。

## Decision

### 1. 使用 AgentCore Runtime 承載多領域 Agent

平台以一個 Amazon Bedrock AgentCore Runtime 承載一個 Supervisor 與五個邏輯領域 Agent。Supervisor 只負責路由；領域 Agent 各自擁有明確 instructions、允許的 MCP tools、Knowledge Base filter 與需求蒐集規則，但不各自部署獨立 Runtime。

### 2. 使用 AgentCore Gateway 作為 MCP 工具邊界

AgentCore Gateway 只使用受控的 AWS Lambda targets 暴露 MCP tools，不直接以 Flask OpenAPI 作為 target。工具 Lambda 與 Flask Lambda 從同一個 Python application core 建置，重用驗證、授權、媒合、冪等與狀態機；模型不得直接執行 SQL、解密 PII 或任意變更交易狀態。

工具依責任分為 `service-request-tools` 與五個領域 target group。這是部署與權限邊界，不代表複製六套業務邏輯。

### 3. 使用 AWS 原生應用與資料服務

- React SPA 部署於 AWS Amplify Hosting。
- Amazon Cognito User Pool 提供 `RESIDENT`、`PROVIDER`、`ADMIN` 預建 Demo 帳號。
- Amazon API Gateway 將 HTTP 請求送至 AWS Lambda 上的 Flask。
- Amazon RDS for PostgreSQL 保存商家、商品、時段、交易、媒合、狀態歷程與稽核資料。
- RDS Proxy 是正式化選項，不是 Demo 第一版必要元件。

五類交易共用 `service_requests`、`service_request_matches` 與 `service_request_events` 聚合；`transaction` 只用來描述資料庫原子交易，不作為業務資料表名稱。

### 4. 將 Agent 理解與商家委派規則分離

領域 Agent 從自然語言抽取需求並追問缺少欄位；Flask 先以服務能力、地區、時段、庫存與啟用狀態做硬條件過濾，再以版本化權重產生穩定分數。最高分商家先獲委派，拒絕或逾時時依排序自動遞補，管理員可人工改派。

### 5. 使用單一 Managed Knowledge Base

一個 S3 知識來源與一個 Amazon Bedrock Managed Knowledge Base 保存五類 FAQ、條款與 SOP。文件以 `service_type`、`doc_kind`、`version` 等 metadata 分流；價格、庫存、時段、商家啟用狀態與交易狀態只由 RDS 或模擬 vendor adapter 提供。

### 6. 固定 Region 與模型基準

- 所有 Demo 工作負載部署於 `us-west-2`。
- Supervisor 與五個領域 Agent 的基準模型為 `amazon.nova-2-lite-v1:0`，每個 Agent 的模型 ID 分別配置，不寫死在 prompt。
- Knowledge Base 的 embedding／vector store 決策已由 [ADR-0005](0005-use-s3-vectors-and-titan-for-managed-knowledge-base.md) 修正為 `amazon.titan-embed-text-v2:0`＋S3 Vectors，並要求繁體中文 retrieval eval。
- 若離線 eval 未達門檻，只升級失敗領域的模型；安全、授權與狀態機不以換模型取代確定性控制。

### 7. 使用無 NAT 的私有 Demo 網路

平台建立跨至少兩個 Availability Zone 的 VPC private subnets。Flask Lambda、工具 Lambda 與 RDS PostgreSQL 位於私有網路；RDS security group 只接受 Lambda security group 的 PostgreSQL 連線。Flask 透過 AgentCore interface VPC endpoint 呼叫 Runtime，S3 使用 gateway endpoint；由於外部付款與廠商 API 均為 mock，Demo 不建立 NAT Gateway。

AgentCore Runtime 不直接連線 RDS。資料庫憑證存於 AWS Secrets Manager，RDS、Secrets 與 PII 使用 AWS KMS；基礎設施以 AWS CDK for Python 定義。

## Alternatives Considered

### Supabase Cloud

- **Pros**：PostgreSQL、Auth、Storage 與 RLS 整合快速。
- **Cons**：不是 AWS 服務，不符合競賽限制。
- **Why not**：AWS-only 是硬性邊界。

### Amazon Bedrock Agents Classic Supervisor／Collaborators

- **Pros**：內建 Supervisor 與 Collaborator 設定介面。
- **Cons**：已進入 Classic 維護模式且不再開放新客戶。
- **Why not**：新專案不能把交付建立在不可新啟用的服務上。

### 六個獨立 AgentCore Runtime

- **Pros**：各 Agent 可獨立部署、擴縮與授權。
- **Cons**：增加 IAM、部署、版本、延遲與觀測複雜度。
- **Why not**：Demo 的五個領域共用交易與工具邊界，一個 Runtime 已足以呈現多 Agent 委派。

### Aurora Serverless v2

- **Pros**：容量可依負載調整，部分版本支援自動暫停。
- **Cons**：Data API 或連線策略增加 Demo 複雜度；RDS Proxy 也會影響自動暫停。
- **Why not**：標準 RDS PostgreSQL 最符合 Flask／SQLAlchemy 的開發與除錯需求。

## Consequences

### Positive

- 所有部署元件符合 AWS-only 限制。
- 五個領域維持獨立推理責任，又共用一套交易與授權邏輯。
- 商家選擇可重現、可稽核，不依賴 LLM 自由生成分數。
- Demo 可完整展示住戶建案、Agent 委派、廠商接單與管理員改派。

### Negative

- 團隊需自行實作 AgentCore Runtime 內的 Supervisor 與五個領域 Agent 編排。
- RDS 不提供 Supabase 的即用型 API 與 Auth 整合，授權必須在 Cognito、API Gateway 與 Flask 明確落實。
- AgentCore Gateway、Runtime、Flask 與 RDS 的 trace correlation 需要統一 request／session ID。
- 同一 application core 會封裝進多個 Lambda artifact，部署流程必須驗證版本一致，避免 REST 與 MCP 行為漂移。
- 無 NAT 的 Demo 不能直接呼叫一般公網廠商 API；未來接入真實外部系統時需另立網路與 egress 決策。

### Risks

- Agent 路由錯誤 → 建案前顯示類別與摘要，並以既有 eval fixtures 做分類與工具選擇評測。
- Agent 越權呼叫工具 → 每個領域配置 allowlist，Gateway 與 Flask 再做身分及資源授權。
- Knowledge Base 回答過期即時資料 → 以 metadata、instructions 與 tool policy 強制即時欄位只查 RDS。
- 水電安全規則未被檢索 → 高風險判斷同時存在 Agent 固定 instructions 與 Flask 確定性檢查，KB 只提供補充說明。

## Follow-up

- 先以餐廳訂位完成一條 walking skeleton，再沿共用 `service_request` 生命週期擴充其餘四類。
- 住戶、Agent 與廠商的長時間 callback 流程由 [ADR-0004](0004-orchestrate-agent-provider-callbacks-with-step-functions.md) 定義。
- 部署前以帳號實際可用模型清單確認模型存取，並以 `data/mock/eval/` 保存基準評測結果。
- 真實廠商 API 或 RDS 連線壓力出現後，另立 ADR 評估 NAT／受控 egress 與 RDS Proxy。

## References

- [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/)
- [Amazon Bedrock AgentCore Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)
- [Amazon RDS for PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html)
