# AWS AgentCore 非同步服務平台架構

這是 AI 生活管家目前的正式 Demo 架構，對應 [ADR-0003](../../adr/0003-adopt-aws-native-agentcore-rds-platform.md)、[ADR-0004](../../adr/0004-orchestrate-agent-provider-callbacks-with-step-functions.md) 與 [ADR-0005](../../adr/0005-use-s3-vectors-and-titan-for-managed-knowledge-base.md)。所有工作負載位於 `us-west-2`，只使用 AWS 服務；外部付款、餐廳、供應商與派工操作使用 mock adapter。

## 圖檔

- [`aws-agentcore-async-platform.mmd`](aws-agentcore-async-platform.mmd)：可編輯 Mermaid 來源。
- [`aws-agentcore-async-platform.svg`](aws-agentcore-async-platform.svg)：向量版正式圖。
- [`aws-agentcore-async-platform.png`](aws-agentcore-async-platform.png)：簡報與文件用點陣圖。

## Demo 主流程

1. `RESIDENT` 從 Amplify Hosting 上的 React SPA 登入 Cognito，在 AI 對話輸入需求。
2. API Gateway 將 JWT 驗證後的請求交給 Flask Lambda；Flask 經 interface VPC endpoint 呼叫單一 AgentCore Runtime。
3. Supervisor 將需求交給五個邏輯領域 Agent 之一，Agent 多輪補齊欄位、查詢單一 Managed Knowledge Base，並產生版本化 `service_request_brief`。
4. 住戶確認後，工具 Lambda 與 Flask 共用的 Python application core 在 RDS 建立 `service_request`，確定性媒合引擎排序廠商，並啟動 Step Functions Standard execution。
5. Step Functions 暫停於 `waiting_provider_response`。廠商登入同一 SPA，接受、拒絕、要求補件或留言；Flask 驗證 membership 與 task version，再以 server-side task token callback 恢復 workflow。
6. 拒絕或管理員模擬逾時會立即改派下一家；補件會透過 workflow worker 重新喚起原領域 Agent，在住戶對話中追問後再回到廠商確認。
7. 廠商接受且細節完整後，workflow 喚起原 Agent 產生最終結論。對話、文件、工作任務、提醒與進度都寫入 RDS projection，React 以短輪詢更新原對話與進度頁。

## 狀態責任

| 狀態 | 真實來源 | 用途 |
|---|---|---|
| 對話推理中的短期執行 | AgentCore Runtime | 分類、追問、文件摘要、廠商問題判讀、最終回覆 |
| 長時間等待與分支 | Step Functions Standard | 等待住戶／廠商 callback、拒絕改派、補件往返 |
| 業務交易與媒合 | RDS PostgreSQL | `service_requests`、matches、events、provider replies |
| UI 進度與提醒 | RDS PostgreSQL | workflow execution／task projection、messages、artifacts |
| 靜態 FAQ／條款／SOP | private S3 source＋Managed Knowledge Base＋S3 Vectors | Titan Embed v2 1024 維向量，以 `service_type` metadata 過濾的 RAG |

## 網路與安全邊界

- VPC 至少跨兩個 Availability Zone；Flask Lambda、工具 Lambda、workflow worker Lambda 與 RDS 位於 private subnets。
- RDS 不公開，security group 只接受 Lambda security group 的 PostgreSQL 連線。
- Flask 透過 AgentCore interface VPC endpoint 呼叫 Runtime；S3 使用 gateway endpoint。
- AgentCore Runtime 不直接連 RDS；所有資料動作經 Gateway Lambda targets。
- Callback token 僅 server-side KMS 加密保存，不傳給瀏覽器、模型或一般 log。
- Demo 沒有真實公網廠商整合，因此不建立 NAT Gateway。
- Secrets Manager 保存資料庫憑證；KMS 保護 RDS、Secrets、PII 與 private artifact bucket。

## Artifact 與 Knowledge Base S3 必須分開

Knowledge Base bucket／prefix 只放 `data/mock/knowledge_base/` 的靜態切分文件與 metadata sidecar。住戶產生的需求文件放在獨立 private artifact bucket／prefix，絕對不能被同步進 Knowledge Base。
