## Context

目前 repo 已將 HTTP 技術方向切換為 Flask，並整理命題資料與架構文件，但尚未有正式後端 application entrypoint、AgentCore Runtime、MCP tools、可驗收表單或交易生命週期。競賽限制只允許 AWS 服務，因此先前的 Supabase 與 Bedrock Agents Classic 方案已由 ADR-0003 取代。提供的資料檔適合做為 RDS seed 與展示 fixtures，但不能直接成為 Knowledge Base 或正式資料庫真實來源。

本 change 同時處理五類表單、AgentCore 多領域 Agent、MCP 工具、RDS 資料邊界、PII、安全確認及 FastAPI 至 Flask 的 stack migration，因此需要跨模組設計。

利害關係人包括消費者、服務商成員、平台管理員、前端、Orchestrator、外部 MCP client 及未來合作廠商 API。

## Goals / Non-Goals

**Goals:**

- 用一組共用元件支援五類服務需求蒐集與媒合。
- 讓 REST 與 MCP 共用相同驗證、授權、媒合、冪等及狀態機。
- 以機器可讀 JSON Schema 固定五類表單與六項 MCP 工具契約。
- 讓消費者確認後建案，服務商後台可承接與追蹤。
- 以 Amplify Hosting、Cognito、Flask Lambda、AgentCore Runtime／Gateway 與 RDS PostgreSQL 形成可逐步實作與測試的 AWS-only MVP。

**Non-Goals:**

- 此 change 不呼叫真實付款、退款、餐廳、供應商或派工平台；內部 Demo 交易與狀態仍須真的寫入 RDS。
- 此 change 不把 Supervisor 與五個邏輯領域 Agent 拆成六個獨立 AgentCore Runtime。
- 此 change 不把 Knowledge Base 當即時資料來源。
- 此 change 不開放 Cognito 公開註冊；Demo 使用預建帳號。
- 此 change 不宣稱命題資料已完成清理或正式匯入。

## Decisions

### 1. 元件與呼叫方向

```text
React SPA on Amplify Hosting
  -> Cognito -> API Gateway -> Flask Lambda REST Blueprints
      -> shared Python application core
          -> repositories -> Amazon RDS for PostgreSQL
          -> mock/vendor adapters
          -> start/callback AWS Step Functions Standard
      -> AgentCore Runtime
          -> Supervisor -> five logical domain agents
              -> AgentCore Gateway MCP tools
                  -> six logical Lambda target groups
                      -> shared Python application core
Step Functions
  -> wait for resident/provider callback without keeping AgentCore busy
  -> invoke workflow worker Lambda -> AgentCore Runtime when reasoning resumes
  -> project every stage/task/message/artifact to RDS
```

工具 Lambda 與 REST Blueprint 都是 transport adapter。它們只能將驗證後 input 轉成 application command/query，不能各自重做媒合、授權或狀態轉移。共用 application core 由同一 monorepo source package 建置進 Flask Lambda 與各工具 Lambda artifact；Demo 不另建需要獨立版本管理的 Lambda Layer。

### 2. Flask 模組邊界

預定目錄：

```text
src/aiwave/
  __init__.py             # create_app
  config.py
  api/
    errors.py
    form_schemas.py       # Blueprint
    service_requests.py          # Blueprint
    provider_service_requests.py # Blueprint
  application/
    form_service.py
    service_request_service.py
    matching_service.py
    workflow_service.py
    conversation_service.py
    artifact_service.py
  domain/
    models.py
    statuses.py
    errors.py
  repositories/
    protocols.py
    postgres.py
  tool_targets/
    handlers.py
  workflow/
    worker.py
    callbacks.py
  schemas/
    loader.py
```

`create_app` 負責設定、extension 與 Blueprint 註冊。公開 function 與 application boundary 使用型別註記。Flask handler 僅處理 HTTP status、header、序列化及 actor context。

### 3. HTTP API 與錯誤契約

REST 基準路徑使用 `/api/v1`：

- `GET /api/v1/form-schemas/{service_type}`
- `POST /api/v1/provider-searches`
- `POST /api/v1/service-requests`
- `GET /api/v1/service-requests/{service_request_id}`
- `GET /api/v1/provider-service-requests`
- `PATCH /api/v1/service-requests/{service_request_id}`
- `GET /api/v1/service-requests/{service_request_id}/progress`
- `GET /api/v1/service-requests/{service_request_id}/messages`
- `POST /api/v1/service-requests/{service_request_id}/messages`
- `GET /api/v1/service-requests/{service_request_id}/artifacts`
- `POST /api/v1/provider-service-requests/{service_request_id}/responses`
- `GET /api/v1/reminders`
- `POST /api/v1/admin/workflow-tasks/{workflow_task_id}/simulate-timeout`

建立資源回傳 201 與 `Location`；驗證錯誤回傳 422；未驗證、未授權、找不到、冪等衝突、版本衝突分別使用 401、403、404、409。所有錯誤使用：

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": [],
    "request_id": "..."
  }
}
```

替代方案是讓工具 Lambda 呼叫 Flask REST；未採用，因為額外 HTTP hop 增加失敗點與序列化成本，也可能造成 REST 與 MCP 授權上下文差異。兩種 transport 改為直接使用相同 application core。

### 4. 表單 Schema Registry

五類表單使用 JSON Schema Draft 2020-12。正式資料表 `form_schemas` 保存 `service_type`、`schema_version`、Schema、啟用狀態、內容雜湊及有效期間；active change 的 `contracts/forms/*.schema.json` 是初版契約來源。

提交流程：

1. Orchestrator 取得指定類別 Schema。
2. 非敏感答案可在對話中蒐集；聯絡資料由受信任前端／Flask 路徑收集。
3. Flask 驗證完整 submission，將 PII 加密並簽發 `submission_ref`。
4. Agent 以正規化 submission 產生版本化 `service_request_brief`；canonical JSON 存 RDS，授權頁面可渲染 HTML，PDF 為選配 artifact。
5. 使用者看到文件摘要並確認後，Flask 簽發綁定 artifact version 的短效 `confirmation_token`。
6. `create_service_request` 只接收 references、類別、版本及冪等鍵，不接收原始 PII；建立成功後以冪等 execution name 啟動 Step Functions workflow。

替代方案是把欄位直接寫死在 prompt；未採用，因為無法版本化、穩定驗證或由前端重用。

### 5. AgentCore Runtime 與 MCP Tool Registry

一個 AgentCore Runtime 內含 Supervisor 與五個邏輯領域 Agent。Supervisor 只做類別路由與跨類別協調；領域 Agent 各自負責欄位抽取、追問與領域工具選擇。五個 Agent 共享 Runtime、session isolation、觀測與版本，但使用不同 instructions、tool allowlist 與 Knowledge Base `service_type` filter。

`contracts/mcp/tools.json` 定義工具名稱、描述、封閉 input schema 與 output schema。AgentCore Gateway 使用 Lambda targets，邏輯上分成 `service-request-tools` 與餐廳、商品、家事、水電、社區五個領域 target group。tool handler 驗證 input 後呼叫 application service。Gateway request interceptor 從已驗證 credential claims 建立 actor context；模型或 client header 傳入的 `consumer_id`、`provider_id` 或 actor 欄位不具有授權效力。

任何 tool error 轉為穩定錯誤碼與 request ID。詳細 dependency error 僅存在伺服器日誌，且先經 PII／secret redaction。

### 6. 資料模型

Amazon RDS for PostgreSQL 正式模型至少包含：

- `service_categories`
- `form_schemas`
- `form_submissions`
- `pii_contacts`
- `providers`
- `provider_members`
- `provider_offerings`
- `provider_service_areas`
- `provider_availability`
- `service_requests`
- `service_request_matches`
- `service_request_events`
- `service_request_artifacts`
- `conversation_threads`
- `conversation_messages`
- `workflow_executions`
- `workflow_tasks`
- `idempotency_records`

`service_requests` 保存目前狀態、版本、service type、schema version、非敏感摘要及 PII reference；`service_request_events` 是 append-only。`service_request_matches` 保存每一服務商的媒合狀態、規則版本、分數與理由。

`service_request_artifacts` 保存 canonical JSON、顯示版本、artifact status 與 optional private S3 object reference；`conversation_messages` 保存住戶、廠商與 Agent 訊息及 audience。`workflow_executions` 對應 Step Functions execution ARN、Agent 領域及非敏感 conversation context reference；`workflow_tasks` 是提醒與進度頁的 read model，保存 stage、等待角色、公開標籤、due time、status、expected version 及加密 callback reference。

命題提供的 JSON／CSV 先載入 staging 或以 fixture adapter 讀取。正式匯入前必須修正：多個頂層 JSON 文件、缺少 form group、主檔與 order service ID 不一致，以及文件未定義的 order type。

### 7. 媒合演算法

媒合分兩階段：

1. 硬條件：服務類別、啟用狀態、服務地區、必要能力、必要安全能力及必要時段。
2. 軟排序：預算符合度、時段接近度、評分及緊急能力。

規則與權重需有版本。相同資料快照、輸入與規則版本必須產生相同排序。每個結果保存人類可理解的 reasons，不把 LLM 生成文字當分數來源。

### 8. 狀態與並行控制

案件狀態：

```text
submitted -> matched | unmatched | cancelled
matched -> accepted | needs_information | unmatched | cancelled
accepted -> in_progress | needs_information | cancelled
needs_information -> submitted | cancelled
in_progress -> completed | needs_information | cancelled
completed, cancelled -> terminal
```

媒合狀態獨立為 `proposed`、`accepted`、`declined`、`expired`。更新使用 `expected_version` 樂觀鎖；目前狀態與事件以同一 database function／transaction 寫入。

Workflow stage 與業務狀態分開：

```text
collecting_details
  -> waiting_resident_confirmation
  -> generating_brief
  -> matching_provider
  -> waiting_provider_response
      -> rematching -> waiting_provider_response
      -> waiting_resident_information -> waiting_provider_response
      -> provider_confirmed
  -> in_progress -> completed
failed, cancelled -> terminal
```

Step Functions 是等待與分支 owner；RDS workflow projection 是產品 UI 的真實來源。每個 state transition 使用冪等 command 更新 projection。廠商回覆先完成 RDS transaction，再以 server-side task token callback；重試不得重複建立訊息、task、match 或 Agent run。

### 9. 安全與 PII

- Cognito 簽發 JWT，API Gateway 驗證 token，application service 只接收由受信任 adapter 建立的 actor context。
- Flask 依 Cognito group、使用者 `sub`、provider membership 與資源 owner 執行授權；前端隱藏按鈕不構成安全控制。
- PII 使用 envelope encryption 或等價的集中加密服務；查詢用值另存 keyed hash，不使用明文雜湊低熵手機號碼。
- prompt、MCP trace、錯誤、一般 log 只記 reference 或遮蔽值。
- confirmation token 綁定 actor、submission hash、摘要版本與短效期限。
- idempotency record 綁定 actor、tool、key、payload hash 與結果 reference。
- Step Functions callback token 若需持久化，使用 KMS envelope encryption 並只由 workflow service 解密；前端、模型、MCP 與一般 log 永遠看不到 token。
- 廠商 callback 同時驗證 provider membership、目前 task owner、task status、expected version 與 idempotency key。
- 附件限制格式、大小、數量及受控物件鍵；後續上線前需增加惡意內容掃描。

### 10. Knowledge Base 邊界

FAQ、注意事項、服務條款與 SOP 存放在一個 S3 知識來源及一個 Amazon Bedrock Managed Knowledge Base，依 `service_type`、`doc_kind` 與 `version` metadata 檢索。服務商可服務狀態、價格、庫存、時段與交易狀態只由 RDS repository／mock 或 vendor adapter 取得。live source 失效時回傳明確錯誤，不 fallback 到 KB 猜測。

水電高風險停手規則同時寫入水電 Agent 固定 instructions 與 Flask 確定性安全檢查；KB 只能補充說明，不能成為唯一控制。

### 11. Region、模型與網路

- 所有 Demo 工作負載使用 `us-west-2`。
- Supervisor 與五個領域 Agent 以 `amazon.nova-2-lite-v1:0` 為 baseline；模型 ID 依 Agent 配置，測試失敗時可只升級單一領域。
- Managed Knowledge Base 使用 `cohere.embed-multilingual-v3`，並以繁體中文 retrieval eval 驗證。
- VPC 至少跨兩個 AZ；Flask Lambda、工具 Lambda 與 RDS 位於 private subnets，RDS security group 只接受 Lambda security group 的 5432 連線。
- Flask 透過 AgentCore interface VPC endpoint 呼叫 Runtime，S3 使用 gateway endpoint。AgentCore Runtime 不直接連 RDS。
- Step Functions 是 AWS managed workflow service；它透過 IAM 核准的 workflow worker Lambda 喚起 AgentCore，人工等待期間不占用 AgentCore Runtime session。
- Demo 的外部付款與廠商 API 都是 mock，因此不建立 NAT Gateway。未來需要公網 egress 時另行決策。
- Cognito JWT 是 Runtime 的 inbound 身分依據；Gateway interceptor 只從可信 claims 衍生 actor context。
- Secrets Manager 保存資料庫憑證；KMS 保護 RDS、Secrets 與 PII；CloudWatch／AgentCore Observability 以 request ID、session ID 與 trace ID 串聯。
- AWS CDK for Python 是基礎設施唯一 source of truth。RDS Proxy 暫不加入 Demo。

## Risks / Trade-offs

- [Risk] Flask 缺少自動 request model 與 OpenAPI → 以 Pydantic／JSON Schema 驗證，CI 檢查 contracts，並由 REST 文件引用同一契約。
- [Risk] 五類 Schema 重複共用欄位 → 初版保持獨立、易讀與可驗證；實作後再用 generator 或 `$defs` 消除維護重複，不能犧牲輸出封閉性。
- [Risk] Supervisor 路由錯誤 → 建案前顯示類別與摘要，跨類別／低信心時強制澄清，建立分類與 handoff 評測集。
- [Risk] Agent 或廠商跨角色存取 → Gateway 採 tool allowlist，API Gateway 驗證 Cognito JWT，Flask 以 RDS ownership／membership 再授權。
- [Risk] 命題 fixtures 資料不一致 → staging import 先做 schema、FK、狀態碼及 JSON 正規化檢查，demo fixtures 與正式資料標示來源。
- [Risk] AgentCore Gateway 整合時間成本 → 先以餐廳 walking skeleton 驗證 Runtime → Gateway → Lambda target；所有 target 重用同一 application core。
- [Risk] 無 NAT 無法呼叫一般公網 API → Demo 只使用 mock adapter；真實合作廠商整合另立 egress 決策。
- [Risk] REST 與工具 Lambda artifact 版本漂移 → CDK 同次部署並在 smoke test 比對 application core 版本。
- [Risk] Step Functions state 與 RDS projection 漂移 → 每步使用冪等 projection command，保存 execution ARN／state name，並提供 ADMIN reconcile 操作與一致性測試。
- [Risk] callback token 洩漏或重放 → token server-side 加密，前端只提交 workflow task ID；Flask 驗證 actor、版本、狀態與冪等鍵。
- [Risk] 人工作業超過 AgentCore Runtime 生命週期 → RDS conversation messages 保存耐久上下文，workflow 恢復時重新組裝必要 context，不依賴常駐 process memory。

## Migration Plan

1. 確認 `pyproject.toml` 與 lockfile 已由 FastAPI／Uvicorn 切換為 Flask，且舊 FastAPI 原型只保留在 archive 或 Git 歷史，不再作為正式入口。
2. 建立 Flask application factory、health endpoint、統一錯誤格式及測試 client。
3. 建立五份表單 Schema loader 與契約測試。
4. 建立 RDS PostgreSQL migrations、repository protocols、Cognito actor mapping 與 deterministic fixtures。
5. 實作共用 application core，再分別接 REST Blueprint 與 AgentCore Gateway Lambda targets。
6. 建立 Step Functions Standard workflow、callback service、artifact／conversation／workflow projection 與輪詢 API。
7. 先以餐廳訂位完成 Runtime → Supervisor → 餐廳 Agent → 文件 → Gateway → Lambda → RDS → Step Functions → 廠商 callback → 最終 Agent 結論 walking skeleton。
8. 將同一骨架擴充至其餘四個領域，並執行五類評測案例。
9. 串接 Amplify Hosting 上的 React 消費者／服務商／管理員流程，完成端到端驗收。

Rollback：在 Flask 尚未接手正式流量前可停用新 entrypoint；資料 migration 應採 additive table／column，回滾時先停用寫入而不刪除已建立案件。由於目前沒有正式 FastAPI API，預期沒有需要相容或恢復的既有路由。

## Deferred Questions

- RDS Proxy 何時由正式化選項升級為必要元件？
- 真實合作廠商 API 需要哪種受控 egress 與重試／補償策略？
- 哪些領域在 Nova 2 Lite baseline 未達評測門檻時需要升級模型？
