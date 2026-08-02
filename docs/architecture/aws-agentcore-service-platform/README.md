# AWS AgentCore Demo 架構

這是 AI 生活管家在 `us-west-2` 的實際 staging 架構，對應 [ADR-0003](../../adr/0003-adopt-aws-native-agentcore-rds-platform.md)、[ADR-0004](../../adr/0004-orchestrate-agent-provider-callbacks-with-step-functions.md)、[ADR-0005](../../adr/0005-use-s3-vectors-and-titan-for-managed-knowledge-base.md)、[ADR-0006](../../adr/0006-use-sse-s3-for-synthetic-vector-index.md) 與 [ADR-0007](../../adr/0007-disclose-openpoint-rewards-as-platform-demo-ledger.md)。部署只使用 AWS 服務；付款、餐廳、供應商、派工與 OPENPOINT 帳務外部系統使用合成資料或 mock adapter。

目前有兩個領域完成閉環：**水電修繕**（`define-flask-mcp-service-intake`）與**商品購買**（`add-product-purchase-automation`）。

## 圖檔

- [`aws-agentcore-official-architecture.svg`](aws-agentcore-official-architecture.svg)：依 AWS 官方架構圖視覺規範製作的可編輯向量版；使用 AWS Cloud／Region／VPC／Availability Zone／private subnet 邊界、官方服務圖示與編號流程。
- [`aws-agentcore-official-architecture.png`](aws-agentcore-official-architecture.png)：3200×1700 的正式簡報版，建議優先使用。
- [`aws-agentcore-async-platform.mmd`](aws-agentcore-async-platform.mmd)：可編輯 Mermaid 來源。
- [`aws-agentcore-async-platform.svg`](aws-agentcore-async-platform.svg)：向量版正式圖。
- [`aws-agentcore-async-platform.png`](aws-agentcore-async-platform.png)：簡報與文件用點陣圖。

圖中的實線是目前線上 E2E 已驗證的路徑；粗虛線是已建立但尚未進入主流程，或下一階段才會完成的接線；細點線是可觀測性。

新版正式圖參考使用者提供的 AWS 網路拓撲圖版面語言，圖示則來自 AWS 官方 [Architecture Icons](https://aws.amazon.com/architecture/icons/) 的 `Icon-package_04302026`（Q2 2026）。本資料夾的 [`icons/`](icons/) 只保留本圖實際使用的官方 SVG，不引入第三方或過期圖示庫。

SVG 以相對路徑引用 `icons/*.svg`，可直接編輯；轉 PNG 時需先把圖示內嵌成 data URI，再以 headless 瀏覽器輸出 3200×1700。

## 目前的請求路徑

1. 住戶從 Amplify Hosting 上的 React SPA 進入 AI 對話；目前 UI 使用受控 demo actor headers，Cognito User Pool 與三個群組已建立，但 JWT 登入尚未接進 SPA／API Gateway。
2. API Gateway（HTTP API payload v2、Amplify-only CORS）將請求交給 private subnet 內的 Flask Lambda。Flask 經 AgentCore interface VPC endpoint 呼叫單一 AgentCore Runtime。
3. Runtime 內的 Supervisor 先用關鍵字路由；詞表沒命中時才以核准模型做 fail-closed 分類，核准清單外的值一律退回澄清或「不支援」，不臆造領域。
4. 被路由到的領域 Agent 在 Runtime 內執行**一輪模型理解**：以 Nova 2 Lite 的 Converse＋強制單一工具抽取結構化欄位與風險訊號，並以 `service_type` equals filter 檢索 Managed Knowledge Base。模型或契約驗證失敗時，Runtime 以固定規則誠實降級（`reasoning.mode = rule-fallback`）。
5. Flask 重新驗證每一個抽出的欄位（契約外鍵丟棄、地區必須命中受控主檔），對安全旗標做確定性 union，然後執行狀態機、確定性媒合與冪等控制。**金額、庫存與案件狀態一律由伺服器規則計算，不由模型產生。**
6. 廠商／供應商從同一 SPA 的後台取得自己的 task，可補問、拒絕或接受；管理員可按鈕模擬逾時。住戶在原對話與「我的預約」看到補問、媒合與最終確認進度。
7. Step Functions Standard 已建立為 durable orchestration boundary，但目前只記錄 workflow 邊界；廠商等待／恢復仍由 API-driven RDS 狀態機完成，尚未使用 task-token callback worker。
8. AgentCore Gateway 與 Gateway Tool Lambda 已部署且共用同一 application core，但 Runtime 尚未實際發出 MCP tool call。

## 兩個已上線領域

| 領域 | 閉環 | 專屬能力 |
|---|---|---|
| 水電修繕 | 多輪追問 → 高風險安全 gate → 版本化需求文件 → 住戶確認 → 確定性媒合 → 廠商承接 → 完工回報 → 住戶驗收 → 點數入帳 | 漏電／裸線／冒煙等 hazard flag 觸發後模型不得解除；不提供未驗證 DIY 指示 |
| 商品購買 | 蒐集品項／預算／數量／收貨地區 → 候選 SKU → 住戶選品 → 確定性定價 → mock 付款授權 → 供應商承接 → 完工回報 → 住戶驗收 → 點數入帳 | 300 SKU／8 家供應商目錄；選品走獨立 REST 端點，body 夾帶的金額一律忽略並由伺服器重算 |

餐廳訂位、家事服務、社區服務諮詢目前只有 Supervisor 路由、欄位與 tool allowlist 契約，尚未有 flow 實作。

## OPENPOINT 回饋（ADR-0007）

回饋點數是 OPEN POINT 生活圈的核心誘因，因此進了主流程；但 OPENPOINT 是真實會員資產系統，發點是不可逆的外部交易，所以：

- **只在平台內記帳。** 對話 final message 與「我的預約」都必須顯示「尚未連動 OPENPOINT 正式帳戶」，投影帶 `isDemoLedger` 旗標讓前端無法漏掉這個揭露。
- **揭露綁在訂單成立**（廠商 `accept`），入帳綁在**住戶驗收**。廠商單方回報完工不得結案。
- **入帳時依完工金額重算**，不沿用訂單成立時的預估；差異以 `amountAdjusted` 明示。
- **確定性整數運算。** 費率以萬分位表示，`basis_amount * rate_bp // 10_000` 全程整數並套單筆上限，讓 Flask 與 Runtime 對同一筆訂單算出相同結果。
- **`point_ledger` 為 append-only 流水帳**，是「是否已發放」的真實來源，重複驗收不會重複入帳；它同時列在 `rds_store.STATE_FIELDS`，否則 staging 會靜默遺失流水帳。

## 資料與責任

| 狀態 | 目前真實來源 | 說明 |
|---|---|---|
| Supervisor 領域委派 | AgentCore Runtime | 一個 Runtime 承載 Supervisor＋五個邏輯 Agent；關鍵字優先，未命中才用模型分類 |
| 每輪欄位抽取與風險判讀 | AgentCore Runtime＋Bedrock Nova 2 Lite | Converse 強制單一工具；輸出必須通過 `contracts/runtime/agent-turn.json` |
| 對話狀態機、媒合、定價、冪等 | Flask application core | 兩個領域皆已完成公開 URL E2E |
| 交易、任務、事件與進度投影 | RDS PostgreSQL | `aiwave_demo_state` JSONB aggregate |
| 回饋點數與發放紀錄 | Flask `points.py`＋RDS `point_ledger` | 整數運算、append-only；平台內 Demo 記帳，見下方 ADR-0007 段落 |
| 會員長期記憶 | RDS PostgreSQL | `mms_member_address`／`mms_member_appliance`／`mms_member_preference`；`detail` 不進 SELECT，明文地址不會進 prompt 或 trace |
| 靜態 FAQ／條款／SOP | private S3＋Managed Knowledge Base＋S3 Vectors | Titan Embed v2、1024 維 COSINE；`never_authoritative_for` 邊界阻擋靜態文件回答價格／庫存／時段／案件狀態 |
| 即時價格／庫存／時段／廠商 | 受控主檔、RDS 或 mock adapter | 絕不從 Knowledge Base 猜測 |

## 網路與安全邊界

- VPC 橫跨兩個 Availability Zone；Flask Lambda、工具 Lambda 與 RDS 位於 isolated private subnets，Demo 不建立 NAT Gateway。
- RDS `PubliclyAccessible=false`，只允許 workload security group 連入 PostgreSQL 5432。
- S3 一律啟用四項 Block Public Access；住戶 artifact bucket 與 Knowledge Base source bucket 分開。
- AgentCore Runtime 使用 VPC 設定；Flask 透過 AgentCore interface endpoint 呼叫 Runtime，S3 使用 gateway endpoint。
- Secrets Manager 保存資料庫憑證；KMS 保護 RDS、Secrets、一般 S3 與 artifact。S3 Vector Index 的合成、非敏感資料依 ADR-0006 使用 SSE-S3。
- Bedrock／AgentCore 只保留必要模型；Flask 與 Runtime **匯入同一個** request gate 模組，請求起始間隔至少 1.05 秒，未核准的模型 ID 在送出前就被拒絕。
- deterministic demo 模式不產生任何 Bedrock 請求，因此離線也能跑完整閉環。
- 對話流程不蒐集門牌、電話或 Email；供應商可見的 brief 只到縣市／行政區層級。
- 沒有建立 EC2 instance、EMR cluster 或 SageMaker TrainingJob，也沒有對 `0.0.0.0/0` 或 `::/0` 開放 Security Group ingress。

## 尚未完成的正式化工作

- 將 Cognito JWT 登入接到 SPA、API Gateway authorizer 與 Flask actor mapping，取代 demo headers。
- 讓 Runtime 實際呼叫 AgentCore Gateway Lambda tools，取代目前由 Flask 直接執行工具邏輯。
- 把 RDS workflow projection 接到 Step Functions task-token callback／worker，而不是只使用 API-driven 狀態機。
- 完成餐廳訂位、家事服務與社區服務諮詢三個領域的資料、工具與端到端流程。
- 住戶對商家的評價、`comment_status` 轉移與評價聚合回饋媒合排序。
- 點數折抵（`used_points`）、退點（`refund_points`）與 `04 已取消` 的收回轉移。
- 發放冷卻期（主辦訂位類的「7 天後核銷」），適合由 Step Functions wait state 實作。

## Artifact 與 Knowledge Base S3 必須分開

Knowledge Base bucket／prefix 只放 `data/mock/knowledge_base/` 白名單中的靜態切分文件與 metadata sidecar。住戶產生的需求文件放在獨立 private artifact bucket，絕對不能同步進 Knowledge Base。
