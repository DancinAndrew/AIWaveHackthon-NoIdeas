# AWS AgentCore 水電 Demo 架構

這是 AI 生活管家在 `us-west-2` 的實際 staging 架構，對應 [ADR-0003](../../adr/0003-adopt-aws-native-agentcore-rds-platform.md)、[ADR-0004](../../adr/0004-orchestrate-agent-provider-callbacks-with-step-functions.md)、[ADR-0005](../../adr/0005-use-s3-vectors-and-titan-for-managed-knowledge-base.md) 與 [ADR-0006](../../adr/0006-use-sse-s3-for-synthetic-vector-index.md)。部署只使用 AWS 服務；付款、餐廳、供應商與派工外部系統使用合成資料或 mock adapter。

## 圖檔

- [`aws-agentcore-async-platform.mmd`](aws-agentcore-async-platform.mmd)：可編輯 Mermaid 來源。
- [`aws-agentcore-async-platform.svg`](aws-agentcore-async-platform.svg)：向量版正式圖。
- [`aws-agentcore-async-platform.png`](aws-agentcore-async-platform.png)：簡報與文件用點陣圖。

圖中的實線是目前線上 E2E 已驗證的路徑；虛線是已建立但尚未進入主流程，或下一階段才會完成的接線。

## 已部署的水電 walking skeleton

1. 住戶從 Amplify Hosting 上的 React SPA 進入 AI 對話；目前 UI 使用受控 demo actor headers，Cognito User Pool 與三個群組已建立，但 JWT 登入尚未接進 SPA／API Gateway。
2. API Gateway 將請求交給 private subnet 內的 Flask Lambda。Flask 經 AgentCore interface VPC endpoint 呼叫單一 AgentCore Runtime。
3. Runtime 內的 Supervisor 以工具式委派選擇五個邏輯 Agent 之一；目前水電領域完成線上閉環，其餘四個領域只有路由、欄位與 allowlist 契約。
4. 水電多輪追問、風險 gate、版本化需求文件、住戶確認與確定性媒合由 Flask 共用 Python application core 執行，交易與訊息寫入 private RDS PostgreSQL。
5. 廠商從同一 SPA 的後台取得自己的 task，可補問、拒絕或接受；管理員可按鈕模擬逾時。住戶在原對話與「我的預約」看到補問、媒合與最終確認進度。
6. Step Functions Standard 已建立為 durable orchestration boundary，但目前只記錄 workflow 邊界；廠商等待／恢復仍由 API-driven RDS 狀態機完成，尚未使用 task-token callback worker。
7. 水電 Knowledge Base 已把 5 份合成正文與 5 份 metadata sidecar 同步至 Titan Text Embeddings V2＋S3 Vectors，並通過實際 retrieval；Runtime 直接檢索與 Gateway tool call 仍是下一階段接線。

## 資料與責任

| 狀態 | 目前真實來源 | 說明 |
|---|---|---|
| Supervisor 領域委派 | AgentCore Runtime | 一個 Runtime 承載 Supervisor＋五個邏輯 Agent；目前是確定性路由 |
| 水電多輪對話與安全 gate | Flask application core | 已部署並完成公開 URL E2E |
| 交易、媒合、訊息與進度 | RDS PostgreSQL | `service_request`／task／artifact／events 的 JSON persistence |
| 廠商等待與改派 | RDS 狀態機＋Flask API | Step Functions callback worker 尚未接入 |
| 靜態 FAQ／條款／SOP | private S3＋Managed Knowledge Base＋S3 Vectors | Titan Embed v2、1024 維 COSINE，5/5 水電文件成功索引 |
| 即時價格／時段／廠商 | RDS 或 mock adapter | 絕不從 Knowledge Base 猜測 |

## 網路與安全邊界

- VPC 橫跨兩個 Availability Zone；Flask Lambda、工具 Lambda 與 RDS 位於 isolated private subnets，Demo 不建立 NAT Gateway。
- RDS `PubliclyAccessible=false`，只允許 workload security group 連入 PostgreSQL 5432。
- S3 一律啟用四項 Block Public Access；住戶 artifact bucket 與 Knowledge Base source bucket 分開。
- AgentCore Runtime 使用 VPC 設定；Flask 透過 AgentCore interface endpoint 呼叫 Runtime，S3 使用 gateway endpoint。
- Secrets Manager 保存資料庫憑證；KMS 保護 RDS、Secrets、一般 S3 與 artifact。S3 Vector Index 的合成、非敏感資料依 ADR-0006 使用 SSE-S3。
- Bedrock／AgentCore 只保留必要模型，client gate 的請求起始間隔至少 1.05 秒。
- 沒有建立 EC2 instance、EMR cluster 或 SageMaker TrainingJob，也沒有對 `0.0.0.0/0` 或 `::/0` 開放 Security Group ingress。

## 尚未完成的正式化工作

- 將 Cognito JWT 登入接到 SPA、API Gateway authorizer 與 Flask actor mapping，取代 demo headers。
- 讓領域 Agent 在 Runtime 內持續多輪，並實際呼叫 AgentCore Gateway Lambda tools 與 Knowledge Base retrieval。
- 把 RDS workflow projection 接到 Step Functions task-token callback／worker，而不是只使用 API-driven 狀態機。
- 完成餐廳、商品、家事與社區四個領域的資料、工具與端到端流程。

## Artifact 與 Knowledge Base S3 必須分開

Knowledge Base bucket／prefix 只放 `data/mock/knowledge_base/` 白名單中的靜態切分文件與 metadata sidecar。住戶產生的需求文件放在獨立 private artifact bucket，絕對不能同步進 Knowledge Base。
