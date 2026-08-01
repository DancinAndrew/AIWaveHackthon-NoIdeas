import { MicIcon, SearchIcon, TileIcon } from './icons';

/**
 * 首頁：對照 OpenPoint App 的版面重建。
 *
 * 唯一的「產品改動」在最上面的搜尋列 —— 原本是關鍵字搜尋，
 * 現在點下去會叫出生活管家對話。這是整個提案的入口。
 */

interface Tile {
  label: string;
  glyph: string;
  bg: string;
  isNew?: boolean;
  /** 有值的話點下去會帶著這句話直接開對話 */
  prompt?: string;
}

// 我的常用功能（照截圖順序）
const FAVORITES: Tile[] = [
  { label: '會員訂閱制', glyph: '訂', bg: '#f5a623' },
  { label: 'iOPEN Mall', glyph: 'M', bg: '#7cb342' },
  { label: '外送平台', glyph: '送', bg: '#e2402f' },
  { label: '雲端開心卡', glyph: '卡', bg: '#4a9fd8' },
  { label: '聯名卡官網', glyph: '聯', bg: '#00a03e' },
  { label: '發票日誌', glyph: '票', bg: '#7cb342' },
  { label: '寄取包裹', glyph: '包', bg: '#8b6a4f' },
  { label: 'i 地圖', glyph: '圖', bg: '#e2402f' },
  { label: '兌換券', glyph: '券', bg: '#f47b20' },
];

// 熱門服務（水電修繕、冷氣清潔這些正是我們 agent 要接管的品類）
const SERVICES: Tile[] = [
  {
    label: '水電修繕',
    glyph: '修',
    bg: '#f47b20',
    isNew: true,
    prompt: '家裡水電有問題想找人來看',
  },
  { label: '服務搜尋', glyph: '搜', bg: '#7cb342' },
  { label: 'AI美食護照', glyph: 'AI', bg: '#4a9fd8' },
  { label: '代收優惠', glyph: '%', bg: '#e2402f' },
  { label: '門市查詢', glyph: '店', bg: '#00a03e' },
  { label: 'X STORE', glyph: 'X', bg: '#23272e' },
  { label: '門市招募', glyph: '徵', bg: '#8b6a4f' },
  { label: '洗衣機清潔', glyph: '洗', bg: '#4a9fd8' },
  {
    label: '冷氣清潔',
    glyph: '冷',
    bg: '#00a9c8',
    prompt: '我想預約冷氣清洗',
  },
  { label: '企客專區', glyph: '企', bg: '#7cb342' },
];

const BANNERS = [
  {
    title: '冷氣壞了？跟管家說一句就好',
    body: '不用填表單、不用比價，管家幫你找師傅、談好價格',
    bg: 'linear-gradient(120deg, #00a03e, #4a9fd8)',
  },
  {
    title: '買指定貝殼幣序號 2990 元',
    body: '送限量虛寶．累儲達標再加碼',
    bg: 'linear-gradient(120deg, #1c2b6b, #7b2ff7)',
  },
  {
    title: 'OPEN POINT 點數 20% 回饋',
    body: '指定服務完成即贈．活動至 08/31',
    bg: 'linear-gradient(120deg, #f47b20, #f6c344)',
  },
];

export function HomeScreen({
  onOpenAgent,
  bannerIndex,
}: {
  onOpenAgent: (prompt?: string) => void;
  bannerIndex: number;
}) {
  const banner = BANNERS[bannerIndex % BANNERS.length];

  return (
    <div className="screen">
      {/* ---- 搜尋列改成 agent 入口 ---- */}
      <div className="searchbar-wrap">
        <button
          className="searchbar"
          onClick={() => onOpenAgent()}
          aria-label="開啟生活管家對話"
        >
          <SearchIcon size={17} color="#9aa1ab" />
          <span>跟管家說你需要什麼</span>
          <span className="agent-hint">
            <MicIcon size={11} color="#00842f" />
            AI 管家
          </span>
        </button>
      </div>

      {/* ---- 我的常用功能 ---- */}
      <section className="card" aria-labelledby="fav-title">
        <div className="card-head green">
          <span id="fav-title">我的常用功能</span>
          <span className="link">編輯</span>
        </div>
        <div className="grid5">
          {FAVORITES.map((t) => (
            <button
              key={t.label}
              className="grid-item"
              onClick={() => t.prompt && onOpenAgent(t.prompt)}
            >
              <span className="ico">
                <TileIcon glyph={t.glyph} bg={t.bg} />
              </span>
              {t.label}
            </button>
          ))}
        </div>
      </section>

      {/* ---- 輪播 banner ---- */}
      <div className="banner">
        <div
          className="banner-slide"
          style={{ background: banner.bg }}
          role="img"
          aria-label={banner.title}
        >
          <h3>{banner.title}</h3>
          <p>{banner.body}</p>
        </div>
        <div className="banner-dots" aria-hidden>
          {BANNERS.map((b, i) => (
            <i key={b.title} className={i === bannerIndex % BANNERS.length ? 'on' : ''} />
          ))}
        </div>
      </div>

      {/* ---- 熱門服務 ---- */}
      <section className="card" aria-labelledby="svc-title">
        <div className="card-head">
          <span id="svc-title">熱門服務</span>
        </div>
        <div className="grid5">
          {SERVICES.map((t) => (
            <button
              key={t.label}
              className="grid-item"
              onClick={() => onOpenAgent(t.prompt)}
            >
              {t.isNew && <span className="tag-new">NEW</span>}
              <span className="ico">
                <TileIcon glyph={t.glyph} bg={t.bg} />
              </span>
              {t.label}
            </button>
          ))}
        </div>
      </section>

      {/* ---- 熱門功能（截圖底部露出的那一區）---- */}
      <section className="card" aria-labelledby="fn-title">
        <div className="card-head">
          <span id="fn-title">熱門功能</span>
        </div>
        <div className="grid5" style={{ paddingBottom: 18 }}>
          {[
            { label: '會員訂閱制', glyph: '訂', bg: '#f5a623' },
            { label: 'i 划算', glyph: '划', bg: '#7cb342' },
            { label: 'i 預購', glyph: '購', bg: '#e2402f' },
            { label: '購物中心', glyph: '物', bg: '#4a9fd8' },
            { label: '開心卡', glyph: '心', bg: '#00a03e' },
          ].map((t) => (
            <div key={t.label} className="grid-item">
              <span className="ico">
                <TileIcon glyph={t.glyph} bg={t.bg} />
              </span>
              {t.label}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
