import type { APIGatewayProxyEventV2, APIGatewayProxyResultV2 } from 'aws-lambda';
import { runUserAgentTurn } from '../agents/userAgent';
import { DEMO_USER_ID } from '../data/users';

const CORS = {
  'access-control-allow-origin': '*',
  'access-control-allow-headers': 'content-type',
  'access-control-allow-methods': 'POST,OPTIONS',
  'content-type': 'application/json; charset=utf-8',
};

function json(statusCode: number, body: unknown): APIGatewayProxyResultV2 {
  return { statusCode, headers: CORS, body: JSON.stringify(body) };
}

/** POST /chat  { sessionId?, inbrAccountId?, message } */
export const handler = async (event: APIGatewayProxyEventV2): Promise<APIGatewayProxyResultV2> => {
  if (event.requestContext?.http?.method === 'OPTIONS') return json(204, {});

  try {
    const body = event.body ? JSON.parse(event.body) : {};
    if (typeof body.message !== 'string' || body.message.trim() === '') {
      return json(400, { error: 'message 為必填' });
    }

    const result = await runUserAgentTurn({
      sessionId: body.sessionId,
      // demo 階段沒有登入，預設用種子會員；正式接 OpenPoint SSO 時換成 token 解出的 id
      inbrAccountId: body.inbrAccountId ?? DEMO_USER_ID,
      message: body.message,
    });

    return json(200, result);
  } catch (err) {
    console.error('chat handler failed', err);
    return json(500, { error: err instanceof Error ? err.message : String(err) });
  }
};
