import { InvokeCommand, LambdaClient } from '@aws-sdk/client-lambda';
import { config } from '../lib/config';
import type { MatchAgentInput, MatchAgentOutput } from './matchAgent';

/**
 * 生活管家 -> 媒合代理 的傳輸層。
 *
 * 本地開發：直接 in-process 呼叫，好 debug。
 * 部署後：MATCH_FUNCTION_NAME 有值，改走 Lambda invoke（兩個 agent 真的是兩個獨立服務）。
 * 上層程式碼不需要知道差別。
 */
export async function callMatchAgent(input: MatchAgentInput): Promise<MatchAgentOutput> {
  if (!config.matchFunctionName) {
    const { runMatchAgent } = await import('./matchAgent');
    return runMatchAgent(input);
  }

  const lambda = new LambdaClient({ region: config.region });
  const res = await lambda.send(
    new InvokeCommand({
      FunctionName: config.matchFunctionName,
      InvocationType: 'RequestResponse',
      Payload: Buffer.from(JSON.stringify(input)),
    }),
  );

  if (res.FunctionError) {
    const detail = res.Payload ? Buffer.from(res.Payload).toString('utf8') : '';
    throw new Error(`媒合 agent 執行失敗: ${res.FunctionError} ${detail}`);
  }
  if (!res.Payload) throw new Error('媒合 agent 沒有回傳內容');

  return JSON.parse(Buffer.from(res.Payload).toString('utf8')) as MatchAgentOutput;
}
