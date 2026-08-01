## 1. 專案與 Flask 基礎

- [x] 1.1 將根專案直接依賴由 FastAPI／Uvicorn 改為 Flask，並更新 README、架構文件與 lockfile；驗證：`pyproject.toml` 不含 FastAPI／Uvicorn、包含 Flask，且 `uv lock --check` 通過。
- [ ] 1.2 建立 Flask application factory、設定載入、Blueprint 註冊與 `/health`；驗證：Flask test client 在未連外部服務時得到 200 與不含機密的版本資訊。
- [ ] 1.3 建立統一成功／錯誤 envelope、request ID 與結構化日誌遮蔽；驗證：400、401、403、404、409、422、500 contract tests 均不回傳 stack、SQL、token 或 PII。

## 2. 表單契約與 submission

- [ ] 2.1 實作五份 Draft 2020-12 JSON Schema loader、版本索引與內容雜湊；驗證：五份 schema 通過 meta-schema，未知類別與未知版本測試回傳指定錯誤。
- [ ] 2.2 為五類表單建立完整、缺欄位、無效條件與條件式欄位 fixtures；驗證：每類至少一組有效與三組失敗案例對應 `service-intake-forms` scenarios。
- [ ] 2.3 實作安全 submission 流程，將聯絡資料加密並簽發 `submission_ref`；驗證：儲存後模型可見 payload、trace 與一般日誌都找不到原始姓名、手機、Email 或詳細地址。
- [ ] 2.4 實作正規化摘要與短效 `confirmation_token`；驗證：token 綁定 actor、submission hash 與摘要版本，過期或內容變更後不能建案。

## 3. RDS、Cognito 與資料安全

- [ ] 3.1 建立 service、form、provider、offering、service area、availability、service_request、match、event、artifact、conversation、workflow、task、PII 與 idempotency migrations；驗證：空資料庫可依序套用 migration，FK、unique key 與必要 index 存在。
- [ ] 3.2 建立 Cognito `RESIDENT`、`PROVIDER`、`ADMIN` 群組與 Flask resource authorization；驗證：以三種 JWT fixture 執行跨使用者與跨組織讀寫測試，未授權請求在 repository 執行前被拒絕。
- [ ] 3.3 建立案件狀態與事件的 transactional database function；驗證：事件寫入故障時案件狀態回滾，合法轉移版本加一，非法與 stale version 回傳衝突。
- [ ] 3.4 建立 PII 加密、keyed lookup hash 與受稽核解密介面；驗證：資料庫不存在 PII 明文，一般 service path 無法直接取得解密值。
- [ ] 3.5 將主辦資料載入 staging 並產生資料品質報告；驗證：報告明列多頂層 JSON、缺少 form group、service ID／vendor ID 及 order type 不一致，且不覆寫原始資料。

## 4. Application services 與 REST API

- [ ] 4.1 定義 repository protocols 與 PostgreSQL adapters，禁止 transport 層直接查表；驗證：service unit tests 可用 in-memory fake repository 執行。
- [ ] 4.2 實作 `FormService` 與 `GET /api/v1/form-schemas/{service_type}`；驗證：最新、指定版本與找不到版本案例符合 MCP／REST 契約。
- [ ] 4.3 實作確定性 `MatchingService` 的硬條件過濾、版本化軟排序與 reasons；驗證：相同快照結果穩定、地區／能力不符必定排除、高風險案件只選合格服務商。
- [ ] 4.4 實作 `POST /api/v1/provider-searches`；驗證：live source 正常、空結果、逾時與 stale cache 案例不以 Knowledge Base 臆造資料。
- [ ] 4.5 實作 `ServiceRequestService.create` 與 `POST /api/v1/service-requests`；驗證：首次建立為 201、相同冪等請求回傳原案件、同 key 不同 payload 為 409、缺確認不寫入。
- [ ] 4.6 實作 consumer 案件查詢及 provider 案件列表；驗證：ownership、組織授權、遮蔽聯絡資料與游標分頁 scenarios 通過。
- [ ] 4.7 實作 `PATCH /api/v1/service-requests/{id}` 狀態更新；驗證：合法轉移、非法轉移、終止狀態與 `expected_version` 衝突均有 contract tests。

## 5. AgentCore Gateway 與 MCP Tools

- [ ] 5.1 以 `contracts/mcp/tools.json` 建立 `service-request-tools` 與五個領域 Lambda target groups；驗證：只公開核准的 MVP tools，工具名稱及 input schemas 與 contract 完全一致。
- [ ] 5.2 將工具 Lambda 與 Flask Lambda 建置自同一 Python application core，不以 HTTP 互相呼叫；驗證：REST 與 MCP 對相同 command 產生相同 domain result、錯誤碼與 core version。
- [ ] 5.3 從驗證 credential context 建立 actor，忽略模型傳入的身分欄位；驗證：consumer 不能呼叫 provider list，跨案件與跨組織查詢被拒絕。
- [ ] 5.4 實作 MCP error mapping、request ID 與 trace redaction；驗證：驗證錯誤、相依服務錯誤與非預期錯誤都不含 stack、secret、PII 或完整 tool arguments。

## 6. AgentCore 多領域 Agent 與評測

- [ ] 6.1 在單一 AgentCore Runtime 實作 Supervisor 與五個邏輯領域 Agent；驗證：每類完整、缺欄位、模糊、跨類別及不支援案例均有 handoff 與 golden expectation。
- [ ] 6.2 實作水電高風險安全分流，禁止模型提供未驗證 DIY 指示；驗證：漏電、裸線、冒煙焦味與淹水 fixtures 都先輸出安全提示並保留高風險標記。
- [ ] 6.3 實作建案前的類別、摘要與聯絡使用確認；驗證：未確認、修改摘要、撤回同意或 token 過期均不呼叫 `create_service_request`。
- [ ] 6.4 建立 Orchestrator regression suite；驗證：測試報告分開呈現分類、欄位、工具選擇、幻覺服務商與安全失敗，不只計算最終文字相似度。
- [ ] 6.5 建立一個 Managed Knowledge Base 與五類 metadata filters；驗證：跨領域文件不會被取回，價格、庫存、時段及狀態問題必須呼叫 RDS 工具。

## 7. Step Functions 與非同步三方閉環

- [ ] 7.1 建立 Step Functions Standard workflow 與 `workflow_executions`／`workflow_tasks` projection；驗證：案件可停在廠商 callback state，AgentCore 不保持 busy，且 UI projection 顯示正確等待角色。
- [ ] 7.2 實作版本化 `service_request_brief` 與 artifact renderer；驗證：住戶修改會產生新版本並使舊 confirmation token 失效，廠商版本不含未授權 PII。
- [ ] 7.3 實作 provider accept／decline／needs-information callback；驗證：membership、task status、expected version、冪等與 server-side token 均受控，瀏覽器及 log 不含 task token。
- [ ] 7.4 實作拒絕立即改派與 ADMIN 模擬逾時；驗證：沿原候選排序建立下一個 task，重試不重複改派，管理員操作寫入 audit event。
- [ ] 7.5 實作廠商補問 → 恢復領域 Agent → 住戶補件 → 回到廠商的閉環；驗證：訊息 audience 正確、原始廠商問題不可變、Agent 只取得必要 conversation context。
- [ ] 7.6 實作 provider confirmed 後的最終 Agent 結論；驗證：原對話新增一次 final message，進度 projection 同步更新，且不宣稱 mock 外部系統完成不可逆交易。

## 8. React 消費者與服務商流程

- [ ] 8.1 建立由 JSON Schema 驅動的五類動態表單與欄位級錯誤顯示；驗證：五類 schema 均可渲染、補值、條件切換並提交有效 submission。
- [ ] 8.2 建立消費者對話、artifact 確認、媒合結果、提醒與進度頁；驗證：短輪詢只讀、不重複觸發 workflow，並清楚顯示目前步驟、等待對象與住戶待辦。
- [ ] 8.3 建立服務商候選案件、遮蔽文件、承接／婉拒／補件／訊息及進度後台；驗證：不同 provider 組織互不可見，承接後才依政策顯示必要聯絡資訊。
- [ ] 8.4 建立 ADMIN 停滯任務、模擬逾時與人工改派頁；驗證：每次操作需要原因並留下 actor、request ID 與前後狀態。

## 9. 端到端、安全與部署

- [ ] 9.1 為餐廳、商品、家事、水電、社區各完成一條端到端驗收；驗證：五條流程都經過多輪補欄位、文件確認、建案、媒合、廠商 callback、必要補件、最終結論及消費者查詢。
- [ ] 9.2 執行 API／MCP／workflow 安全測試；驗證：輸入白名單、SQL injection、資源授權、角色繞過、callback token 洩漏／重放、冪等、附件限制、PII log scan 與 rate limit 測試通過。
- [ ] 9.3 使用 AWS CDK for Python 建立 VPC、兩個 AZ private subnets、security groups、AgentCore interface endpoint、S3 gateway endpoint、Lambda targets、Step Functions、Secrets Manager 與 KMS；驗證：RDS 不公開、無 NAT、Runtime 不直接連 RDS，且 Lambda 能透過核准路徑存取依賴。
- [ ] 9.4 部署 Amplify Hosting、Cognito、API Gateway、Flask Lambda、AgentCore Runtime／Gateway、Step Functions 與 RDS staging，建立 health／dependency probes；驗證：部署網址、五類 demo fixtures、監控 request ID 及失敗 fallback 可在展示環境重現。
- [x] 9.5 更新 README、AWS 架構圖與 Knowledge Base 上傳資料；驗證：正式圖不含 Supabase，清楚呈現 Step Functions callback、進度 projection 與無 NAT 邊界，KB chunk 具有 Bedrock metadata sidecar。

## 10. 水電 walking skeleton 增量

- [x] 10.1 以 framework-free contract tests 鎖定水電完整閉環、安全 gate、授權、冪等、拒絕改派與模擬逾時；驗證：先保存 RED commit，再以相同測試轉為 GREEN。
- [x] 10.2 實作共用 application core 與 deterministic Demo adapter，並保留 AgentCore Supervisor → utility logical Agent adapter 邊界；驗證：未連 AWS 也能走完整閉環，response 不冒稱 AgentCore 已執行。
- [x] 10.3 將「智慧助理」「我的預約」「後台管理」接到 `/api/v1` 投影，並在快捷功能的「我的預約」旁新增「後台管理」；驗證：保留既有 layout／色彩／手機框，frontend build、lint 與瀏覽器 E2E 通過。
- [x] 10.4 建立 fail-closed AWS account preflight、pre-deploy guardrail 與合成 KB upload manifest；驗證：只允許 us-west-2 有效暫時憑證、唯讀 STS 身分檢查，policy tests 阻擋公開 S3／RDS、全網 Security Group、EC2／EMR／SageMaker training、未核准模型、非白名單路徑、雜湊變更、常見 PII／付款識別碼及執行檔，且 guardrail 不呼叫 AWS。
- [x] 10.5 將 API Gateway HTTP API payload v2 接到現行 Flask app，移除舊 handler 對未宣告 adapter 與舊媒合 Agent 的依賴；驗證：health、base64 JSON、actor headers、受限 CORS 與 invalid-event contract tests 通過。
- [ ] 10.6 建立 AWS staging IaC 與部署腳本，涵蓋 frontend hosting、API Gateway、Flask Lambda、AgentCore Runtime／Gateway、Step Functions、RDS、Cognito、S3 KB；驗證：diff／synth 不含 Supabase、RDS 不公開，部署後以公開 URL 重跑 water-repair smoke。
