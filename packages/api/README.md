# 生活管家後端（Flask + Bedrock 雙 Agent）

## 這是什麼

把「在 OpenPoint App 裡找分類 → 填一長串諮詢單 → 跟好幾家廠商來回問價」
壓縮成一段對話。後端由兩個 AI Agent 組成：

```
React 前端
   │  POST /chat
   ▼
Flask (app.py)
   │
   ▼
生活管家 Agent (user_agent.py)          ← 代表「會員」
   │  工具：get_member_context / update_request / list_districts
   │        dispatch_matching / create_booking / remember_preference
   │
   │  dispatch_matching
   ▼
廠商媒合 Agent (match_agent.py)          ← 代表「平台／廠商端」
   │  工具：search_candidates / submit_match
   ▼
報價評分引擎 (quoting.py) + 廠商資料庫 (repo/)
```

**關鍵設計**：報價與評分完全由 `quoting.py` 的規則引擎算，不讓 LLM 決定金額。
LLM 只負責排序微調與用人話解釋。報價是這個提案最不能出錯的地方。

## 本地跑起來

```powershell
# 1. 建 venv（只需一次，從 repo 根目錄執行）
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r packages\api\requirements.txt

# 2. 設定 .env（複製 .env.example）
#    需要有可用的 AWS credentials（aws configure）與 Bedrock 模型權限

# 3. 啟動
.venv\Scripts\python.exe packages\api\app.py
```

啟動後：

| 端點 | 說明 |
|---|---|
| `GET /health` | 確認資料層、模型、區域設定 |
| `GET /context?inbrAccountId=...` | 會員資料 + 歷史單 + 建議話術，前端開場用 |
| `POST /chat` | `{ "sessionId"?, "inbrAccountId"?, "message" }` |

## 驗證

```powershell
# 端到端多輪對話（會真的打 Bedrock，約 40 秒）
.venv\Scripts\python.exe packages\api\scripts\smoke.py

# HTTP 層（路由 / CORS / JSON / 一次真實對話）
.venv\Scripts\python.exe packages\api\scripts\test_http.py
```

## 環境變數

| 變數 | 預設 | 說明 |
|---|---|---|
| `AWS_REGION` | `us-west-2` | |
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | 這個 workshop 帳號實測可用的模型 |
| `REPO_DRIVER` | `memory` | `memory` 免 AWS 資源；`dynamodb` 走真實資料表 |
| `TABLE_NAME` | `op-life-agent` | DynamoDB 表名 |
| `MATCH_FUNCTION_NAME` | 空 | 空 = 媒合 agent in-process 呼叫；有值 = 走 Lambda invoke |
| `PORT` | `3001` | |

## 部署到 Lambda

`lambda_handler.py` 提供兩個 handler：

- `chat_handler` — 用 `apig-wsgi` 把 Flask 包成 API Gateway HTTP API (payload v2) 的 handler
- `match_handler` — 不對外開放，由 `chat_handler` 用 Lambda invoke 呼叫

Runtime 用 **python3.13**（本機是 3.14，但 Lambda 最新支援 3.13，程式碼維持 3.13 相容）。
相依套件都是純 Python，不需要 Docker，可以用
`pip install --target` 搭配 `--platform manylinux2014_x86_64 --only-binary=:all:` 打包。

## 已知限制

- `/chat` 目前**沒有身分驗證**，會員身分靠 request body 的 `inbrAccountId` 指定。
  上線前必須改成驗證 OpenPoint SSO token，由 token 解出會員身分。
- `REPO_DRIVER=memory` 時資料存在程序記憶體，重啟就消失。
- 會員 PII（姓名／電話／地址）目前是明文。統一資訊的 `pms_form_feedback`
  是用 aes256-gcm 加密 + hash 索引，正式接軌時要照做。

## 可視化控制台

啟動後端後打開 <http://127.0.0.1:3001/> 就有一頁開發控制台（`static/index.html`，
零依賴、不需要 npm build）。它把後端每一輪回傳的東西全部攤開：

| 面板 | 看什麼 |
|---|---|
| 對話 | 管家的回覆、每輪耗時、工具呼叫次數 |
| 服務單 | slot filling 進度：症狀／品牌／機齡／地址（含 county+district code）／時段、還缺哪些欄位 |
| 媒合結果 | 廠商卡片：綜合分數、報價區間、到府檢測費、最快到府日、標籤、推薦理由、壓縮機等大額風險 |
| 預約單 | 訂單編號、訂金、預估總額、`orderStatus`（對齊 `mms_order_record`） |
| Agent 動作紀錄 | 這一輪兩個 agent 各呼叫了哪些工具、順序、每個工具的完整輸入輸出 JSON |
| 會員偏好 | 價格敏感度、重視特質、觀察筆記 —— 會隨對話變動，這是推播的基礎 |

這頁的價值在於**看得見 agent 的決策過程**：例如會員說「預算不要太高」時，
「Agent 動作紀錄」會出現 `remember_preference`，而「會員偏好」的價格敏感度
會從 0.6 跳到 0.8，下次媒合的排序權重就跟著變。

## 疑難排解

### 打開 `/` 是 404

幾乎都是**舊的 server 進程還在聽 3001**。因為 `debug=False`（不開 reloader，
免得 MemoryRepo 的資料被熱重載清掉），改了程式碼不會自動生效，必須重啟。

先確認狀況：

```powershell
.venv\Scripts\python.exe packages\api\scripts\diagnose.py
```

它會列出 Flask 實際註冊的路由、`index.html` 的絕對路徑與是否存在、
用 test client 直接請求 `/` 的狀態碼，以及 3001 埠是否已被佔用。
如果 test client 是 200 但瀏覽器 404，就是舊進程的問題。

找出並關掉佔用者：

```powershell
netstat -ano | findstr :3001          # 看 LISTENING 那幾行的 PID
Stop-Process -Id <PID> -Force
```

`TIME_WAIT` 的那幾行可以忽略，那是已關閉連線的殘留，不會擋新的 server。

改完程式碼後的正確流程：**Ctrl+C 停掉 → 重新 `python app.py` → 瀏覽器重新整理**。

## 兩種前端執行方式

### A. 單一程序（demo 用，最省事）

先 build 一次，之後只要開 Flask 一個程序：

```powershell
npm run build -w @op/frontend          # 產出 packages/frontend/dist
.venv\Scripts\python.exe packages\api\app.py
```

| 路徑 | 內容 |
|---|---|
| `http://127.0.0.1:3001/` | React App（OpenPoint 介面） |
| `http://127.0.0.1:3001/console` | 開發控制台（攤開 agent 內部狀態） |

因為同源，沒有 CORS 問題，網路環境再爛也不會出事。**demo 建議用這個。**

### B. 前後端分離（改前端時用）

```powershell
# 終端機 1
.venv\Scripts\python.exe packages\api\app.py
# 終端機 2
npm run dev -w @op/frontend            # http://localhost:5173，有 HMR
```

Vite 會把 `/api/*` proxy 到 3001。

### 為什麼 API 有兩組路徑

每個 API 都註冊了 `/chat` 和 `/api/chat` 兩條：

- 方式 B：vite proxy 把 `/api` 前綴拿掉 → 打到 Flask 的 `/chat`
- 方式 A：同源沒有 proxy → 由 `/api/chat` 別名接住

這樣**同一份前端 build 在兩種情境都能跑**，不用改 base url、不用重新 build。

## 規則式槽位抽取（op_agent/extract.py）

實測發現模型會「說記下來了但沒真的呼叫 `update_request`」，
那樣服務單是空的、前端進度條全白，看起來像壞掉。

所以在呼叫 LLM 之前先跑一輪規則抽取（trace 裡會看到 `rule_prefill`）：

| 抽什麼 | 依據 |
|---|---|
| 症狀 | `SYMPTOM_TO_ITEMS` 的 key 當字典，與報價引擎永遠同步 |
| 品牌／機型／機齡 | 「主臥那台」對應到會員家電檔，機齡由 `installedYear` 算 |
| 地址 | 訊息含完整地址，或含「爸媽家」「板橋」等既有地址的特徵詞 |
| 時段 | 上午／下午／都可以 等關鍵詞 |

**會員有多個地址而訊息沒指明時刻意回 `None`**，讓管家去問。
派錯地址的代價太高，寧可多問一句。
