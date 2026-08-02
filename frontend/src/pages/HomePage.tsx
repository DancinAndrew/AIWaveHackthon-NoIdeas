import { useNavigate } from "react-router-dom";
import openImg from "../assets/open.png";
import "./HomePage.css";

export default function HomePage() {
  const navigate = useNavigate();

  return (
    <div className="phone-frame">
      <div className="app-content">
        {/* 頂部狀態列 */}
        <div className="status-bar">
          <span className="status-time">16:00 🔕</span>
          <span className="status-right">|||  4G 🔋57</span>
        </div>

        {/* 搜尋列 + Chatbot 按鈕 */}
        <div className="search-row">
          <div className="search-bar" onClick={() => navigate("/chat")}>
            <span className="search-icon">🔍</span>
            <span className="search-text">輸入文字或語音搜尋</span>
          </div>
          <button className="chatbot-btn" onClick={() => navigate("/chat")} aria-label="AI 智慧助理">
            <img src={openImg} alt="OPEN小將" className="chatbot-icon" />
          </button>
        </div>

        {/* 我的常用功能區塊 */}
        <div className="section-card">
          <div className="section-header">
            <span className="section-title">我的常用功能</span>
            <span className="section-edit">編輯</span>
          </div>
          <div className="icon-grid">
            <div className="icon-item">
              <div className="icon-circle white">💚</div>
              <span className="icon-label">uniopen</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle white">👤</div>
              <span className="icon-label">會員訂閱制</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle white"><span className="icon-text-bold">M</span></div>
              <span className="icon-label">iOPEN Mall</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle white">🚗</div>
              <span className="icon-label">外送平台</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle white">☁️</div>
              <span className="icon-label">雲端開心卡</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle white">💳</div>
              <span className="icon-label">聯名卡官網</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle white">🧾</div>
              <span className="icon-label">發票日誌</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle white">📦</div>
              <span className="icon-label">寄取包裹</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle white">🗺️</div>
              <span className="icon-label">i 地圖</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle white">🎟️</div>
              <span className="icon-label">兌換券</span>
            </div>
          </div>
        </div>

        {/* 美麗生活圈 */}
        <div className="section-block">
          <h3 className="block-title">美麗生活圈</h3>
          <div className="icon-grid">
            <div className="icon-item">
              <div className="icon-circle green-outline">☕</div>
              <span className="icon-label">星巴克</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">💊</div>
              <span className="icon-label">康是美</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🏬</div>
              <span className="icon-label">高雄夢時代</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🏢</div>
              <span className="icon-label">台北時代</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🌿</div>
              <span className="icon-label">BEING spa</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">⚽</div>
              <span className="icon-label">BEINGsport</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🏋️</div>
              <span className="icon-label">BEING fit</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🎨</div>
              <span className="icon-label">UNIKCY</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">💚</div>
              <span className="icon-label">統一藥品</span>
            </div>
          </div>
        </div>

        {/* 會員生活圈 */}
        <div className="section-block">
          <h3 className="block-title">會員生活圈</h3>
          <div className="icon-grid">
            <div className="icon-item">
              <div className="icon-circle green-outline">💚</div>
              <span className="icon-label">uniopen</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🏠</div>
              <span className="icon-label">萬家福</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🎵</div>
              <span className="icon-label">速邁樂</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">📚</div>
              <span className="icon-label">博客來</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline"><span className="icon-text-bold">M</span></div>
              <span className="icon-label">iOPEN Mall</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🟣</div>
              <span className="icon-label">Yahoo</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🛒</div>
              <span className="icon-label">PChome</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🍔</div>
              <span className="icon-label">foodomo</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🍦</div>
              <span className="icon-label">聖德科斯</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🍩</div>
              <span className="icon-label">統一多拿滋</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🍜</div>
              <span className="icon-label">21風味館</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🍕</div>
              <span className="icon-label">酷聖石</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🧴</div>
              <span className="icon-label">Semeur聖娜</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🥬</div>
              <span className="icon-label">統一生機</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">📊</div>
              <span className="icon-label">統一證券</span>
            </div>
          </div>
        </div>

        {/* 熱門服務 */}
        <div className="section-block">
          <h3 className="block-title">熱門服務</h3>
          <div className="icon-grid">
            <div className="icon-item">
              <div className="icon-circle green-outline badge-new">🔧</div>
              <span className="icon-label">水電修繕</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🔍</div>
              <span className="icon-label">服務搜尋</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🍽️</div>
              <span className="icon-label">AI美食護照</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">💰</div>
              <span className="icon-label">代收優惠</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🏪</div>
              <span className="icon-label">門市查詢</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">✖️</div>
              <span className="icon-label">X STORE</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">🏢</div>
              <span className="icon-label">門市招募</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">👕</div>
              <span className="icon-label">洗衣機清潔</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">❄️</div>
              <span className="icon-label">冷氣清潔</span>
            </div>
            <div className="icon-item">
              <div className="icon-circle green-outline">👔</div>
              <span className="icon-label">企客專區</span>
            </div>
          </div>
        </div>

        {/* 我的預約入口（獨立區塊突出顯示） */}
        <div className="section-block">
          <h3 className="block-title">快捷功能</h3>
          <div className="icon-grid">
            <div className="icon-item new-feature" onClick={() => navigate("/my-bookings")}>
              <div className="icon-circle green-outline highlight">📅</div>
              <span className="icon-label">我的預約</span>
            </div>
            <div className="icon-item new-feature" onClick={() => navigate("/dashboard")}>
              <div className="icon-circle green-outline highlight">🛠️</div>
              <span className="icon-label">後台管理</span>
            </div>
          </div>
        </div>

        {/* 底部留白 */}
        <div className="bottom-spacer" />
      </div>

      {/* 底部 Tab Bar */}
      <div className="tab-bar">
        <div className="tab-item active">
          <span className="tab-icon">🏠</span>
          <span className="tab-label">首頁</span>
        </div>
        <div className="tab-item">
          <span className="tab-icon">🅿️</span>
          <span className="tab-label">點數兌換</span>
        </div>
        <div className="tab-item">
          <span className="tab-icon">💲</span>
          <span className="tab-label">付款碼</span>
        </div>
        <div className="tab-item">
          <span className="tab-icon">🛎️</span>
          <span className="tab-label">服務</span>
        </div>
        <div className="tab-item" onClick={() => navigate("/dashboard")}>
          <span className="tab-icon">👤</span>
          <span className="tab-label">會員中心</span>
        </div>
      </div>
    </div>
  );
}
