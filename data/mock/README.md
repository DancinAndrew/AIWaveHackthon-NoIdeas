# data/mock — 五類服務模擬資料集

全部由 `tools/datagen/` 以固定 seed（20260801）生成，**同一 seed 重跑 sha256 完全相同**。
重建：

```bash
.venv/bin/python tools/datagen/run_all.py
```

`manifest.json` 記錄每個檔案的筆數與 sha256。`data/competition/` 是原始命題檔，唯讀不改。

## 檔案一覽

### geo — 地理代碼

| 檔案 | 筆數 | 說明 |
|---|---|---|
| `geo/counties.json` | 22 | 縣市代碼（來自命題檔） |
| `geo/districts.json` | 368 | 全國行政區。命題檔只有 200 筆、缺 8 個縣市（台中、彰化、雲林、嘉義縣市、苗栗、新竹市、南投），已補齊 code 070~237 共 168 筆並標 `source: filled` |

### master — 結構化主檔

| 檔案 | 筆數 | 說明 |
|---|---|---|
| `master/providers.json` | 96 | 五類服務商共用結構：能力、證照、計價、SLA、每日容量 |
| `master/provider_service_areas.json` | 273 | 服務商 × 行政區。覆蓋 19 縣市 / 174 個行政區 |
| `master/provider_availability.json` | 2694 | 家事／水電／社區單位的 21 天可預約時段與剩餘容量 |
| `master/restaurants.json` | 40 | 10 種料理 × 4 家，含營業時間、桌型、低消、訂金、取消規則、飲食支援 |
| `master/restaurant_slots.json` | 8298 | 餐廳 × 日期 × 時段 × 桌型的可訂桌數 |
| `master/products.json` | 300 | SKU：規格、價格、促銷、配送、退換貨、保固 |
| `master/product_inventory.json` | 300 | 庫存與補貨預計時間 |
| `master/housekeeping_offerings.json` | 144 | 服務項目 × 計價模式（計時／按坪／按台／固定價） |
| `master/repair_technicians.json` | 56 | 技師專長、證照、勘查費、緊急能力 |
| `master/communities.json` | 20 | 社區／大樓 |
| `master/responsible_units.json` | 10 | 責任單位、受理範圍、SLA、轉介與升級規則 |

### knowledge — 靜態知識（Knowledge Base）

五份 markdown，每類一份，含 FAQ／注意事項／服務條款／SOP。
frontmatter 的 `never_authoritative_for` 明確列出**不得由 KB 回答**的欄位
（價格、庫存、時段、案件狀態），對應 SPEC §2.3 與 design.md §10 的邊界。

水電那份含高風險停手指引（瓦斯味、冒煙、觸電感、淹水、受困），是安全流程的依據。

### knowledge_base — S3／Bedrock Knowledge Base 上傳資料

`knowledge/` 的五份合併文件依二級標題切成小型 Markdown，輸出至五個
`service_type` 子目錄。每個 `*.md` 都有同名的 `*.md.metadata.json` sidecar，格式為
Bedrock Knowledge Base 的 `metadataAttributes`；至少包含 `service_type`、`doc_kind`、
`version`、`effective_from` 與 `authoritative_scope=static_only`。

同步到 S3 時只上傳 `knowledge_base/`，不要把 `master/`、`cases/`、`eval/`、PII 或原始
五份合併文件加入 Knowledge Base data source。Agent 檢索時必須固定加入
`service_type` metadata filter。

### cases — 案件資料

| 檔案 | 筆數 | 說明 |
|---|---|---|
| `cases/service_requests.json` | 500 | 五類各 100 筆。含口語化 `request_summary`、結構化 `form_payload`、狀態、版本、高風險旗標 |
| `cases/service_request_matches.json` | 628 | 媒合結果，含分數、`rule_version` 與可讀的 `reasons[]`（規則產生，非 LLM 文字） |
| `cases/service_request_events.json` | 1630 | append-only 狀態歷程，全部通過狀態機驗證 |
| `cases/provider_replies.json` | 351 | 廠商回覆 |
| `cases/pii_vault.json` | 500 | PII 集中處。全部虛構，手機用測試保留號段 `0900-000-xxx`，Email 用 `example.invalid` |
| `cases/conflict_fixtures.json` | 12 | 冪等重試與樂觀鎖版本衝突的驗收 fixture |

案件本體只存 `pii_ref`，不存明文 PII。

### eval — AI 評測集

| 檔案 | 筆數 | 說明 |
|---|---|---|
| `eval/eval.jsonl` | 428 | 單輪評測 |
| `eval/multi_turn.jsonl` | 50 | 多輪：先講一半 → 被追問 → 補齊 → 摘要確認 → 明確同意才建案 |
| `eval/holdout_human.jsonl` | 5 | **空白樣板**，由團隊成員手寫，禁止用 LLM 產生（見下方說明） |

單輪配額：

| 類別 | 筆數 | 驗證什麼 |
|---|---|---|
| normal | 200 | 五類正常分類與欄位抽取 |
| missing_required | 60 | 只追問缺的欄位，不重問已知的 |
| conditional_field | 30 | 條件式追問觸發 |
| high_risk | 40 | 安全指引優先於媒合與建案 |
| ambiguous | 39 | 資訊不足時澄清，不得亂猜類別 |
| cross_category | 30 | 一句話跨兩類時拆單或請使用者選 |
| unsupported | 29 | 叫車、簽證、醫療、法律、金融等明確拒絕並導向正確管道 |

每筆的 `expected` 含 `service_type`、`extracted_fields`、`missing_required_fields`、
`next_action`、`safety_action`、`tool_calls`、**`must_not_call`**。
`must_not_call` 用來抓「還沒取得同意就呼叫 `create_service_request`」這種違規。

## 三個刻意的設計，不要當成 bug

**1. 有些地方查不到服務商。** 澎湖、金門、連江完全沒有服務商；全國 368 個行政區只有
174 個有覆蓋。這是為了讓 `unmatched` 與 `relaxation_suggestions` 這條路徑真的有資料走過。
案件裡有 100+ 筆 unmatched，全部附放寬建議。

**2. PII 只出現在 `pii_vault.json`。** 評測句子與案件摘要裡的聯絡資料都是
`{{CONTACT_NAME}}` / `{{CONTACT_MOBILE}}` placeholder。SPEC §6 要求 prompt 與 log 不得含
明文 PII，資料集本身就必須先做到，否則等於自己示範怎麼違規。
`tools/datagen/validate.py` 有 PII regex gate 會擋。

**3. `holdout_human.jsonl` 是空的。** 評測句子和分類器共享同一個語言先驗，離線分數會
系統性虛高。這 5 筆（建議擴充到 60~80 筆）必須由人手寫、不看生成器、不用 LLM 改寫，
最後分開報 in-distribution / out-of-distribution 兩個分數。

## 驗證

```bash
.venv/bin/python tools/datagen/validate.py
```

檢查：行政區完整性、外鍵、狀態機合法性、評測欄位是否存在於表單 schema、
`missing_required_fields` 是否等於「必填清單 − 已抽取欄位」、PII 洩漏、配額分佈。
