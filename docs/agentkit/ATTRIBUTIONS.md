# 授權聲明

agentkit vendor 並改編了五個 MIT 授權專案的成果。它們的授權條款已被保留。agentkit 本身為 MIT（見 `LICENSE`，如有添加）。

## ECC — `affaan-m/ECC`
- 授權：MIT（完整文字在 `ECC-LICENSE`）。
- Vendored 的內容：`agents/`、`skills/`、`rules/{common,python}/`、`commands/`、`contexts/`，以及 `mcp-configs/mcp-servers.json` 的精選子集，逐字複製進 `payload/.claude/`。固定的 commit 記錄在 `VERSION`。
- **未** vendor 的內容：所有非 Python 語言包、hook 執行期，以及與後端 / RAG 工作無關的 domain 技能。見 `docs/ARCHITECTURE.md`。

## Andrej Karpathy 指導方針 — `multica-ai/andrej-karpathy-skills`
- 授權：MIT。
- 使用的內容：四條原則（先想再寫、簡單優先、外科手術式修改、目標驅動執行）構成了 `CLAUDE.md` 的第 1 節。

## OpenSpec — `Fission-AI/OpenSpec`（`@fission-ai/openspec`）
- 授權：MIT。
- 使用方式：在部署時透過 npm 安裝，並以 `openspec init` 建立鷹架。未 vendor——OpenSpec 是一個 CLI，應該被安裝而不是被複製。

## grill-me 概念 — Matt Pocock（`mattpocock/skills`）
- 授權：MIT。
- 使用的內容：`grill-me` 技能（`payload/.claude/skills/grill-me/`）是對 Matt Pocock 的 grill-me 技能所普及的「計畫審問」模式的獨立重新實作。沒有複製任何 code——SKILL.md 是原創的，為 agentkit 撰寫。配套的 `quiz-me` 技能是 agentkit 原創（理解測試的對應物）。

## superpowers — `obra/superpowers`、`obra/superpowers-lab`
- 授權：MIT。
- 使用的內容：`systematic-debugging` 技能移植自 `obra/superpowers`，保留其「主檔 + 支援檔」結構（`root-cause-tracing.md`、`defense-in-depth.md`、`condition-based-waiting.md`、可執行的 `find-polluter.sh`），全部改寫為 Python/pytest。`finding-duplicate-functions` 技能移植自 `obra/superpowers-lab`，保留主檔 + `scripts/`（可執行的 `extract_functions.py` + 兩個 prompt 模板），改寫為 Python `ast` 流程。`verification-loop` 技能吸收了 `verification-before-completion` 的 Iron Law + Gate Function + 反合理化表格。所有移植均改寫範例與措辭，並在各 SKILL.md 的 frontmatter 標註來源。

## OpenKB 啟發 — `VectifyAI/OpenKB`
- 授權：Apache-2.0。
- 使用的內容：`skill-trigger-eval` 技能是 agentkit 原創，**沒有複製任何 code**——它受 OpenKB 的「skill description 觸發準確度 eval」概念啟發，SKILL.md 為 agentkit 重新撰寫。

## 觀念啟發 — Loop Engineering SOP 與 Domain-Driven Design
- 三個技能為 agentkit 原創，**沒有複製任何 code**，僅吸收公開觀念：
  - `ubiquitous-language` — 概念源自 Eric Evans《Domain-Driven Design》的 Ubiquitous Language，及 Matt Pocock「Software Fundamentals Matter More Than Ever」演講中把該觀念用於 AI 協作的術語庫實踐。
  - `post-mortem`、`adversarial-spec-review` — 概念源自「AI-Assisted Loop Engineering 開發流程 SOP」的事後檢討與對抗性規格審查階段。
- 這些觀念本身屬於軟體工程通用實踐；agentkit 將其改寫為 Python/FastAPI 取向的 SKILL.md。

---
本專案是獨立整合，與 ECC、Karpathy 指導方針、OpenSpec、grill-me 技能、superpowers 或 OpenKB 的作者沒有關聯或背書。
