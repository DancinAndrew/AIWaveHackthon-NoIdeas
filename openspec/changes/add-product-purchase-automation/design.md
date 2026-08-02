## Context

水電 walking skeleton 已證明對話 → 文件 → 確認 → 委派 → 廠商回覆 → 結論這條閉環。商品購買重用同一條骨幹，但插入三段水電沒有的流程：**選品**、**下單前定價**、**mock 付款授權**。本文件說明這三段如何在不破壞既有 projection 與授權邊界的前提下加入。

現況約束：

- `walking_skeleton/store.py` 的 `service_requests`、`artifacts`、`progress`、`tasks`、`events`、`idempotency` 已是類別無關的泛型容器，不需修改。
- `walking_skeleton/service.py` 目前把水電邏輯與流程骨幹混在一起（`SERVICE_TYPE`、`ACTIVE_AGENT` 為模組層常數，`_start_utility_request` / `_continue_utility_request` 直接操作 store）。加入第二個類別必須先抽出共用骨幹。
- 前端 `api/types.ts` 把 `serviceType` 寫死為 `"utility_repair"` 字面值，加入第二類別必然要放寬。

## Goals / Non-Goals

Goals：

- 商品購買在 deterministic fallback 下可完整跑完 E2E，金額與庫存皆可重現。
- 選品與定價的所有數字由伺服器規則計算，模型只負責文字。
- 新增 stage 不破壞水電案件的既有行為與測試。

Non-Goals：

- 不實作真實付款、真實供應商 API、物流追蹤。
- 不實作多重促銷疊加、跨 SKU 購物車、分批出貨。
- 不在本 change 建立 Step Functions state machine 或 AgentCore Runtime；沿用現有 deterministic adapter 與 in-memory／RDS store 邊界。

## Decisions

### 1. Stage 命名重用 provider 語意

商品的供應商在領域模型上就是 `provider`，因此 **不** 新增 `waiting_supplier_response` / `supplier_confirmed`，而重用 `waiting_provider_response` / `provider_confirmed`。

理由：前端 `WorkflowStage` union、`MyBookingsPage` 的等待角色判斷、`DashboardPage` 的 task 操作、`/reminders` 的待辦計算全部依 stage 名稱分支。新增同義詞會讓這四處各長出一組 if，且跨類別統計失去意義。

只新增三個語意上真正不存在於水電的 stage：

| Stage | 等待角色 | 說明 |
|---|---|---|
| `awaiting_resident_selection` | resident | 已有候選 SKU，等住戶挑一個 |
| `authorizing_payment` | 無 | mock 授權中，自動推進 |
| `out_of_stock` | resident | 全部缺貨且不接受替代品 |

替代方案是每個類別自成一套 stage 命名；未採用，因為 projection 與提醒是跨類別共用的 read model。

### 2. 選品用獨立 REST 端點，不用自然語言

`POST /api/v1/service-requests/{id}/selections`，body 只有 `{ "sku": "...", "expectedVersion": n }`。

理由：

- 「我要第 2 個」這種自然語言指涉在候選清單重算後會指到不同商品，是實際會發生的錯誤，不是理論風險。
- 金額必須由伺服器計算。若靠對話推進，模型有機會把金額寫進訊息，違反「金額不由模型產生」。
- 端點回傳完整重算後的 artifact，前端不需要自己算價。

安全上，端點 MUST 忽略 body 中任何 `finalAmount`、`shippingFee`、`price` 欄位，一律以伺服器目錄重算。`expectedVersion` 防止住戶在候選清單已因庫存變動重算後，仍用舊清單選品。

替代方案是純對話選品；未採用，理由如上。

### 3. 付款授權是獨立 stage 但自動推進

`awaiting_resident_confirmation` → 住戶確認 → 建立 `order_status='01'` → `authorizing_payment` → mock 授權 → `order_status='02'` → `waiting_provider_response`。

`authorizing_payment` 在同一個 request 內完成，住戶不需多按一次。保留為獨立 stage 的理由是可稽核：授權失敗時案件會**停在**這個 stage 且訂單維持 `01`，這在 projection 上看得見，比「確認後直接跳到等待供應商」更能反映真實金流流程。

措辭上禁止「已付款」、「已扣款」，統一用「Demo 模擬授權，未產生真實扣款」。

### 4. 商品目錄完整載入，不內嵌子集

水電把 2 家廠商硬編在 `service.py`，是因為 provider 主檔在 walking skeleton 階段只需要兩筆就能示範改派。商品不同：候選搜尋的說服力直接來自目錄廣度（300 SKU、多類別、多配送方式、多促銷型態）。

因此新增 `walking_skeleton/product_catalog.py`，於模組載入時讀取 `data/mock/master/products.json` 與 `product_inventory.json`，建立記憶體索引：

- `by_item_type`: 品項 → SKU list
- `by_category`: 類別 → SKU list
- `inventory`: SKU → `{stock_on_hand, reserved, restock_eta}`

檔案路徑透過環境變數 `PRODUCT_CATALOG_DIR` 覆寫，預設指向 repo 內 `data/mock/master`。載入為唯讀，MUST NOT 寫回原檔（`AGENTS.md` 對 `data/competition/` 的限制同樣適用於 mock 主檔的來源完整性）。

未解決：Lambda 打包時這兩個 JSON 需一併包入，或改由 S3 讀取。本 change 只處理本機與測試路徑，部署打包方式延後決策。

### 5. 定價規則

`list_price` 是唯一的定價基準；`sale_price` 是衍生值，不可作為計算輸入。實測 `data/mock/master/products.json` 300 筆：

| 分布 | 筆數 | 語意 |
|---|---|---|
| 有促銷、`applies_from_quantity = 1`、`sale_price == round(list_price × (1 − rate))` | 160 | 促銷已反映在 `sale_price` |
| 有促銷、`applies_from_quantity = 2`、`sale_price == list_price` | 42 | 促銷未反映，需達數量門檻才折 |
| 無促銷、`sale_price == list_price` | 98 | 無折扣 |

也就是 `sale_price` 的定義是「促銷數量門檻已滿足時的單價」。若以 `sale_price` 為基準再乘 `discount_rate`，160 筆會被折兩次，42 筆會在未達門檻時被誤折。因此：

```text
promo_applies   = promotion is not None and quantity >= promotion.applies_from_quantity
unit_price      = round(list_price × (1 − discount_rate)) if promo_applies else list_price
original_amount = list_price × quantity
discount_amount = original_amount − unit_price × quantity
after_discount  = unit_price × quantity
shipping_fee    = 0 if after_discount >= delivery.free_over else delivery.fee
final_amount    = after_discount + shipping_fee
```

`sale_price` 改作**資料一致性斷言**使用：對 `applies_from_quantity <= 1` 的商品，`quantity = 1` 算出的 `unit_price` MUST 等於 `sale_price`。這在測試中對全部 300 筆驗證，可攔下目錄資料被改壞的情況。

`free_over` 為 `9999` 且配送方式為大型商品專車時，資料語意是「不適用免運」；規則以 `after_discount >= free_over` 判斷即可自然得到不免運的結果，不需特例。

金額一律整數（TWD 無小數）。折扣用 `round` 而非截斷，並在 artifact 逐項顯示，避免住戶自行加總對不上。

### 6. 候選搜尋兩階段

硬條件（全部 MUST 成立）：

1. 品項或類別命中住戶需求
2. `sale_price ≤ budget.max_amount`
3. 可售量 `stock_on_hand − reserved ≥ quantity`
4. 住戶宣告品牌偏好時，`brand` 必須命中
5. 住戶宣告必要規格時，`specs` 必須包含且相符

軟排序（版本化權重，`PRODUCT_RANKING_RULE_VERSION = "1.0.0"`）：

- 價格符合度：促銷後單價相對預算的餘裕
- 評分：`rating / 5`
- 到貨速度：`delivery.estimated_days` 越短越高
- 促銷力度：`discount_rate`

排序 tie-break 用 `sku` 字典序，確保完全可重現。分數與理由一起保存，理由是規則產生的中文句子，不是模型輸出。

住戶標記 `accept_substitutes` 時，若硬條件結果為空，放寬條件 4、5 後重搜，並將結果標記 `isSubstitute: true`。條件 1、2、3 不放寬。

### 7. Service 層重構邊界

`service.py` 抽出：

- `_route_new_request(conversation, content)`：呼叫 orchestrator，依 `service_type` 分派到各類別的 start handler
- `_continue_request(conversation, content)`：依案件的 `serviceType` 分派到各類別的 continue handler
- 共用不動：`_message`、`_append_assistant`、`_event`、`_set_progress`、`_progress_projection`、`_create_provider_task`、`_rematch`、`_apply_provider_response`、`_apply_timeout`、`idempotent`

水電專屬邏輯（安全篩檢、`HIGH_RISK_TERMS`、`DEMO_PROVIDERS`）移到 `utility_flow.py`，商品邏輯放 `product_flow.py`。`service.py` 保留骨幹與跨類別共用行為。

`_apply_provider_response` 對兩類別共用，但 `accept` 的必填欄位不同（水電要 `arrivalWindow`，商品要 `estimatedShipDate`）。以案件的 `serviceType` 決定必填欄位，驗證仍在進入交易前完成，維持既有「無效 accept 不得消耗 task 版本」的性質。

### 8. 訂單狀態與 stage 的對應

| Stage | `order_status` |
|---|---|
| `collecting_details` / `awaiting_resident_selection` / `awaiting_resident_confirmation` | 尚未建單 |
| `authorizing_payment` | `01` 待付款 |
| `waiting_provider_response` / `waiting_resident_information` / `rematching` | `02` 待確認 |
| `provider_confirmed` | `03` 已確認 |
| `out_of_stock` / cancelled | `90` 已取消（若已建單） |

`04` 進行中、`80` 已完成、`99` 已退款 的觸發條件（出貨、簽收、退貨）不在本 change 範圍。

### 9. PII 與授權

- AI 對話 MUST NOT 蒐集詳細門牌、收件人姓名、電話。住戶主動輸入時不寫入案件摘要或 artifact。
- 供應商可見 artifact 只含商品明細、數量、金額、收貨縣市／行政區。
- 選品與確認端點以受信任 request context 判斷 owner（Demo 為 `X-Demo-Resident-Id`），body 不得覆寫。
- 跨住戶存取回 403/404 且不洩漏案件內容。

### 10. 持久化：沿用 JSONB aggregate，不做 migration

調查 staging 後修正了原本的假設。實際狀況：

- staging RDS（`aiwavestaging-databaseb269d8bb-7lmmmlnk8o2f`，postgres 16.13）位於 `PRIVATE_ISOLATED` 子網、`PubliclyAccessible=false`。本機實測 DNS 解析到 `10.42.1.169`、TCP 5432 逾時，**開發機無法直連**，這是設計如此。
- 兩個 staging Lambda 都是 `STORE_BACKEND=rds`，走 `rds_store.py`，把整個 demo 狀態存進**單一 JSONB 列** `aiwave_demo_state`，該表由 app 首次使用時 `CREATE TABLE IF NOT EXISTS` 建立。
- 專案**沒有 migration runner**。唯一會套用 `sql/schema.sql` 的 `scripts/rds_load.py` 走的是 `op_agent/rds.py` 的 `PGHOST` 路徑，那是為 `scripts/rds_create.py` 建立的**公開** RDS 設計的舊路徑，與現行 staging 無關。因此 `sql/schema.sql` 目前是未被套用的設計文件。

決策：商品購買**不新增 migration**，案件狀態沿用 `aiwave_demo_state`。部署後即生效，不需要任何 DDL 步驟。

`sql/schema.sql` 仍新增下列表定義，但明確標記為**未套用的設計交付物**，目的是記錄正規化模型與命題 `mms_order_record` 的欄位對應，供後續正規化 change 使用：

```text
mms_supplier            供應商主檔（supplier_id, name, rating, is_enable）
mms_product             SKU 主檔（sku, supplier_id, category, name, brand, item_type,
                        specs jsonb, list_price, sale_price, promotion jsonb,
                        delivery jsonb, return_policy jsonb, warranty_months, rating）
mms_product_inventory   庫存（sku, stock_on_hand, reserved, restock_eta, updated_at）
mms_product_order       Demo 訂單（order_no, inbr_account_id, sku, quantity,
                        order_type '05', order_status, original_amount, discount_amount,
                        shipping_fee_amount, final_amount, county_code, district_code,
                        version, order_time, confirm_time, cancel_time）
```

欄位命名對齊命題 `mms_order_record`，方便後續遷移。`specs`、`promotion`、`delivery`、`return_policy` 用 `jsonb`：這些結構隨供應商而異，且只讀出來顯示，不進 SQL 運算。金額與數量進運算，所以是獨立整數欄位。

因為沒有可用的 migration 路徑，這些 DDL **不會**在本 change 被執行，也**不會**有「空資料庫可依序套用」的驗證證據。tasks.md 的驗證條件已相應改為可實際達成的靜態檢查。

### 11. MCP 工具與 service layer 共用

本 change 只實作 REST transport；商品相關 MCP tools（例如 `search_products`、`get_product_availability`）**不**在此交付，SPEC 第 5 節的 MVP 工具清單也尚未包含它們。

為避免將來補上工具時複製業務邏輯，`product_catalog.py` 與 `product_flow.py` 的對外函式 MUST 保持 transport 無關：

- 只接收純資料參數（`actor_id`、案件識別碼、SKU、數量等），不接收 Flask `request`、`g` 或 header。
- 授權以傳入的 actor context 判斷，不自行從 request 取值。
- 錯誤以 `walking_skeleton/errors.py` 的 `ValidationError` / `ForbiddenError` / `NotFoundError` / `ConflictError` 表達，由各 transport 自行映射成 HTTP 或 MCP 錯誤碼。

如此未來的工具 Lambda 可直接 import 同一組函式，符合「REST 與 MCP tools 共用 service layer，不得各自複製業務邏輯」。新增 MCP 工具契約時需另開 OpenSpec change 修改 `mcp-service-tools` 與 `contracts/mcp/tools.json`。

## Risks / Trade-offs

- [Risk] `service.py` 重構可能破壞水電既有測試 → 先跑 `test_utility_walking_skeleton.py` 建立基線，重構後必須全綠才加商品邏輯。
- [Risk] 300 SKU 載入拖慢 Lambda cold start → 模組層載入一次並建索引；若實測不可接受，改為延遲載入或裁剪欄位。目前無實測數據，不預先優化。
- [Risk] 候選清單與實際庫存之間有 race → 選品端點重新檢查可售量，不足時回 409 並重算清單。本 change 不實作庫存預留（reservation），因為那需要釋放機制與逾時處理，超出範圍。
- [Risk] `accept_substitutes` 放寬規格可能產生住戶完全不想要的候選 → 替代品必須標記，且理由要說明放寬了哪個條件。
- [Risk] 前端 `serviceType` 放寬為 union 後，既有 narrowing 可能失效 → 以 `tsc --noEmit` 驗證，不用 `as` 繞過。
- [Trade-off] 選品新增一個 REST 端點增加 API 面積，換取金額正確性與可稽核性。判斷為值得。

## Migration Plan

1. 建立水電測試基線（現有測試必須全綠）。
2. 抽出 `service.py` 共用骨幹，水電邏輯移入 `utility_flow.py`；重跑水電測試確認行為不變。
3. 新增 `product_catalog.py` 與其單元測試（搜尋、可售量、定價、缺貨）。
4. 新增 `product_flow.py` 與 E2E 測試（完整流程、缺貨、改選、供應商婉拒改派、冪等、跨住戶授權）。
5. 擴充 `orchestration.py` 路由與其測試（商品命中、雙領域衝突、未支援領域）。
6. 新增選品端點與 contract 測試（忽略用戶端金額、非選品類別、版本衝突）。
7. 新增 SQL migration。
8. 前端型別放寬 → client 方法 → ChatPage 候選卡片 → MyBookings / Dashboard。
9. `tsc --noEmit` 與 pytest 全綠後才合併。

## Open Questions

- Lambda 打包如何攜帶商品目錄 JSON（內嵌 vs S3）。
- 是否需要庫存預留機制；目前以選品時重檢 + 409 替代。
- `mms_product_order` 是否最終併入命題 `mms_order_record` 單表。
- 何時引入 migration runner，以及正規化表要走一次性 VPC 內 Lambda 或 RDS Data API。這是獨立 change 的範圍。
- `packages/api/scripts/rds_create.py`（建立 `PubliclyAccessible=True` 的 RDS）與 README／`infra/guardrails.py` 宣告的「RDS 明確設為非公開」互相衝突。本 change 兩者皆不使用，但該衝突仍未解決，應由專門的 change 決定是否移除舊腳本。
