import type { ReactNode } from 'react';

/** iPhone 風格狀態列。時間會走，讓 demo 錄影看起來自然一點。 */
function StatusBar({ now }: { now: Date }) {
  const hh = now.getHours();
  const mm = String(now.getMinutes()).padStart(2, '0');
  return (
    <div className="statusbar">
      <span>
        {hh}:{mm}
      </span>
      <span className="statusbar-right" aria-hidden>
        <svg width="17" height="12" viewBox="0 0 17 12" fill="currentColor">
          <rect x="0" y="8" width="3" height="4" rx="0.8" />
          <rect x="4.5" y="6" width="3" height="6" rx="0.8" />
          <rect x="9" y="3.5" width="3" height="8.5" rx="0.8" />
          <rect x="13.5" y="1" width="3" height="11" rx="0.8" opacity="0.35" />
        </svg>
        <span style={{ fontSize: 11, fontWeight: 700 }}>4G</span>
        <span className="battery">
          <span style={{ width: '69%' }} />
        </span>
      </span>
    </div>
  );
}

/**
 * 手機外框。
 * 桌機上會畫出實體手機邊框（demo 時投影出來比較有說服力），
 * 視窗寬度 < 480px 時自動變成滿版，真的用手機開也正常。
 */
export function PhoneFrame({
  now,
  children,
  tabbar,
}: {
  now: Date;
  children: ReactNode;
  tabbar: ReactNode;
}) {
  return (
    <div className="phone-shell">
      <StatusBar now={now} />
      {children}
      {tabbar}
    </div>
  );
}
