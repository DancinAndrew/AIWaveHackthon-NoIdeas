import { useEffect, useRef, useState } from 'react';
import type { ChatMessage, ServiceRequest, VendorProposal } from '../types';
import { CloseIcon, MascotIcon, SendIcon } from './icons';
import { ProposalCard } from './ProposalCard';

/** 服務單完成度指示條：讓會員看得到「還缺什麼」，不是黑盒子 */
function SlotStrip({ request }: { request?: ServiceRequest | null }) {
  const slots = request?.slots ?? {};
  const items = [
    { label: '症狀', done: (slots.symptoms?.length ?? 0) > 0, value: slots.symptoms?.join('、') },
    { label: '機型', done: Boolean(slots.brand || slots.variant), value: [slots.brand, slots.variant].filter(Boolean).join(' ') },
    {
      label: '地址',
      done: Boolean(request?.address),
      value: request?.address ? `${request.address.countyName}${request.address.districtName}` : undefined,
    },
    {
      label: '時段',
      done: Boolean(request?.preferredContactTime),
      value: request?.preferredContactTime === '1' ? '上午' : request?.preferredContactTime === '2' ? '下午' : request?.preferredContactTime === '3' ? '皆可' : undefined,
    },
  ];

  return (
    <div className="slot-strip" aria-label="服務單填寫進度">
      {items.map((it) => (
        <span key={it.label} className={`slot-chip${it.done ? ' done' : ''}`}>
          {it.done ? `${it.label}：${it.value}` : it.label}
        </span>
      ))}
    </div>
  );
}

/**
 * 生活管家對話介面。
 *
 * 這個畫面取代了原本 OpenPoint 的「服務搜尋 → 選分類 → 填諮詢單」流程。
 * 會員只講話，管家負責問清楚、找廠商、談價格、建單。
 */
export function AgentSheet({
  messages,
  request,
  busy,
  suggestions,
  offline,
  onClose,
  onSend,
  onPick,
}: {
  messages: ChatMessage[];
  request?: ServiceRequest | null;
  busy: boolean;
  suggestions: string[];
  offline: boolean;
  onClose: () => void;
  onSend: (text: string) => void;
  onPick: (p: VendorProposal) => void;
}) {
  const [text, setText] = useState('');
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // 新訊息時自動滾到底
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, busy]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function submit() {
    const value = text.trim();
    if (!value || busy) return;
    setText('');
    onSend(value);
  }

  const lastAgentMatch = [...messages].reverse().find((m) => m.match?.proposals?.length)?.match;
  const alreadyBooked = messages.some((m) => m.booking);

  return (
    <div className="sheet" role="dialog" aria-modal="true" aria-label="生活管家">
      <header className="sheet-head">
        <MascotIcon size={38} />
        <div>
          <div className="title">生活管家</div>
          <div className="subtitle">
            {busy ? '正在處理…' : '幫你搞定叫修、比價、預約'}
          </div>
        </div>
        <button onClick={onClose} aria-label="關閉對話" style={{ marginLeft: 'auto' }}>
          <CloseIcon size={20} />
        </button>
      </header>

      {offline && (
        <div className="offline-bar">
          連不到後端。請確認已執行 <code>python packages/api/app.py</code>
        </div>
      )}

      <SlotStrip request={request} />

      <div className="chat-log" ref={logRef}>
        {messages.map((m) => (
          <div key={m.id}>
            <div className={`bubble-row${m.role === 'user' ? ' me' : ''}`}>
              {m.role === 'agent' && <MascotIcon size={28} />}
              <div className={`bubble ${m.role === 'agent' ? 'agent' : 'me'}`}>{m.text}</div>
            </div>

            {/* 這一輪如果有媒合結果，直接把廠商卡片接在訊息下面 */}
            {m.match && m.match.proposals.length > 0 && (
              <div style={{ display: 'grid', gap: 8, marginTop: 8, paddingLeft: 36 }}>
                {m.match.proposals.map((p) => (
                  <ProposalCard
                    key={p.vendorId}
                    proposal={p}
                    isBest={p.vendorId === m.match?.recommendedVendorId}
                    onPick={onPick}
                    disabled={busy || alreadyBooked}
                  />
                ))}
              </div>
            )}

            {/* 建單成功的確認卡 */}
            {m.booking && (
              <div
                style={{
                  marginTop: 8,
                  marginLeft: 36,
                  background: '#e8f7ed',
                  border: '1.5px solid #00a03e',
                  borderRadius: 14,
                  padding: '12px 13px',
                }}
              >
                <div style={{ fontWeight: 800, color: '#00842f', fontSize: 14 }}>
                  預約成立
                </div>
                <div style={{ fontSize: 12, color: '#3d6b4d', marginTop: 3, lineHeight: 1.7 }}>
                  訂單 {m.booking.orderNo}
                  <br />
                  {m.booking.vendorName} · {m.booking.serviceDate}
                  <br />
                  訂金 {m.booking.depositAmount.toLocaleString('zh-TW')} 元
                </div>
              </div>
            )}

            {m.elapsedMs != null && (
              <div className="bubble-meta" style={{ paddingLeft: 36, marginTop: 3 }}>
                {(m.elapsedMs / 1000).toFixed(1)} 秒
                {m.trace?.length ? ` · ${m.trace.length} 個動作` : ''}
                {m.trace?.some((t) => t.agent === 'match-agent') ? ' · 已詢問廠商' : ''}
              </div>
            )}
          </div>
        ))}

        {busy && (
          <div className="bubble-row">
            <MascotIcon size={28} />
            <div className="bubble agent" style={{ padding: 0 }}>
              <div className="typing" aria-label="管家正在輸入">
                <i />
                <i />
                <i />
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="composer">
        {/* 沒有媒合結果前顯示建議話術，有結果後就不佔空間了 */}
        {!lastAgentMatch && suggestions.length > 0 && (
          <div className="quick-row">
            {suggestions.map((s) => (
              <button key={s} onClick={() => onSend(s)} disabled={busy}>
                {s}
              </button>
            ))}
          </div>
        )}
        <div className="composer-row">
          <label htmlFor="agent-input" className="sr-only">
            輸入訊息
          </label>
          <textarea
            id="agent-input"
            ref={inputRef}
            rows={1}
            value={text}
            placeholder="說說你遇到什麼問題…"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          <button
            className="send"
            onClick={submit}
            disabled={busy || !text.trim()}
            aria-label="送出"
          >
            <SendIcon size={17} />
          </button>
        </div>
      </div>
    </div>
  );
}
