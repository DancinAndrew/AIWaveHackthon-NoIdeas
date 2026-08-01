import { runMatchAgent, type MatchAgentInput } from '../agents/matchAgent';

/**
 * 媒合代理的 Lambda 入口。
 * 由生活管家 Lambda 直接 invoke（不對外開放 HTTP），
 * 因為它是「代表平台/廠商端」的內部服務。
 */
export const handler = async (event: MatchAgentInput) => {
  if (!event?.request) throw new Error('payload 缺少 request');
  return runMatchAgent({
    request: event.request,
    preferences: event.preferences ?? {},
  });
};
