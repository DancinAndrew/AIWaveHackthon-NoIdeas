## ADDED Requirements

### Requirement: 單一 Runtime 的多領域 Agent 拓撲
系統 SHALL 在一個 Amazon Bedrock AgentCore Runtime 內執行一個 Supervisor 與 `restaurant_reservation`、`product_purchase`、`housekeeping_service`、`utility_repair`、`community_consultation` 五個邏輯領域 Agent。系統 MUST NOT 為 Demo 將六個邏輯 Agent 部署為六個獨立 Runtime。

#### Scenario: 單一類別需求路由
- **WHEN** Supervisor 收到可明確分類為五類之一的完整或部分需求
- **THEN** Supervisor 只將該需求交給對應領域 Agent，並在 trace 中保留路由類別與非敏感理由

#### Scenario: 模糊或跨類別需求
- **WHEN** 使用者輸入無法可靠分類或同時涉及多個類別
- **THEN** Supervisor 要求澄清或建立明確的多案件計畫，不得任意選擇單一領域並直接建案

### Requirement: 領域 Agent 工具與知識範圍
每個領域 Agent SHALL 只有該領域所需的 MCP tool allowlist，且查詢 Managed Knowledge Base 時 MUST 套用固定 `service_type` metadata filter。Agent MUST NOT 以 Knowledge Base 內容回答價格、庫存、可用時段、商家啟用狀態或交易狀態。

#### Scenario: 水電 Agent 查詢安全 SOP
- **WHEN** 水電 Agent 查詢 Knowledge Base
- **THEN** 檢索固定使用 `service_type = utility_repair`，不得混入其他領域文件

#### Scenario: 詢問即時庫存
- **WHEN** 商品 Agent 需要回答特定 SKU 是否有貨
- **THEN** Agent 呼叫結構化即時資料工具，不得引用 Knowledge Base 推測庫存

### Requirement: Agent 與確定性委派分離
領域 Agent SHALL 負責需求理解、欄位抽取與缺欄位追問；商家硬條件過濾、版本化評分、委派寫入與自動遞補 MUST 由 Flask application service 執行。模型產生的自由文字不得直接成為排序分數或資料庫狀態。

#### Scenario: 自動委派最高分商家
- **WHEN** 使用者確認交易且媒合服務回傳至少一個符合硬條件的候選
- **THEN** 系統依確定性排序委派最高分商家，保存規則版本、分數與理由

#### Scenario: 商家拒絕或逾時
- **WHEN** 已委派商家拒絕或在規則期限內未接受
- **THEN** Flask 依原候選排序自動委派下一名，並寫入不可變狀態事件

### Requirement: 內部交易與外部模擬邊界
平台 SHALL 在 RDS 建立並追蹤真實的內部 Demo 交易；付款、餐廳、供應商與派工等外部操作 MUST 經由明確標示的 mock adapter 執行，不得產生真實扣款或不可逆外部交易。

#### Scenario: 商品訂單 Demo
- **WHEN** 住戶確認商品訂單
- **THEN** 系統建立 `pending` 內部訂單並取得模擬付款結果，且不傳送信用卡資料或呼叫真實支付服務

#### Scenario: 餐廳接受訂位
- **WHEN** 平台已建立 `pending` 訂位且餐廳帳號接受
- **THEN** 內部訂位狀態轉為 `confirmed`，即使沒有呼叫外部餐廳系統也不得宣稱外部系統已完成訂位

### Requirement: 水電高風險規則不依賴檢索
瓦斯味、冒煙、觸電感、裸線、淹水與人員受困等高風險判斷 MUST 同時存在於水電 Agent 固定 instructions 與 Flask 確定性安全檢查；Knowledge Base 只能補充說明，不能成為唯一安全控制。

#### Scenario: Knowledge Base 無回傳
- **WHEN** 水電需求含高風險徵兆但 Knowledge Base 查詢失敗或無相關 chunk
- **THEN** 系統仍先輸出停止操作與緊急聯繫指引，且在安全確認前不得媒合或建案
