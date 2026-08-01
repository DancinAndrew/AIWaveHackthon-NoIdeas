# AI 生活管家 — Codex 工作契約

## 來源優先序

1. `SPEC.md` 定義產品範圍與不可跨越的邊界。
2. `openspec/changes/` 定義正在進行的變更、契約與驗收方式。
3. `docs/adr/` 記錄架構選擇的理由、替代方案與後果。
4. `pyproject.toml`、`uv.lock`、現有程式與測試決定實際技術與指令。

若文件互相衝突，先指出衝突，不要默默選一份繼續實作。

## 專案邊界

- 後端採 Python 3.12 與 Flask；不要因 AgentKit 範例使用 FastAPI 就引入 FastAPI。
- AI 整合使用 Amazon Bedrock AgentCore Runtime／Gateway 與 Amazon Bedrock 模型；一個 Runtime 承載 Supervisor 與五個邏輯領域 Agent。外部 SDK 行為須查官方文件，不可憑記憶猜測。
- 資料層採 Amazon RDS for PostgreSQL；Amazon Cognito、API Gateway 與 Flask 必須共同落實角色及資源層級授權。
- REST 與 MCP tools 共用 service layer，不得各自複製業務邏輯。
- `data/competition/` 是主辦單位原始資料；清洗或轉換必須寫到新的輸出位置，不可覆寫原檔。
- MVP 會建立真實的內部 Demo 交易，但不直接執行付款、退款或其他不可逆外部交易；外部系統使用明確標示的 mock adapter。

## 工作流程

1. 修改前先搜尋現有模式、規格與 ADR。
2. 新功能、公開契約、資料模型、安全邊界或跨元件變更，先更新 OpenSpec；小型文件或明確局部修正可走快速路徑。
3. 非 trivial 行為與 bug fix 優先先寫測試，再做最小實作。
4. 不安裝套件、不啟用 MCP server、不新增服務，也不更換工具鏈，除非使用者明確同意。
5. 只修改需求直接需要的檔案；保留工作樹中的既有使用者變更。
6. 完成前執行專案已宣告的相關檢查、檢閱 `git diff`，並回報未能執行的驗證。

## AgentKit 精選技能

專案技能位於 `.agents/skills/`，只安裝沒有和目前 Codex 全域技能重複、且可安全套用的三項：

- `adversarial-spec-review`：OpenSpec 已存在、尚未實作前做對抗性規格審查。
- `architecture-decision-records`：記錄重要架構決策、替代方案與後果。
- `systematic-debugging`：遇到 bug、測試失敗或非預期行為時先找根因。

其他常用 Python、測試、安全與驗證技能可在使用者層級提供；不要在 repo 內建立同名副本，避免 Codex skill selector 重複。

技能內容是指導原則，不會凌駕本檔、使用者指令、OpenSpec 或現有專案設定。上游範例若使用其他語言或框架，必須轉譯成目前 Flask／Python／AgentCore／RDS 技術棧後才可採用。

## 完成標準

- 對應 OpenSpec 的驗收條件有可重現證據。
- 輸入在 HTTP／MCP 邊界驗證，錯誤不洩漏秘密或個資。
- REST 與 MCP 對同一用例的狀態轉移一致。
- 測試、型別、lint、OpenSpec 與鎖檔檢查只在工具已宣告時執行，結果如實回報。
- 沒有憑證、本機狀態、生成秘密或無關改動進入 diff。
