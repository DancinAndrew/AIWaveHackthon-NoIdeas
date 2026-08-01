# AgentKit 精選安裝說明

本專案從 [DancinAndrew/agentkit](https://github.com/DancinAndrew/agentkit) `0.1.0` 的 `main` commit `f02fe81cb5b8930fbf337a79baa7b7d96c926cfc` 精選可重用內容，安裝日期為 2026-08-01。

## 安裝內容

上游 `.claude/skills/` 中三個不和目前 Codex 全域技能重複、且適合此專案的 skills，已移植到 `.agents/skills/`：

- `adversarial-spec-review`
- `architecture-decision-records`
- `systematic-debugging`（保留三份方法文件；排除 `find-polluter.sh`）

另加入 `.codex/rules/agentkit.rules`，將上游 permissions 的破壞性操作意圖轉成 Codex exec policy。

## Codex 相容調整

- 移除 Codex skill frontmatter 不支援的 `origin` 與 `tools` 欄位。
- 將已安裝 skills 的 Claude Code 專用詞彙改為 Codex，並將 FastAPI 邊界範例改成 Flask。
- 上游範例可能同時包含 TypeScript、FastAPI 或其他框架；套用時以 `AGENTS.md` 的 Flask／Python 邊界為準。

## 刻意不安裝

- `install.sh`、`CLAUDE.md`、Claude plugin、commands、contexts、settings 與 Claude agents：不是 Codex 原生介面。
- `fastapi-patterns` 與 FastAPI rules：本專案已決定使用 Flask。
- `mcp-server-patterns`：上游版本綁定 Node／TypeScript SDK，不適合本專案的 Python 邊界；實作時應查官方 MCP Python 文件。
- `api-design`、`python-patterns`、`python-testing`、`search-first`、`security-review`、`tdd-workflow`、`verification-loop` 等：目前使用者層級已存在；Codex 不會合併同名 skill，repo 再安裝只會造成重複。
- `eval-harness`：包含 Claude 專用路徑與指令，沒有可直接採用的 Codex 介面。
- `postgres-patterns`：含不適合直接套用到受管 Supabase 的通用管理建議。
- `deployment-patterns`、`cost-aware-llm-pipeline` 等：範例與目前 AWS／Bedrock 路線不一致，等具體實作需求成立後再評估。
- MCP server 設定：不在未審查、未取得同意時啟用外部工具。
- OpenSpec 與 sysdoc 鷹架：本 repo 已有 `openspec/`、`SPEC.md`、`docs/architecture/` 與 `docs/adr/`，重建會產生兩套來源。
- CI、pre-commit、statusline 與 hooks：會改變整個 repo 或本機行為，需另行決策。
- 其餘通用或 RAG／MLOps skills：目前需求沒有直接證據，避免技能清單膨脹。

## 更新方式

更新前先比對上游 commit 與本檔列出的本地調整，不可直接重跑 `install.sh` 或覆寫 `.agents/skills/`。更新後至少執行 skill frontmatter 驗證、legacy path 掃描、exec-policy 測試、OpenSpec strict validation 與 `git diff` review。

授權與上游來源見 [ATTRIBUTIONS.md](ATTRIBUTIONS.md)、[ECC-LICENSE](ECC-LICENSE) 與 [UPSTREAM_VERSION](UPSTREAM_VERSION)。下載的上游 commit 沒有根目錄 `LICENSE`；GitHub metadata 標示 MIT，而 `ATTRIBUTIONS.md` 也宣稱 AgentKit 為 MIT，但原始授權檔並不完整。若要對外散布或大規模 vendor 更多 AgentKit 原創內容，應先向上游確認授權檔。
