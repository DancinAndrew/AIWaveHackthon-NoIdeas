import type { Booking, ServiceRequest } from '../types';
import { PERIOD_LABEL } from '../types';
import { BackIcon, CheckIcon, MascotIcon, OrderTrackIcon } from './icons';

const money = (n: number) => n.toLocaleString('zh-TW');

/**
 * 訂單狀態時間軸。
 * 節點直接對齊統一資訊 mms_order_record.order_status 的服務訂單流程：
 *   11 待訂金支付 → 12 已付訂金待報價 → 13 已報價待同意
 *   → 14 已同意 → 15 已驗收待尾款 → 80 已完成
 */
const FLOW: Array<{ code: string; label: string }> = [
  { code: '11', label: '待付訂金' },
  { code: '12', label: '待報價' },
  { code: '13', label: '待同意' },
  { code: '14', label: '施工中' },
  { code: '15', label: '待尾款' },
  { code: '80', label: '已完成' },
];

function Timeline({ status }: { status: string }) {
  const current = FLOW.findIndex((s) => s.code === status);
  return (
    <div className="timeline" aria-label="訂單進度">
      {FLOW.map((step, i) => {
        const done = current > i;
        const on = current === i;
        return (
          <div key={step.code} className={`tl-step${done ? ' done' : ''}${on ? ' on' : ''}`}>
            <span className="dot">{done ? <CheckIcon size={9} /> : null}</span>
            {step.label}
          </div>
        );
      })}
    </div>
  );
}

function OrderCard({ booking, request }: { booking: Booking; request?: ServiceRequest }) {
  const addr = booking.address;
  const symptoms = request?.slots.symptoms?.join('、');

  return (
    <article className="order-card">
      <div className="order-top">
        <div className="order-no">訂單編號 {booking.orderNo}</div>
        <div className="order-vendor">{booking.vendorName}</div>
        {symptoms && (
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
            冷氣維修 · {symptoms}
          </div>
        )}
      </div>

      <Timeline status={booking.orderStatus} />

      <div className="order-body">
        <div className="order-kv">
          <span>到府時間</span>
          <span>
            {booking.serviceDate} {PERIOD_LABEL[booking.servicePeriod] ?? ''}
          </span>
        </div>
        <div className="order-kv">
          <span>服務地址</span>
          <span>
            {addr.countyName}
            {addr.districtName}
          </span>
        </div>
        <div className="order-kv">
          <span>訂金</span>
          <span>{money(booking.depositAmount)} 元</span>
        </div>
        <div className="order-kv">
          <span>預估總額</span>
          <span>
            {money(booking.estimatedMin)}–{money(booking.estimatedMax)} 元
          </span>
        </div>
      </div>
    </article>
  );
}

/**
 * 訂單追蹤畫面。
 * 這是 OpenPoint 原本沒有集中入口的東西 —— 各家服務商的單散在不同分頁，
 * 我們把它收斂成一個「所有委託都在這裡」的清單。
 */
export function OrderScreen({
  bookings,
  requests,
  onBack,
  onOpenAgent,
}: {
  bookings: Booking[];
  requests: ServiceRequest[];
  onBack: () => void;
  onOpenAgent: () => void;
}) {
  // 進行中的服務單（還沒成單，例如管家還在問問題或已媒合待選）
  const pending = requests.filter(
    (r) => r.status !== 'BOOKED' && r.status !== 'CANCELLED',
  );
  const sorted = [...bookings].sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  return (
    <div className="screen">
      <div className="screen-head">
        <button onClick={onBack} aria-label="返回">
          <BackIcon size={20} />
        </button>
        <h2>我的委託</h2>
        <span style={{ marginLeft: 'auto' }}>
          <OrderTrackIcon size={26} />
        </span>
      </div>

      {sorted.length === 0 && pending.length === 0 && (
        <div className="empty-state">
          <MascotIcon size={72} />
          <h3>還沒有委託中的服務</h3>
          <p>
            跟生活管家說一句「冷氣不冷」，
            <br />
            他會幫你問清楚、找師傅、談好價格。
          </p>
          <button className="cta" onClick={onOpenAgent}>
            找管家幫忙
          </button>
        </div>
      )}

      {pending.length > 0 && (
        <>
          <div style={{ padding: '12px 14px 2px', fontSize: 12, color: '#6b7280' }}>
            進行中的諮詢
          </div>
          {pending.map((r) => (
            <div key={r.requestId} className="order-card">
              <div className="order-top">
                <div className="order-no">服務單 {r.requestId}</div>
                <div className="order-vendor" style={{ fontSize: 14 }}>
                  {r.slots.symptoms?.join('、') ?? '尚未描述問題'}
                </div>
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 3 }}>
                  {r.status === 'MATCHED'
                    ? '管家已找到廠商，等你選一家'
                    : r.status === 'MATCHING'
                      ? '正在詢問廠商…'
                      : '管家還在跟你確認細節'}
                </div>
              </div>
            </div>
          ))}
        </>
      )}

      {sorted.length > 0 && (
        <>
          <div style={{ padding: '14px 14px 2px', fontSize: 12, color: '#6b7280' }}>
            已成立的預約
          </div>
          {sorted.map((b) => (
            <OrderCard
              key={b.orderNo}
              booking={b}
              request={requests.find((r) => r.requestId === b.requestId)}
            />
          ))}
        </>
      )}
    </div>
  );
}
