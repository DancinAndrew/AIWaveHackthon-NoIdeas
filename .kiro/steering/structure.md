# 專案結構

```text
.
├── packages/api/            # ★ 現行 Python 後端（唯一執行入口）
├── frontend/                # ★ 現行 React SPA（React 呼叫的就是這個）
├── infra/                   # AWS CDK stack、部署閘門、AgentCore Runtime 程式
├── openspec/                # 變更提案、契約、驗收情境、任務
├── docs/                    # 命題文件、ADR、架構圖、資料說明
├── data/competition/        # 主辦單位原始資料（唯讀，不可覆寫）
├── data/mock/               # 由 tools/datagen 產生的開發用資料
├── tools/datagen/           # mock data 產生器
├── backend/app.py           # 舊 Flask／Lambda 骨架（僅參考）
├── packages/backend/        # 舊 TypeScript 參考實作（僅參考）
├── SPEC.md                  # 產品現況、範圍、架構邊界
├── AGENTS.md                # Agent 工作契約
├── pyproject.toml / uv.lock # 唯一 Python 依賴來源
└── cdk.json                 # CDK app 指向 infra.app，output 到 infra/cdk.out
```

## 現行 vs 參考（很重要）

| 路徑 | 狀態 |
|---|---|
| `packages/api/app.py` | ★ 現行 Flask 入口 |
| `packages/api/lambda_handler.py` | ★ Lambda 入口（只吃 API Gateway HTTP API payload v2；無效 event fail closed 回 `400 invalid_lambda_event`） |
| `frontend/` | ★ 現行 React SPA |
| `packages/api/op_agent/` | 合併前的冷氣雙 Agent 原型，**不是**現行 API |
| `backend/app.py` | 早期連線骨架，**不是**現行 API |
| `packages/backend/` | 舊 TypeScript 參考（含 DynamoDB 概念，現行資料層是 RDS PostgreSQL） |
| `docs/architecture/flask-supabase-aws-mvp/`、`docs/archive/` | 決策歷史，不代表現行架構 |
| `docs/adr/0001-*` | 已被 ADR-0003 取代 |

改東西前先確認是不是在改「參考」目錄。現行架構圖在 `docs/architecture/aws-agentcore-service-platform/`。

## packages/api/

```text
app.py                  Flask 入口
lambda_handler.py       API Gateway v2 → Flask 轉接
bedrock_safety.py       GuardedBedrockRuntime：所有 Bedrock Converse 的必經 gate
tool_lambda.py          AgentCore Gateway 的 Lambda target
walking_skeleton/       共用 application core
  ├── api.py            Blueprint／路由
  ├── service.py        業務邏輯（REST 與 MCP 共用）
  ├── orchestration.py  SupervisorOrchestrator 邊界（本機 deterministic ↔ AgentCore 可換）
  ├── store.py          記憶體 store（本機 Demo）
  ├── rds_store.py      RDS PostgreSQL repository
  └── errors.py         錯誤型別與錯誤碼
tests/                  unittest，命名 test_*.py
sql/  scripts/  static/  requirements.txt
```

REST 路由一律掛在 `/api/v1` 之下。本機以 demo header 模擬 actor context：`X-Demo-Role` 搭配 `X-Demo-Resident-Id` / `X-Demo-Provider-Id` / `X-Demo-Admin-Id`；廠商與管理員寫入另需 `Idempotency-Key`。

## frontend/

```text
src/pages/        HomePage（首頁）、ChatPage（智慧助理）、MyBookingsPage（我的預約）、DashboardPage（後台管理）
src/components/   共用元件
src/api/          API client
tests/            *.test.ts（node --test）＋ utility-walkthrough.e2e.mjs
```

每個 page 一支 `.tsx` 配一支同名 `.css`。

## infra/

```text
app.py              CDK app 入口（cdk.json 指向 infra.app）
aiwave_stack.py     AiwaveStaging stack：Flask Lambda、AgentCore Runtime／Gateway、RDS、
                    Step Functions、Cognito、S3、Knowledge Base
preflight.py        帳號／憑證預檢（fail-closed）
guardrails.py       synth 後 template 與上傳清單掃描
upload-manifest.json 允許上傳 S3 的檔案路徑＋SHA-256 白名單
runtime/            AgentCore Runtime 程式（agent_runtime.py）
tests/              test_cdk_stack / test_cdk_entrypoint / test_guardrails / test_preflight
```

## openspec/

```text
config.yaml
changes/define-flask-mcp-service-intake/
  ├── proposal.md  design.md  tasks.md  .openspec.yaml
  ├── specs/       需求與 scenarios（SHALL／MUST）
  └── contracts/   forms/（五類表單 JSON Schema）、mcp/tools.json
```

## data/

```text
competition/        主辦單位原始 SQL／CSV／JSON。唯讀；清洗結果寫到別處
mock/cases/         service_requests、matches、events、provider_replies、conflict_fixtures
mock/cases/pii_vault.json   ⚠ 禁止上傳 AWS、禁止進入 prompt／日誌
mock/geo/           counties.json、districts.json
mock/knowledge/     每類服務一份說明
mock/knowledge_base/<service_type>/   KB 同步用；每份正文配一個 .metadata.json sidecar
                    目前只有 utility_repair 的 10 個檔案在上傳白名單內
mock/eval/          eval.jsonl、holdout_human.jsonl、multi_turn.jsonl
```

## 文件與規格的分工

| 位置 | 回答什麼 | 何時更新 |
|---|---|---|
| `SPEC.md` | 產品現在是什麼、做與不做 | 產品邊界改變時**先**更新 |
| `openspec/changes/` | 這次要改什麼、如何證明完成 | 功能、公開契約、資料模型、安全邊界改變時 |
| `docs/adr/NNNN-*.md` | 為什麼選這個方案 | 架構選擇改變時新增（遞增四位數編號） |

細節（欄位、錯誤碼、驗收情境）只放 OpenSpec，`SPEC.md` 只留摘要與連結。

## 來源優先序（衝突時）

1. `SPEC.md`
2. `openspec/changes/`
3. `docs/adr/`
4. `pyproject.toml`、`uv.lock`、現有程式與測試

文件互相衝突時**先指出衝突**，不要默默挑一份繼續實作。

## 其他慣例

- `.agents/skills/`：專案限定 skill（`adversarial-spec-review`、`architecture-decision-records`、`systematic-debugging`）。
- `.codex/rules/agentkit.rules`：禁用的破壞性指令。
- `.venv/`、`node_modules/`、`infra/cdk.out/`、`.env` 都是本機產物，不提交。
- 只改需求直接需要的檔案，保留工作樹中既有的使用者變更。
