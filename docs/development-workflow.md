# 開發流程實務指南

這份文件是**動手做的流程**：怎麼開一個新服務類別、每一關要跑什麼指令、哪些坑已經踩過。

規格分層（`SPEC.md` / `openspec/` / `docs/adr/` 各自回答什麼）已寫在 [README 的「規格流程」](../README.md#規格流程)，這裡不重複，只補實務細節。行為契約以 [`AGENTS.md`](../AGENTS.md) 為準；本文若與它衝突，以 `AGENTS.md` 為準。

---

## 1. 本機環境

### 起服務

```bash
# 後端（terminal 1）
cd packages/api
STORE_BACKEND=memory PORT=8000 ../../venv/bin/python app.py

# 前端（terminal 2）
npm --prefix frontend run dev -- --host 127.0.0.1
```

開 <http://127.0.0.1:5173>。

### 三個已知坑

**Port 5000 不能用。** macOS Monterey 之後 AirPlay Receiver 佔住 5000，會回 `403 Forbidden` 而且 Server header 是 `AirTunes`。一律用 8000。

**`STORE_BACKEND=memory` 重啟就清空。** demo 前不要重啟後端，否則進行中的對話會消失。改後端程式碼必須重啟才生效（Flask 沒開 reload）。

**後端重啟後前端要重新整理。** 前端把 conversation ID 存在 `localStorage`，後端重啟後那個 ID 不存在。`ChatPage` 已經會在收到 404／403 時自動清掉並開新對話，但**其他錯誤**才顯示「連不上後端」。如果看到連線錯誤橫幅，先確認 8000 真的有服務在跑。

**`venv/` 與 `.venv/` 不一致。** README 寫 `.venv/bin/python`，但目前 repo 裡是 `venv/`。兩者都能跑測試，指令請按你機器上實際存在的那個調整。

---

## 2. 每一關要跑的指令

```bash
# 後端全套測試（目前 134 tests）
cd packages/api && STORE_BACKEND=memory ../../venv/bin/python -m unittest discover -s tests -t .

# 前端
npm --prefix frontend run build         # tsc -b + vite build ← 真正的型別檢查在這
npm --prefix frontend run lint          # oxlint
npm --prefix frontend test              # node:test（5 tests）

# 部署前（只在真的要 deploy 時）
python -m infra.preflight --env-file .env
python -m infra.preflight --env-file .env --online
python -m infra.guardrails \
  --template infra/cdk.out/AiwaveStaging.template.json \
  --manifest infra/upload-manifest.json
```

`AGENTS.md` 的原則是「只在工具已宣告時執行，結果如實回報」。沒跑的檢查要說沒跑，不要假裝跑過。

### 型別檢查：不要用 `tsc --noEmit`

`frontend/tsconfig.json` 是 solution-style 設定（`"files": []` + `references` 指向 `tsconfig.app.json` / `tsconfig.node.json`）。所以：

```bash
cd frontend && npx tsc --noEmit    # 永遠 exit 0，什麼都沒檢查
```

實測方式：在 `frontend/src/` 放一行 `export const broken: number = "not a number";`

| 指令 | 是否抓到錯誤 |
|---|---|
| `npx tsc --noEmit` | **沒有**（exit 0） |
| `npx tsc -b` | 有（exit 2） |
| `npx tsc -p tsconfig.app.json --noEmit` | 有（exit 2） |
| `npm run build` | 有（exit 2，因為它跑 `tsc -b`） |

要單獨做型別檢查用 `cd frontend && npx tsc -b`；平常直接跑 `npm --prefix frontend run build` 就同時涵蓋型別與打包。

---

## 3. 六階段流程

以商品購買為例，實際跑過一遍的樣子。

### 階段 0：讀規格，不寫程式

讀 `SPEC.md` 的該類別範圍、`openspec/changes/define-flask-mcp-service-intake/contracts/forms/<service>.schema.json` 的表單契約、`data/mock/knowledge/<service>.md` 的政策知識，以及既有的水電實作當範本。

**這一步最容易被跳過，但它決定後面所有事。** 商品購買的定價規則就是在這步發現 `sale_price` 已含折扣，避免了一個會少收錢的 bug。

### 階段 1：寫 OpenSpec，還是不寫程式

```
openspec/changes/add-<service>-automation/
├── .openspec.yaml
├── proposal.md   Why / What / Capabilities / Impact / Open Questions
├── design.md     設計決策 + 風險取捨 + Migration Plan
├── tasks.md      每項任務配一個「客觀驗證步驟」
└── specs/        requirement + scenario
```

`openspec/config.yaml` 的硬規則：

- spec 用 `SHALL` / `MUST`，且要涵蓋 success、missing-input、authorization、idempotency、safety 情境
- design 要說明 Agent 邊界、狀態轉移、PII 處理，並記錄**未解決的部署選擇**而不是當作已完成
- task 必須配客觀驗證步驟；只有 fixture 的整合不可標記完成

寫 `Open Questions` 不是偷懶，是把未解問題留在文件裡。商品購買的「Lambda 打包如何攜帶目錄 JSON」就是這樣被記下來，後來證實是真的部署阻礙。

### 階段 2：先寫測試，再寫實作

`AGENTS.md`：非 trivial 行為與 bug fix 優先先寫測試。寫完先跑一次確認全紅，再實作。

**測試分兩類是刻意的：**

| 類型 | 資料 | 目的 |
|---|---|---|
| 規則測試 | 合成的小 fixture | 釘住規則，不依賴哪筆真實資料剛好存在 |
| 完整性測試 | 真實全量 fixture | 抓「資料與規則不一致」 |

例如 `test_product_catalog.py` 用合成商品測定價規則，另外用真實 300 筆斷言 `sale_price` 與規則一致 —— 後者就是重複折扣 bug 的回歸防線。

### 階段 3：小步實作，每步保持綠燈

商品購買的依賴順序：目錄 → 對話 → 選品 → 訂單 → 前端。每階段結束跑全套測試，確認**既有服務沒回歸**。

實際軌跡：31 → 37 → 72 → 95 → 123 → 134 tests，每一步全綠。動到共用程式碼（例如 `_apply_provider_response`）時每改一次就重跑。

### 階段 4：真實環境驗證，不只靠測試

**這步最重要。** 測試綠不代表 demo 不會壞。每階段結束起 Flask + 打真實 HTTP 走完整流程，把每個畫面會顯示的值印出來看。

商品購買有三個問題只有這步才看到：`折扣：-0 元`、`運費：120 元（運費 120 元）`、`備註：xxx這是 Demo...`（缺分隔）。

### 階段 5：收尾檢查 + commit

跑第 2 節全部指令，然後檢閱 diff：

- 無憑證、無 `.env`、無 `dist/`
- `data/competition/` 零變更（那是主辦原始資料，只能讀）
- 無與本次變更無關的檔案

commit message 要寫清楚**還沒完成的部分**，特別是會讓別人踩雷的（見第 6 節的部署阻礙）。

---

## 4. 加一個新服務類別

階段 1 的骨幹重構就是為此做的。**不需要改 `service.py`。**

### 擴充點

| 檔案 | 要做什麼 |
|---|---|
| `walking_skeleton/<service>_flow.py` | 新增，實作 `flows.py` 的 `ServiceFlow` protocol |
| `walking_skeleton/service.py` | `default_flows()` 加一行註冊 |
| `walking_skeleton/orchestration.py` | `DeterministicDemoOrchestrator` 加路由關鍵字 |
| `frontend/src/api/types.ts` | `ServiceType` union 已有五類；新 stage 加進 `WorkflowStage` |
| `frontend/src/api/viewModels.ts` | 新 stage 的標籤與顏色、`SERVICE_NAMES` |

### `ServiceFlow` 要提供什麼

`service.py` 擁有跨類別共通的一切：對話、訊息、artifact 版本、provider task、改派、冪等、授權、projection。flow 只負責該類別**不同**的部分：

```
service_type / agent_name / service_name / schema_version
stage_labels        該類別用到的 stage → 中文標籤
routing_hint        供 supervisor 組招呼語與「不支援」回覆
supports_selection  是否需要住戶從多個候選中選一個
init_request        建立案件時補該類別欄位
start / continue_turn   對話推進
build_summary / fallback_summary / build_canonical / projection_fields
list_providers / rank_candidates
validate_accept / apply_accept
```

flow 收到的 `svc` 是 service 實例，透過它使用共用 seam（`set_progress`、`append_assistant`、`render_artifact`、`dispatch_first_candidate`…）。

### 兩個約束

**stage 名稱不要造同義詞。** 商品的供應商在領域模型上就是 `provider`，所以重用 `waiting_provider_response` / `provider_confirmed`，沒有另建 `waiting_supplier_response`。前端的 stage 標籤、等待角色判斷、`/reminders` 待辦計算都依 stage 名稱分支，同義詞會讓四個地方各長一組 if。只新增該類別**真正獨有**的 stage。

**flow 函式要 transport 無關。** 只接純資料參數，不吃 Flask `request` / `g` / header，錯誤用 `errors.py` 的 `ValidationError` / `ForbiddenError` / `NotFoundError` / `ConflictError` 表達。這樣未來的 AgentCore Gateway tool Lambda 可以 import 同一組函式，符合「REST 與 MCP 共用 service layer」。

### 保護擴充點的測試

`tests/test_service_flow_dispatch.py` 用 stub flow 證明六件事：delegation 選對 flow、continuation 依 stored `serviceType` 分派、既有類別不受影響、未註冊類別由 supervisor 回覆且**不建案**、已存案件遇缺失 flow 拋 `UnsupportedServiceTypeError`（500 而非靜默 fallback）、flow 只能用自己宣告過 label 的 stage。

加新服務時這些測試應該繼續通過。如果壞了，代表擴充方式偏離了設計。

---

## 5. 兩個必須遵守的判斷原則

### 文件衝突要先指出，不能默默選一份

`AGENTS.md` 明文要求。實際遇過兩次：

**RDS 有兩套互斥設計。** `packages/api/scripts/rds_create.py` 建 `PubliclyAccessible=True` 的 RDS，但 README 與 `infra/guardrails.py` 要求 RDS 必須非公開。這個衝突**尚未解決**，記在 `add-product-purchase-automation/design.md` 的 Open Questions。目前兩者都不使用。

**自己的 spec 差點被自己違反。** 「雙領域關鍵字衝突澄清」原本列為延後，但實作時發現那會讓 fallback 靜默選一個領域 —— 直接違反 spec 的「MUST NOT 靜默選擇」。**未實作可以接受，違反不行**，所以補了實作並在 tasks.md 註明它從延後移上來。

### 砍範圍要留痕跡

商品購買從 40 項砍到 14 項，但做法是：**spec 保留完整需求，tasks.md 明列延後項與理由**，不是刪掉規格。

延後理由分兩種，文件裡要分開寫：

- **真延後**：替代品推薦、缺貨分支、訂單狀態 `04`/`80`/`99`
- **由「不蒐集」滿足而非延後**：PII 要求。商品流程只有品項/預算/數量/縣市/行政區五個欄位，沒有姓名、電話、門牌的存放位置 —— 這比事後遮蔽更強，算滿足不算跳過

---

## 6. 目前狀態與已知阻礙

### 部署阻礙（重要）

**現在直接 `cdk deploy` 會讓整個 API 掛掉，連正常的水電流程一起死。**

`infra/aiwave_stack.py` 的 Lambda asset 是 `repository_root / "packages" / "api"`，bundling 只 `cp -au .`。但 `product_catalog.default_catalog_dir()` 解析到 repo 根的 `data/mock/master`，在 `/var/task` 下不存在，`create_app()` 在 cold start 就拋：

```
RuntimeError: product catalogue file is missing: /data/mock/master/products.json
```

`ProductPurchaseFlow.__init__` 在 `default_flows()` 就載入目錄，而那是 `create_app()` 的一部分 —— 所以不是「商品購買壞掉」，是**全部 500**。

建議修法：CDK 先把 `packages/api` 與 `data/mock/master`（共約 351 KB）合併到暫存目錄再做 asset，避免把 mock 資料複製進 `packages/api/` 造成兩份事實來源。

**不要走 S3**：`infra/guardrails.py` 的上傳白名單只允許 `infra/upload-manifest.json` 裡的 10 個水電知識庫檔案，上傳 `products.json` 會被閘門擋下。

### 部署前還缺的東西

| 項目 | 狀態 |
|---|---|
| `AWS_CREDENTIAL_EXPIRATION` | `.env` 未填，`infra.preflight` 會直接失敗 |
| region | 必須 `us-west-2`（`infra/preflight.py:15` 寫死） |
| CDK | `infra/node_modules/.bin/cdk` 未安裝 |
| 前端 | `VITE_API_BASE_URL` 要指向 API Gateway 後重新 build，再走 Amplify manual deployment |

### `.env.example` 與 preflight 不一致

`.env.example` 仍寫 `us-east-1`，且缺 `AWS_CREDENTIAL_EXPIRATION`。README 第 148 行要求 `.env.example` 必須同步。這是既有不一致，尚未修。

---

## 7. 流程真的抓到東西

三個 bug，被不同關卡抓到 —— 這是每一道關卡不是形式的證據。

| Bug | 被什麼抓到 | 若沒抓到的後果 |
|---|---|---|
| 重複折扣：以 `sale_price` 為基準再乘 `discount_rate`，160 筆商品折兩次 | **階段 0 讀規格時去驗證真實資料** | 單筆最多少收 1,932 元，所有促銷商品都算錯 |
| 促銷免運失效：48 筆 `free_shipping` 促銷（label「本檔免運」）`discount_rate` 為 `0.0`，舊規則只看 rate 所以運費照收 | **階段 4 找 demo 例子時跑了 8 個情境** | 卡片同時顯示「本檔免運」和「運費 400 元」，自我矛盾 |
| `candidatesVersion` 沒放進 projection | **階段 4 E2E 實測** | 住戶改一次預算，選品就 409 |

第三個特別值得記：當時 28 個測試全過，因為它們都硬編 `expectedVersion: 1`，剛好繞過 bug。**測試綠 ≠ 沒問題，一定要真的跑一遍看畫面上的值。**

另外還修了一個測試自身的 flaky：`assertNotIn("09", body)` 會撞到 `requestId` 十六進位字串。斷言 PII 不外洩要用**樣式比對**（手機號碼、Email、門牌的 regex），不要用裸字串片段。

### 檢查指令本身也要驗證

寫這份文件時發現：整個商品購買開發過程中回報的「`tsc --noEmit` 通過」**全部是空操作**。`frontend/tsconfig.json` 是 solution-style 設定，`tsc --noEmit` 不會檢查任何檔案，永遠 exit 0。

真正的型別檢查一直是由 `npm run build`（內含 `tsc -b`）提供的，而它每次都有跑並通過，所以結論沒有錯 —— 但「已驗證」的依據有一半是假的。

**教訓**：把一個指令當成品質關卡之前，先故意製造一個它應該要抓到的錯誤，確認它真的會失敗。exit 0 不等於檢查過。

---

## 8. 快速參考

```bash
# 起本機環境
cd packages/api && STORE_BACKEND=memory PORT=8000 ../../venv/bin/python app.py
npm --prefix frontend run dev -- --host 127.0.0.1

# 全套檢查
cd packages/api && STORE_BACKEND=memory ../../venv/bin/python -m unittest discover -s tests -t .
npm --prefix frontend run build && npm --prefix frontend run lint && npm --prefix frontend test

# demo 用句子
# 水電：浴室水管一直漏水 → 沒有漏電也沒有冒煙 → 內湖區 → 明天下午兩點 → 確認送出
# 商品：想買除濕機，預算 15000 以內，送台北市大安區 → 點「選這個」→ 確認送出
# 歧義：冷氣壞了想直接買一台新的還是修比較好 → 會反問，不建案
```

| 想找什麼 | 去哪 |
|---|---|
| 產品邊界、五類服務範圍 | [`SPEC.md`](../SPEC.md) |
| 這次變更的需求與驗收 | [`openspec/changes/`](../openspec/changes/) |
| 架構決策理由 | [`docs/adr/`](adr/) |
| Agent 行為契約 | [`AGENTS.md`](../AGENTS.md) |
| 部署與安全閘門 | [README「AWS 部署安全閘門」](../README.md#aws-部署安全閘門) |
| 跨類別骨幹與擴充點 | `packages/api/walking_skeleton/flows.py` |
