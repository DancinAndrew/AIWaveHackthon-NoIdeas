## ADDED Requirements

### Requirement: 商品目錄只從結構化來源取得
商品的 SKU、名稱、品牌、規格、類別、定價、促銷、配送方式與退換貨代碼 SHALL 只從結構化商品目錄取得（Demo 為 `data/mock/master/products.json`，正式為 RDS `mms_product`）。Knowledge Base MUST NOT 作為價格、庫存、補貨時間、促銷是否仍在檔期或案件狀態的來源。當目錄來源不可用時，系統 SHALL 回傳明確錯誤，MUST NOT 以 Knowledge Base 或模型記憶推測商品資料。

#### Scenario: 住戶詢問價格
- **WHEN** 住戶問「這台除濕機多少錢」
- **THEN** 系統從結構化目錄取得該 SKU 的 `list_price`、`sale_price` 與促銷後金額，回覆中的每個數字都可追溯至目錄欄位

#### Scenario: 目錄來源不可用
- **WHEN** 商品目錄載入失敗
- **THEN** 系統回覆目前無法查詢商品並保留案件於 `collecting_details`，MUST NOT 回覆任何金額、庫存或到貨天數

#### Scenario: 政策問題交給 Knowledge Base
- **WHEN** 住戶問「七日內可以退貨嗎」
- **THEN** 系統以 Knowledge Base 的退換貨政策作答，並註明實際適用條款以商品退換貨代碼為準

### Requirement: 可售量必須扣除保留量
可售量 SHALL 定義為 `stock_on_hand - reserved`，且 MUST 以非負整數表示。系統 MUST NOT 以 `stock_on_hand` 單獨判斷可售。當可售量小於住戶需求數量時，該 SKU SHALL 標記為不足，並附帶 `restock_eta`（可為未知）。

#### Scenario: 保留量導致不足
- **WHEN** 某 SKU `stock_on_hand` 為 3、`reserved` 為 2，住戶需求數量為 2
- **THEN** 該 SKU 的可售量為 1，被標記為不足，且候選清單不得將其呈現為可立即出貨

#### Scenario: 補貨時間未知
- **WHEN** 不足的 SKU 其 `restock_eta` 為 null
- **THEN** 系統回覆補貨時間未定，MUST NOT 推估任何日期

### Requirement: 候選商品搜尋為確定性規則
候選搜尋 SHALL 分為硬條件與軟排序兩階段。硬條件 MUST 包含：品項或類別命中、單價不超過預算上限、可售量滿足需求數量。若住戶宣告品牌偏好或必要規格，MUST 於硬條件套用；若住戶標記接受替代品，系統 MAY 在硬條件放寬品牌與非必要規格後補足候選，且 MUST 標示該候選為替代品。軟排序 MUST 為版本化規則，於相同資料快照與相同輸入下產生相同排序。模型 MAY 調整說明文字，MUST NOT 變更任何金額、庫存、到貨天數或排序所依據的分數。

#### Scenario: 完整條件命中
- **WHEN** 住戶要求「除濕機、預算 5000 元以內、數量 1、台北市內湖區」
- **THEN** 系統回傳單價不超過 5000 元且可售量至少 1 的除濕機候選，並附每筆的排序理由

#### Scenario: 不接受替代品且無完全符合
- **WHEN** 住戶指定品牌且標記不接受替代品，該品牌無可售 SKU
- **THEN** 系統回傳空候選並說明原因，MUST NOT 改推其他品牌

#### Scenario: 接受替代品
- **WHEN** 住戶標記接受替代品且指定品牌無庫存
- **THEN** 系統補入近似規格的其他品牌候選，且每筆明確標示為替代品

#### Scenario: 排序可重現
- **WHEN** 以相同資料快照、相同需求與相同規則版本重複搜尋
- **THEN** 候選順序與分數完全一致

### Requirement: 訂單金額由確定性規則計算
訂單金額 SHALL 由系統計算並逐項揭露：`original_amount`（單價 × 數量）、`discount_amount`（促銷折抵）、`shipping_fee_amount`（運費，達免運門檻時為 0）、`final_amount`（實付）。運費 MUST 取自該 SKU 的配送方式；`free_over` 判斷 MUST 以促銷後小計為基準。金額 MUST NOT 由模型產生或修改。

#### Scenario: 達免運門檻
- **WHEN** 促銷後小計為 1200 元、配送方式免運門檻為 990 元
- **THEN** `shipping_fee_amount` 為 0，且 artifact 明確顯示已達免運

#### Scenario: 未達免運門檻
- **WHEN** 促銷後小計為 500 元、配送方式運費 120 元、免運門檻 990 元
- **THEN** `final_amount` 為 620 元，且各項金額逐項顯示

#### Scenario: 促銷有數量門檻
- **WHEN** 促銷 `applies_from_quantity` 為 2 而住戶數量為 1
- **THEN** `discount_amount` 為 0，且回覆說明未達促銷數量門檻

### Requirement: 配送方式限制必須遵守
系統 SHALL 依商品的配送方式代碼套用限制。大型商品專車與冷鏈商品 MUST NOT 提供超商取貨。當住戶要求的到貨期限早於配送方式的預估工作天時，系統 SHALL 明確告知無法保證，並 MUST NOT 承諾到貨日。

#### Scenario: 大型家電不可超商取貨
- **WHEN** 候選為大型商品專車配送的除濕機，住戶要求超商取貨
- **THEN** 系統說明該商品僅能專車配送，並保留住戶改選其他候選的機會

#### Scenario: 到貨期限無法滿足
- **WHEN** 住戶要求兩天內到貨，候選配送預估為 7 個工作天
- **THEN** 系統揭露預估工作天並說明無法保證，MUST NOT 顯示可於期限內到貨
