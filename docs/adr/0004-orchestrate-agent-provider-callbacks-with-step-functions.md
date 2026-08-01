# ADR-0004：以 Step Functions 編排 Agent、住戶與廠商非同步閉環

- 狀態：Accepted
- 日期：2026-08-01
- 決策者：AIWaveHackthon-NoIdeas 團隊
- 延伸：[ADR-0003](0003-adopt-aws-native-agentcore-rds-platform.md)
- 關聯規格：`SPEC.md`、`openspec/changes/define-flask-mcp-service-intake/`

## Context

Demo 不只要在住戶確認後建立案件，還要讓領域 Agent 自動媒合廠商、等待廠商登入承接或補問、必要時回到住戶對話補件，最後主動產生結論。廠商可能數小時後才回覆，等待期間也必須在提醒與進度頁顯示目前步驟、等待對象與下一個動作。

AgentCore Runtime 適合執行多輪推理與短期非同步工作，但人工作業等待不應靠一個持續執行的 Agent session 維持。RDS 仍是業務狀態、文件、訊息與進度投影的真實來源。

## Decision

### 1. Step Functions Standard 保存長流程

每個已確認的 `service_request` 啟動一個 AWS Step Functions Standard execution。Workflow 負責媒合、等待廠商 callback、拒絕後改派、補件往返與最終確認；AgentCore 只在分類、追問、文件摘要、廠商訊息判讀或最終回覆時被喚起，不在等待期間保持 busy。

### 2. 廠商回覆是受驗證的人工作業 callback

廠商從 Cognito 驗證的後台接受、拒絕、要求補件或新增訊息。Flask 先驗證 provider membership 與目前任務，再寫入 RDS，最後以 server-side Step Functions task token 恢復 workflow。Task token 必須加密保存，不得送到瀏覽器或模型。

Demo 的「模擬逾時」由管理員按鈕送出受稽核的 timeout callback；拒絕與逾時都立即依既有候選排序改派下一家。

### 3. 文件、訊息與進度都投影至 RDS

- `service_request_artifacts` 保存版本化需求文件；canonical payload 為 JSON，住戶與廠商頁面可渲染 HTML，必要時再輸出 PDF 至獨立 KMS 加密的 private S3 artifact bucket。
- `conversation_threads`／`conversation_messages` 保存住戶－Agent、廠商－Agent及系統訊息，完整 PII 仍以 reference 表示。
- `workflow_executions`／`workflow_tasks` 保存目前步驟、等待角色、期限、提醒、Step Functions execution ARN 與加密 callback reference。
- `service_request_events` 保存不可變業務歷程。前端只讀 RDS projection，不直接讀 Step Functions execution history。

### 4. 前端以輪詢呈現主動更新

React SPA 每數秒輪詢案件 progress、messages 與 reminders。Workflow 產生新追問或最終結論時寫入 conversation message，因此原 AI 對話與提醒頁都能顯示；Demo 不加入 WebSocket。

## Alternatives Considered

### 只使用 AgentCore Runtime asynchronous task

- **Pros**：服務較少，Agent 程式可直接在背景繼續工作。
- **Cons**：Runtime 長工作負載有生命週期上限，人工作業可能跨數小時或數天；等待也難以用明確 callback、分支與稽核表示。
- **Why not**：不適合作為廠商人工回覆的持久 workflow owner。

### 只以 Flask、RDS 狀態與排程輪詢

- **Pros**：不增加 Step Functions，資料全在既有後端。
- **Cons**：必須自行實作等待、重試、callback、分支、逾時與恢復，流程可觀測性較差。
- **Why not**：三方多步驟閉環會把 workflow engine 邏輯堆進 Flask。

### WebSocket 即時推送

- **Pros**：訊息與狀態可即時顯示。
- **Cons**：增加連線、重連、授權與部署範圍。
- **Why not**：Demo 使用短輪詢即可清楚展示進度，不值得先增加即時連線成本。

## Consequences

### Positive

- Agent 不必常駐等待廠商，人工作業可安全暫停與恢復。
- 住戶、廠商與管理員看到相同、可稽核的流程投影。
- 廠商補問可恢復原領域 Agent，再向住戶追問或直接使用既有文件回答。
- 拒絕、模擬逾時、自動改派與最終結論成為可驗收分支。

### Negative

- 新增 Step Functions state machine、callback token 管理與 workflow／RDS 一致性責任。
- 同一案件同時存在業務狀態與 workflow stage，必須明確區分並測試映射。
- 輪詢不是即時推送，狀態顯示會有數秒延遲。

### Risks

- callback 重放或越權 → token 僅 server-side 加密保存；Flask 驗證 provider membership、task status、版本與冪等鍵。
- Step Functions 已前進但 RDS projection 未更新 → 每個 state transition 使用冪等 command，保存 execution ARN／state name，並提供管理員 reconcile。
- Agent 回覆與廠商原意不一致 → 原始廠商訊息不可變保存，結論附 provider confirmation reference。
- PII 出現在文件或訊息 → artifact 產生前套用欄位 allowlist；詳細聯絡資料只經受稽核路徑提供給已承接廠商。

## References

- [AgentCore asynchronous and long-running agents](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-long-run.html)
- [Step Functions human approval callback](https://docs.aws.amazon.com/step-functions/latest/dg/tutorial-human-approval.html)
- [Step Functions service integration patterns](https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html)
