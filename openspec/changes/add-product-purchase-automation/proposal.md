## Why

`define-flask-mcp-service-intake` 已交付水電修繕的 walking skeleton，證明「Supervisor 路由 → 領域 Agent 蒐集 → 需求文件確認 → 確定性委派 → 廠商回覆 → 恢復 Agent → 最終結論」這條閉環可行。五類服務中，商品購買是唯一在住戶確認前就能得到**確定金額**與**確定庫存**的類別，因此它是驗證下列三件事最短的路徑：

1. 即時結構化資料（SKU、庫存、運費、促銷）與靜態 Knowledge Base（退換貨政策、配送條款）的邊界是否真的分離。
2. 住戶在多個候選之間**主動選擇**時，確認流程與 artifact 版本控制是否仍然嚴謹。
3. Demo 交易（建立 `pending` 訂單 → mock 付款授權 → 供應商承接）能否在不執行任何不可逆外部交易的前提下完成。

水電流程沒有選品步驟、沒有下單前定價、也沒有付款授權，這三段是商品購買必須新增的能力。

## What Changes

- 新增商品目錄與庫存的即時查詢邊界：SKU 搜尋、可售量計算、運費與促銷試算，全部只從結構化資料來源取得。
- 新增住戶選品步驟：Agent 回傳候選 SKU，住戶明確選定一項後才產生訂單摘要文件。
- 新增下單前定價：單價 × 數量 − 促銷折扣 + 運費，並在 artifact 中逐項揭露；金額 MUST 由確定性規則計算，不得由模型產生。
- 新增 mock 付款授權 stage：以 `authorizing_payment` 表示，明確標示為 Demo 授權，不執行真實扣款。
- 新增商品訂單狀態機並對齊命題 `mms_order_record` 的 `order_type='05'` 狀態碼（`01` 待付款、`02` 待確認、`03` 已確認、`90` 已取消、`99` 已退款）。
- 新增缺貨處理：可售量不足時，依住戶的「是否接受替代品」決定提供近似 SKU 或揭露 `restock_eta` 後結案。
- 擴充 Supervisor 確定性 fallback 的路由詞彙，使商品需求委派至 `product_agent`。
- 擴充 REST walking skeleton：新增 `POST /api/v1/service-requests/{id}/selections` 供住戶選品，其餘既有端點沿用。
- 擴充前端型別與頁面：`serviceType` 由單一字面值放寬為 union，對話中新增商品候選卡片，訂單摘要與供應商後台重用既有 projection。

本 change **不**新增 AgentCore Runtime、**不**新增 Step Functions state machine、**不**新增第三方付款或供應商 API 整合，也**不**引入新的 Python 或前端執行期依賴。

## Capabilities

### New Capabilities

- `product-catalog-availability`: 定義商品目錄、庫存、定價、運費與促銷的即時資料邊界，以及與 Knowledge Base 的職責分界。
- `product-purchase-order-lifecycle`: 定義商品需求的選品、確認、mock 付款授權、供應商委派、缺貨與改派的合法狀態轉移與冪等規則。

### Modified Capabilities

- `async-agent-provider-workflow`: 新增 `awaiting_resident_selection`、`authorizing_payment`、`out_of_stock` 三個 stage 與選品 REST 端點；商品類別重用既有 `waiting_provider_response`、`waiting_resident_information`、`rematching`、`provider_confirmed` 語意與 projection。
- `agentcore-domain-orchestration`: 確定性 Demo fallback 新增 `product_purchase` → `product_agent` 路由，並定義與水電關鍵字衝突時的處理。

## Impact

- 後端：`packages/api/walking_skeleton/` 新增 `product_catalog.py`；`service.py` 抽出跨類別共用流程並新增商品分支；`api.py` 新增一個選品端點；`orchestration.py` 擴充路由詞彙。`store.py` 不變。
- 資料：Demo 以 `data/mock/master/products.json` 與 `product_inventory.json` 為商品目錄的唯一事實來源，讀取後不覆寫原檔。案件狀態沿用 walking skeleton 既有的 `aiwave_demo_state` JSONB aggregate（`rds_store.py` 於首次使用時 `CREATE TABLE IF NOT EXISTS` 建立），因此本 change **不需要** migration。`packages/api/sql/schema.sql` 新增的 `mms_supplier`、`mms_product`、`mms_product_inventory`、`mms_product_order` 屬於**未套用的設計交付物**，用於記錄正規化模型與命題欄位對應，供後續正規化 change 使用。
- 前端：`api/types.ts`、`api/client.ts`、`pages/ChatPage.tsx`、`pages/MyBookingsPage.tsx`、`pages/DashboardPage.tsx`。
- 安全：選品與確認端點必須驗證案件 owner；供應商只能看到遮蔽後的收貨地區（縣市／行政區），不得取得詳細門牌。價格與庫存不得由模型自由生成。
- 依賴：無新增套件。商品資料以標準庫 `json` 讀取。

## Open Questions

- Demo 是否需要在 `mms_product_order` 之外同時寫入命題原始 `mms_order_record` 結構；目前假設只寫本專案表，欄位命名對齊命題以便後續遷移。
- 促銷疊加規則：知識庫載明「多數促銷不可疊加」，但 mock 資料每個 SKU 僅有單一 `promotion`，因此本 change 只實作單一促銷；多重促銷延後決策。
