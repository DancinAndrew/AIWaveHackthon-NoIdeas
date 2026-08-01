# 水電修繕 walking skeleton API

`packages/api/app.py` 是目前 Flask 執行入口。它提供同一條可在本機與 AWS Lambda 執行的 `/api/v1` 契約；先前的冷氣雙 Agent 原型保留在 `op_agent/` 作為參考，但不再是前端執行入口。

## 本機啟動

使用已核准並完成同步的 Python 環境：

```bash
PORT=8000 .venv/bin/python packages/api/app.py
```

健康檢查：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

目前 local adapter 明確回傳 `orchestrationMode: deterministic-demo`。它不會假裝已呼叫 AgentCore；正式 staging 會在相同 `SupervisorOrchestrator` 邊界換成 AgentCore Supervisor → `utility_repair_agent`。

## Demo actor context

本機 walking skeleton 用 header 模擬日後由 Cognito/API Gateway 驗證後產生的 actor context：

| 角色 | 必填 header |
|---|---|
| 住戶 | `X-Demo-Role: RESIDENT`、`X-Demo-Resident-Id` |
| 廠商 | `X-Demo-Role: PROVIDER`、`X-Demo-Provider-Id` |
| 管理員 | `X-Demo-Role: ADMIN`、`X-Demo-Admin-Id` |

廠商與管理員寫入另需 `Idempotency-Key`。Actor 一律取自受信任 header，request body 內的 `residentId`／`providerId` 不具授權效果。

## REST 路由

- `POST /api/v1/conversations`
- `POST /api/v1/conversations/{conversation_id}/messages`
- `GET /api/v1/conversations/{conversation_id}/messages`
- `GET /api/v1/service-requests`
- `GET /api/v1/service-requests/{service_request_id}/progress`
- `GET /api/v1/reminders`
- `GET /api/v1/provider-service-requests`
- `POST /api/v1/provider-service-requests/{task_id}/responses`
- `POST /api/v1/admin/workflow-tasks/{task_id}/simulate-timeout`

## 驗證

```bash
.venv/bin/python -m unittest packages/api/tests/test_utility_walking_skeleton.py
.venv/bin/python -m compileall -q packages/api/walking_skeleton packages/api/app.py
openspec validate define-flask-mcp-service-intake --strict
uv lock --check
```

測試涵蓋 Supervisor 委派、多輪補欄位、需求文件、住戶確認、廠商補問、住戶補件、廠商接受、高風險暫停、跨廠商授權、冪等、拒絕改派與管理員模擬逾時。

## AWS 帳號資料限制

不得把 `data/mock/cases/pii_vault.json`、競賽原始資料、對話中的聯絡資料／詳細地址或任何禁止類別資料上傳 AWS。部署 gate 只允許通過掃描的合成 KB／mock 子集；S3 必須四項 Block Public Access，RDS 必須為 private 且不可公開。
