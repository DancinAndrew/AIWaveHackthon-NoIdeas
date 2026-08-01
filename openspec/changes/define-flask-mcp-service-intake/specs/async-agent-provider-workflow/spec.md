## ADDED Requirements

### Requirement: 領域 Agent 多輪蒐集與需求文件
Supervisor SHALL 將明確的單一領域需求交給對應領域 Agent；該 Agent MUST 依表單 Schema 多輪追問缺少欄位，並在住戶確認前產生版本化 `service_request_brief`。文件 SHALL 保存 canonical JSON、非敏感摘要、schema version、產生者與版本；提供廠商的版本 MUST 遮蔽未授權 PII。

#### Scenario: 水電需求文件完成
- **WHEN** 水電 Agent 已取得問題症狀、地區、風險旗標與可服務時段
- **THEN** 系統產生 `draft` brief，顯示給住戶確認，且在確認前不得開始廠商委派

#### Scenario: 住戶修改文件內容
- **WHEN** 住戶在確認前修正時段或問題描述
- **THEN** 系統建立新 artifact version，舊版本標為 superseded，confirmation token 不得沿用

### Requirement: Step Functions 保存非同步三方流程
每個經住戶確認建立的 `service_request` SHALL 啟動一個 Step Functions Standard execution。Workflow MUST 明確表示 `matching_provider`、`waiting_provider_response`、`waiting_resident_information`、`rematching`、`provider_confirmed`、`in_progress`、`completed`、`failed` 與 `cancelled` 等 stage。AgentCore Runtime MUST NOT 為等待人工作業而持續保持 busy。

#### Scenario: 等待廠商期間 Agent 停止執行
- **WHEN** 第一順位廠商已收到候選任務但尚未回覆
- **THEN** workflow 暫停於 callback state，AgentCore 不持續執行，RDS projection 顯示等待廠商

#### Scenario: 恢復原領域 Agent
- **WHEN** 廠商提出需要住戶回答的新問題
- **THEN** workflow 以案件綁定的領域與 conversation context 喚起原領域 Agent，將必要問題寫入住戶對話

### Requirement: 廠商 callback 與自動改派
廠商 SHALL 只能透過 Cognito 驗證的後台對其組織目前可操作的 `workflow_task` 接受、拒絕、要求補件或新增訊息。Flask MUST 驗證 membership、task status、expected version 與 idempotency key，再以 server-side callback 恢復 workflow。拒絕或管理員模擬逾時 SHALL 立即改派下一名候選。

#### Scenario: 廠商要求補件
- **WHEN** 已委派廠商選擇 `needs_information` 並提供具體問題
- **THEN** 原始訊息不可變保存，task 完成，workflow 轉為 `waiting_resident_information` 並恢復領域 Agent

#### Scenario: 廠商拒絕後改派
- **WHEN** 廠商拒絕目前候選任務
- **THEN** 系統將媒合標記為 `declined`、完成目前 task，並依原規則版本及排序建立下一位廠商的 task

#### Scenario: 管理員模擬逾時
- **WHEN** ADMIN 對等待中的廠商任務按下模擬逾時
- **THEN** 系統記錄 admin actor 與原因，將媒合標為 `expired`，並走與拒絕相同的改派分支

### Requirement: callback token 不得暴露
Step Functions task token MUST 只存在於 server-side 受控邊界，若需持久化 SHALL 使用 KMS envelope encryption。Token MUST NOT 出現在瀏覽器 payload、URL、Agent prompt、MCP arguments、conversation message 或一般 log。

#### Scenario: 廠商送出接受
- **WHEN** 廠商前端送出 task ID、action 與 expected version
- **THEN** Flask 由可信 repository 取得 callback reference 並完成 callback，前端 request 與 response 均不包含 task token

### Requirement: RDS 提供提醒與進度投影
系統 SHALL 以 `workflow_executions` 與 `workflow_tasks` 保存目前 stage、等待角色、可讀標籤、due time、reminder state 與完成時間；以 `conversation_messages` 保存三方訊息；以 `service_request_artifacts` 保存需求文件。前端 MUST 從授權後的 RDS projection API 讀取，不直接查詢 Step Functions execution history。

#### Scenario: 住戶查看進度
- **WHEN** 案件正在等待廠商確認
- **THEN** 住戶頁顯示「已媒合廠商，等待回覆」、最近事件時間及目前無需住戶操作，不顯示 callback token 或內部錯誤

#### Scenario: 住戶有待補資料
- **WHEN** workflow 進入 `waiting_resident_information`
- **THEN** 提醒頁顯示住戶待辦，原 AI 對話顯示領域 Agent 的具體追問

### Requirement: 最終結論回到原對話
廠商接受且必要細節完整後，workflow SHALL 喚起原領域 Agent，以已確認 artifact、廠商原始回覆與非敏感狀態產生最終結論，保存為 conversation message 並將 stage 更新為 `provider_confirmed`。模型不得宣稱 mock 外部系統已完成不可逆交易。

#### Scenario: 水電廠商完成確認
- **WHEN** 廠商接受派工並確認可到場時段與勘查條件
- **THEN** 住戶對話收到包含廠商、時段、注意事項與平台內確認狀態的結論，進度頁同步顯示下一步

### Requirement: Demo 使用輪詢更新
React SPA SHALL 以短週期 REST polling 取得 messages、progress 與 reminders；此 change MUST NOT 要求 WebSocket。重複輪詢 MUST 為唯讀且不得重複觸發 Agent 或 workflow callback。

#### Scenario: 結論在輪詢後出現
- **WHEN** workflow 寫入新的 final Agent message
- **THEN** 下一次 polling 回傳該訊息與新 stage，前端只新增一次且不重新執行 workflow

### Requirement: 水電 walking skeleton REST 契約
Flask SHALL 暴露版本化 `/api/v1` REST 介面，讓現有 React 頁面完成單一水電案例。住戶身分 SHALL 由受信任的 request context 取得；Demo local adapter MAY 使用 `X-Demo-Resident-Id`、`X-Demo-Provider-Id` 與 `X-Demo-Role` header 模擬該 context，但服務層 MUST NOT 接受 request body 覆寫 actor。所有寫入端點 SHALL 驗證 JSON object、動作白名單與 `Idempotency-Key`。

Walking skeleton SHALL 至少提供：

- `POST /api/v1/conversations`
- `POST /api/v1/conversations/{conversation_id}/messages`
- `GET /api/v1/conversations/{conversation_id}/messages`
- `GET /api/v1/service-requests`
- `GET /api/v1/service-requests/{service_request_id}/progress`
- `GET /api/v1/reminders`
- `GET /api/v1/provider-service-requests`
- `POST /api/v1/provider-service-requests/{task_id}/responses`
- `POST /api/v1/admin/workflow-tasks/{task_id}/simulate-timeout`

#### Scenario: 現有三個前端頁面讀取同一流程投影
- **WHEN** 住戶在「智慧助理」確認水電需求文件並開始媒合
- **THEN**「我的預約」從 `service-requests` 與 `progress` 顯示同一案件，「後台管理」從 `provider-service-requests` 顯示目前受派廠商可操作的 task

#### Scenario: actor 不可由 body 冒用
- **WHEN** 廠商在 response body 放入另一個 `providerId` 或住戶在 body 放入另一個 `residentId`
- **THEN** Flask 忽略該欄位並只以受信任 request context 執行資源授權

### Requirement: 水電 Agent 的確定性 Demo fallback
正式部署 SHALL 由一個 AgentCore Runtime 中的 Supervisor 將水電任務當工具委派給水電邏輯 Agent。為使本機與 CI 不依賴模型連線，application core SHALL 同時提供符合相同 turn contract 的確定性 Demo fallback；fallback 的安全判斷、狀態轉移、廠商硬條件過濾與冪等 MUST 為程式規則，不得由模型自由決定。

#### Scenario: 模型或 AgentCore 尚未連線
- **WHEN** local／test 設定選擇 deterministic adapter
- **THEN** 完整 water-repair E2E 仍可走完，且 API 明確回傳 `orchestrationMode: deterministic-demo`，不得假裝已由 AgentCore 執行

#### Scenario: 正式 AgentCore 委派
- **WHEN** staging 設定選擇 AgentCore adapter 且 Supervisor 判斷為 `utility_repair`
- **THEN** turn trace 顯示 Supervisor 呼叫 `utility_repair_agent`，而狀態改變仍只能透過核准的 application tools

### Requirement: Hackathon AWS 帳號使用限制
AWS staging 部署 MUST 將主辦方的帳號使用規範視為 deployment gate，而非僅文件提醒。所有 S3 bucket MUST 開啟四項 S3 Block Public Access；RDS MUST 位於 private subnets 且 `PubliclyAccessible=false`。此 Demo MUST NOT 建立 EC2、EMR 或 SageMaker training job。Security Group MUST NOT 對 `0.0.0.0/0` 或 `::/0` 開放 ingress；API 的公開入口只能是 API Gateway／受管 frontend hosting。

部署前資料掃描 MUST 阻擋個資、受監管資料、財務資料、種族／政治／宗教／工會／基因／生物特徵／性傾向或性生活／健康／支付處理資料及惡意程式碼。AWS 只可上傳本專案合成且通過掃描的 Knowledge Base／mock 子集，不得上傳 `pii_vault.json`、競賽原始資料或對話中輸入的姓名、電話、Email、詳細地址與附件。

Bedrock／AgentCore 呼叫 SHALL 使用必要模型白名單與低於 1 RPS 的 client-side rate limiter；部署程式 MUST NOT 批次啟用與本專案無關的模型。Demo 成本設定 SHALL 使用完成 walking skeleton 所需的最小資源，並提供 teardown 指令。

#### Scenario: S3 與 RDS 安全驗收
- **WHEN** IaC synth／diff 完成
- **THEN** policy test 證明每個 S3 bucket 四項 Block Public Access 均為 true，且每個 RDS instance／cluster `PubliclyAccessible` 為 false

#### Scenario: 禁止資料在部署前被上傳
- **WHEN** deployment package 或 KB upload manifest 包含 `pii_vault.json`、競賽原始資料路徑、疑似聯絡資訊或禁止類別標記
- **THEN** deployment gate 失敗且不呼叫任何 AWS create／upload API

#### Scenario: Bedrock 速率與模型最小化
- **WHEN** walking skeleton 呼叫 Bedrock／AgentCore
- **THEN** 單一 Demo client 的呼叫間隔大於一秒，且模型 ID 必須在專案明確白名單內
