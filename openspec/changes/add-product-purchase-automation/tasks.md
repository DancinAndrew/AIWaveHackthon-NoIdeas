## 1. 重構前基線（已完成）

- [x] 1.1 執行現有水電測試建立基線；驗證：`venv/bin/python -m unittest packages/api/tests/test_utility_walking_skeleton.py` 全數通過（基線 10 tests OK），完整 `unittest discover -s tests -t .` 為 31 tests OK，作為重構後比對基準。
- [x] 1.2 抽出 `service.py` 的跨類別骨幹（`_route_new_request`、`_continue_request` 分派），水電專屬邏輯移入 `utility_flow.py`；驗證：水電測試通過數量與 1.1 相同且無跳過（31 tests OK），`service.py` 不再含 `HIGH_RISK_TERMS`、`DEMO_PROVIDERS`、`DISTRICTS`、`CONFIRM_PHRASES` 或任何水電專屬文案。
- [x] 1.3 將 `serviceType` 由模組常數改為案件欄位驅動的分派；驗證：`tests/test_service_flow_dispatch.py` 以 stub flow 證明 delegation 選對 flow、continuation 依 stored `serviceType` 分派、未註冊類別由 supervisor 回覆且不建案、已存案件遇缺失 flow 拋 `UnsupportedServiceTypeError`（500）而非靜默走水電流程；全套 37 tests OK。

---

# MVP 範圍

本 change 縮小為可 demo 的最短完整閉環：**理解需求 → 查真實目錄 → 列候選 → 住戶選品 → 確定金額 → 確認 → mock 授權 → 委派供應商 → 供應商承接 → 結論回對話**。

`## 延後` 段列出刻意排除的項目與理由。延後項不影響上述閉環，且其中多數（缺貨、婉拒改派、補件往返）在水電流程已經演示過相同機制。

## 2. 商品目錄與定價（純函式，無狀態、無 HTTP）

- [x] 2.1 新增 `product_catalog.py`，載入 `products.json` 與 `product_inventory.json`，建立品項／類別索引；驗證：`tests/test_product_catalog.py::FixtureIntegrityTest` 證明 300 筆商品與 300 筆庫存全部載入、38 個品項與 8 個類別索引完整、每個 SKU 皆可查得，且 `test_loading_does_not_mutate_fixture_files` 以 SHA-256 證明載入後原始檔案未被修改。
- [x] 2.2 實作可售量 `stock_on_hand - reserved` 與硬條件過濾（品項或類別命中、單價不超預算、可售量滿足數量）；驗證：`AvailabilityTest` 與 `HardFilterTest` 對預算、可售量為 0、`reserved` 造成不足、品項不符、品牌不符、規格不符、數量大於可售量各有一組排除測試；預算邊界值（等於上限）判定為通過；可售量夾在 0 以上；缺 `item_type` 與 `category` 時拋 `ValueError`。
- [x] 2.3 實作定價：以 `list_price` 為基準、依 `applies_from_quantity` 決定促銷是否套用、`after_discount >= free_over` 決定免運；驗證：`PricingTest` 涵蓋無促銷／促銷生效／未達數量門檻／達免運／未達免運／大型商品不適用免運，金額皆為 `int` 且 `original − discount + shipping == final`；`test_sale_price_matches_rule_for_every_product` 對全部 300 筆斷言 `sale_price` 與規則一致（gate ≤ 1 者比對 quantity=1 單價，gate > 1 者斷言 `sale_price == list_price`），作為重複折扣的回歸防線。
- [x] 2.4 實作版本化軟排序與規則產生的中文理由；驗證：`RankingTest` 證明相同輸入連跑 10 次排序與分數完全一致、tie-break 依 `sku` 字典序、`limit` 生效、`PRODUCT_RANKING_RULE_VERSION` 固定為 `1.0.0`；理由字串全由 `_reasons()` 規則產生，模組不含任何模型呼叫。

## 3. 商品對話流程

- [x] 3.1 擴充 `orchestration.py` 的 `product_purchase` 關鍵字路由；驗證：`tests/test_product_flow.py::SupervisorRoutingTest` 證明購買意圖語句路由至 `product_agent`、水電症狀語句仍路由至 `utility_repair_agent`、`orchestrationMode` 為 `deterministic-demo`、無關語句不路由；水電既有測試無回歸（全套 95 tests OK）。詞表刻意採「故障動詞」而非家電名詞，使「想買冷氣」為純購買、「冷氣壞了想買新的」才觸發澄清。
- [x] 3.1a 實作雙領域關鍵字衝突的澄清分支（原列為延後，因會違反 `agentcore-domain-orchestration` 的「MUST NOT 靜默選擇」而提前實作）；驗證：`Delegation.needs_clarification` 為真時 supervisor 回覆澄清問題且 `store.service_requests` 為空，`trace[0].target` 為 `None`。
- [x] 3.2 新增 `product_flow.py`：蒐集品項、預算、數量、收貨地區（縣市＋行政區）；驗證：`ProductConversationTest` 證明一句話含多欄位時直接進選品、分次提供時依序只追問缺少欄位、已取得欄位不重複詢問、缺少地區時明確說明不需門牌；`ExtractorTest` 覆蓋數字與中文數字預算、數量的四種寫法；`test_volunteered_contact_details_are_not_stored` 證明住戶主動提供的電話、Email、門牌都不會進入案件或 projection，但行政區保留。
- [x] 3.3 實作 `awaiting_resident_selection`：欄位齊全後回傳候選清單；驗證：stage 為 `awaiting_resident_selection`、`waitingFor` 為 `resident`、`residentActionRequired` 為真；`test_selection_stage_creates_no_order_artifact_or_task` 證明此時 `store.artifacts` 與 `store.tasks` 皆為空、`orderNo` 與 `selectedSku` 為 `None`；候選金額逐項相加等於實付且不超預算。
- [x] 3.4 額外：抽出 `geo.py` 共用行政區對照表，水電與商品共用；驗證：搬移後全套測試通過數不變（72 tests OK），`utility_flow.py` 不再自行定義 `DISTRICTS`。
- [x] 3.5 額外：`ProductCatalog.suppliers()` 由目錄彙總 8 家供應商；驗證：`SupplierDerivationTest` 檢查 8 家、評分在 0~5、capabilities 來自實際配送方式、結果有快取。`responseSlaHours` 因 fixture 無來源而使用單一 demo 常數並註明，不逐家編造。

## 4. 選品、訂單與供應商

- [x] 4.1 新增 `POST /api/v1/service-requests/{id}/selections`，只接受 `sku` 與 `expectedVersion`；驗證：`SelectionEndpointTest` 證明 body 夾帶 `finalAmount`／`shippingFee`／`unitPrice` 時被忽略且金額由伺服器重算；SKU 不在候選清單回 422 且 stage 不變；對水電案件呼叫回 422（`supports_selection = False`）；其他住戶呼叫回 403/404 且回應不含 SKU；缺 `Idempotency-Key` 回 422；同 key 同 payload 冪等、同 key 不同 payload 回 409。
- [x] 4.2 實作訂單摘要 artifact 與改選時的版本遞增；驗證：首次選品為 version 1 `draft`；改選後為 version 2 且舊版本 `superseded`；artifact 逐項顯示商品、規格、數量、單價、促銷、原價、折扣、運費（含免運門檻說明）、實付、配送工作天、供應商、退換貨政策；改變需求（數量）時回到 `awaiting_resident_selection`、清空 `selectedSku`，且舊 `expectedVersion` 隨即回 409。
- [x] 4.3 實作確認 → 建立 `order_type='05'`／`order_status='01'` → `authorizing_payment` mock 授權 → `'02'` → 委派供應商；驗證：`OrderConfirmationTest` 證明未確認（提問）時不建立訂單與 task；確認後 `orderNo` 以 `ORD` 開頭、`orderStatus` 為 `02`、`orderType` 為 `05`、stage 為 `waiting_provider_response`；已確認 artifact 的 `canonical.amounts` 與訂單 `orderAmounts` 完全相同；訊息含「Demo 模擬付款授權」與「未產生真實扣款」且不含「已付款」「已扣款」「付款完成」「已完成付款」；事件含 `product_order_created`／`payment_authorized`／`supplier_matched`。`PaymentFailureTest` 以可注入的 mock authorizer 證明授權失敗時 stage 停在 `authorizing_payment`、訂單維持 `01`、未建立 task，重試成功後不會建立第二筆訂單。
- [x] 4.4 擴充 `_apply_provider_response`：商品 `accept` 需 `estimatedShipDate`，成功後 `order_status='03'` 並產生最終結論；驗證：`SupplierAcceptTest` 證明商品缺 `estimatedShipDate` 回 422 且 task 狀態與版本均未變；水電缺 `arrivalWindow` 行為不變；成功後 stage 為 `provider_confirmed`、`orderStatus` 為 `03`、final message 含出貨日／實付金額／退換貨政策／Demo 揭露；同 key 同 payload 冪等；非受派供應商回 403 且 task 仍為 pending；供應商可見的 brief 含商品、實付與行政區，但不含住戶 ID、Email 或電話。
- [x] 4.5 額外：商品訂單狀態機守衛；驗證：`OrderStateMachineTest` 證明 `01 → 03` 非法轉移被拒且狀態不變、合法轉移使 `orderVersion` 遞增、終止狀態（`90`）無法再轉移，且轉移表的鍵值集合與命題 `order_type='05'` 的七個狀態碼完全一致。

## 5. 前端

- [x] 5.1 放寬 `api/types.ts` 的 `serviceType` 為 `ServiceType` union（五類），新增 `ProductCandidate`、`ProductOrderStatus`、`SelectionResult`、`DemoProvider` 型別與 `awaiting_resident_selection`、`authorizing_payment`、`out_of_stock` 三個 stage；`ServiceRequestProjection` 的水電專屬欄位改為選填；新增 `client.ts` 的 `selectProduct(serviceRequestId, sku, expectedVersion)`；驗證：`npx tsc --noEmit`、`npm run build`、`npm run lint`、`npm test`（5 tests）全部通過，未用 `as` 斷言繞過；`selectProduct` 簽章不含任何金額參數。
- [x] 5.2 在 `ChatPage.tsx` 渲染商品候選卡片與選品按鈕，選品後顯示訂單摘要；驗證：`awaiting_resident_selection` 時每張卡顯示名稱、品牌、評分、供應商、規格、促銷標籤、單價、折扣、運費（含免運門檻）、實付、配送方式與工作天、可售量、退換貨政策與最多 3 條理由；點選後 artifact 標題依 `serviceType` 顯示「訂單摘要」或「水電需求文件」；409 顯示「候選清單已更新」而非通用錯誤；agent 標籤新增「商品 Agent」。
- [x] 5.3 更新 `MyBookingsPage.tsx` 顯示商品案件與新 stage 標籤，`DashboardPage.tsx` 的商品 accept 需填預計出貨日；驗證：卡片類型改用 `booking.serviceName`（不再硬編「水電修繕」），商品案件顯示收貨地區／數量／供應商／訂單編號與狀態，未建單時顯示「尚未建立訂單」、缺貨時顯示「缺貨，尚未建立訂單」；Dashboard 依 `brief.serviceType` 切換必填欄位（商品填預計出貨日、水電填可到場時段）並送出對應的 `estimatedShipDate`／`arrivalWindow`。
- [x] 5.4 額外：新增 `GET /api/v1/demo/providers` 供 Dashboard 切換身分；驗證：回傳 10 個身分（8 家商品供應商 + 2 家水電廠商），依服務類型分組於下拉選單；端點只回傳目錄中已公開的識別碼與名稱、不含憑證，並在程式碼與 API 文件字串明確標示為 demo-only 且不具授權效力；取得失敗時前端回退到內建的兩家水電廠商。

## 6. 收尾驗證

- [x] 6.1 執行完整後端測試；驗證：於 `packages/api` 以 `STORE_BACKEND=memory` 執行 `python -m unittest discover -s tests -t .` 為 **125 tests OK**（階段 1 基線 37），水電測試無回歸。
- [x] 6.2 執行前端檢查；驗證：`npx tsc --noEmit`、`npm run build`、`npm run lint`、`npm test`（5 tests）皆通過。
- [x] 6.3 檢閱 `git diff`；驗證：`data/competition/` 零變更、`.env` 未進 diff、新增檔案無憑證字樣（掃 `ASIA`／`AWS_SECRET`／`BEGIN PRIVATE`）。例外：`frontend/README.md` 為 Vite 腳手架產生的未追蹤檔案，與本 change 無關，未納入提交。

---

## 延後（不影響 MVP 閉環）

以下項目已寫入 `specs/`，但不在本次實作範圍。除非另有說明，理由都是「不影響 demo 主軸，且需要額外造資料或已在水電流程演示過相同機制」。

| 項目 | 對應 spec | 延後理由 |
|---|---|---|
| `accept_substitutes` 放寬品牌／規格重搜 | `product-catalog-availability` | MVP 只實作「不接受替代品」行為；替代品需刻意造無庫存資料才演得出來 |
| 配送方式限制（大型商品／冷鏈不可超商取貨） | `product-catalog-availability` | 純規則，demo 腳本不會走到 |
| 缺貨分支 `out_of_stock` | `product-purchase-order-lifecycle` | 需刻意造全品項缺貨資料 |
| 選品瞬間庫存不足回 409 | `product-purchase-order-lifecycle` | race condition，單人 demo 不會發生 |
| `needs_information` 補件往返 | `async-agent-provider-workflow` | 水電流程已演示相同機制，商品重複演無加分 |
| `decline` 與 ADMIN 模擬逾時改派 | `async-agent-provider-workflow` | 同上 |
| 訂單狀態 `04`／`80`／`99` 轉移 | `product-purchase-order-lifecycle` | 出貨、簽收、退貨不在 MVP 驗收終點（終點為 `03` 已確認） |
| 雙領域關鍵字衝突澄清 | `agentcore-domain-orchestration` | 邊緣案例 |
| `mms_supplier` 等正規化表 SQL | proposal Impact | 專案無 migration runner，狀態沿用 `aiwave_demo_state` JSONB aggregate（見 design §10）；做了會成為第三份未套用的 SQL |

### 由「不蒐集」滿足而非延後

下列安全需求在 MVP 中**已被滿足**，但不是靠遮蔽，而是靠流程中不存在蒐集路徑，這比事後遮蔽更強：

- 對話中不蒐集聯絡資料（`product-purchase-order-lifecycle`）：商品流程只有品項、預算、數量、縣市、行政區五個欄位，沒有姓名／電話／Email／門牌欄位。
- 供應商可見版本不含 PII（`product-purchase-order-lifecycle`）：artifact 本身就只含商品明細、金額與行政區，沒有需要遮蔽的欄位。

驗證方式：task 3.2 明確斷言流程中不存在這些欄位；task 4.2 斷言 artifact 欄位集合。
