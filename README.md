# AI 生活管家

AI 生活管家是「2026 雲湧智生：臺灣生成式 AI 應用黑客松」參賽專案。使用者可以用自然語言描述生活需求，由 AgentCore Runtime 內的 Supervisor 路由至五個領域 Agent，透過多輪對話產生需求文件並自動委派商家；Step Functions 等待廠商承接、補問或拒絕，必要時恢復原 Agent 向住戶補件，最後把結論與進度顯示在原對話及提醒頁。

> [!IMPORTANT]
> `main` 分支目前仍在 MVP 基礎建設階段。`backend/app.py` 只有 Flask／AWS Lambda 連線骨架與測試端點，尚未實作完整的需求理解、建案與媒合流程。

## MVP 服務範圍

- 餐廳訂位
- 商品購買
- 家事服務
- 水電修繕
- 社區服務諮詢

MVP 聚焦在「理解需求 → 補齊欄位 → 產生文件 → 使用者確認 → 建立交易 → 自動委派商家 → 等待廠商 → 接受／拒絕／補件 → 恢復 Agent → 最終結論」。交易、訊息與進度真的寫入 RDS；付款、餐廳、供應商與派工平台使用 mock adapter，不執行不可逆外部交易。

## 技術方向

| 層級 | 技術／原則 |
|---|---|
| 前端 | React SPA，部署於 AWS Amplify Hosting（待實作） |
| 身分 | Amazon Cognito；預建住戶、廠商、管理員 Demo 帳號 |
| HTTP 後端 | Amazon API Gateway＋Flask on AWS Lambda；已有 Lambda 入口骨架 |
| AI | 一個 Amazon Bedrock AgentCore Runtime；Supervisor＋五個邏輯領域 Agent |
| 長流程 | AWS Step Functions Standard；等待住戶／廠商 callback、改派與恢復 Agent |
| 工具介面 | AgentCore Gateway＋Lambda targets；與 Flask 共用 Python application core |
| 資料庫 | Amazon RDS for PostgreSQL；交易、artifact、三方訊息、workflow task 與進度投影 |
| Region／模型 | `us-west-2`；Nova 2 Lite baseline；Cohere Embed Multilingual v3 |
| 部署 | AWS CDK for Python；private subnets、無 NAT 的 Demo 架構 |
| 規格管理 | OpenSpec；產品總覽見 `SPEC.md` |

一個 Amazon Bedrock Managed Knowledge Base 只保存 FAQ、條款與 SOP 等靜態內容，並以 `service_type` metadata 隔離五類知識；供應商、價格、庫存、時段、交易與狀態等即時資料必須來自 RDS 或受控 mock／合作廠商 adapter。

## 專案結構

```text
.
├── .agents/skills/       # 專案限定的 Codex 工作流
├── .codex/rules/         # Codex 指令防護規則
├── backend/              # Flask 與 AWS Lambda 後端入口
├── data/competition/     # 主辦單位原始資料；不可覆寫
├── data/mock/            # 由資料工具產生的開發用資料
├── docs/                 # 命題、ADR、架構圖與資料說明
├── openspec/             # 變更提案、契約、驗收情境與任務
├── tools/datagen/        # mock data 產生工具
├── .env.example          # 環境變數範本，不含真實憑證
├── .python-version       # 專案 Python 版本
├── pyproject.toml        # Python 專案與唯一直接依賴清單
├── SPEC.md               # 產品現況、範圍與不可跨越的邊界
└── uv.lock               # 可重現的完整依賴鎖檔
```

正式 Python 入口是 `backend/app.py`；根目錄不再保留無功能的 `main.py` 或一次性 Bedrock 測試腳本。

## 架構決策

現行 AWS-only 平台決策記錄在 [`ADR-0003`](docs/adr/0003-adopt-aws-native-agentcore-rds-platform.md)：採用 AgentCore、Flask、RDS、Cognito、Amplify Hosting 與 Managed Knowledge Base。[`ADR-0004`](docs/adr/0004-orchestrate-agent-provider-callbacks-with-step-functions.md) 定義 Step Functions、人工作業 callback、需求文件、三方訊息及進度投影。原 [`ADR-0001`](docs/adr/0001-single-orchestrator-flask-mcp-service-platform.md) 已被取代，只保留歷史脈絡。

正式架構圖位於 [`AWS AgentCore 服務平台架構`](docs/architecture/aws-agentcore-service-platform/)。舊的 [`Flask + AWS + Supabase MVP 架構圖`](docs/architecture/flask-supabase-aws-mvp/) 只保留作為決策歷史，不代表目前架構。

早期的 FastAPI＋Aurora AWS 架構圖已移至 [`docs/archive/`](docs/archive/aws-architecture-fastapi-aurora-draft/)。該資料只供決策追溯，不代表目前要實作的架構。

## 開發環境

需求：

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

建立本機環境：

```bash
cp .env.example .env
uv sync --locked
```

`uv sync` 會建立或更新 `.venv/`；該目錄屬於本機產物，不應提交。請提交 `pyproject.toml` 與 `uv.lock`，確保團隊使用一致的依賴版本。

目前保留的 Python 直接依賴如下：

- `aws-lambda-powertools`：API Gateway／Lambda 事件轉接
- `flask`：HTTP 後端框架
- `boto3`：Amazon Bedrock Runtime 與其他 AWS 服務客戶端
- `pydantic-settings`：環境設定驗證
- `supabase`：舊方案遺留的 Supabase API 客戶端；依 active OpenSpec 待移除，不是正式部署目標

`pyproject.toml` 與 `uv.lock` 是唯一依賴來源；不要另外手動維護 `requirements.txt`。若部署工具未來要求該格式，應由鎖檔在部署流程中產生。

## 啟動目前的後端骨架

```bash
uv run --locked python backend/app.py
```

預設監聽 `http://127.0.0.1:5000`，目前只有 `GET /api/test`。AWS Lambda handler 為 `backend.app.lambda_handler`；完整 `/health`、REST API 與 MCP tools 仍以 OpenSpec tasks 為準。

## 環境變數

先複製 `.env.example`，再填入本機使用的 AWS 認證。不要提交 `.env` 或把憑證寫進 Python 腳本。

| 變數 | 用途 |
|---|---|
| `AWS_ACCESS_KEY_ID` | AWS SigV4 access key |
| `AWS_SECRET_ACCESS_KEY` | AWS SigV4 secret key |
| `AWS_SESSION_TOKEN` | SSO／STS 暫時憑證使用；非必要時可留空 |
| `AWS_DEFAULT_REGION` | AWS SDK 預設區域 |
| `AWS_REGION` | 應用程式使用的 AWS 區域 |
| `AWS_BEARER_TOKEN_BEDROCK` | Bedrock bearer token；只有採用此驗證方式時才需要 |

正式實作若新增 RDS、Cognito、AgentCore 或其他服務設定，必須同步更新 `.env.example`，但範例值只能使用空字串或明確的 placeholder。

## 規格流程

`SPEC.md` 和 `openspec/` 同時存在是刻意的分層，不是兩份互相競爭的規格：

| 位置 | 回答的問題 | 內容粒度 |
|---|---|---|
| [`SPEC.md`](SPEC.md) | 這個產品現在是什麼、做與不做什麼？ | 穩定的產品目標、MVP 範圍、架構邊界與跨變更原則 |
| [`openspec/changes/`](openspec/changes/) | 這次要改什麼、如何證明完成？ | proposal、design、requirements、scenarios、JSON contracts 與 tasks |
| [`docs/adr/`](docs/adr/) | 為什麼選這個方案？ | 替代方案、決策理由、後果與風險 |

維護原則：產品邊界改變時先更新 `SPEC.md`；功能或契約改變時建立／更新 OpenSpec change；架構選擇改變時新增 ADR。詳細欄位、錯誤碼與驗收情境只放 OpenSpec，`SPEC.md` 保留摘要與連結，避免兩邊各維護一份細節。

目前流程：

1. 先確認 `SPEC.md` 的產品邊界。
2. 在 `openspec/changes/` 建立或更新變更提案、設計、契約與任務。
3. 驗證目前的 OpenSpec change：

   ```bash
   openspec validate define-flask-mcp-service-intake --strict --no-interactive
   ```

4. 依任務建立測試，再實作最小可驗收功能。
5. 當依賴變更時更新鎖檔，並確認設定一致：

   ```bash
   uv lock --check
   ```

## Codex／AgentKit 工作流

本 repo 採用 [DancinAndrew/agentkit](https://github.com/DancinAndrew/agentkit) 的 Codex-native 精選安裝，不直接執行上游偏 Claude／FastAPI 的完整安裝器。專案契約見 [`AGENTS.md`](AGENTS.md)，精選範圍、排除項目與更新方式見 [`docs/agentkit/PORTING.md`](docs/agentkit/PORTING.md)，決策理由見 [`ADR-0002`](docs/adr/0002-selective-codex-native-agentkit.md)。

新開的 Codex task 會從 `.agents/skills/` 發現這些 repo skills。它們不會安裝套件、啟用 MCP server 或改變現有 OpenSpec；需要新增依賴或外部服務時仍須先取得同意。

## 原始競賽資料

主辦命題見 [`docs/（統一資訊）命題文件`](<docs/(統一資訊) 命題文件 - 2026 雲湧智生：臺灣生成式 AI 應用黑客松競賽.pdf>)；配套 SQL、CSV、JSON 與資料說明集中放在 [`data/competition/`](data/competition/)。這些檔案視為原始輸入，不可覆寫；清洗或轉換結果放在 `data/mock/` 或後續定義的輸出目錄。
