/**
 * 本地開發伺服器。
 *
 * 重點：它只是把 HTTP request 轉成 API Gateway v2 的 event 格式，
 * 然後呼叫「跟部署到 Lambda 完全同一份」的 handler。
 * 所以本地測過的行為，上雲行為一致。
 */
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// 讀 repo 根目錄的 .env（不引第三方套件）
loadDotEnv();

const { config } = await import('../lib/config');
const { handler: chatHandler } = await import('../handlers/chat');
const { handler: contextHandler } = await import('../handlers/context');

function loadDotEnv(): void {
  for (const p of ['.env', '../../.env', '../../../.env']) {
    try {
      const text = readFileSync(resolve(process.cwd(), p), 'utf8');
      for (const line of text.split(/\r?\n/)) {
        const m = /^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/.exec(line);
        if (!m) continue;
        const [, key, rawValue] = m;
        if (process.env[key] !== undefined) continue;
        process.env[key] = rawValue.replace(/^['"]|['"]$/g, '');
      }
      return;
    } catch {
      // 換下一個路徑
    }
  }
}

async function readBody(req: IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const c of req) chunks.push(c as Buffer);
  return Buffer.concat(chunks).toString('utf8');
}

function corsPreflight(res: ServerResponse): void {
  res.writeHead(204, {
    'access-control-allow-origin': '*',
    'access-control-allow-headers': 'content-type',
    'access-control-allow-methods': 'GET,POST,OPTIONS',
  });
  res.end();
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? '/', `http://localhost:${config.port}`);
  const method = req.method ?? 'GET';

  if (method === 'OPTIONS') return corsPreflight(res);

  try {
    if (url.pathname === '/health') {
      res.writeHead(200, { 'content-type': 'application/json' });
      return res.end(
        JSON.stringify({ ok: true, repo: config.repoDriver, model: config.modelId, region: config.region }),
      );
    }

    if (url.pathname === '/context' && method === 'GET') {
      const event = {
        requestContext: { http: { method } },
        queryStringParameters: Object.fromEntries(url.searchParams),
      } as never;
      const out = (await contextHandler(event)) as {
        statusCode: number;
        headers: Record<string, string>;
        body: string;
      };
      res.writeHead(out.statusCode, out.headers);
      return res.end(out.body);
    }

    if (url.pathname === '/chat' && method === 'POST') {
      const body = await readBody(req);
      const event = { requestContext: { http: { method } }, body } as never;
      const started = Date.now();
      const out = (await chatHandler(event)) as {
        statusCode: number;
        headers: Record<string, string>;
        body: string;
      };
      console.log(`[chat] ${out.statusCode} ${Date.now() - started}ms`);
      res.writeHead(out.statusCode, out.headers);
      return res.end(out.body);
    }

    res.writeHead(404, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ error: 'not found' }));
  } catch (err) {
    console.error(err);
    res.writeHead(500, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ error: err instanceof Error ? err.message : String(err) }));
  }
});

server.listen(config.port, () => {
  console.log(`
生活管家後端已啟動
  http://localhost:${config.port}/health
  POST http://localhost:${config.port}/chat      { "message": "冷氣不冷了" }
  GET  http://localhost:${config.port}/context

  資料層: ${config.repoDriver}    模型: ${config.modelId}    區域: ${config.region}
`);
});
