# 任務：住戶評價商家並回饋媒合排序

每個任務都配一個客觀驗證步驟。`.kiro/hooks/verify-after-spec-task.json` 會在任務
標記完成後自動跑完整檢查（API 測試、compileall、前端測試、build、lint）。

- [ ] 1. 建立對應的 OpenSpec change `add-provider-reviews`
  - 依 `openspec/changes/` 既有格式撰寫 proposal、design、spec、tasks
  - spec 需求需與本 spec 的需求 1~6 對得上
  - _驗證_：requirements 使用 SHALL／MUST，且含成功、授權、驗證失敗、重複提交與 prompt 隔離情境
  - _需求_：全部

- [ ] 2. 建立評價計算模組 `packages/api/walking_skeleton/reviews.py`
  - 分數白名單驗證（總分 1~5 必填、分項選填、文字長度上限）
  - 貝氏平滑 `rankingScore`，`C = 20`、`m = 3.8` 為模組常數
  - `_public_review_summary()` 回傳不含 `commentText`
  - _驗證_：1 筆 5 星的 rankingScore 低於 4.6 分 301 則；不合法分數丟 ValidationError
  - _需求_：2, 3, 4

- [ ] 3. 新增 store 欄位與持久化
  - `store.py` 加 `reviews`、`review_summaries`，皆為以 id 為鍵的 dict
  - `rds_store.STATE_FIELDS` 同步加入兩個欄位
  - _驗證_：`_restore_state` 對非 Mapping 欄位會丟錯，測試需證明 dict 形態可正確 snapshot／restore
  - _需求_：1, 4

- [ ] 4. 實作提交評價的 service 轉移
  - 僅 `completed` 且 owner 可評；一案一評；`comment_status` `01`→`02`
  - 驗證置於 `store.idempotent` 之前，錯誤不得推進狀態
  - 寫入 `resident_submitted_review` 事件，內容不含評價原文
  - _驗證_：非 completed 回 409；非 owner 回 403；重複提交回 409 且只有一筆評價；不合法分數回 422 且 `comment_status` 不變
  - _需求_：1, 2

- [ ] 5. 實作聚合投影更新
  - 每筆評價寫入後同步更新 `review_summaries`
  - _驗證_：連續寫入多筆後平均與樣本數正確，`rankingScore` 隨樣本數收斂
  - _需求_：4

- [ ] 6. 新增 REST 路由
  - `POST`／`GET /api/v1/service-requests/{id}/review`、`GET /api/v1/provider-reviews`
  - 住戶寫入要求 `Idempotency-Key`
  - _驗證_：缺 header 回 422；廠商只能讀自己的聚合；跨廠商讀取回 403
  - _需求_：1, 6

- [ ] 7. 媒合排序改為加權分數
  - 硬條件過濾維持在加權之前
  - 排序理由含分數與樣本數
  - 權重帶版本號
  - _驗證_：不在服務區的高分廠商不得入選；相同輸入重複媒合結果一致；理由字串含「評價 x.x（n 則）」
  - _需求_：5

- [ ] 8. 驗證評價文字不進入 prompt 與日誌
  - 以含疑似指令與含聯絡資料的評價文字作為 fixture
  - _驗證_：媒合結果不受 injection 影響；prompt、trace、`_event` 內容皆不含評價原文
  - _需求_：3

- [ ] 9. 前端：住戶評價入口與表單
  - `MyBookingsPage` 在 `completed` 未評價時顯示入口，已評價顯示星等
  - 表單標示文字「不會提供給 AI」
  - _驗證_：`tsc -b`、`oxlint`、`node --test` 通過；presentation 函式有測試涵蓋未評價與已評價
  - _需求_：1, 2, 3

- [ ] 10. 前端：廠商端只讀聚合
  - `DashboardPage` 顯示自己的聚合分數與樣本數
  - _驗證_：型別不含他人資料；build 與 lint 通過
  - _需求_：6

- [ ] 11. 文件收斂
  - 更新 `SPEC.md` 的消費者流程與非目標
  - 新增 ADR 記錄「評價文字不進 prompt」與「貝氏平滑冷啟動」兩個決策
  - _驗證_：ADR 列出替代方案與後果；`SPEC.md` 僅保留摘要與連結
  - _需求_：3, 4
