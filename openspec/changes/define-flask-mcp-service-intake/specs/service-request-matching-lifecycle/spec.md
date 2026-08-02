## ADDED Requirements

### Requirement: 案件與事件交易一致性
建立或變更服務需求時，系統 SHALL 在單一資料庫交易中同時寫入案件目前狀態與不可變狀態事件；任何一步失敗 MUST 回滾整個操作。

#### Scenario: 建立案件成功
- **WHEN** 經確認的有效 submission 被首次建立
- **THEN** 一筆案件與一筆 `submitted` 事件同時存在，且共享 actor、request ID 與時間脈絡

#### Scenario: 事件寫入失敗
- **WHEN** 案件可寫入但狀態事件無法寫入
- **THEN** 交易整體回滾，系統不得留下沒有歷程的案件

### Requirement: 確定性媒合與理由
系統 SHALL 先以服務類別、啟用狀態、服務地區、必要能力與必要時段進行硬條件過濾，再以可設定權重對預算、時段接近度、服務商評分及緊急能力排序；每筆媒合 MUST 保存分數版本與可供使用者理解的理由。

#### Scenario: 排除服務區域不符的服務商
- **WHEN** 服務商評分很高但不服務案件地區
- **THEN** 服務商不得因軟分數高而進入候選結果

#### Scenario: 相同輸入得到穩定排序
- **WHEN** 在資料與規則版本均未改變時重複媒合同一案件
- **THEN** 候選排序、分數與理由保持一致

#### Scenario: 高風險水電案件
- **WHEN** 水電案件含高風險旗標
- **THEN** 只有具對應緊急處理能力且服務區域符合的服務商可列入候選，並保留安全分流標記

#### Scenario: 偏好影響媒合結果
- **WHEN** 會員偏好檔含 `blockedVendorIds`
- **THEN** 媒合排除這些商家，且排序權重反映 `priceSensitivity`

### Requirement: 案件與媒合狀態分離
系統 MUST 分別維護案件狀態與每個候選服務商的媒合狀態。案件狀態 SHALL 使用 `submitted`、`matched`、`accepted`、`needs_information`、`in_progress`、`completed`、`cancelled` 或 `unmatched`；媒合狀態 SHALL 使用 `proposed`、`accepted`、`declined` 或 `expired`。

#### Scenario: 單一服務商婉拒
- **WHEN** 多個候選服務商中的一個將媒合狀態改為 `declined`
- **THEN** 其他候選仍可承接，案件不得直接標示為 `cancelled`

#### Scenario: 服務商承接
- **WHEN** 一個有權限的候選服務商成功承接案件
- **THEN** 該媒合變為 `accepted`、案件變為 `accepted`，其他仍為 `proposed` 的媒合依規則失效

#### Scenario: 沒有候選服務商
- **WHEN** 媒合完成後沒有任何符合硬條件的服務商
- **THEN** 案件變為 `unmatched`，消費者收到可放寬條件或等待人工處理的選項

### Requirement: 合法案件狀態機
系統 SHALL 只允許文件化的狀態轉移：`submitted` 可至 `matched`、`unmatched`、`cancelled`；`matched` 可至 `accepted`、`needs_information`、`unmatched`、`cancelled`；`accepted` 可至 `in_progress`、`needs_information`、`cancelled`；`needs_information` 可至 `submitted` 或 `cancelled`；`in_progress` 可至 `completed`、`needs_information` 或 `cancelled`。`completed` 與 `cancelled` MUST 為終止狀態。

#### Scenario: 正常完成案件
- **WHEN** 案件依序從 `submitted`、`matched`、`accepted`、`in_progress` 轉至 `completed`
- **THEN** 每次轉移均成功且歷程完整保留

#### Scenario: 終止狀態不可逆
- **WHEN** actor 嘗試將 `completed` 或 `cancelled` 案件轉為任何其他狀態
- **THEN** 系統拒絕轉移並保留原狀態與版本

#### Scenario: 補件後重新媒合
- **WHEN** 消費者補齊 `needs_information` 案件的必要資料並再次確認
- **THEN** 案件回到 `submitted`，使用新版本輸入重新執行媒合

### Requirement: 角色與資料可見性
系統 SHALL 以 Amazon Cognito 定義 `RESIDENT`、`PROVIDER` 與 `ADMIN` 群組，並在 API Gateway 驗證 JWT、在 Flask service layer 執行資源層級授權。住戶只能讀取自己的案件；廠商成員只能讀取其組織獲委派或承接的案件；管理員行為 MUST 被稽核。

#### Scenario: Flask 阻擋跨組織讀取
- **WHEN** 廠商成員嘗試透過 REST 或 MCP 工具查詢其他組織的案件
- **THEN** Flask 根據可信 actor context 與 RDS membership 拒絕，且 repository 不得收到未授權的跨組織查詢

#### Scenario: 管理員查詢
- **WHEN** 管理員基於支援目的讀取案件
- **THEN** 系統驗證管理員角色並記錄查詢原因、actor 與 request ID

### Requirement: PII 與非敏感摘要分離
案件 SHALL 以安全參照連結加密聯絡資料，並另外保存可供分類與媒合的非敏感摘要。媒合、狀態事件、模型 trace 及一般日誌 MUST NOT 複製完整 PII。

#### Scenario: 產生媒合摘要
- **WHEN** 案件建立完成
- **THEN** 媒合資料只包含服務條件、粗粒度地區與風險標記，不包含姓名、電話、Email 或詳細地址

#### Scenario: 已承接服務商取得必要聯絡資料
- **WHEN** 授權規則允許已承接服務商聯繫消費者
- **THEN** 系統以受稽核的專用讀取路徑解密最少必要欄位，不將資料寫入 MCP trace 或一般日誌

### Requirement: 五類端到端案件驗收
系統 MUST 能以相同案件生命週期處理五類表單；Supervisor SHALL 路由至對應領域 Agent，但不得建立類別專屬資料庫狀態機。

#### Scenario: 餐廳訂位端到端
- **WHEN** 完整餐廳需求經確認建立案件並找到候選餐廳
- **THEN** 案件可被候選服務商承接、更新進度並由消費者查詢

#### Scenario: 商品購買端到端
- **WHEN** 完整商品需求經確認建立案件且即時目錄有符合商品
- **THEN** 媒合結果引用可驗證商品與供應商資料，案件沿共用狀態機追蹤

#### Scenario: 家事服務端到端
- **WHEN** 完整家事需求含地區、規模、時段及寵物條件
- **THEN** 只有符合硬條件的服務商被媒合，並沿共用狀態機追蹤

#### Scenario: 水電修繕端到端
- **WHEN** 高風險水電需求完成安全提示與明確確認
- **THEN** 案件保留高風險標記並只媒合具相應能力的服務商

#### Scenario: 社區諮詢端到端
- **WHEN** 使用者不知道責任單位但提供足夠地區與議題資訊
- **THEN** 系統建立案件、媒合候選責任單位並在承接前遵守聯絡資料遮蔽偏好
