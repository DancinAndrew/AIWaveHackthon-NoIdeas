# ADR-0006：合成 Knowledge Base 向量索引使用 SSE-S3

- 狀態：Accepted
- 日期：2026-08-02
- 決策者：AIWaveHackthon-NoIdeas 團隊
- 補充：[ADR-0005](0005-use-s3-vectors-and-titan-for-managed-knowledge-base.md) 的向量資料加密決策
- 關聯規格：`SPEC.md`、`openspec/changes/define-flask-mcp-service-intake/`

## Context

水電 walking skeleton 的 S3 Vectors bucket 只保存經 manifest、內容掃描與 SHA-256 驗證的合成 FAQ、條款與 SOP embedding，不保存住戶對話、聯絡資訊、地址、附件或交易資料。RDS、Secrets Manager、一般 S3 artifact／source bucket 與 PII 仍由客戶管理 KMS 金鑰保護。

第一次以同一把客戶管理 KMS 金鑰建立 S3 Vectors index 時，非同步索引服務因金鑰政策沒有授權 `indexing.s3vectors.amazonaws.com` 而失敗。AWS 文件指出 S3 Vectors 預設 SSE-S3 使用 AES-256，且客戶管理 SSE-KMS 適合需要額外金鑰控制或詳細 KMS 稽核的情境。

## Decision

S3 Vectors bucket 與其繼承設定的 index 使用 SSE-S3（`AES256`）。不把應用程式共用的客戶管理 KMS 金鑰授權給 S3 Vectors 非同步索引 service principal。

此例外只適用於已驗證、非敏感的合成 Knowledge Base 向量資料。原始 Knowledge Base source bucket 仍維持四項 S3 Block Public Access、TLS-only bucket policy 與 SSE-KMS；RDS、Secrets、artifact bucket 與任何 PII 邊界也繼續使用 SSE-KMS。

## Alternatives Considered

### 共用應用程式 KMS 金鑰並新增 S3 Vectors key policy

- **Pros**：向量資料也有相同的客戶管理金鑰、CloudTrail KMS 稽核與停用控制。
- **Cons**：需讓非同步索引 service principal 使用共用金鑰，增加跨服務政策、部署排序與金鑰失效影響範圍。
- **Why not**：Demo 向量資料為可重建的合成文件，額外控制不抵銷耦合與 KMS 請求成本。

### 為 S3 Vectors 建立專用客戶管理 KMS 金鑰

- **Pros**：隔離索引服務權限，不擴大其他資料的共用金鑰政策。
- **Cons**：增加一把付費金鑰、輪替與 teardown 管理，對十個合成 KB 物件不成比例。
- **Why not**：目前沒有合規要求必須使用客戶管理金鑰。

## Consequences

### Positive

- 向量資料仍由 AWS 託管的 AES-256 靜態加密保護。
- S3 Vectors 不再依賴共用 KMS key policy，降低部署失敗與 blast radius。
- 沒有額外 KMS key 或 S3 Vectors 背景索引的 KMS 請求成本。

### Negative

- 向量資料沒有客戶管理金鑰的獨立停用、輪替政策與 KMS 使用稽核。
- 若未來允許敏感資料進入 Knowledge Base，必須先重評並以新 bucket／index 遷移，因為建立後不能改變加密設定。

### Risks

- 敏感資料誤入 SSE-S3 vector bucket → upload manifest 與內容掃描持續 fail-closed，住戶輸入與附件永遠不在白名單。
- 未來資料分類改變但未重評 → OpenSpec 及 ADR review 將「KB 是否仍只含合成非敏感資料」列為改版條件。

## References

- [Data protection and encryption in S3 Vectors](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-data-encryption.html)
- [Setting encryption in S3 Vectors](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-sectting-encryption.html)

