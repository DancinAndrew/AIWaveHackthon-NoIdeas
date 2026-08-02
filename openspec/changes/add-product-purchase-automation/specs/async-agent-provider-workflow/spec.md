## MODIFIED Requirements

### Requirement: Step Functions 保存非同步三方流程
每個經住戶確認建立的 `service_request` SHALL 啟動一個 Step Functions Standard execution。Workflow MUST 明確表示 `matching_provider`、`waiting_provider_response`、`waiting_resident_information`、`rematching`、`provider_confirmed`、`in_progress`、`completed`、`failed` 與 `cancelled` 等 stage。

商品購買類別 SHALL 額外使用 `awaiting_resident_selection`、`authorizing_payment` 與 `out_of_stock` 三個 stage，並 MUST 重用既有的 `waiting_provider_response`、`waiting_resident_information`、`rematching` 與 `provider_confirmed` 語意，使進度投影與提醒邏輯跨類別一致。Stage 名稱 MUST NOT 依服務類別另建同義詞。

AgentCore Runtime MUST NOT 為等待人工作業而持續保持 busy。

#### Scenario: 等待廠商期間 Agent 停止執行
- **WHEN** 第一順位廠商已收到候選任務但尚未回覆
- **THEN** workflow 暫停於 callback state，AgentCore 不持續執行，RDS projection 顯示等待廠商

#### Scenario: 恢復原領域 Agent
- **WHEN** 廠商提出需要住戶回答的新問題
- **THEN** workflow 以案件綁定的領域與 conversation context 喚起原領域 Agent，將必要問題寫入住戶對話

#### Scenario: 商品案件等待住戶選品
- **WHEN** 商品案件欄位齊全並取得候選 SKU
- **THEN** stage 為 `awaiting_resident_selection`、等待角色為住戶，且在住戶選品前不啟動供應商委派

#### Scenario: 商品案件等待 mock 付款授權
- **WHEN** 住戶確認訂單摘要
- **THEN** stage 先轉為 `authorizing_payment`，授權完成後才轉為 `waiting_provider_response`

### Requirement: 水電 walking skeleton REST 契約
Flask SHALL 暴露版本化 `/api/v1` REST 介面，讓現有 React 頁面完成單一水電案例。住戶身分 SHALL 由受信任的 request context 取得；Demo local adapter MAY 使用 `X-Demo-Resident-Id`、`X-Demo-Provider-Id` 與 `X-Demo-Role` header 模擬該 context，但服務層 MUST NOT 接受 request body 覆寫 actor。所有寫入端點 SHALL 驗證 JSON object、動作白名單與 `Idempotency-Key`。

Walking skeleton SHALL 至少提供：

- `POST /api/v1/conversations`
- `POST /api/v1/conversations/{conversation_id}/messages`
- `GET /api/v1/conversations/{conversation_id}/messages`
- `GET /api/v1/service-requests`
- `GET /api/v1/service-requests/{service_request_id}/progress`
- `POST /api/v1/service-requests/{service_request_id}/selections`
- `GET /api/v1/reminders`
- `GET /api/v1/provider-service-requests`
- `POST /api/v1/provider-service-requests/{task_id}/responses`
- `POST /api/v1/admin/workflow-tasks/{task_id}/simulate-timeout`

`POST /api/v1/service-requests/{service_request_id}/selections` SHALL 只供需要住戶在多個候選之間選擇的類別使用；請求 MUST 只包含候選識別碼與 `expectedVersion`，MUST NOT 包含金額、庫存或供應商欄位。伺服器 MUST 以自身資料重新計算金額，MUST NOT 信任任何用戶端傳入的價格。

#### Scenario: 現有三個前端頁面讀取同一流程投影
- **WHEN** 住戶在「智慧助理」確認水電需求文件並開始媒合
- **THEN**「我的預約」從 `service-requests` 與 `progress` 顯示同一案件，「後台管理」從 `provider-service-requests` 顯示目前受派廠商可操作的 task

#### Scenario: actor 不可由 body 冒用
- **WHEN** 廠商在 response body 放入另一個 `providerId` 或住戶在 body 放入另一個 `residentId`
- **THEN** Flask 忽略該欄位並只以受信任 request context 執行資源授權

#### Scenario: 選品端點不接受用戶端金額
- **WHEN** 選品請求的 body 夾帶 `finalAmount` 或 `shippingFee`
- **THEN** Flask 忽略這些欄位並以伺服器端目錄重新計算金額，artifact 顯示的金額不受請求影響

#### Scenario: 非選品類別呼叫選品端點
- **WHEN** 對水電案件呼叫選品端點
- **THEN** 系統回傳驗證錯誤，案件 stage 不變

### Requirement: RDS 提供提醒與進度投影
系統 SHALL 以 `workflow_executions` 與 `workflow_tasks` 保存目前 stage、等待角色、可讀標籤、due time、reminder state 與完成時間；以 `conversation_messages` 保存三方訊息；以 `service_request_artifacts` 保存需求文件。前端 MUST 從授權後的 RDS projection API 讀取，不直接查詢 Step Functions execution history。

Projection 的 `serviceType` SHALL 可表示全部五類服務，前端型別 MUST NOT 將其固定為單一類別字面值。`displayLabel` SHALL 依類別提供住戶可理解的中文標籤。

#### Scenario: 住戶查看進度
- **WHEN** 案件正在等待廠商確認
- **THEN** 住戶頁顯示「已媒合廠商，等待回覆」、最近事件時間及目前無需住戶操作，不顯示 callback token 或內部錯誤

#### Scenario: 住戶有待補資料
- **WHEN** workflow 進入 `waiting_resident_information`
- **THEN** 提醒頁顯示住戶待辦，原 AI 對話顯示領域 Agent 的具體追問

#### Scenario: 商品與水電案件並存
- **WHEN** 同一住戶同時有進行中的商品案件與水電案件
- **THEN**「我的預約」同時列出兩筆並各自顯示對應類別名稱與 stage 標籤，不互相覆蓋

#### Scenario: 缺貨案件的提醒
- **WHEN** 商品案件進入 `out_of_stock`
- **THEN** 進度頁顯示缺貨與已知補貨時間，等待角色為住戶，且不顯示任何金額已成立的訊息

### Requirement: 水電 Agent 的確定性 Demo fallback
正式部署 SHALL 由一個 AgentCore Runtime 中的 Supervisor 將領域任務當工具委派給對應邏輯 Agent。為使本機與 CI 不依賴模型連線，application core SHALL 同時提供符合相同 turn contract 的確定性 Demo fallback；fallback 的安全判斷、狀態轉移、候選硬條件過濾、金額計算與冪等 MUST 為程式規則，不得由模型自由決定。

#### Scenario: 模型或 AgentCore 尚未連線
- **WHEN** local／test 設定選擇 deterministic adapter
- **THEN** 完整 E2E 仍可走完，且 API 明確回傳 `orchestrationMode: deterministic-demo`，不得假裝已由 AgentCore 執行

#### Scenario: 正式 AgentCore 委派
- **WHEN** staging 設定選擇 AgentCore adapter 且 Supervisor 判斷為 `utility_repair`
- **THEN** turn trace 顯示 Supervisor 呼叫 `utility_repair_agent`，而狀態改變仍只能透過核准的 application tools

#### Scenario: 商品案件的確定性金額
- **WHEN** deterministic adapter 處理商品選品與確認
- **THEN** `original_amount`、`discount_amount`、`shipping_fee_amount` 與 `final_amount` 均由規則計算，重複執行結果一致
