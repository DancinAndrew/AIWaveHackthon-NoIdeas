## 1. 點數發放引擎

- [x] 1.1 `points.grant_reward` 以完工金額重算並產生 `02 已發放` 投影，保留 `estimatedPoints`／`estimatedBasisAmount`；驗證：5000 預估 → 6200 完工得 62 點且 `amountAdjusted` 為 true。
- [x] 1.2 未回報完工金額時沿用訂單成立時的基礎與來源；驗證：得 50 點、`amountAdjusted` 為 false。
- [x] 1.3 `points.ledger_entry` 產生 append-only 項目，僅含金額與點數，不含個資；驗證：測試斷言項目欄位與 `direction` 為 `earn`。
- [x] 1.4 `points.grant_disclosure_sentence` 在金額調整時說明原預估；驗證：句子含「訂單成立時預估 50 點」與「尚未連動 OPENPOINT 正式帳戶」。

## 2. 狀態機與授權

- [x] 2.1 新增 `awaiting_resident_acceptance` 與 `completed` 兩個 stage 與對應 label；驗證：進度投影回傳正確 `displayLabel` 與 `waitingFor`。
- [x] 2.2 `provider_report_completion` 授權先於驗證，且僅允許 `provider_confirmed`；驗證：未指派廠商得 403、案件未確認得 409。
- [x] 2.3 完工金額驗證置於 `store.idempotent` 之前；驗證：五種不合法金額皆回 422 且案件維持 `provider_confirmed`。
- [x] 2.4 住戶僅在明確驗收語句時結案，回報問題維持等待驗收；驗證：描述施工問題後 stage 不變且流水帳為空。
- [x] 2.5 以流水帳擋重複發放；驗證：重複驗收後該案件 `earn` 項目仍只有一筆。

## 3. 持久化

- [x] 3.1 `store.point_ledger` 以 `ledgerId` 為鍵的 dict；驗證：`RdsJsonStore._restore_state` 要求每個欄位為 JSON object，用 list 會在還原時失敗。
- [x] 3.2 `rds_store.STATE_FIELDS` 同步加入 `point_ledger`；驗證：漏加會讓 staging 靜默遺失流水帳，`_snapshot_state` 以 `STATE_FIELDS` 決定寫入範圍。

## 4. 介面

- [x] 4.1 新增 `GET /api/v1/provider-active-cases`；驗證：只回傳該廠商已承接未完成的案件，並以 `canReportCompletion` 標示可否回報。
- [x] 4.2 新增 `POST /api/v1/provider-active-cases/{id}/completion`，需 `Idempotency-Key`；驗證：同 key 重試不重複推進狀態。
- [x] 4.3 廠商後台新增「進行中」區塊與完工說明／完工金額表單；驗證：`npm run build` 與 `npm run lint` 通過。
- [x] 4.4 「我的預約」以綠色區塊呈現已入帳並顯示原預估差異；驗證：`node --test` 覆蓋已發放與待發放兩種呈現。
- [x] 4.5 `provider_confirmed` 分頁歸類改為進行中；驗證：測試斷言其 `filter` 為 `upcoming`、`completed` 為 `completed`。

## 5. 文件

- [x] 5.1 建立本 OpenSpec change 的 proposal、spec 與 tasks；驗證：requirements 使用 SHALL／MUST 並含成功、授權、驗證失敗與重複發放情境。
- [x] 5.2 更新 `SPEC.md` 的 MVP 消費者流程，加入完工驗收與點數入帳。

## 6. 後續變更（本變更不做）

- [ ] 6.1 住戶評價、`comment_status` 轉移、聚合投影與媒合排序整合（評價文字不得進入 prompt）。
- [ ] 6.2 折抵、退點與 `04 已取消` 收回轉移。
- [ ] 6.3 發放冷卻期（對應主辦訂位類「7 天後核銷」），可考慮由 Step Functions wait state 實作。
