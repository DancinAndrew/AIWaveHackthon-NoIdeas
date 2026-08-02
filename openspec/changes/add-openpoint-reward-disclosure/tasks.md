## 1. 點數計算引擎

- [x] 1.1 建立 `packages/api/walking_skeleton/points.py`，沿用 `mms_order_record` 的 `point_status` 代碼，費率以萬分位整數表示；驗證：相同基礎金額重複計算結果一致，1% × 5000 得 50 點、1% × 2800 得 28 點。
- [x] 1.2 實作單筆上限與 `capped` 標記；驗證：基礎金額 1000000 得 500 點且 `capped` 為 true。
- [x] 1.3 實作 `normalize_reported_amount` 白名單驗證；驗證：0、負數、`"abc"`、布林 `true` 與 1000001 全部回傳 422。
- [x] 1.4 實作 `reward_disclosure_sentence`，同時包含點數、金額來源、發放條件與 Demo 記帳邊界；驗證：句子含「待發放」與「尚未連動 OPENPOINT 正式帳戶」。

## 2. Service layer 與契約

- [x] 2.1 在 accept 分支產生 `pointsReward` 並保存於案件；驗證：承接回應含 `pointsReward`，狀態為 `01`。
- [x] 2.2 金額驗證置於 `store.idempotent` 之前；驗證：不合法金額回傳 422 後任務仍為 `pending` 且 `version` 為 1。
- [x] 2.3 案件投影與進度投影帶出 `pointsReward`；驗證：`GET /api/v1/service-requests` 與 `.../progress` 皆可讀到點數，未承接時為 null。
- [x] 2.4 寫入 `points_reward_estimated` 狀態事件；驗證：進度事件清單含該事件型別，內容不含個資。

## 3. 前端揭露

- [x] 3.1 `types.ts` 新增 `PointsReward` 與 `PointStatus`，`ProviderTaskResponse` 新增選填 `estimatedAmount`；驗證：`npm run build` 的 `tsc -b` 通過。
- [x] 3.2 `viewModels.ts` 新增 `pointsRewardPresentation`；驗證：`node --test` 覆蓋一般與套用上限兩種情形。
- [x] 3.3 「我的預約」卡片顯示 OPENPOINT 區塊，含預計點數、計算依據、發放狀態與 Demo 邊界；驗證：`npm run lint` 通過且測試斷言 note 含發放條件與未連動正式帳戶。
- [x] 3.4 廠商後台可回報預估金額並在已處理卡片顯示已告知住戶的點數；驗證：非整數或超出範圍時前端先阻擋並提示。

## 4. 文件

- [x] 4.1 建立本 OpenSpec change 的 proposal、design、spec 與 tasks；驗證：requirements 使用 SHALL／MUST 並含成功、未達揭露時機、驗證失敗與安全邊界情境。
- [x] 4.2 新增 ADR 記錄 OPENPOINT 以平台內 Demo 記帳呈現的決策與後果；驗證：ADR 列出替代方案與風險。
- [x] 4.3 更新 `SPEC.md` 的 MVP 範圍與非目標，讓產品邊界先於實作被記錄；驗證：`SPEC.md` 明示不對 OPENPOINT 正式帳戶發點。

## 5. 後續變更的前提（本變更不做）

- [ ] 5.1 服務完成與住戶驗收生命週期（`in_service` → `awaiting_resident_acceptance` → `completed`）。
- [ ] 5.2 `mms_point_ledger` append-only 流水帳與 `02 已發放` 轉移。
- [ ] 5.3 住戶評價、聚合投影與媒合排序整合（評價文字不得進入 prompt）。
