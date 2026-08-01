/**
 * 端到端煙霧測試：不開 HTTP，直接跑多輪對話，驗證
 *   slot filling -> 媒合代理 -> 報價 -> 建立預約單 -> 偏好記錄
 * 都真的會發生。
 *
 * 執行：npm run smoke -w @op/backend
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

for (const p of ['.env', '../../.env']) {
  try {
    const text = readFileSync(resolve(process.cwd(), p), 'utf8');
    for (const line of text.split(/\r?\n/)) {
      const m = /^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/.exec(line);
      if (m && process.env[m[1]] === undefined) process.env[m[1]] = m[2].replace(/^['"]|['"]$/g, '');
    }
    break;
  } catch {
    /* try next */
  }
}

const { runUserAgentTurn } = await import('../agents/userAgent');
const { DEMO_USER_ID } = await import('../data/users');

const TURNS = [
  '我家冷氣不冷了，主臥那台',
  '台北市大安區復興南路一段100號5樓，下午方便',
  '我想選最便宜的那家',
];

let sessionId: string | undefined;

for (const [i, message] of TURNS.entries()) {
  console.log(`\n${'='.repeat(70)}\n[第 ${i + 1} 輪] 會員：${message}\n${'='.repeat(70)}`);
  const started = Date.now();
  const r = await runUserAgentTurn({ sessionId, inbrAccountId: DEMO_USER_ID, message });
  sessionId = r.sessionId;

  for (const t of r.trace) {
    console.log(`  · [${t.agent}] ${t.tool}`);
  }
  console.log(`\n管家：${r.reply}\n`);
  console.log(
    `  服務單狀態：${r.request?.status ?? '-'}` +
      `  症狀=${r.request?.slots.symptoms?.join('/') ?? '-'}` +
      `  地址=${r.request?.address ? r.request.address.countyName + r.request.address.districtName : '-'}` +
      `  時段=${r.request?.preferredContactTime ?? '-'}`,
  );
  if (r.match) {
    console.log(`  媒合結果（${r.match.proposals.length} 家）：`);
    for (const p of r.match.proposals) {
      console.log(
        `    - ${p.vendorName}  分數 ${p.score}  ${p.quote.estimatedMin}~${p.quote.estimatedMax} 元  最快 ${p.earliestSlot.date}`,
      );
    }
  }
  if (r.booking) {
    console.log(
      `  預約單：${r.booking.orderNo}  ${r.booking.vendorName}  ${r.booking.serviceDate}  訂金 ${r.booking.depositAmount} 元  狀態 ${r.booking.orderStatus}`,
    );
  }
  console.log(`  (${Date.now() - started}ms)`);
}

console.log('\n煙霧測試結束');
