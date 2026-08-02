## ADDED Requirements

### Requirement: 商品需求的欄位蒐集順序
商品 Agent SHALL 依 `product-purchase.schema.json` 蒐集欄位，且 MUST 在取得下列全部欄位後才進入選品：商品需求描述、類別、預算上限、數量、收貨地區（縣市與行政區）、是否接受替代品。Agent MUST NOT 在 AI 對話中要求詳細門牌、收件人姓名或電話。缺少任一必填欄位時，Agent SHALL 只追問缺少的欄位，MUST NOT 重複詢問已取得的欄位。

#### Scenario: 一句話包含多個欄位
- **WHEN** 住戶說「想買一台除濕機，預算五千以內，送台北市內湖區」
- **THEN** 系統擷取品項、預算、數量預設 1 與收貨地區，接著只追問是否接受替代品

#### Scenario: 缺少收貨地區
- **WHEN** 住戶只描述商品與預算
- **THEN** 系統追問收貨的縣市與行政區，並明確說明不需要提供詳細門牌

#### Scenario: 不在對話蒐集聯絡資料
- **WHEN** 住戶主動在對話輸入手機號碼
- **THEN** 系統不將該值寫入案件摘要或 artifact，並提示聯絡資料會在受信任表單路徑另行蒐集

### Requirement: 住戶選品後才產生訂單摘要
系統 SHALL 在欄位齊全後進入 `awaiting_resident_selection`，並回傳候選 SKU 清單。住戶 MUST 透過選品操作明確指定一個 SKU，系統才產生訂單摘要 artifact 並進入 `awaiting_resident_confirmation`。系統 MUST NOT 在住戶未選品前建立訂單、預留庫存或委派供應商。

#### Scenario: 選品成功
- **WHEN** 住戶從候選清單選定一個 SKU
- **THEN** 系統產生 version 1 的 `draft` 訂單摘要 artifact，逐項顯示單價、數量、促銷、運費、實付金額、預估工作天與退換貨政策，並進入 `awaiting_resident_confirmation`

#### Scenario: 選擇不在候選清單的 SKU
- **WHEN** 選品請求的 SKU 不在該案件目前候選清單中
- **THEN** 系統回傳驗證錯誤，案件 stage 不變，MUST NOT 建立 artifact

#### Scenario: 選品時庫存已不足
- **WHEN** 住戶選定的 SKU 在選品瞬間可售量已低於需求數量
- **THEN** 系統回傳衝突錯誤、重新計算候選清單並停留在 `awaiting_resident_selection`

#### Scenario: 住戶改選其他商品
- **WHEN** 住戶在 `awaiting_resident_confirmation` 改選另一個 SKU
- **THEN** 系統建立新版本 artifact、將舊版本標為 `superseded`，且舊版本的確認不得用於建立訂單

### Requirement: 確認後才建立 Demo 訂單並模擬付款授權
住戶明確確認 artifact 後，系統 SHALL 以 `order_type='05'` 建立 Demo 訂單、寫入 `order_status='01'`（待付款），並進入 `authorizing_payment`。付款授權 SHALL 為明確標示的 mock adapter；授權成功後 `order_status` 轉為 `'02'`（待確認）並進入 `waiting_provider_response`。系統 MUST NOT 宣稱已完成真實扣款、真實金流授權或任何不可逆外部交易。

#### Scenario: 確認並完成 mock 授權
- **WHEN** 住戶回覆確認送出
- **THEN** 系統建立 `order_status='01'` 訂單、執行 mock 授權後轉為 `'02'`，並在對話明確說明這是 Demo 模擬授權、未產生真實扣款

#### Scenario: 未確認不建立訂單
- **WHEN** 住戶在 `awaiting_resident_confirmation` 詢問其他問題但未表示確認
- **THEN** 系統回答問題並維持 stage，MUST NOT 建立訂單或呼叫付款授權

#### Scenario: mock 授權失敗
- **WHEN** mock 付款授權回傳失敗
- **THEN** 案件停留在 `authorizing_payment`、訂單維持 `order_status='01'`，並向住戶說明可重試，MUST NOT 委派供應商

### Requirement: 供應商委派、回覆與自動改派
授權完成後系統 SHALL 依確定性規則排序候選供應商並委派第一順位，建立 `pending` workflow task。供應商 SHALL 只能對自己組織目前可操作的 task 執行 `accept`、`decline` 或 `needs_information`。Flask MUST 驗證供應商 membership、task status、`expectedVersion` 與 `Idempotency-Key`。`accept` MUST 附帶預計出貨資訊；`needs_information` MUST 附帶具體問題。`decline` 或管理員模擬逾時 SHALL 立即改派下一順位供應商；無下一順位時案件轉為 `unmatched` 並向住戶說明。

#### Scenario: 供應商承接
- **WHEN** 受派供應商送出 `accept` 與預計出貨時程
- **THEN** `order_status` 轉為 `'03'`（已確認）、stage 轉為 `provider_confirmed`，住戶對話收到含供應商、金額、預計出貨與退換貨政策的最終結論

#### Scenario: 供應商要求補充
- **WHEN** 受派供應商送出 `needs_information` 與具體問題
- **THEN** 原始問題不可變保存、task 完成、stage 轉為 `waiting_resident_information`，並在住戶對話顯示該追問

#### Scenario: 供應商婉拒後改派
- **WHEN** 受派供應商送出 `decline`
- **THEN** 該媒合標記為 `declined`，系統依原排序建立下一順位供應商 task，stage 回到 `waiting_provider_response`

#### Scenario: 非受派供應商嘗試操作
- **WHEN** 未被指派的供應商對該 task 送出任何 action
- **THEN** 系統回傳 403，且錯誤訊息不得洩漏案件內容或住戶資料

#### Scenario: 重試不重複建立
- **WHEN** 供應商以相同 `Idempotency-Key` 與相同 payload 重複送出 `accept`
- **THEN** 系統回傳與首次相同的結果，MUST NOT 重複建立訊息、task、媒合或訂單狀態轉移

#### Scenario: 相同金鑰不同內容
- **WHEN** 供應商以相同 `Idempotency-Key` 送出不同 payload
- **THEN** 系統回傳 409，且不套用任何變更

### Requirement: 缺貨處理
當所有候選 SKU 的可售量皆不足需求數量時，系統 SHALL 依住戶的替代品接受度處理。接受替代品時 SHALL 提供近似規格候選；不接受替代品時 SHALL 進入 `out_of_stock`、揭露已知 `restock_eta` 並結束本次流程，且 MUST NOT 建立訂單。

#### Scenario: 不接受替代品且全部缺貨
- **WHEN** 住戶不接受替代品且符合條件的 SKU 全部可售量為 0
- **THEN** stage 轉為 `out_of_stock`，回覆揭露已知補貨時間或說明補貨時間未定，且不建立訂單

#### Scenario: 缺貨後改為接受替代品
- **WHEN** 住戶在 `out_of_stock` 後表示願意接受替代品
- **THEN** 系統重新搜尋並回到 `awaiting_resident_selection`，MUST NOT 沿用先前已失效的候選清單

### Requirement: 商品案件的資源授權與 PII 邊界
選品、確認與案件查詢 SHALL 只允許案件 owner 執行；系統 MUST 以受信任 request context 判斷 actor，MUST NOT 接受 request body 覆寫身分。供應商可見版本 SHALL 只包含商品明細、數量、金額與收貨的縣市／行政區，MUST NOT 包含詳細門牌、收件人姓名、電話或 Email。

#### Scenario: 跨住戶存取
- **WHEN** 住戶 A 嘗試對住戶 B 的案件選品
- **THEN** 系統回傳 403 或 404，MUST NOT 洩漏該案件是否存在的商品內容

#### Scenario: 供應商看到的遮蔽版本
- **WHEN** 供應商開啟受派 task 的需求文件
- **THEN** 文件顯示商品、數量、金額與收貨行政區，不含詳細門牌與聯絡資料

### Requirement: 商品訂單狀態機
商品訂單 SHALL 只允許下列轉移，且 MUST 對齊命題 `mms_order_record` 於 `order_type='05'` 定義的狀態碼：

```text
01 待付款 -> 02 待確認 | 90 已取消
02 待確認 -> 03 已確認 | 90 已取消
03 已確認 -> 04 進行中 | 90 已取消
04 進行中 -> 80 已完成 | 90 已取消
80 已完成 -> 99 已退款
90 已取消, 99 已退款 -> terminal
```

狀態更新 SHALL 使用 `expectedVersion` 樂觀鎖，且狀態與事件 MUST 於同一資料庫交易寫入。本 change 的 MVP 驗收終點為 `03 已確認`；`04`、`80`、`99` 的觸發條件延後決策。

#### Scenario: 非法轉移被拒絕
- **WHEN** 嘗試將 `order_status` 由 `'01'` 直接改為 `'03'`
- **THEN** 系統回傳衝突錯誤且不寫入任何狀態或事件

#### Scenario: 版本衝突
- **WHEN** 兩個請求以相同 `expectedVersion` 同時更新同一訂單
- **THEN** 只有一個成功並使版本加一，另一個回傳 409

#### Scenario: 事件與狀態同時寫入
- **WHEN** 狀態轉移過程中事件寫入失敗
- **THEN** 訂單狀態一併回滾，不留下狀態已改但無事件的紀錄
