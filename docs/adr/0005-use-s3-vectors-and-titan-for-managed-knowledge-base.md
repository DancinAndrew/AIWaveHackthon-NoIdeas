# ADR-0005：Managed Knowledge Base 使用 S3 Vectors 與 Titan Text Embeddings V2

- 狀態：Accepted
- 日期：2026-08-02
- 決策者：AIWaveHackthon-NoIdeas 團隊
- 修正：[ADR-0003](0003-adopt-aws-native-agentcore-rds-platform.md) 的 Knowledge Base embedding／vector store 決策
- 關聯規格：`SPEC.md`、`openspec/changes/define-flask-mcp-service-intake/`

## Context

Hackathon 帳號要求只啟用必要模型、限制生成式 AI 請求並減少非必要成本。原 ADR-0003 選擇 Cohere Embed Multilingual v3，但未固定 vector store；OpenSearch Serverless 的常駐容量不適合只有少量合成文件的水電 Demo。現在 `us-west-2` 已支援 Amazon Bedrock Managed Knowledge Base、Titan Text Embeddings V2 與 S3 Vectors 整合。

## Decision

單一 Managed Knowledge Base 使用 `amazon.titan-embed-text-v2:0` 的 1024 維 floating-point embedding，向量儲存使用一個 private Amazon S3 Vectors bucket 與 COSINE index。原始 FAQ／條款／SOP 仍放在另一個四項 Block Public Access 全開的 S3 source bucket，並只上傳通過 manifest、內容掃描與 SHA-256 驗證的合成文件。

Knowledge Base ingestion 不在一般對話路徑自動觸發；部署者只在文件版本變更後明確執行一次 sync，以避免重複 embedding 請求。繁體中文 retrieval 必須用本專案 eval fixtures 驗證，未達門檻時先調整 chunk／查詢，不直接開啟更多模型。

## Alternatives Considered

### Cohere Embed Multilingual v3＋OpenSearch Serverless

- **Pros**：多語檢索能力明確，與原 ADR-0003 一致。
- **Cons**：需要額外模型存取；OpenSearch Serverless 對小型 Demo 有不成比例的常駐成本。
- **Why not**：違反只開必要模型與限制成本的優先順序。

### Titan Text Embeddings V2＋OpenSearch Serverless

- **Pros**：保留 AWS 原生 embedding，OpenSearch 查詢能力成熟。
- **Cons**：仍有常駐向量服務容量，部署元件及權限更多。
- **Why not**：十個水電 KB 物件不需要專用搜尋叢集容量。

### 不建立 Managed Knowledge Base，只由 Runtime 直接讀 S3

- **Pros**：服務最少，不產生 embedding 成本。
- **Cons**：無語意檢索、metadata filter 與 Managed Knowledge Base 引用；偏離已接受的 AgentCore 多領域 RAG 架構。
- **Why not**：無法驗證正式架構的 Knowledge Base 邊界。

## Consequences

### Positive

- 模型白名單維持 Nova 2 Lite 與 Titan Embed v2 兩個必要模型。
- S3 Vectors 適合小型、低頻 Demo，避免 OpenSearch Serverless 常駐容量。
- source bucket、vector bucket 與住戶 artifact bucket 保持分離，降低資料誤同步風險。
- CloudFormation 可直接建立 vector bucket、index、Managed Knowledge Base 與 S3 data source。

### Negative

- Titan Text Embeddings V2 以英文最佳化；繁體中文品質必須用實際 fixture 驗證。
- S3 Vectors metadata 與查詢能力有自身限制，未來複雜 hybrid search 可能需要重評 vector store。
- Knowledge Base sync 是受控部署步驟，不會在 CloudFormation 完成後自動執行。

### Risks

- 繁中召回不足 → 保存 top-k、命中 chunk 與 metadata filter 的離線評測；未過門檻不宣稱 RAG 完成。
- 未掃描資料進入 KB → upload script 只能讀取 `infra/upload-manifest.json` 回傳的 verified paths。
- 重複 sync 造成超量 embedding 請求 → 部署狀態保存上次 manifest digest，內容未變時不啟動 ingestion job。
- vector bucket 權限過寬 → bucket policy 只允許 Knowledge Base service role 的必要 S3 Vectors actions。

## References

- [Using S3 Vectors with Amazon Bedrock Knowledge Bases](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-bedrock-kb.html)
- [Supported models and Regions for Amazon Bedrock Knowledge Bases](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-supported.html)
- [AWS::S3Vectors::Index](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3vectors-index.html)
