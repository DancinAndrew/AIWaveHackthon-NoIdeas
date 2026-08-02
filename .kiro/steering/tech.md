# 技術棧與常用指令

## 技術棧

| 層級 | 技術 |
|---|---|
| 語言／版本 | Python 3.12（`.python-version`）；TypeScript 6 |
| 套件管理 | **uv**（Python，唯一來源 `pyproject.toml` + `uv.lock`）；npm（`frontend/`、`infra/`） |
| 前端 | React 19＋React Router 7＋Vite 8，部署於 AWS Amplify Hosting；lint 用 **oxlint** |
| HTTP 後端 | **Flask 3** on AWS Lambda，經 API Gateway HTTP API **v2** |
| AI | Amazon Bedrock AgentCore Runtime／Gateway（`bedrock-agentcore`）＋`boto3` Bedrock Runtime |
| 長流程 | AWS Step Functions Standard |
| 資料庫 | Amazon RDS for PostgreSQL（`psycopg[binary]`） |
| 身分 | Amazon Cognito User Pool（群組 `RESIDENT` / `PROVIDER` / `ADMIN`） |
| IaC | AWS CDK for Python（`aws-cdk-lib`、`constructs`），CLI 由 `infra/node_modules` 提供 |
| 測試 | Python `unittest`（無 pytest）；前端 `node --test` |
| 規格 | OpenSpec（`openspec/`）＋ ADR（`docs/adr/`） |

Python 直接依賴只有 `pyproject.toml` 裡那幾個（`aws-cdk-lib`、`aws-lambda-powertools`、`bedrock-agentcore`、`boto3`、`constructs`、`flask`、`flask-cors`、`pydantic-settings`）。不要新增依賴、不要手寫根目錄 `requirements.txt`、不要引入 FastAPI（AgentKit 範例用 FastAPI，本專案不用）。`packages/api/requirements.txt` 與 `infra/runtime/requirements.txt` 是 Lambda／Runtime 打包用的釘版清單，不是開發環境來源。

## 部署常數

- Region 固定 `us-west-2`。
- 生成模型只允許 `amazon.nova-2-lite-v1:0`。
- 所有直接 Bedrock Converse 呼叫必須走 `packages/api/bedrock_safety.py` 的 `GuardedBedrockRuntime`：請求起始間隔 ≥ 1.05 秒（<1 RPS）、SDK 自動 retry 關閉、任何重試需重新進入 gate。
- Knowledge Base embedding：`README.md` 與 `ADR-0005` 記載 Titan Text Embeddings V2（1024 維）＋S3 Vectors；`SPEC.md` §3 仍寫 `cohere.embed-multilingual-v3`。這兩處衝突，動到 KB 前先請使用者確認，不要自己選一個。

## 環境建置

```bash
cp .env.example .env      # 填本機 AWS 憑證；絕不提交 .env
uv sync --locked          # 建立／更新 .venv/
```

## 常用指令

專案文件裡的指令都寫成 POSIX 的 `.venv/bin/python`。**本機是 Windows／PowerShell，實際路徑是 `.venv\Scripts\python.exe`**；`cdk.json` 的 `"app": ".venv/bin/python -m infra.app"` 在 Windows 上直接跑 cdk 會失敗，需要改用 `--app` 覆寫或在 POSIX 環境執行。以下沿用文件原文，執行時自行換算。

啟動（開兩個 terminal，**不要**由 agent 常駐執行）：

```bash
PORT=8000 .venv/bin/python packages/api/app.py     # Flask，健康檢查 /api/v1/health
cd frontend && npm run dev -- --host 127.0.0.1     # http://127.0.0.1:5173
```

測試與檢查（`discover` 必須加 `-t .`，否則 `infra.*` / `packages.api.*` 匯入會失敗）：

```bash
.venv/bin/python -m unittest discover -s packages/api/tests -t .   # 31 tests
.venv/bin/python -m unittest discover -s infra/tests -t .          # 24 tests
.venv/bin/python -m compileall -q packages/api/walking_skeleton packages/api/app.py
npm --prefix frontend test
npm --prefix frontend run build      # tsc -b && vite build
npm --prefix frontend run lint       # oxlint
openspec validate define-flask-mcp-service-intake --strict --no-interactive
uv lock --check
```

文件常引用的單檔寫法同樣有效，例如 `.venv/bin/python -m unittest packages/api/tests/test_utility_walking_skeleton.py`（10 tests）。

E2E（需先起服務）：`frontend/tests/utility-walkthrough.e2e.mjs`

### 本機環境現況（2026-08 實測，動手前先確認）

- `.venv/` 目前是 **Python 3.14.6**、由 stdlib `venv` 建立，不是 `uv sync` 建立的 3.12 環境，且**未安裝 `aws-cdk-lib`**。
- 因此 `infra/tests` 的 `test_cdk_stack`、`test_cdk_entrypoint` 會 `ModuleNotFoundError: No module named 'aws_cdk'`，任何 CDK synth／deploy 也跑不起來。
- `packages/api/tests` 31 項可通過。
- `infra/tests/test_guardrails.py` 有 2 項失敗：`guardrails.py` 比對上傳白名單時混用 `data/mock/...`（正斜線）與 `data\mock\...`（Windows 反斜線），檔案實際存在卻被判為「未核准／缺少」。這是既有的路徑分隔符問題，不是你造成的。
- 需要完整 Python 環境時先跑 `uv sync --locked`（會依 `.python-version` 使用 3.12）。

## 部署安全閘門（fail-closed，必做）

任何 `cdk deploy` 或 S3 upload **之前**：

```bash
.venv/bin/python -m infra.preflight --env-file .env
.venv/bin/python -m infra.preflight --env-file .env --online   # 唯一唯讀檢查：STS GetCallerIdentity
.venv/bin/python -m infra.guardrails \
  --template infra/cdk.out/AiwaveStaging.template.json \
  --manifest infra/upload-manifest.json
```

- preflight 只接受 `us-west-2`、含 session token 且剩餘效期 ≥ 15 分鐘的暫時憑證。
- guardrails 強制：S3 四項 Block Public Access、RDS 非公開、Security Group 不對全網開放；禁止 EC2 instance、EMR cluster、SageMaker training job 與未核准 Bedrock 模型。
- S3 只允許上傳 `data/mock/knowledge_base/utility_repair/` 的 10 個檔案，路徑與 SHA-256 釘在 `infra/upload-manifest.json`。
- `data/competition/`、`data/mock/cases/pii_vault.json`、住戶對話與附件**永不**上傳 AWS。

CDK：`infra/node_modules/.bin/cdk synth|deploy AiwaveStaging`。`cdk destroy AiwaveStaging` 不可逆且會刪 RDS — 只在使用者明確要求時執行。這是會計費的 staging（RDS 與 interface VPC endpoint 尤其貴）。

## 程式撰寫規則

- Flask 分層：application factory → Blueprint → service → repository。REST 與 MCP tools **共用同一 service layer**，不得各自複製業務邏輯。
- 工具不得讓模型執行任意 SQL。
- 輸入在 HTTP／MCP 邊界以白名單 Schema 驗證；錯誤訊息不洩漏秘密或個資。
- 寫入前需明確確認；廠商／管理員寫入需 `Idempotency-Key`，同 key 重試不得重複建案。
- Actor 只取自受信任 header／JWT；request body 裡的 `residentId`／`providerId` 無授權效力。
- Cognito 只給粗粒度群組；每次讀寫都要在 Flask 檢查 owner、廠商 membership 與合法狀態轉移。
- Step Functions callback token 只在 server-side 加密保存，不得進入瀏覽器、prompt、MCP arguments 或一般日誌。
- prompt、Knowledge Base、trace 與日誌不得含完整姓名、電話、Email、地址或附件內容；聯絡資料與詳細地址加密儲存，比對用欄位另存不可逆雜湊。
- 非 trivial 行為與 bug fix 先寫測試再做最小實作。
- 禁止：`rm -rf`、`git reset --hard`、`git push --force`、`git clean -f`（見 `.codex/rules/agentkit.rules`）。
