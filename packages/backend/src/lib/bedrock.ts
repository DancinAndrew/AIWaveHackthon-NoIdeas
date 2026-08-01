import {
  BedrockRuntimeClient,
  ConverseCommand,
  type ContentBlock,
  type Message,
  type Tool,
  type ToolConfiguration,
} from '@aws-sdk/client-bedrock-runtime';
import { config } from './config';
import type { AgentTraceEntry } from '../domain/types';

const client = new BedrockRuntimeClient({ region: config.region });

/** 一個 agent 可以呼叫的工具 */
export interface AgentTool<I = any, O = any> {
  name: string;
  description: string;
  /** JSON Schema */
  schema: Record<string, unknown>;
  run: (input: I) => Promise<O>;
}

export interface RunAgentOptions {
  agentName: AgentTraceEntry['agent'];
  systemPrompt: string;
  messages: Message[];
  tools: AgentTool[];
  /** 防止無限 tool loop */
  maxTurns?: number;
  temperature?: number;
  maxTokens?: number;
}

export interface RunAgentResult {
  text: string;
  trace: AgentTraceEntry[];
  /** 完整對話（含 toolUse / toolResult），可存進 session 讓下一輪延續 */
  messages: Message[];
}

function toToolConfig(tools: AgentTool[]): ToolConfiguration | undefined {
  if (tools.length === 0) return undefined;
  return {
    tools: tools.map<Tool>((t) => ({
      toolSpec: {
        name: t.name,
        description: t.description,
        inputSchema: { json: t.schema },
      },
    })),
  };
}

function extractText(content: ContentBlock[] | undefined): string {
  return (content ?? [])
    .map((b) => ('text' in b ? b.text : undefined))
    .filter((t): t is string => Boolean(t))
    .join('\n')
    .trim();
}

/**
 * Bedrock Converse tool-use loop。
 *
 * 流程：送出對話 -> 若 stopReason 是 tool_use 就執行工具、把結果回灌 -> 直到模型給純文字。
 * 每次工具呼叫都記進 trace，前端可以畫成「agent 做了什麼」的時間軸。
 */
export async function runAgent(opts: RunAgentOptions): Promise<RunAgentResult> {
  const { agentName, systemPrompt, tools, maxTurns = 8 } = opts;
  const toolMap = new Map(tools.map((t) => [t.name, t]));
  const messages: Message[] = [...opts.messages];
  const trace: AgentTraceEntry[] = [];

  for (let turn = 0; turn < maxTurns; turn++) {
    const res = await client.send(
      new ConverseCommand({
        modelId: config.modelId,
        system: [{ text: systemPrompt }],
        messages,
        toolConfig: toToolConfig(tools),
        inferenceConfig: {
          temperature: opts.temperature ?? 0.3,
          maxTokens: opts.maxTokens ?? 2048,
        },
      }),
    );

    const assistant = res.output?.message;
    if (!assistant) throw new Error('Bedrock 沒有回傳 message');
    messages.push(assistant);

    const toolUses = (assistant.content ?? []).flatMap((b) =>
      'toolUse' in b && b.toolUse ? [b.toolUse] : [],
    );

    if (res.stopReason !== 'tool_use' || toolUses.length === 0) {
      return { text: extractText(assistant.content), trace, messages };
    }

    // 執行這一輪所有工具呼叫，結果一次回灌
    const results: ContentBlock[] = [];
    for (const use of toolUses) {
      const tool = use.name ? toolMap.get(use.name) : undefined;
      let output: unknown;
      let ok = true;
      if (!tool) {
        ok = false;
        output = { error: `未知的工具: ${use.name}` };
      } else {
        try {
          output = await tool.run(use.input as never);
        } catch (err) {
          ok = false;
          output = { error: err instanceof Error ? err.message : String(err) };
        }
      }

      trace.push({
        agent: agentName,
        tool: use.name ?? 'unknown',
        input: use.input,
        output,
        at: new Date().toISOString(),
      });

      results.push({
        toolResult: {
          toolUseId: use.toolUseId,
          content: [{ json: output as Record<string, unknown> }],
          status: ok ? 'success' : 'error',
        },
      });
    }
    messages.push({ role: 'user', content: results });
  }

  return {
    text: '抱歉，我這邊處理有點卡住了，可以請你再說一次需求嗎？',
    trace,
    messages,
  };
}

export type { Message };
