import type { APIGatewayProxyEventV2, APIGatewayProxyResultV2 } from 'aws-lambda';
import { getRepo } from '../repo';
import { DEMO_USER_ID } from '../data/users';
import { suggestedPrompts } from '../agents/userAgent';

const CORS = {
  'access-control-allow-origin': '*',
  'access-control-allow-headers': 'content-type',
  'access-control-allow-methods': 'GET,OPTIONS',
  'content-type': 'application/json; charset=utf-8',
};

/** GET /context?inbrAccountId=... 給前端開場用（會員資訊 + 歷史單 + 建議話術） */
export const handler = async (event: APIGatewayProxyEventV2): Promise<APIGatewayProxyResultV2> => {
  const repo = getRepo();
  const id = event.queryStringParameters?.inbrAccountId ?? DEMO_USER_ID;
  const user = await repo.getUser(id);
  if (!user) {
    return { statusCode: 404, headers: CORS, body: JSON.stringify({ error: '會員不存在' }) };
  }
  const [requests, bookings] = await Promise.all([
    repo.listRequestsByUser(id),
    repo.listBookingsByUser(id),
  ]);

  return {
    statusCode: 200,
    headers: CORS,
    body: JSON.stringify({
      user,
      requests,
      bookings,
      suggestedPrompts: suggestedPrompts(),
    }),
  };
};
