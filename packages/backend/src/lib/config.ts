/** 集中讀環境變數，避免各處散落 process.env */
export const config = {
  region: process.env.AWS_REGION ?? 'us-west-2',
  modelId: process.env.BEDROCK_MODEL_ID ?? 'us.anthropic.claude-haiku-4-5-20251001-v1:0',
  repoDriver: (process.env.REPO_DRIVER ?? 'memory') as 'memory' | 'dynamodb',
  tableName: process.env.TABLE_NAME ?? 'op-life-agent',
  /** 有值就用 Lambda invoke 呼叫媒合 agent，沒值就 in-process 呼叫 */
  matchFunctionName: process.env.MATCH_FUNCTION_NAME || undefined,
  port: Number(process.env.PORT ?? 3001),
};
