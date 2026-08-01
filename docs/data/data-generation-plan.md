# 五類服務資料集：決策紀錄

Status: 已實作
產出：[data/mock/](../../data/mock/) · 生成器：`tools/datagen/` · 說明：[data/mock/README.md](../../data/mock/README.md)

---

## 1. 核心決策：合成為主，抓取只用一次

| 資料 | 做法 | 理由 |
|---|---|---|
| 縣市／行政區代碼 | 補齊為全國 368 筆 | 唯一「事實正確性有意義」的資料 |
| 服務商、餐廳、SKU、時段、案件、評測集 | 確定性合成（seed 20260801） | 見下 |
| 真實店家（Google Maps／EZTable／PChome） | **不抓** | 見下 |

**不抓真實店家的三個理由：**

1. SPEC §2.3 明訂「沒有合作廠商正式 API 時，不宣稱已完成真實訂位、購買或派工」。
   放真店名會讓 demo 看起來像真的能訂，評審一問就露餡。
2. 抓得到的只有店名／地址／營業時間；真正需要的**可訂時段、低消、庫存、證照、
   出勤區域**全部抓不到。結果會是一半真一半假 —— 最難維護、最容易自相矛盾。
3. ToS／robots／個資風險，時間成本高於效益。

**關鍵手法：反向生成。** 先用程式產生結構化答案（skeleton），再由片段組合出使用者
口語句子。評測集的 ground truth 天生正確、免人工標注。反過來（先寫句子再標注）
一定有標注雜訊。

---

## 2. 命題資料的問題清單（實測，非推測）

### 2.1 訂單 `order_record範例資料.json`（99 筆）

| 問題 | 證據 | 對應處置 |
|---|---|---|
| `order_type='07'` 未定義 | 64/99 筆使用；SQL COMMENT 只定義到 06 | 依 vendor 15/service 18 與 `order_items` 形態判定為商城訂單 |
| `service_id=18` / `vendor_id=15` 不在主檔 | 主檔只有 service 1,2,3,4,5,9,16,17；vendor 1,2,5,10,11,14 | 合成資料自建 ID 空間，不沿用 |
| `platform_code` 出現 `00`(31)、`03`(1) | SQL 只定義 `01:OP APP` | 標為 unknown，不猜語意 |
| **`order_items` 是 jsonb 裡的「字串」，且有 4 種 schema** | vendor 1/11 camelCase、vendor 15 snake_case、vendor 11 外層包 `{orderItems,totalAmount}`、vendor 14 巢狀外送結構 | 合成資料使用單一 canonical 格式 |
| **28 筆狀態／時間戳不一致** | status 80/70 無 `complete_time`；90 無 `cancel_time`；99 的 `refund_amount=0` | 合成資料由狀態機產生，強制自我一致 |
| **PII 是真的 AES-GCM 密文，無金鑰** | `member_name` 為 bytea 亂碼 | 合成資料自帶 PII 策略（見 §3） |
| **地址店名虛構且無法對應行政區** | 「宇宙市銀河區地球路」「OO屋-島語（測試餐廳）」 | 合成資料全部綁真實行政區代碼 |
| 樣本厚度不足 | 只有 10 個會員；時間集中 2026-06-02~06-24 | 合成 500 案件 / 60 消費者 |

### 2.2 其他檔案

- `相關主檔設定.json`、`諮詢單相關範例資料.json`、`縣市區域範例資料.json`
  **三個都是多份 JSON 文件並排**，不是單一合法 JSON。主檔那份還夾一行純文字 type 對照表。
- `pms_form_group` 完全缺席，但 topic 引用 group 60/93/129。
- 唯一那張 `pms_form` id=9 名為「測試表單」，`is_enable='0'`、`is_deleted='1'`。
- `pms_form_feedback.service_id=7` 也不在主檔；其 `status='1'` 沒有任何 enum 文件。
- **`sys_district` 只有 200 筆，只涵蓋 22 縣市中的 14 個。** 台中、苗栗、新竹市、南投、
  彰化、雲林、嘉義縣市**一個行政區都沒有**，台南只有 3 個。code 序列在 069 與 238 之間斷開。

> 最後這項後果最大：`search_providers` 硬條件第一關就是 `district_code`，
> 用命題資料**無法在中部任何縣市做媒合**。已補齊 code 070~237 共 168 筆。

---

## 3. 三個刻意的設計（在 README 也有記，這裡說明為什麼）

### 3.1 有些地方查不到服務商 — 因為媒合失敗路徑必須被測到

生成資料時人會下意識讓每個需求都找得到服務商，結果 `unmatched`、
`relaxation_suggestions`、「有服務商但時段全滿」這幾條路徑一次都沒執行過。
評審問「台東凌晨三點漏水怎麼辦」才發現前端根本沒做這個狀態。

因此：離島 3 縣市完全無服務商、368 個行政區只覆蓋 174 個、部分廠商全時段滿檔。
產出的 500 筆案件裡有 100+ 筆 `unmatched`，全部附放寬建議。

### 3.2 PII 只在 `pii_vault.json` — 因為資料集本身就是架構的示範

SPEC §6 要求 prompt、KB、trace、log 不得含明文姓名／電話／地址。合成 pipeline 很自然
會把「我是王小明 0912-345-678」寫進 `user_utterance`，然後這個檔案進 git、進 prompt、
進評測 log。「反正是假人」讓人放鬆，但架構驗收看的是**資料流**不是資料真偽。

因此：句子用 `{{CONTACT_NAME}}` placeholder，真值集中在 `pii_vault.json`，
手機用測試保留號段 `0900-000-xxx`，Email 用 `example.invalid`，
`validate.py` 有 PII regex gate 會擋。

### 3.3 `holdout_human.jsonl` 是空的 — 因為自己生成的評測集會給你虛高的分數

評測句子和分類器共享同一個語言先驗，離線 accuracy 會系統性虛高（同類任務常見
10~30pt）。傳統 train/test split 切的是樣本，切不掉語言先驗的相關性 —— 這是 split
抓不到的洩漏。

因此：留一份空白樣板，必須由人手寫、不看生成器、不用 LLM 改寫，
最後分開報 in-distribution / out-of-distribution 兩個分數。簡報時秀 OOD 那個。

---

## 4. 沒做的事

- **沒有匯入 Supabase。** 只產出檔案，seed script 尚未寫。
- **沒有正規化命題訂單資料。** 99 筆命題訂單維持原樣放在 `data/competition/`，
  沒有做 `order_items` adapter 與代碼字典 —— 因為合成資料已足以支撐五類流程，
  命題訂單只在需要展示「處理髒資料」時才需要動。
- **holdout 只有 5 筆空白樣板**，需要人工填到 60~80 筆。
- 沒有寫 JSON Schema 對 `contracts/forms/*.schema.json` 的逐欄位驗證，
  目前 `validate.py` 只檢查欄位群是否存在。
