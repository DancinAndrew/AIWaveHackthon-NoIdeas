import { useCallback, useEffect, useRef, useState } from 'react';
import { getContext, getHealth, postChat } from './api';
import type {
  Booking,
  ChatMessage,
  ContextResponse,
  ServiceRequest,
  UserPreferences,
  VendorProposal,
} from './types';
import { PhoneFrame } from './components/PhoneFrame';
import { HomeScreen } from './components/HomeScreen';
import { AgentSheet } from './components/AgentSheet';
import { OrderScreen } from './components/OrderScreen';
import { MemberScreen } from './components/MemberScreen';
import { PayScreen, PointsScreen } from './components/SimpleScreens';
import {
  HomeIcon,
  MemberIcon,
  OrderTrackIcon,
  PayIcon,
  PointsIcon,
  RainbowIcon,
} from './components/icons';

type Tab = 'home' | 'points' | 'pay' | 'service' | 'member';

const FALLBACK_PROMPTS = ['我家冷氣不冷了', '冷氣在滴水', '冷氣有異音'];

let seq = 0;
const nextId = () => `m${++seq}`;

export default function App() {
  const [now, setNow] = useState(() => new Date());
  const [tab, setTab] = useState<Tab>('home');
  const [showOrders, setShowOrders] = useState(false);
  const [agentOpen, setAgentOpen] = useState(false);
  const [bannerIndex, setBannerIndex] = useState(0);

  const [offline, setOffline] = useState(false);
  const [ctx, setCtx] = useState<ContextResponse | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [request, setRequest] = useState<ServiceRequest | null>(null);
  const [bookings, setBookings] = useState<Booking[]>([]);
  /** 對話中即時更新的偏好，會員中心會馬上反映管家學到什麼 */
  const [livePrefs, setLivePrefs] = useState<UserPreferences | null>(null);
  const sessionId = useRef<string | undefined>(undefined);

  /* ---- 時鐘與 banner 輪播，純視覺 ---- */
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 20_000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    const t = setInterval(() => setBannerIndex((i) => i + 1), 5_000);
    return () => clearInterval(t);
  }, []);

  /* ---- 開場載入後端狀態與會員背景 ---- */
  const loadContext = useCallback(async () => {
    try {
      await getHealth();
      const data = await getContext();
      setCtx(data);
      setBookings(data.bookings ?? []);
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, []);

  useEffect(() => {
    void loadContext();
  }, [loadContext]);

  /* ---- 送一句話給管家 ---- */
  const send = useCallback(
    async (text: string) => {
      setMessages((prev) => [...prev, { id: nextId(), role: 'user', text }]);
      setBusy(true);
      const started = performance.now();

      try {
        const res = await postChat({ message: text, sessionId: sessionId.current });
        sessionId.current = res.sessionId;
        setRequest(res.request ?? null);
        if (res.preferences) setLivePrefs(res.preferences);
        if (res.booking) {
          setBookings((prev) =>
            prev.some((b) => b.orderNo === res.booking!.orderNo)
              ? prev
              : [...prev, res.booking!],
          );
        }
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: 'agent',
            text: res.reply,
            match: res.match ?? null,
            booking: res.booking ?? null,
            trace: res.trace,
            elapsedMs: performance.now() - started,
          },
        ]);
        setOffline(false);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: 'agent',
            text: `抱歉，我這邊出了狀況：${err instanceof Error ? err.message : String(err)}`,
          },
        ]);
        setOffline(true);
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  /* ---- 開啟對話。第一次開場先讓管家打招呼，不要空白畫面 ---- */
  const openAgent = useCallback(
    (prompt?: string) => {
      setAgentOpen(true);
      setMessages((prev) => {
        if (prev.length > 0) return prev;
        const name = ctx?.user.displayName;
        const acs = (ctx?.user.appliances ?? []).filter((a) => a.kind === 'AC');
        const known =
          acs.length > 0
            ? `我看到你家有 ${acs.length} 台冷氣（${acs
                .map((a) => `${a.location ?? ''}${a.brand ?? ''}`)
                .join('、')}）。`
            : '';
        return [
          {
            id: nextId(),
            role: 'agent',
            text: `${name ? `${name}你好，` : '你好，'}我是你的生活管家。${known}\n有什麼需要幫忙的？直接說就好，不用填表單。`,
          },
        ];
      });
      if (prompt) {
        // 等 sheet 動畫開始後再送，訊息出現的順序才自然
        setTimeout(() => void send(prompt), 260);
      }
    },
    [ctx, send],
  );

  /* ---- 點「就約這家」＝ 用自然語言告訴管家，讓 agent 走正常決策路徑 ---- */
  const pickVendor = useCallback(
    (p: VendorProposal) => {
      void send(`我要約 ${p.vendorName}`);
    },
    [send],
  );

  const closeAgent = useCallback(() => {
    setAgentOpen(false);
    // 關掉對話後同步一次，訂單頁才看得到剛成立的單
    void loadContext();
  }, [loadContext]);

  const suggestions = ctx?.suggestedPrompts?.slice(0, 4) ?? FALLBACK_PROMPTS;
  const pendingCount =
    bookings.length + (request && request.status !== 'BOOKED' ? 1 : 0);

  const tabbar = (
    <nav className="tabbar" aria-label="主導覽">
      {(
        [
          { id: 'home', label: '首頁', icon: <HomeIcon /> },
          { id: 'points', label: '點數兌換', icon: <PointsIcon /> },
          { id: 'pay', label: '付款碼', icon: <PayIcon /> },
          { id: 'service', label: '服務', icon: <RainbowIcon /> },
          { id: 'member', label: '會員中心', icon: <MemberIcon /> },
        ] as const
      ).map((t) => (
        <button
          key={t.id}
          aria-current={tab === t.id && !showOrders ? 'page' : undefined}
          onClick={() => {
            setShowOrders(false);
            if (t.id === 'service') {
              // 「服務」在原 App 是服務分類清單 —— 那正是我們要取代的東西，
              // 所以這裡直接叫出管家，底層畫面保持不動。
              openAgent();
              return;
            }
            setTab(t.id as Tab);
          }}
        >
          {t.icon}
          {t.label}
        </button>
      ))}
    </nav>
  );

  return (
    <PhoneFrame now={now} tabbar={tabbar}>
      {offline && !agentOpen && (
        <div className="offline-bar">
          連不到後端。請先執行 <code>python packages/api/app.py</code>
        </div>
      )}

      {/* 訂單頁是浮動入口叫出來的，優先於 tab */}
      {showOrders ? (
        <OrderScreen
          bookings={bookings}
          requests={request ? [request] : (ctx?.requests ?? [])}
          onBack={() => setShowOrders(false)}
          onOpenAgent={() => openAgent()}
        />
      ) : tab === 'member' ? (
        <MemberScreen user={ctx?.user} livePreferences={livePrefs} />
      ) : tab === 'points' ? (
        <PointsScreen user={ctx?.user} />
      ) : tab === 'pay' ? (
        <PayScreen user={ctx?.user} />
      ) : (
        <HomeScreen onOpenAgent={openAgent} bannerIndex={bannerIndex} />
      )}

      {/* 訂單追蹤的浮動入口 —— 這是新增的功能，原 App 沒有集中的委託清單 */}
      {!agentOpen && !showOrders && (
        <button
          className="fab"
          onClick={() => setShowOrders(true)}
          aria-label={`追蹤我的委託${pendingCount ? `，${pendingCount} 筆` : ''}`}
        >
          <OrderTrackIcon size={30} />
          {pendingCount > 0 && <span className="badge">{pendingCount}</span>}
        </button>
      )}

      {agentOpen && (
        <AgentSheet
          messages={messages}
          request={request}
          busy={busy}
          suggestions={suggestions}
          offline={offline}
          onClose={closeAgent}
          onSend={send}
          onPick={pickVendor}
        />
      )}
    </PhoneFrame>
  );
}
