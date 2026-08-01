import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import "./MyBookingsPage.css";

// 對應後端 mms_order_record 的前端型別
interface Booking {
  record_id: number;
  order_no: string;
  order_type: string;
  order_status: string;
  order_time: string;
  service_time: string | null;
  service_name: string;
  final_amount: number;
}

// 訂單類型對應中文
const ORDER_TYPE_MAP: Record<string, string> = {
  "01": "服務訂單",
  "02": "訂位",
  "03": "預約",
  "04": "其他",
  "05": "商品訂單",
  "06": "訂餐",
};

// 訂單狀態對應中文與顏色
const ORDER_STATUS_MAP: Record<string, { label: string; color: string }> = {
  "01": { label: "待付款", color: "#f39c12" },
  "02": { label: "待確認", color: "#f39c12" },
  "03": { label: "已確認", color: "#2980b9" },
  "04": { label: "進行中", color: "#8e44ad" },
  "80": { label: "已完成", color: "#27ae60" },
  "90": { label: "已取消", color: "#95a5a6" },
  "99": { label: "已退款", color: "#e74c3c" },
};

// Mock 資料 — 之後接後端 API
const MOCK_BOOKINGS: Booking[] = [
  {
    record_id: 1,
    order_no: "ORD20260801001",
    order_type: "01",
    order_status: "03",
    order_time: "2026-08-01T10:30:00Z",
    service_time: "2026-08-03T14:00:00Z",
    service_name: "冷氣清洗",
    final_amount: 2500,
  },
  {
    record_id: 2,
    order_no: "ORD20260730002",
    order_type: "02",
    order_status: "03",
    order_time: "2026-07-30T18:00:00Z",
    service_time: "2026-08-02T19:00:00Z",
    service_name: "餐廳訂位 - 鼎泰豐信義店",
    final_amount: 0,
  },
  {
    record_id: 3,
    order_no: "ORD20260728003",
    order_type: "03",
    order_status: "80",
    order_time: "2026-07-28T09:00:00Z",
    service_time: "2026-07-29T10:00:00Z",
    service_name: "洗衣機清洗",
    final_amount: 1800,
  },
  {
    record_id: 4,
    order_no: "ORD20260725004",
    order_type: "01",
    order_status: "04",
    order_time: "2026-07-25T11:00:00Z",
    service_time: "2026-08-01T09:00:00Z",
    service_name: "水電修繕 - 廚房水龍頭更換",
    final_amount: 3200,
  },
];

export default function MyBookingsPage() {
  const navigate = useNavigate();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "upcoming" | "completed">("all");

  useEffect(() => {
    // TODO: 之後換成 fetch(`${API_BASE_URL}/api/bookings`)
    setTimeout(() => {
      setBookings(MOCK_BOOKINGS);
      setLoading(false);
    }, 500);
  }, []);

  const filteredBookings = bookings.filter((b) => {
    if (filter === "upcoming") return ["01", "02", "03", "04"].includes(b.order_status);
    if (filter === "completed") return ["80", "90", "99"].includes(b.order_status);
    return true;
  });

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    return d.toLocaleDateString("zh-TW", {
      month: "numeric",
      day: "numeric",
      weekday: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="phone-frame">
      <div className="bookings-page">
        {/* 頂部導航 */}
        <div className="bookings-header">
          <button className="back-btn" onClick={() => navigate("/")}>
            ← 返回
          </button>
          <span className="bookings-title">我的預約</span>
          <div className="header-spacer" />
        </div>

        {/* 篩選 Tab */}
        <div className="filter-tabs">
          <button
            className={`filter-tab ${filter === "all" ? "active" : ""}`}
            onClick={() => setFilter("all")}
          >
            全部
          </button>
          <button
            className={`filter-tab ${filter === "upcoming" ? "active" : ""}`}
            onClick={() => setFilter("upcoming")}
          >
            即將到來
          </button>
          <button
            className={`filter-tab ${filter === "completed" ? "active" : ""}`}
            onClick={() => setFilter("completed")}
          >
            已完成
          </button>
        </div>

        {/* 預約列表 */}
        <div className="bookings-list">
          {loading ? (
            <div className="loading-state">載入中...</div>
          ) : filteredBookings.length === 0 ? (
            <div className="empty-state">
              <span className="empty-icon">📋</span>
              <p>目前沒有預約項目</p>
            </div>
          ) : (
            filteredBookings.map((booking) => {
              const status = ORDER_STATUS_MAP[booking.order_status] || {
                label: "未知",
                color: "#999",
              };
              return (
                <div key={booking.record_id} className="booking-card">
                  <div className="booking-card-header">
                    <span className="booking-type">
                      {ORDER_TYPE_MAP[booking.order_type] || "其他"}
                    </span>
                    <span
                      className="booking-status"
                      style={{ background: status.color }}
                    >
                      {status.label}
                    </span>
                  </div>
                  <div className="booking-card-body">
                    <h4 className="booking-service">{booking.service_name}</h4>
                    <div className="booking-info">
                      <span>📅 預約時間：{booking.service_time ? formatDate(booking.service_time) : "待確認"}</span>
                    </div>
                    <div className="booking-info">
                      <span>🧾 訂單編號：{booking.order_no}</span>
                    </div>
                    {booking.final_amount > 0 && (
                      <div className="booking-amount">
                        NT$ {booking.final_amount.toLocaleString()}
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
