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

### Requirement: 會員長期記憶讀寫
領域 Agent SHALL 在每輪開始前讀取該會員已登錄的常用地址、家電清單與偏好，並 MUST NOT 重複詢問記憶中已有且仍有效的欄位。觀察到長期偏好時 Agent SHALL 以欄位層 merge 寫回偏好檔，MUST NOT 整列覆蓋。記憶內容在送入模型或 MCP tool 前 MUST 完成 PII 遮蔽。偏好如何影響候選排除與排序權重，由 `service-request-matching-lifecycle` 的確定性媒合需求規範。

#### Scenario: 已登錄家電不重複詢問
- **WHEN** 會員家電清單已有主臥分離式冷氣，且住戶描述該機器故障
- **THEN** Agent 直接引用該機型繼續追問症狀，不再詢問品牌、型號與安裝年份

#### Scenario: 長期偏好以 merge 寫回
- **WHEN** 住戶在對話中表達只考慮低價方案
- **THEN** Agent 更新 `priceSensitivity`，既有 `preferredVendorTags` 與 `notes` 不被清空

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

### Requirement: 領域 Agent 每輪模型理解與封閉抽取輸出
領域 Agent SHALL 在 Runtime 內對每一輪住戶訊息執行核准模型推論，產生追問文案與結構化欄位抽取，並以 `contracts/runtime/agent-turn.json` 的封閉 `extractedFields` 回傳。Agent MUST NOT 只依賴關鍵字比對決定欄位值，也 MUST NOT 回傳契約未定義的鍵。Runtime 對模型的每次請求 MUST 通過與 Flask 相同的 Bedrock request gate 與模型白名單。

#### Scenario: 一句話同時提供多個欄位
- **WHEN** 住戶在同一句話提供症狀、地區與可到場時段
- **THEN** Agent 在同一輪抽出全部三個欄位，`missingFields` 只保留仍缺少的項目，且不重複追問已取得的欄位

#### Scenario: 未命中固定詞表的自然語句
- **WHEN** 住戶以固定詞表未涵蓋的說法描述時段或地區（例如「禮拜六白天都可以」）
- **THEN** Agent 仍抽出可用值並繼續推進流程，不得以同一句追問重複卡住同一欄位

#### Scenario: 抽取結果必須可稽核
- **WHEN** Agent 完成一輪模型推論
- **THEN** trace 記錄該輪 `model_invoke` 與所用模型 ID，`reasoning.mode` 為 `model`，且不含完整 prompt、個資或秘密

### Requirement: Flask 對模型抽取結果的驗證式合併
Flask application service SHALL 對 `extractedFields` 逐欄位重新驗證後才寫入案件狀態：允許鍵以 allowlist 限定，地區必須命中受控地區主檔，字串長度與列舉值必須符合契約。模型自由文字 MUST NOT 直接成為案件狀態、媒合分數或委派決定。

#### Scenario: 丟棄契約外的鍵
- **WHEN** Runtime 回傳契約未定義的欄位或型別不符的值
- **THEN** Flask 丟棄該鍵並保留原有狀態，不因此拒絕整輪對話

#### Scenario: 地區超出 Demo 服務範圍
- **WHEN** 住戶提供的地區可被辨識，但不在受控地區主檔或沒有可服務廠商
- **THEN** 系統明確告知目前 Demo 服務範圍並請住戶改提供範圍內地區，不得寫入未知地區，也不得以同一追問無限重複

#### Scenario: 模型不得放寬安全狀態
- **WHEN** 確定性安全檢查已判定高風險
- **THEN** 即使模型回傳 `riskScreenAnswered` 或全為 false 的 `hazardFlags`，系統仍維持 safety hold 與既有 hazard flag，且不進行媒合

### Requirement: Knowledge Base 檢索的固定領域過濾與非事實邊界
領域 Agent 查詢 Managed Knowledge Base SHALL 固定套用該 Agent 的 `service_type` metadata filter，並將檢索結果僅作為說明性參考回傳。檢索內容 MUST NOT 成為欄位值、媒合條件或狀態判斷依據；檢索失敗 MUST NOT 阻斷安全提示與流程推進。

#### Scenario: 檢索固定領域過濾
- **WHEN** 水電 Agent 查詢 Knowledge Base
- **THEN** 請求帶入 `service_type = utility_repair` 的 equals filter，回傳的每一筆參考都標記其 `service_type` 與 `doc_kind`

#### Scenario: 檢索失敗或無結果
- **WHEN** Knowledge Base 呼叫失敗或沒有相關 chunk
- **THEN** Agent 仍完成該輪追問或安全提示，`reasoning.knowledgeBaseQueried` 誠實反映結果，且不臆造來源

### Requirement: 模型不可用時的誠實降級
當核准模型呼叫失敗或回傳不符契約的輸出時，Runtime SHALL 以固定規則完成該輪並將 `reasoning.mode` 標記為 `rule-fallback` 並附上非敏感 `degradedReason`。系統 MUST NOT 在此情況宣稱模型已執行，也 MUST NOT 因降級而略過安全篩檢或建案前確認。

#### Scenario: 模型呼叫失敗
- **WHEN** Bedrock 呼叫拋出錯誤或超出時間限制
- **THEN** 該輪以 Runtime 固定規則回應，`reasoning.mode` 為 `rule-fallback`，且對話與進度不進入錯誤狀態

#### Scenario: 高風險文案不由模型撰寫
- **WHEN** 該輪判定為高風險或處於 safety hold
- **THEN** 停止操作與緊急聯繫指引使用固定文案，不採用模型生成內容

### Requirement: 關鍵字未命中時的 fail-closed 模型分類
Supervisor SHALL 先以確定性方式路由：命中單一領域關鍵字或已有 active agent 時不得花費模型呼叫。關鍵字未命中且模型可用時，Supervisor SHALL 以核准模型將該句分類為五類之一、模糊或不支援，並只接受核准的 `service_type` 值。模型回傳核准清單以外的值、未使用工具或呼叫失敗時，MUST 退回澄清或不支援回覆，MUST NOT 臆造領域。

#### Scenario: 口語描述未命中詞表
- **WHEN** 住戶第一句是「廚房水槽下面在滴水」這類詞表未涵蓋的說法
- **THEN** Supervisor 以模型分類為 `utility_repair` 並交給水電 Agent，`route.reasonCode` 為 `model_classification`，trace 保留 Supervisor 的分類紀錄

#### Scenario: 關鍵字已足夠
- **WHEN** 住戶訊息命中單一領域關鍵字，或請求已帶 active agent
- **THEN** Supervisor 直接路由，不產生分類用的模型請求

#### Scenario: 分類結果不在核准清單
- **WHEN** 模型回傳五類以外的服務類別、沒有使用分類工具，或分類呼叫失敗
- **THEN** 系統回覆目前支援的服務範圍，`route.agent` 為 null，且不建立任何案件
