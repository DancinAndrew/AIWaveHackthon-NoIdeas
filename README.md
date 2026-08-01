# OpenPoint 生活管家

> 2026 雲湧智生：臺灣生成式 AI 應用黑客松競賽 — 統一資訊命題

把 OpenPoint App 裡「找分類 → 填一長串諮詢單 → 跟好幾家廠商來回問價」的流程，
壓縮成**一段對話**。

```
現在                                       我們的提案
─────────────────────────────────         ─────────────────────────────
會員：冷氣壞了                             會員：我家冷氣不冷了，主臥那台
  ↓ 打開 App，找「服務」分頁                  ↓
  ↓ 在十幾個分類裡找「水電修繕」              管家：主臥那台 2018 年的大金
  ↓ 讀服務說明、注意事項、服務條款                  分離式對嗎？這次是大安區
  ↓ 填諮詢單（症狀、機型、地址、時段…）              還是板橋爸媽家？
  ↓ 送出，等廠商聯絡                        會員：大安區，下午方便
  ↓ 廠商 A 來電問一輪                         ↓
  ↓ 想比價 → 再填一次給廠商 B                管家：找到 3 家。冷研明天就到，
  ↓ 自己比較價格、時間、保固                       2,400–4,280 元，有原廠零件
  ↓ 決定，再打電話約時間                           和一年保固。要約嗎？
```

---

## 目前完成度

| 模組 | 狀態 |
|---|---|
| 雙 Agent 後端（Flask + Bedrock） | **完成，實測通過** |
| React 前端（OpenPoint 介面 + 手機尺寸） | **完成，build 通過** |
| 冷氣維修 workflow 端到端 | **完成**（對話 → 媒合 → 報價 → 建單 → 追蹤） |
| 資料層抽象（memory / DynamoDB / RDS） | 介面完成，目前跑 memory |
| RDS PostgreSQL 部署腳本 | 腳本完成、靜態檢查過，**未實際建立** |
| AWS 部署（S3 + CloudFront + Lambda） | **未做**，`packages/infra` 是空殼 |

---

## 五分鐘跑起來

需要：Node 20+、Python 3.11+、可用的 AWS credentials（Bedrock 權限）

```powershell
# 1. Python 環境
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r packages\api\requirements.txt

# 2. Node 相依
npm install

# 3. 設定（複製 .env.example 成 .env，預設值就能跑）
copy .env.example .env

# 4. Build 前端
npm run build -w @op/frontend

# 5. 啟動（一個程序搞定 App + API）
.venv\Scripts\python.exe packages\api\app.py
```

打開瀏覽器：

| 網址 | 內容 |
|---|---|
| <http://127.0.0.1:3001/> | **React App** — 模擬 OpenPoint 介面，手機尺寸 |
| <http://127.0.0.1:3001/console> | **開發控制台** — 把 agent 內部狀態全部攤開 |

改前端時另開 vite（有 HMR）：`npm run dev -w @op/frontend` → <http://localhost:5173>

---

## 建議的 demo 動線

```
1. 點最上面的搜尋列          ← 原本是關鍵字搜尋，現在是管家入口
2. 「我家冷氣不冷了，主臥那台」
     → 進度條亮起「症狀：不冷」「機型：大金 分離式」
     → 管家反問是大安區還是板橋（沒有亂猜地址）
3. 「台北市大安區復興南路一段100號5樓，下午方便」
     → 約 20 秒，出現 3 張廠商卡，第一張綠框「推薦」
     → 卡上揭露壓縮機的最壞情況
4. 點「就約這家」            → 預約成立
5. 關掉對話，點右下角吉祥物   → 訂單追蹤，時間軸停在「待付訂金」
6. 點底部「會員中心」        → 價格敏感度、管家的觀察筆記
```

第 3 步等 20 秒是正常的：管家和媒合代理各打一次 Bedrock。

---

## 架構

```
┌──────────────────────────────────────────────────────────┐
│  React App   packages/frontend                            │
│  首頁 · 管家對話 · 訂單追蹤 · 會員中心 · 點數 · 付款碼      │
└────────────────────────┬─────────────────────────────────┘
                         │  POST /api/chat
                         ▼
┌──────────────────────────────────────────────────────────┐
│  Flask   packages/api/app.py                              │
│  /  ·  /console  ·  /health  ·  /context  ·  /chat        │
└────────────────────────┬─────────────────────────────────┘
                         ▼
        ┌────────────────────────────────────┐
        │  規則式槽位抽取  extract.py         │  ← LLM 的安全網
        └────────────────┬───────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│  生活管家 Agent   user_agent.py        代表「會員」        │
│                                                          │
│  get_member_context   讀地址/家電/偏好/點數                │
│  update_request       slot filling                       │
│  list_districts       縣市 → 行政區                        │
│  dispatch_matching  ──┐                                  │
│  create_booking       │                                  │
│  remember_preference  │                                  │
└───────────────────────┼──────────────────────────────────┘
                        ▼   match_client.py
              本地 in-process ／ 雲上 Lambda invoke
                        ▼
┌──────────────────────────────────────────────────────────┐
│  廠商媒合 Agent   match_agent.py     代表「平台／廠商端」   │
│                                                          │
│  search_candidates   撈廠商 + 算報價 + 算五維分數           │
│  submit_match        LLM 只能挑順序 + 寫推薦理由            │
└──────────┬────────────────────────────┬──────────────────┘
           ▼                            ▼
   quoting.py                      repo/
   報價／評分規則引擎               memory ／ dynamodb ／（RDS 腳本備好）
```

兩個 Agent 各跑獨立的 Bedrock Converse tool-use loop，模型是 **Claude Haiku 4.5**。

---

## 四個關鍵設計決策

### 1. 錢的事情不交給 LLM

`search_candidates` 回傳的是**已經算好的事實**（報價區間、最快到府日、五維分數）。
`submit_match` 的參數只有 `vendorIds`、`reasons`、`summary` ——
**LLM 在結構上就拿不到修改金額的權力**。

驗證方式：在 `/console` 展開 `submit_match` 的輸入 JSON，看不到任何數字欄位。

### 2. 報價把大額風險拆出來

```
主區間     = 到府檢測費 + 常規項目（冷媒／排水／控制板／風扇馬達）
majorRisks = 壓縮機更換（獨立揭露，不含在主區間）
機齡 ≥ 8 年 = 上限乘 1.15，並在 assumptions 說明原因
```

不這樣做的話「不冷」會同時對應冷媒填充和壓縮機更換，
區間變成 `2,400–21,300 元` — 對會員毫無參考價值。

### 3. 評分權重隨會員價格敏感度浮動

```
價格權重 = 0.2 + sensitivity × 0.3     → 0.2 ~ 0.5
品質權重 = 0.35 - sensitivity × 0.15   → 0.2 ~ 0.35
速度 0.2 · 偏好命中 0.15 · 品牌專精 0.1
```

會員說「預算不要太高」→ `remember_preference` 把 sensitivity 從 0.6 拉到 0.8
→ **下次媒合的排序真的會變**。這是「偏好資產」不只是存起來好看的證明，
在「會員中心」頁面看得到那條進度條移動。

### 4. 規則層當 LLM 的安全網

實測發現模型會「說記下來了但沒真的呼叫 `update_request`」，
那樣服務單是空的、前端進度條全白，看起來像壞掉。

所以呼叫 LLM 之前先跑一輪規則抽取（trace 裡的 `rule_prefill`）：

| 抽什麼 | 依據 |
|---|---|
| 症狀 | 用 `SYMPTOM_TO_ITEMS` 的 key 當字典，與報價引擎永遠同步 |
| 品牌／機型／機齡 | 「主臥那台」對應會員家電檔，機齡由 `installedYear` 算 |
| 地址 | 完整地址，或「爸媽家」「板橋」這種既有地址的特徵詞 |
| 時段 | 上午／下午／都可以 |

**會員有多個地址而訊息沒指明時刻意不猜**，讓管家去問。派錯地址的代價太高。

---

## 與命題資料集的對應

不是自己編一套 schema，而是對齊統一資訊給的表：

| 我們的欄位 | 命題資料集 |
|---|---|
| `inbrAccountId` | `mms_order_record.inbr_account_id` |
| `countyCode`(2碼) / `districtCode`(3碼) | `sys_county` / `sys_district` |
| `serviceVendorId` = 11 | `cms_homepage_service_vendor`（修繕服務） |
| `Booking.orderStatus` = `'11'` | `mms_order_record.order_status`（待訂金支付） |
| `Booking.orderType` = `'01'` | 服務訂單 |
| `preferredContactTime` `'1'/'2'/'3'` | `pms_form_feedback.preferred_contact_time` |
| `ServiceRequest.slots` | 概念上取代 `pms_form_feedback.feedback_content` 的 answerList |

**提案的核心論點就在最後一列**：原本會員要填 `pms_form_topic` 定義的一長串題目，
我們用對話取代表單，產出等價的結構化資料。

縣市與行政區不是手打的 —— `scripts/gen_geo.py` 直接從命題資料集的
`縣市區域範例資料.json` 產生（22 縣市、200 行政區）。

---

## 專案結構

```
packages/
├── api/                      後端（Python Flask）★ 主要實作
│   ├── app.py                Flask 路由 + serve React build
│   ├── lambda_handler.py     Lambda 入口（apig-wsgi）
│   ├── op_agent/
│   │   ├── user_agent.py     生活管家（6 工具）
│   │   ├── match_agent.py    廠商媒合代理（2 工具）
│   │   ├── match_client.py   in-process ↔ Lambda invoke 切換
│   │   ├── bedrock.py        Converse tool-use loop
│   │   ├── quoting.py        報價／評分規則引擎
│   │   ├── extract.py        規則式槽位抽取（LLM 安全網）
│   │   ├── domain.py         型別定義（TypedDict）
│   │   ├── geo.py            地址 → county/district code
│   │   ├── seed.py           6 家廠商 + demo 會員
│   │   ├── rds.py            RDS 連線設定
│   │   └── repo/             base / memory / dynamo
│   ├── sql/schema.sql        商家與客戶的 PostgreSQL DDL
│   ├── static/index.html     開發控制台（零依賴）
│   └── scripts/              驗證與 RDS 部署腳本
│
├── frontend/                 前端（React + Vite + TS）
│   └── src/
│       ├── App.tsx           狀態管理與畫面切換
│       ├── api.ts            後端 client
│       ├── theme.css          OpenPoint 設計 token + 手機外框
│       └── components/
│           ├── PhoneFrame    手機外框 + 狀態列
│           ├── HomeScreen    首頁（搜尋列改成管家入口）
│           ├── AgentSheet    管家對話
│           ├── ProposalCard  廠商方案卡
│           ├── OrderScreen   訂單追蹤（狀態時間軸）
│           ├── MemberScreen  會員中心（管家記住的事）
│           └── SimpleScreens 點數兌換 / 付款碼
│
├── infra/                    CDK（尚未實作）
└── backend/                  ⚠ 早期 TypeScript 版，已被 api/ 取代
                               不在 npm workspaces 內，IDE 會顯示紅線
```

---

## 驗證

```powershell
# 後端 HTTP 層：路由 / CORS / 錯誤處理 / 一次真實對話（20 項檢查）
.venv\Scripts\python.exe packages\api\scripts\test_http.py

# 端到端 4 輪對話：slot filling → 媒合 → 報價 → 建單 → 偏好累積
.venv\Scripts\python.exe packages\api\scripts\smoke.py

# 前端 typecheck + build
npm run build -w @op/frontend

# 前端相依健檢（esbuild binary 是否真的下載了）
node scripts\check_frontend_deps.mjs

# 疑難排解：列出 Flask 路由、靜態檔位置、port 佔用狀況
.venv\Scripts\python.exe packages\api\scripts\diagnose.py
```

---

## 環境變數

| 變數 | 預設 | 說明 |
|---|---|---|
| `AWS_REGION` | `us-west-2` | |
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | 這個 workshop 帳號實測可用；Sonnet 4/4.5 被 deny |
| `REPO_DRIVER` | `memory` | `memory` 免 AWS 資源；`dynamodb` 走真實資料表 |
| `TABLE_NAME` | `op-life-agent` | DynamoDB 表名 |
| `MATCH_FUNCTION_NAME` | 空 | 空 = 媒合代理 in-process；有值 = 走 Lambda invoke |
| `PORT` | `3001` | |
| `PG*` | 空 | RDS 連線資訊，由 `scripts/rds_create.py` 自動寫入 |

`REPO_DRIVER=memory` 意味著**重啟後端資料就消失**。demo 前注意這點。

---

## 已知限制

**這幾條是刻意的取捨，不是疏漏。**

| 項目 | 現況 | 正式環境該怎麼做 |
|---|---|---|
| **身分驗證** | `/chat` 沒有驗證，會員身分靠 request body 的 `inbrAccountId` 指定 —— 任何人都能讀取任意會員的地址電話 | 驗證 OpenPoint SSO token，由 token 解出會員身分 |
| **PII** | 姓名／電話／地址明文儲存 | 依 `pms_form_feedback` 做法改 aes256-gcm 加密 + hash 索引（`schema.sql` 已預留 `*_hash` 欄位） |
| **資料持久性** | memory driver，重啟即失 | 切 `REPO_DRIVER=dynamodb` 或接 RDS |
| **吉祥物圖示** | `MascotIcon` 是依 OPEN 小將視覺特徵重繪的近似 SVG | 向統一集團取得官方素材替換 |
| **點數／付款碼頁** | 純視覺佔位，未接金流 | — |
| **CORS** | 開放所有來源 | 收斂成 OpenPoint 網域白名單 |

---

## 下一步可以做的

1. **AWS 部署** — S3 + CloudFront 放前端、Lambda（python3.13 + apig-wsgi）+ API Gateway 放後端、DynamoDB 存資料。`packages/infra` 待實作。
2. **RDS PostgreSQL** — 腳本已備好（`scripts/rds_create.py` → `rds_load.py` → `rds_query.py`），但要注意 Lambda 連 RDS 需要 VPC + NAT Gateway（每月約 32 鎂），這是最容易吃掉時間的地方。
3. **擴充服務類別** — 目前只做冷氣維修，`ServiceCategory` 已預留清潔／水電。
4. **主動推播** — `mms_member_preference` 的資料已經在累積，可以做「上次冷氣修好三個月了，要不要順便清洗」這種主動提醒。
5. **移除 `packages/backend`** — 早期 TS 版，已被 Python 版完全取代，留著只會讓 IDE 一直顯示紅線。

---

## 資料來源

命題資料集由統一資訊提供，位於
`(統一資訊) 命題數據集 - 2026 雲湧智生：臺灣生成式 AI 應用黑客松競賽/`：

| 檔案 | 用途 |
|---|---|
| `縣市區域範例資料.json` | 產生 `geo_generated.py`（22 縣市 200 行政區） |
| `諮詢單相關table.sql` | 服務單欄位設計參考、PII 加密做法 |
| `mms_order_record.sql` | 訂單狀態機（`orderStatus` 流程） |
| `相關主檔設定.json` | 服務商 ID（11 = 修繕服務） |
