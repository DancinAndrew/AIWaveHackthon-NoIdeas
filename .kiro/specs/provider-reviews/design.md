# 設計：住戶評價商家並回饋媒合排序

## 資料模型

`store.py` 新增兩個欄位，**都必須是以 id 為鍵的 dict**，因為
`RdsJsonStore._restore_state` 對每個 `STATE_FIELDS` 都做
`isinstance(value, Mapping)` 檢查，用 list 會在還原時丟
`RDS demo state field ... must be an object`。同時要同步
`rds_store.STATE_FIELDS`，漏加會讓本機測試全過但 staging 靜默遺失資料。

```
reviews: dict[review_id, {
  reviewId, serviceRequestId, residentId, providerId, serviceType,
  overallScore,                       # 1..5 必填
  professionalism, punctuality,       # 1..5 選填
  priceTransparency, attitude,        # 1..5 選填
  tags: list[str], commentText: str,
  status,                             # published / hidden
  createdAt, updatedAt
}]

review_summaries: dict["{providerId}:{serviceType}", {
  providerId, serviceType,
  reviewCount, averageOverall,        # 本平台實際完成案件
  averageProfessionalism, averagePunctuality,
  averagePriceTransparency, averageAttitude,
  rankingScore,                       # 貝氏平滑後，供排序使用
  updatedAt
}]
```

一案一評由 `serviceRequestId` 唯一性保證。記憶體 store 以查找既有評價實作，
正式化到 RDS 時對應 `UNIQUE (service_request_id)`。

## 評價文字的隔離邊界

這是本功能最關鍵的設計決定，理由見 requirements 需求 3。

```
評價文字 ──→ 前端顯示給人看（唯一出口）
   │
   └──✗ prompt / Knowledge Base / trace / 一般日誌

數值分數 ──→ 聚合投影 ──→ 媒合排序 ──→ 可解釋理由
```

實作上以模組邊界強制：`matching` 只接收 `review_summaries` 的數值欄位，
不接收 `reviews`。`_public_review_summary()` 的回傳不含 `commentText`，
讓「不小心把文字帶進排序」在介面層就不成立。

## 冷啟動：貝氏平滑

`data/mock/master/providers.json` 的合成評分（3.4~4.6、213~715 則）與新產生的
真實評價不能混用裸平均，否則「一筆 5 星的新廠商」會贏過「4.6 分 301 則」。

```
rankingScore = (C × m + Σ overallScore) / (C + n)

C = 20        先驗樣本數
m = 3.8       全站先驗平均（取 mock 資料的中位水準）
n             本平台實際評價數
```

`C` 與 `m` 放在模組常數並以測試釘住。UI 上「平台歷史評分」與
「本平台完成案件評分」分開顯示，不把兩種來源混成一個數字。

## 媒合排序

現行是確定性 tuple `(responseSlaHours, -rating, providerId)`。改為加權分數，
因為 `SPEC.md` 要求可解釋理由，而純 lexicographic 會讓評分永遠只是 SLA 的附屬。

`packages/backend/src/agents/quoting.ts` 的 `scoreVendor` 是舊 TypeScript 參考
（`quality = rating/5 × 0.8 + 案件數 × 0.2`），可轉譯但不可直接使用 —— 該目錄
是合併前參考，不是現行架構。

硬條件過濾（服務區、能力、啟用狀態）**維持在加權之前**，評分高不得讓不在服務區的
廠商入選。加權只決定通過硬條件者的順序。權重以版本號記錄，讓「相同輸入結果一致」
可被測試。

## 介面

```
POST /api/v1/service-requests/{id}/review     住戶提交，需 Idempotency-Key
GET  /api/v1/service-requests/{id}/review     住戶讀自己的評價
GET  /api/v1/provider-reviews                 廠商讀自己的聚合與內容
```

住戶寫入要求 `Idempotency-Key`：雖然 README 的表格只對廠商與管理員寫入要求，
但一案一評是不可逆的狀態轉移（`comment_status` `01`→`02`），重試不得產生第二筆。

驗證一律在進入交易前完成，沿用 `provider_response` 與
`provider_report_completion` 的既有模式，格式錯誤不得推進 `comment_status`。

## 前端

- `MyBookingsPage`：`completed` 且未評價的卡片顯示「評價」入口；已評價顯示星等。
- 新增評價表單元件：總分必填星等、分項選填、文字選填並標示「不會提供給 AI」。
- `DashboardPage`：廠商區塊顯示自己的聚合分數與樣本數，只讀。

## 未解決的問題

- 評價可修改期限（N 天）尚未決定，目前設計為建立後不可改，`updatedAt` 欄位先預留。
- `m = 3.8` 的先驗平均取自 mock 資料的目視中位；真實資料進來後應重新校準。
