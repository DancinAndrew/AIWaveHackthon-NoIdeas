## MODIFIED Requirements

### Requirement: 單一 Runtime 的多領域 Agent 拓撲
系統 SHALL 在一個 Amazon Bedrock AgentCore Runtime 內執行一個 Supervisor 與 `restaurant_reservation`、`product_purchase`、`housekeeping_service`、`utility_repair`、`community_consultation` 五個邏輯領域 Agent。系統 MUST NOT 為 Demo 將六個邏輯 Agent 部署為六個獨立 Runtime。

確定性 Demo fallback SHALL 以版本化關鍵字規則實作同一路由決策，且 MUST 至少支援 `utility_repair` 與 `product_purchase`。當同一輸入同時命中多個領域的關鍵字時，fallback MUST NOT 靜默選擇其中一個領域建案，而 SHALL 要求住戶澄清。尚未實作的領域 MUST 明確回覆目前不支援，MUST NOT 以其他領域流程代為處理。

#### Scenario: 單一類別需求路由
- **WHEN** Supervisor 收到可明確分類為五類之一的完整或部分需求
- **THEN** Supervisor 只將該需求交給對應領域 Agent，並在 trace 中保留路由類別與非敏感理由

#### Scenario: 模糊或跨類別需求
- **WHEN** 使用者輸入無法可靠分類或同時涉及多個類別
- **THEN** Supervisor 要求澄清或建立明確的多案件計畫，不得任意選擇單一領域並直接建案

#### Scenario: 商品需求由 fallback 路由
- **WHEN** deterministic fallback 收到「想買一台除濕機」
- **THEN** 路由結果為 `product_purchase` 與 `product_agent`，且 turn 明確標示 `orchestrationMode: deterministic-demo`

#### Scenario: 商品與水電關鍵字同時命中
- **WHEN** 住戶說「冷氣壞了想直接買一台新的還是修比較好」
- **THEN** fallback 回覆澄清問題請住戶選擇維修或購買，MUST NOT 直接建立任一類別的案件

#### Scenario: 尚未實作的領域
- **WHEN** deterministic fallback 收到餐廳訂位需求
- **THEN** 系統明確回覆目前僅支援水電修繕與商品購買，MUST NOT 以商品或水電流程代為處理

### Requirement: 領域 Agent 工具與知識範圍
每個領域 Agent SHALL 只有該領域所需的 MCP tool allowlist，且查詢 Managed Knowledge Base 時 MUST 套用固定 `service_type` metadata filter。Agent MUST NOT 以 Knowledge Base 內容回答價格、庫存、可用時段、商家啟用狀態或交易狀態。

商品 Agent 的 allowlist SHALL 包含商品搜尋、庫存查詢與訂單建立所需工具，MUST NOT 包含水電技師派工或餐廳訂位工具。

#### Scenario: 水電 Agent 查詢安全 SOP
- **WHEN** 水電 Agent 查詢 Knowledge Base
- **THEN** 檢索固定使用 `service_type = utility_repair`，不得混入其他領域文件

#### Scenario: 詢問即時庫存
- **WHEN** 商品 Agent 需要回答特定 SKU 是否有貨
- **THEN** Agent 呼叫結構化即時資料工具，不得引用 Knowledge Base 推測庫存

#### Scenario: 商品 Agent 查詢退換貨政策
- **WHEN** 住戶詢問退貨期限
- **THEN** 檢索固定使用 `service_type = product_purchase`，且回覆同時說明實際適用條款以該商品的退換貨代碼為準

#### Scenario: 商品 Agent 不得跨領域取用工具
- **WHEN** 商品 Agent 嘗試呼叫水電派工工具
- **THEN** Gateway 依 allowlist 拒絕該呼叫並記錄穩定錯誤碼

### Requirement: 內部交易與外部模擬邊界
平台 SHALL 在 RDS 建立並追蹤真實的內部 Demo 交易；付款、餐廳、供應商與派工等外部操作 MUST 經由明確標示的 mock adapter 執行，不得產生真實扣款或不可逆外部交易。

商品購買的 mock 付款授權 SHALL 在對話與進度投影中明確揭露為 Demo 模擬；系統 MUST NOT 使用「已付款」、「已扣款」或「已完成付款」等會讓住戶誤認真實金流已發生的措辭。

#### Scenario: 商品訂單 Demo
- **WHEN** 住戶確認商品訂單
- **THEN** 系統建立 `order_status='01'` 內部訂單並取得模擬付款結果，且不傳送信用卡資料或呼叫真實支付服務

#### Scenario: 餐廳接受訂位
- **WHEN** 平台已建立 `pending` 訂位且餐廳帳號接受
- **THEN** 內部訂位狀態轉為 `confirmed`，即使沒有呼叫外部餐廳系統也不得宣稱外部系統已完成訂位

#### Scenario: 付款措辭不得誤導
- **WHEN** mock 付款授權成功
- **THEN** 住戶對話說明這是 Demo 模擬授權且未產生真實扣款，並在最終結論再次揭露
