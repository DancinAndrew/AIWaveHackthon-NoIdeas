/**
 * 全部用 inline SVG，不引 icon 套件 —— 少一個相依、也不用擔心離線載不到字型。
 * 風格盡量貼近 OpenPoint App 的線性圖示。
 */

interface IconProps {
  size?: number;
  color?: string;
  className?: string;
}

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none',
  xmlns: 'http://www.w3.org/2000/svg',
  'aria-hidden': true as const,
});

export function SearchIcon({ size = 18, color = 'currentColor' }: IconProps) {
  return (
    <svg {...base(size)}>
      <circle cx="11" cy="11" r="6.5" stroke={color} strokeWidth="1.8" />
      <path d="M16 16l4.5 4.5" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function CloseIcon({ size = 20, color = 'currentColor' }: IconProps) {
  return (
    <svg {...base(size)}>
      <path
        d="M6 6l12 12M18 6L6 18"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function SendIcon({ size = 18, color = 'currentColor' }: IconProps) {
  return (
    <svg {...base(size)}>
      <path
        d="M4 12l16-8-6 8 6 8-16-8z"
        stroke={color}
        strokeWidth="1.7"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
}

export function BackIcon({ size = 20, color = 'currentColor' }: IconProps) {
  return (
    <svg {...base(size)}>
      <path
        d="M14.5 5L8 12l6.5 7"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function MicIcon({ size = 18, color = 'currentColor' }: IconProps) {
  return (
    <svg {...base(size)}>
      <rect x="9.2" y="3" width="5.6" height="10" rx="2.8" stroke={color} strokeWidth="1.7" />
      <path
        d="M5.5 11a6.5 6.5 0 0013 0M12 17.5V21"
        stroke={color}
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </svg>
  );
}

/* ---------------- 底部導覽 ---------------- */

export function HomeIcon({ size = 22, color = 'currentColor' }: IconProps) {
  return (
    <svg {...base(size)}>
      <path
        d="M4 10.5L12 4l8 6.5V19a1 1 0 01-1 1h-4v-5H9v5H5a1 1 0 01-1-1v-8.5z"
        stroke={color}
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function PointsIcon({ size = 22, color = 'currentColor' }: IconProps) {
  return (
    <svg {...base(size)}>
      <rect x="3.5" y="3.5" width="17" height="17" rx="4" stroke={color} strokeWidth="1.7" />
      <path
        d="M9.5 16.5v-9h3a2.6 2.6 0 010 5.2h-3"
        stroke={color}
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function PayIcon({ size = 22, color = 'currentColor' }: IconProps) {
  return (
    <svg {...base(size)}>
      <circle cx="12" cy="12" r="8.5" stroke={color} strokeWidth="1.7" />
      <path
        d="M12 6.5v11M14.8 9.2a2.8 2.8 0 00-2.8-1.4c-1.6 0-2.8.9-2.8 2.2s1 1.9 2.8 2.2c1.8.3 2.8.9 2.8 2.2s-1.2 2.2-2.8 2.2a2.9 2.9 0 01-2.9-1.5"
        stroke={color}
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** OpenPoint 的「服務」是彩虹圖示，這裡照配色重畫 */
export function RainbowIcon({ size = 22 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M2.5 19a9.5 9.5 0 0119 0" stroke="#4a9fd8" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M5.4 19a6.6 6.6 0 0113.2 0" stroke="#e2402f" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M8.3 19a3.7 3.7 0 017.4 0" stroke="#7cb342" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

export function MemberIcon({ size = 22, color = 'currentColor' }: IconProps) {
  return (
    <svg {...base(size)}>
      <circle cx="12" cy="8" r="3.8" stroke={color} strokeWidth="1.7" />
      <path
        d="M4.5 20c0-3.6 3.4-6 7.5-6s7.5 2.4 7.5 6"
        stroke={color}
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </svg>
  );
}

/* ---------------- 首頁功能格子（簡化的品類圖示） ---------------- */

export function TileIcon({
  glyph,
  bg,
  fg = '#fff',
  size = 42,
}: {
  glyph: string;
  bg: string;
  fg?: string;
  size?: number;
}) {
  return (
    <div
      aria-hidden
      style={{
        width: size,
        height: size,
        borderRadius: 12,
        background: bg,
        color: fg,
        display: 'grid',
        placeItems: 'center',
        fontSize: size * 0.44,
        fontWeight: 700,
        lineHeight: 1,
      }}
    >
      {glyph}
    </div>
  );
}

/* ---------------- 吉祥物 ---------------- */

/**
 * OPEN 小將風格的頭像。
 *
 * 這是依照 OPEN 小將的視覺特徵（三色彩虹外框 + 米白臉 + 對話框尖角）
 * 重新繪製的近似圖形，用途是讓 demo 看起來像 OpenPoint 生態的一部分。
 * 正式提案時應該向統一集團取得官方素材替換掉，這裡只是佔位。
 */
export function MascotIcon({ size = 40 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size * 0.96}
      viewBox="0 0 100 96"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="生活管家"
    >
      {/* 對話框本體：藍色最外圈，右上有尖角 */}
      <path
        d="M50 3C24 3 6 20 6 43c0 21 17 37 41 38l-3 12 20-13c19-4 30-19 30-37C94 20 76 3 50 3z"
        fill="#4a9fd8"
        stroke="#4a3728"
        strokeWidth="4.5"
        strokeLinejoin="round"
      />
      {/* 紅圈 */}
      <path
        d="M50 12C30 12 15 25 15 43s15 30 35 30 35-12 35-30S70 12 50 12z"
        fill="#e2402f"
        stroke="#4a3728"
        strokeWidth="3.6"
      />
      {/* 綠圈 */}
      <path
        d="M50 20C34 20 22 30 22 43.5S34 66 50 66s28-9 28-22.5S66 20 50 20z"
        fill="#7cb342"
        stroke="#4a3728"
        strokeWidth="3.2"
      />
      {/* 臉 */}
      <ellipse cx="50" cy="43.5" rx="21" ry="17.5" fill="#faf3e3" stroke="#4a3728" strokeWidth="3" />
      {/* 眼睛 */}
      <ellipse cx="42" cy="40" rx="3.4" ry="5" fill="#4a3728" />
      <ellipse cx="58" cy="40" rx="3.4" ry="5" fill="#4a3728" />
      {/* 鼻子 */}
      <ellipse cx="50" cy="47" rx="3.6" ry="2.4" fill="#8b6a4f" />
      {/* 嘴巴 */}
      <path
        d="M43 50.5c2.6 3.4 11.4 3.4 14 0"
        stroke="#4a3728"
        strokeWidth="2.6"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

/** 訂單追蹤 icon：吉祥物 + 收據，一眼看得出是「我的服務單」 */
export function OrderTrackIcon({ size = 30 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <rect
        x="6.5"
        y="3.5"
        width="19"
        height="25"
        rx="3"
        fill="#fff"
        stroke="#00a03e"
        strokeWidth="2"
      />
      <path
        d="M11 11h10M11 16h10M11 21h6"
        stroke="#00a03e"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <circle cx="24" cy="23.5" r="6.5" fill="#f47b20" stroke="#fff" strokeWidth="2" />
      <path
        d="M21.4 23.6l1.9 1.9 3.4-3.6"
        stroke="#fff"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function CheckIcon({ size = 10, color = '#fff' }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" fill="none" aria-hidden>
      <path
        d="M2.5 6.3l2.2 2.2L9.5 3.7"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function StarIcon({ size = 12, color = '#f47b20' }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill={color} aria-hidden>
      <path d="M8 1.5l1.9 4 4.4.6-3.2 3 .8 4.4L8 11.4l-3.9 2.1.8-4.4-3.2-3 4.4-.6L8 1.5z" />
    </svg>
  );
}
