# 產品概觀

## 這是什麼

**AI 生活管家** — 「2026 雲湧智生：臺灣生成式 AI 應用黑客松」參賽專案。

住戶用自然語言描述生活需求，系統以多輪對話補齊欄位、產生版本化需求文件，經住戶確認後自動委派商家，並追蹤到最終結論。

## 支援的五類服務

1. 餐廳訂位
2. 商品購買
3. 家事服務
4. 水電修繕
5. 社區服務諮詢

五類共用同一組資料表（`service_requests`、`service_request_matches`、`service_request_events`）與同一條 REST／MCP service layer，差異只在表單 Schema 與領域 Agent 提示。

## 核心流程

```
理解需求 → 補齊欄位 → 產生需求文件 → 住戶確認 → 建立案件
   → 自動媒合商家 → 等待廠商 → 接受／拒絕／補件 → 恢復 Agent → 最終結論
```

- 單一 AgentCore Runtime 內含一個 Supervisor（負責路由）＋五個邏輯領域 Agent（負責欄位抽取、追問、工具選擇）。
- Step Functions Standard 持有長流程；人工等待期間 Agent 不常駐。
- 廠商婉拒或逾時會立即自動改派下一名候選。

## 三種角色

| 角色 | 能力 |
|---|---|
| `RESIDENT` | 對話提出需求、確認案件、補件、查看進度與提醒 |
| `PROVIDER` | 只看到媒合給自己的案件；承接／婉拒／要求補件／更新進度 |
| `ADMIN` | 後台管理、模擬逾時等 Demo 操作 |

## 目前實作狀態（不要誇大）

- 已完成並部署到 AWS staging：**水電修繕 walking skeleton** 的端到端閉環。
- 線上 API 誠實回報 `orchestrationMode: agentcore-runtime`；本機 adapter 回報 `deterministic-demo`。
- 尚未完成：Cognito JWT 驗證、Runtime 內持續多輪、Gateway tool call、Step Functions callback worker、其餘四類服務的知識庫內容。
- 回報進度時只描述已有可重現證據的部分，不把 mock 或 fixture 說成真實整合。

## 明確非目標

- 不執行真實付款、退款或任何不可逆的外部交易。付款、餐廳、供應商、派工都是明確標示的 mock adapter。
- 不用 Knowledge Base 當價格、庫存、可預約時段或案件狀態的真實來源（那些只能來自 RDS 或 mock／廠商 adapter）。
- 不把 Supervisor 與五個領域 Agent 拆成六個獨立 AgentCore Runtime，也不為每個商家建 Agent。
- 不讓模型取代專業技師做安全診斷；水電高風險情境必須輸出停止操作並聯繫專業人員的提示。
- 不開放公開註冊；Demo 帳號預先建立。

## 語言慣例

- 使用者介面、產品與規劃文件：繁體中文。
- 協定識別碼、欄位名、狀態值、程式碼：英文 snake_case。
