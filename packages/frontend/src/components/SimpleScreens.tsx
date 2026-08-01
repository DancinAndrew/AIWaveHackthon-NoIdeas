import type { UserProfile } from '../types';
import { TileIcon } from './icons';

/**
 * 點數兌換與付款碼。
 *
 * 這兩頁不是提案重點，但 demo 時評審會亂點底部導覽，
 * 點下去沒反應會讓人以為 App 壞了。所以做到「看起來合理」就好，
 * 不接後端、不假裝有功能。
 */

export function PointsScreen({ user }: { user?: UserProfile }) {
  const points = user?.points ?? 0;
  const items = [
    { name: '中杯咖啡兌換券', cost: 120, glyph: '咖', bg: '#8b6a4f' },
    { name: '冷氣清洗折抵 200 元', cost: 800, glyph: '冷', bg: '#00a9c8' },
    { name: '水電修繕折抵 300 元', cost: 1200, glyph: '修', bg: '#f47b20' },
    { name: '超商購物金 50 元', cost: 500, glyph: '購', bg: '#7cb342' },
  ];

  return (
    <div className="screen">
      <div
        style={{
          margin: '10px 12px',
          borderRadius: 14,
          padding: '18px',
          background: 'linear-gradient(120deg, #f47b20, #f6c344)',
          color: '#fff',
          textAlign: 'center',
        }}
      >
        <div style={{ fontSize: 12, opacity: 0.95 }}>可用點數</div>
        <div style={{ fontSize: 34, fontWeight: 800, lineHeight: 1.2 }}>
          {points.toLocaleString('zh-TW')}
        </div>
        <div style={{ fontSize: 11, opacity: 0.9 }}>OPEN POINT</div>
      </div>

      <section className="card" aria-labelledby="ex-title">
        <div className="card-head">
          <span id="ex-title">熱門兌換</span>
        </div>
        <div style={{ padding: '4px 0 8px' }}>
          {items.map((it) => {
            const enough = points >= it.cost;
            return (
              <div
                key={it.name}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 11,
                  padding: '10px 14px',
                  borderBottom: '1px solid #f2f4f6',
                }}
              >
                <TileIcon glyph={it.glyph} bg={it.bg} size={36} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13.5, fontWeight: 600 }}>{it.name}</div>
                  <div style={{ fontSize: 11.5, color: '#6b7280' }}>
                    {it.cost.toLocaleString('zh-TW')} 點
                  </div>
                </div>
                <span
                  className={`chip${enough ? ' green' : ''}`}
                  style={{ fontSize: 11.5, padding: '5px 12px' }}
                >
                  {enough ? '可兌換' : '點數不足'}
                </span>
              </div>
            );
          })}
        </div>
      </section>

      <div
        style={{
          textAlign: 'center',
          fontSize: 11,
          color: '#9aa1ab',
          padding: '8px 30px 20px',
          lineHeight: 1.7,
        }}
      >
        服務完成後的點數回饋會依 mms_order_record 的
        <br />
        earn_points 欄位計算。
      </div>
    </div>
  );
}

export function PayScreen({ user }: { user?: UserProfile }) {
  // 用會員編號生一組穩定的假條碼數字，讓畫面看起來像真的
  const seed = user?.inbrAccountId?.replace(/\D/g, '').slice(0, 13) ?? '2601150000018';
  const code = seed.padEnd(13, '0');

  return (
    <div className="screen">
      <div className="card" style={{ padding: '22px 18px', textAlign: 'center' }}>
        <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 14 }}>
          請出示條碼給門市人員掃描
        </div>

        {/* 條碼：用不等寬的線條模擬，純視覺 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'center',
            gap: 2,
            height: 76,
            marginBottom: 10,
          }}
          role="img"
          aria-label="會員付款條碼"
        >
          {code
            .split('')
            .flatMap((d, i) => {
              const n = Number(d) || 1;
              return [
                <span
                  key={`${i}b`}
                  style={{ width: (n % 3) + 1.5, height: '100%', background: '#23272e' }}
                />,
                <span key={`${i}s`} style={{ width: 2, height: '100%', background: '#fff' }} />,
              ];
            })}
        </div>
        <div
          style={{
            fontFamily: 'Consolas, monospace',
            fontSize: 15,
            letterSpacing: '0.22em',
            fontWeight: 600,
          }}
        >
          {code}
        </div>

        <div
          style={{
            marginTop: 18,
            paddingTop: 14,
            borderTop: '1px dashed #e6e8eb',
            display: 'flex',
            justifyContent: 'space-around',
            fontSize: 12,
          }}
        >
          <div>
            <div style={{ color: '#6b7280' }}>可用點數</div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>
              {(user?.points ?? 0).toLocaleString('zh-TW')}
            </div>
          </div>
          <div>
            <div style={{ color: '#6b7280' }}>綁定支付</div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>OPEN 錢包</div>
          </div>
        </div>
      </div>

      <div
        style={{
          textAlign: 'center',
          fontSize: 11,
          color: '#9aa1ab',
          padding: '4px 30px',
          lineHeight: 1.7,
        }}
      >
        此頁為 demo 佔位畫面，未接金流。
      </div>
    </div>
  );
}
