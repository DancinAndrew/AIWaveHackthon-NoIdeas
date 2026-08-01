# ADR-0002：精選安裝 Codex-native AgentKit

**日期：** 2026-08-01

**狀態：** Accepted

## Context

當時專案已有 OpenSpec、ADR、Flask、Bedrock、Supabase 與 AWS 架構文件，但缺少可隨 repo 分享的 AI 開發工作流。上游 AgentKit 提供 Python／後端導向的 skills；其安裝器同時會部署 Claude Code 設定、FastAPI 規則、OpenSpec、sysdoc 與可選 CI，直接執行會和專案重疊或產生錯誤技術提示。Supabase 架構其後已由 ADR-0003 取代。

## Decision

不執行上游 `install.sh`。從固定上游 commit 精選三個不和使用者層級重複、且適合本專案的 skills，移植到 `.agents/skills/`，並以 `AGENTS.md` 與 `.codex/rules/agentkit.rules` 補上專案邊界及破壞性操作防護。保留既有 `SPEC.md`、OpenSpec、ADR 與架構文件作為唯一來源。

## Alternatives Considered

### 完整執行上游安裝器

- 優點：最接近上游預設，內容完整。
- 缺點：加入 Claude 專用介面、FastAPI 規則與重複文件，也可能透過 npm 安裝或更新 OpenSpec。
- 未採用原因：與 Codex、Flask 與「不未經同意改變依賴」的專案邊界衝突。

### 只依賴使用者全域 skills

- 優點：repo 幾乎沒有新增檔案。
- 缺點：其他協作者或新環境無法重現同一工作流，專案限制也不會隨版本控制保存。
- 未採用原因：黑客松 repo 需要可分享、可審查的專案級基線。

### Vendor 全部 AgentKit skills

- 優點：未來需求變動時不必再次加入 skill。
- 缺點：大量無關項目會增加發現噪音，並帶入 FastAPI、Node MCP 與 RAG／MLOps 假設。
- 未採用原因：違反最小、針對性安裝原則。

## Consequences

### Positive

- 對抗性規格審查、ADR 與系統化除錯流程可隨 repo 分享。
- Codex 讀到的專案限制可隨架構 ADR 演進；現行 AWS-only 架構以 ADR-0003 與 ADR-0004 為準。
- 不新增套件、不啟用外部服務，也不重建既有規格系統。

### Negative

- 上游更新不能直接覆蓋，需重新比對本地調整。
- 精選 skills 仍含跨語言範例，使用時必須依 `AGENTS.md` 轉譯成目前技術棧。

### Risks

- 上游文件可能漂移；以固定 commit、來源說明與驗證清單降低更新風險。
- Codex 介面規格可能變動；更新 Codex 後需重新驗證 skill frontmatter 與 exec policy。
