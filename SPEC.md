# AI 生活管家：服務需求理解與媒合平台規格

## 1. 產品目標

本專案讓住戶以文字或語音描述生活需求，由一個 AgentCore Runtime 內的 Supervisor 路由至對應領域 Agent。領域 Agent 以多輪對話蒐集缺少欄位並產生需求文件，住戶確認後由確定性規則自動委派合適商家；系統等待商家承接、拒絕或補問，必要時恢復原領域 Agent 向住戶補件，最後在對話與進度頁回傳結論。

第一階段支援五類服務：

1. 餐廳訂位
2. 商品購買
3. 家事服務
4. 水電修繕
5. 社區服務諮詢

## 2. MVP 範圍

### 2.1 消費者流程

- 接收文字需求；語音由前端轉為文字後使用相同流程。
- 將需求分類為五類服務之一，或標示為模糊、跨類別、不支援。
- 以版本化表單 Schema 表示已取得欄位、缺少欄位與條件式必填欄位。
- 只追問建立服務需求所需的缺少欄位。
- 在寫入前顯示摘要，取得明確確認後才建立案件。
- 產生版本化 `service_request_brief`，住戶可在送出前檢視，廠商只能看到符合授權與遮蔽規則的版本。
- 依類別、地區、時段、預算、緊急程度及服務商能力產生媒合結果與理由。
- 當廠商要求補件時，在原領域 Agent 對話中收到追問並可繼續補充。
- 在提醒與進度頁查詢目前步驟、等待對象、待辦、服務商回覆與最終結論。

### 2.2 服務商流程

- 服務商只能查看媒合給自己或其組織的案件。
- 服務商可承接、婉拒、要求補件、更新進度與新增回覆。
- 服務商回覆會恢復該案件 workflow；婉拒或模擬逾時會立即自動改派下一名候選。
- 每次狀態變更均保留操作者、時間、前後狀態與非敏感摘要。

### 2.3 非目標

- MVP 會在 RDS 建立並追蹤真實的內部 Demo 交易，但不直接完成真實付款、退款或不可逆的外部交易。
- 在沒有合作廠商正式 API 時，付款、餐廳、供應商與派工操作使用明確標示的 mock adapter；不得宣稱外部系統已完成操作。
- 不以 Knowledge Base 作為價格、庫存、可預約時段或案件狀態的真實來源。
- 不將 Supervisor 與五個邏輯領域 Agent 部署成六個獨立 AgentCore Runtime，也不為每個商家建立 Agent。
- 不由模型取代專業技師進行安全診斷；水電高風險情境必須提供停止操作及聯繫專業人員的提示。

## 3. 架構約束

- 前端：React SPA，部署於 AWS Amplify Hosting。
- 身分：Amazon Cognito User Pool，Demo 預建 `RESIDENT`、`PROVIDER`、`ADMIN` 群組帳號，不開放公開註冊。
- HTTP 後端：Flask on AWS Lambda，採 application factory、Blueprint、service、repository 分層，經 Amazon API Gateway 提供介面。
- AI：一個 Amazon Bedrock AgentCore Runtime 承載 Supervisor 與五個邏輯領域 Agent；Supervisor 路由，領域 Agent 負責欄位抽取、追問與工具選擇。
- Workflow：AWS Step Functions Standard 保存每個已確認案件的長流程，負責等待住戶／廠商 callback、改派與恢復 Agent；AgentCore 不在人工等待期間保持執行。
- 工具邊界：Amazon Bedrock AgentCore Gateway 以獨立 Lambda targets 提供標準 MCP tools；Flask Lambda 與工具 Lambda 共用同一 Python application core，工具不得讓模型直接執行任意 SQL。
- 資料庫：Amazon RDS for PostgreSQL；API Gateway 驗證 Cognito JWT，Flask 依住戶 owner、廠商 membership 與管理員角色執行資源授權。RDS Proxy 是正式化選項，不是 Demo 第一版必要元件。
- 靜態知識：一個 S3 知識來源與一個 Amazon Bedrock Managed Knowledge Base 保存 FAQ、條款、服務說明與 SOP，以 `service_type` metadata 隔離五類內容。
- 即時資料：供應商、服務範圍、價格、庫存、時段、交易與狀態只從 RDS 或受控 mock／合作廠商 adapter 讀取。
- 核心交易：五類共用 `service_requests`、`service_request_matches` 與 `service_request_events`；`transaction` 僅指資料庫原子交易。
- 長流程投影：RDS 的 `service_request_artifacts`、`conversation_threads`、`conversation_messages`、`workflow_executions` 與 `workflow_tasks` 是文件、訊息、提醒與頁面進度的真實來源；前端不直接讀取 Step Functions history。
- Region 與模型：統一部署於 `us-west-2`；六個邏輯 Agent 以 `amazon.nova-2-lite-v1:0` 為基準，KB 使用 `cohere.embed-multilingual-v3`。
- 網路：Flask Lambda、工具 Lambda 與 RDS 位於跨至少兩個 AZ 的 private subnets；使用 AgentCore interface endpoint 與 S3 gateway endpoint。外部整合均為 mock，因此 Demo 不建立 NAT Gateway。
- 部署：使用 AWS CDK for Python；資料庫憑證進 Secrets Manager，RDS、Secrets 與 PII 使用 KMS。

## 4. 五類表單摘要

所有表單均包含 `service_type`、`schema_version`、`request_summary`、聯絡資料、聯絡偏好、個資使用同意，以及建立案件前的確認狀態。各類別至少蒐集：

| 服務類別 | 核心欄位 | 重要條件式欄位 |
|---|---|---|
| 餐廳訂位 | 地區、日期時間、人數、料理偏好、預算 | 飲食限制、無障礙／兒童需求、包廂 |
| 商品購買 | 商品需求、類別、預算、數量、收貨地區 | 品牌、規格、替代品接受度、到貨期限 |
| 家事服務 | 服務項目、住宅類型、服務地區、日期時段 | 坪數／房數、頻率、寵物、清潔用品、照片 |
| 水電修繕 | 問題類型、症狀、地區、緊急程度、可服務時段 | 漏電／冒煙／淹水等危險旗標、設備資訊、照片 |
| 社區服務諮詢 | 社區／大樓、議題類別、需求描述、急迫度 | 涉及區域、附件、責任單位線索、匿名偏好 |

完整 JSON Schema 由 active OpenSpec change 的 `contracts/forms/` 定義。

## 5. MCP 工具範圍

MVP 工具如下：

- `get_form_schema`：取得服務類別及版本對應的表單 Schema。
- `search_providers`：以結構化條件查詢服務商並回傳可解釋的排序理由。
- `create_service_request`：在確認、同意及 idempotency key 完整時建立服務需求。
- `get_service_request_status`：由案件擁有者或有權限的服務商讀取案件。
- `list_provider_service_requests`：列出目前服務商可查看的案件，支援分頁與狀態篩選。
- `update_service_request_status`：依合法狀態機更新案件並寫入歷程。

工具輸入輸出契約由 active OpenSpec change 的 `contracts/mcp/tools.json` 定義。

## 6. 安全與資料治理

- API 與 MCP 輸入必須通過白名單 Schema 驗證。
- Cognito 只提供身分與粗粒度群組；Flask 必須在每次讀寫前檢查交易 owner、廠商 membership 與合法狀態轉移，不能只依前端介面或 token 群組。
- 建立案件與任何外部交易前必須取得明確確認；重試使用同一 idempotency key 不得重複建立案件。
- Step Functions callback token 只能在 server-side 加密保存，不得傳到瀏覽器、Agent prompt、MCP arguments 或一般日誌。
- 模型提示、Knowledge Base、追蹤紀錄及應用日誌不得包含完整姓名、電話、Email、地址或附件內容。
- 聯絡資料與詳細地址需加密儲存；用於精確比對的欄位另存不可逆雜湊。
- 服務商後台必須驗證組織成員身分與案件授權，不能只依前端隱藏資料。
- 上傳檔案限制類型、大小與數量，並以不含原始檔名的物件鍵儲存。

## 7. 驗收方法

- 每一服務類別至少具備：完整輸入、缺少必填欄位、條件式欄位、模糊分類及不安全情境案例。
- 每一 MCP 工具具備成功、輸入驗證失敗、未授權、找不到資源與重試案例。
- 端到端流程需驗證「理解需求 → 補齊欄位 → 產生文件 → 確認 → 建案 → 媒合 → 等待廠商 → 接受／拒絕／補件 → 恢復 Agent → 最終結論」。
- 規格驗收以 OpenSpec scenarios 為準；實作完成後將 scenarios 對應成自動化測試。

## 8. 延後決策

- 何時因實際連線壓力加入 RDS Proxy。
- 合作廠商 API 可用後，哪些 mock adapter 升級為真實整合，以及是否需要 NAT Gateway 或其他受控 egress。
- 哪個領域的 Agent 在基準評測未達標時需要升級模型。
