# AI 生活管家

AI 生活管家是「2026 雲湧智生：臺灣生成式 AI 應用黑客松」參賽專案。使用者可以用自然語言描述生活需求，由 AgentCore Runtime 內的 Supervisor 路由至五個領域 Agent，透過多輪對話產生需求文件並自動委派商家；Step Functions 等待廠商承接、補問或拒絕，必要時恢復原 Agent 向住戶補件，最後把結論與進度顯示在原對話及提醒頁。

> [!IMPORTANT]
> `main` 已把「水電修繕 walking skeleton」部署到 AWS staging，並以公開 Amplify URL 完成住戶多輪對話、AgentCore Supervisor 委派、版本化需求文件、自動媒合、廠商補問／接受及住戶進度頁 E2E。線上 API 誠實標示 `orchestrationMode: agentcore-runtime`。
>
> Runtime 內的每輪模型理解、Knowledge Base retrieval 與 Supervisor 模型分類已實作並由契約測試覆蓋，但只以 fake Bedrock／retrieve client 驗證過，**尚未對真實 Bedrock 執行**；每一輪都會誠實回報 `reasoning.mode` 是 `model` 還是 `rule-fallback`。Cognito JWT、Runtime 呼叫 Gateway tool 與 Step Functions callback worker 仍是下一階段，不冒充已完成。

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
| 前端 | React SPA，已部署於 AWS Amplify Hosting |
| 身分 | Cognito User Pool 與三個群組已建立；目前 SPA 仍使用受控 demo actor headers |
| HTTP 後端 | Amazon API Gateway HTTP API v2＋Flask on AWS Lambda；transport contract 已完成 |
| AI | 一個 AgentCore Runtime；Supervisor 關鍵字 fast-path＋fail-closed 模型分類，水電 Agent 以 Nova 2 Lite 強制單一工具做每輪欄位抽取，Knowledge Base 檢索固定 `service_type` filter |
| 安全兜底 | 高風險停手規則同時存在於 Runtime 與 Flask；模型不得清除已觸發的 hazard flag、不得解除 safety hold，也不撰寫安全文案 |
| 長流程 | Step Functions Standard durable boundary 已建立；目前等待／改派由 RDS＋Flask 狀態機執行 |
| 工具介面 | AgentCore Gateway＋Lambda target 已部署；目前 Web 主流程仍由 Flask 呼叫共用 Python core，Runtime 尚未呼叫 Gateway tool |
| 資料庫 | Amazon RDS for PostgreSQL；交易、artifact、三方訊息、workflow task 與進度投影 |
| Region／模型 | `us-west-2`；Nova 2 Lite 白名單；Titan Text Embeddings V2（1024 維） |
| 部署 | AWS CDK for Python；private subnets、無 NAT 的 Demo 架構 |
| 規格管理 | OpenSpec；產品總覽見 `SPEC.md` |

一個 Amazon Bedrock Managed Knowledge Base 只保存 FAQ、條款與 SOP 等靜態內容。目前已同步水電領域 5 份正文與 5 份 metadata sidecar，5/5 成功索引並通過繁體中文 retrieval；其餘四類資料尚未加入。供應商、價格、庫存、時段、交易與狀態等即時資料必須來自 RDS 或受控 mock／合作廠商 adapter。

## 專案結構

```text
.
├── .agents/skills/       # 專案限定的 Codex 工作流
├── .codex/rules/         # Codex 指令防護規則
├── backend/              # 早期 Flask／Lambda 連線骨架（參考）
├── frontend/             # React：智慧助理、我的預約與後台管理
├── packages/api/         # 現行 Flask API、walking skeleton core 與測試
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

現行 Python 入口是 `packages/api/app.py`；`packages/api/op_agent/` 與 `backend/app.py` 保留為合併前參考，不是 React 目前呼叫的 API。

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

Supabase 直接依賴已移除；正式部署只使用 AWS 服務。

`pyproject.toml` 與 `uv.lock` 是唯一依賴來源；不要另外手動維護 `requirements.txt`。若部署工具未來要求該格式，應由鎖檔在部署流程中產生。

## 啟動水電 walking skeleton

先啟動 Flask：

```bash
PORT=8000 .venv/bin/python packages/api/app.py
```

再開另一個 terminal 啟動 React：

```bash
cd frontend
npm run dev -- --host 127.0.0.1
```

打開 `http://127.0.0.1:5173`。從首頁進「智慧助理」輸入水電需求；案件會同步出現在「我的預約」，廠商操作在快捷功能旁新增的「後台管理」。

本機驗證：

```bash
.venv/bin/python -m unittest discover -s packages/api/tests -t packages/api -p "test_*.py"
.venv/bin/python -m unittest discover -s infra/runtime/tests -t . -p "test_*.py"
.venv/bin/python -m unittest discover -s infra/tests -t . -p "test_*.py"
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run lint
```

`infra/runtime/tests` 覆蓋 Runtime 內的模型抽取、知識檢索與 fail-closed 分類；`packages/api/tests` 覆蓋 Flask 的驗證式合併與安全兜底。兩邊都用 fake Bedrock client，所以本機驗證不會產生任何 Bedrock 請求。

## AWS staging

- 前端：<https://staging.d3t5jckbd6yy6y.amplifyapp.com>
- API health：<https://67wcdv3h8b.execute-api.us-west-2.amazonaws.com/api/v1/health>
- Region：`us-west-2`

部署由 `infra/aiwave_stack.py` 與專案本機 CDK 管理。前端使用 Amplify manual deployment；Flask、AgentCore Runtime／Gateway、RDS、Step Functions、Cognito、S3 與 Knowledge Base 由 `AiwaveStaging` stack 管理。公開 E2E 腳本為 `frontend/tests/utility-walkthrough.e2e.mjs`。

這是會產生成本的 hackathon staging，尤其是 RDS 與 interface VPC endpoint。展示結束後，確認不再需要資料，再執行：

```bash
infra/node_modules/.bin/cdk destroy AiwaveStaging
```

`destroy` 會移除 staging 資源，屬不可逆操作；執行前應再次確認 stack 名稱與需要保留的資料。

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

## AWS 部署安全閘門

主辦方的 AWS 帳號限制已實作為 fail-closed 本機檢查。任何 CDK deploy 或 S3 upload 之前，都必須先對 synth 產生的 JSON template 執行：

```bash
.venv/bin/python -m infra.preflight --env-file .env
# 更新憑證並確認離到期至少 15 分鐘後，才執行唯一的唯讀 AWS 檢查：
.venv/bin/python -m infra.preflight --env-file .env --online

.venv/bin/python -m infra.guardrails \
  --template infra/cdk.out/AiwaveStaging.template.json \
  --manifest infra/upload-manifest.json
```

帳號預檢只接受 `us-west-2`、含 session token 且至少還有 15 分鐘效期的暫時憑證；輸出會遮蔽 access key，線上模式只呼叫 STS `GetCallerIdentity`。基礎設施閘門會要求所有 S3 bucket 明確開啟四項 Block Public Access、RDS 明確設為非公開、Security Group 不得對全網開放，並禁止建立 EC2 instance、EMR cluster、SageMaker training job 或引用未核准的 Bedrock 模型。S3 只允許上傳 [`utility_repair`](data/mock/knowledge_base/utility_repair/) 的 10 個合成文件／metadata sidecar；路徑與 SHA-256 皆固定在 [`upload-manifest.json`](infra/upload-manifest.json)，同時掃描常見個資、支付識別碼、二進位及執行檔內容。`data/competition/`、`pii_vault.json`、住戶對話與附件均不在上傳白名單。

這個檢查只驗證本機部署輸入，不會自行呼叫 AWS。所有直接 Bedrock Converse 呼叫另由 [`bedrock_safety.py`](packages/api/bedrock_safety.py) 共用同一個 process gate：請求起始間隔固定至少 1.05 秒、模型只允許 `amazon.nova-2-lite-v1:0`，SDK 自動 retry 關閉；任何明確重試都必須重新進入 gate。正式 AgentCore Runtime 仍須限制為 Demo 所需的單一承載方式，避免多個 process 各自節流後合計超過帳號限制。

## 規格流程

`SPEC.md` 和 `openspec/` 同時存在是刻意的分層，不是兩份互相競爭的規格：

| 位置 | 回答的問題 | 內容粒度 |
|---|---|---|
| [`SPEC.md`](SPEC.md) | 這個產品現在是什麼、做與不做什麼？ | 穩定的產品目標、MVP 範圍、架構邊界與跨變更原則 |
| [`openspec/changes/`](openspec/changes/) | 這次要改什麼、如何證明完成？ | proposal、design、requirements、scenarios、JSON contracts 與 tasks |
| [`docs/adr/`](docs/adr/) | 為什麼選這個方案？ | 替代方案、決策理由、後果與風險 |

維護原則：產品邊界改變時先更新 `SPEC.md`；功能或契約改變時建立／更新 OpenSpec change；架構選擇改變時新增 ADR。詳細欄位、錯誤碼與驗收情境只放 OpenSpec，`SPEC.md` 保留摘要與連結，避免兩邊各維護一份細節。

實務操作流程、如何新增一個服務類別、本機環境已知坑與目前的部署阻礙，見 [`docs/development-workflow.md`](docs/development-workflow.md)。

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
