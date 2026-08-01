import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import "./DashboardPage.css";

// 對應 mms_order_record 的前端型別
interface BookingRequest {
  record_id: number;
  order_no: string;
  order_type: string;
  order_status: string;
  order_time: string;
  service_time: string | null;
  service_name: string;
  customer_name: string;
  customer_phone: string;
  address: string;
  final_amount: number;
  note: string;
}

const ORDER_TYPE_MAP: Record<string, string> = {
  "01": "服務訂單",
  "02": "訂位",
  "03": "預約",
  "04": "其他",
  "05": "商品訂單",
  "06": "訂餐",
};

// Mock 資料 — 之後接後端 API
const MOCK_REQUESTS: BookingRequest[] = [
  {
    record_id: 101,
    order_no: "ORD20260801010",
    order_type: "01",
    order_status: "02",
    order_time: "2026-08-01T11:30:00Z",
    service_time: "2026-08-03T14:00:00Z",
    service_name: "冷氣清洗（分離式 x2）",
    customer_name: "王*明",
    customer_phone: "0912***456",
    address: "台北市信義區松仁路 XX 號",
    final_amount: 4000,
    note: "希望下午 2 點後到，有養寵物請注意",
  },
  {
    record_id: 102,
    order_no: "ORD20260801011",
    order_type: "03",
    order_status: "02",
    order_time: "2026-08-01T10:00:00Z",
    service_time: "2026-08-02T10:00:00Z",
    service_name: "洗衣機清洗（直立式）",
    customer_name: "李*華",
    customer_phone: "0987***321",
    address: "新北市板橋區文化路 XX 號 3F",
    final_amount: 1800,
    note: "",
  },
  {
    record_id: 103,
    order_no: "ORD20260731008",
    order_type: "01",
    order_status: "02",
    order_time: "2026-07-31T16:00:00Z",
    service_time: "2026-08-04T09:00:00Z",
    service_name: "水電修繕 — 浴室漏水檢修",
    customer_name: "張*芬",
    customer_phone: "0955***789",
    address: "台北市大安區忠孝東路 XX 巷 X 號",
    final_amount: 0,
    note: "需現場估價，希望早上時段",
  },
  {
    record_id: 104,
    order_no: "ORD20260730005",
    order_type: "02",
    order_status: "02",
    order_time: "2026-07-30T20:00:00Z",
    service_time: "2026-08-02T18:30:00Z",
    service_name: "餐廳訂位 — 鼎泰豐信義店（4 位）",
    customer_name: "陳*宇",
    customer_phone: "0922***654",
    address: "",
    final_amount: 0,
    note: "需要兒童座椅 x1",
  },
];

export default function DashboardPage() {
  const navigate = useNavigate();
  const [requests, setRequests] = useState<BookingRequest[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // TODO: 之後換成 fetch(`${API_BASE_URL}/api/admin/bookings?status=pending`)
    setTimeout(() => {
      setRequests(MOCK_REQUESTS);
      setLoading(false);
    }, 400);
  }, []);

  const handleAccept = (recordId: number) => {
    setRequests((prev) =>
      prev.map((r) =>
        r.record_id === recordId ? { ...r, order_status: "03" } : r
      )
    );
  };

  const handleReject = (recordId: number) => {
    setRequests((prev) =>
      prev.map((r) =>
        r.record_id === recordId ? { ...r, order_status: "90" } : r
      )
    );
  };

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

  const pendingRequests = requests.filter((r) => r.order_status === "02");
  const processedRequests = requests.filter((r) => r.order_status !== "02");

  return (
    <div className="phone-frame">
      <div className="dashboard-page">
        {/* 頂部導航 */}
        <div className="dashboard-header">
          <button className="back-btn" onClick={() => navigate("/")}>
            ← 返回
          </button>
          <span className="dashboard-title">後台管理</span>
          <div className="header-spacer" />
        </div>

        {/* 統計摘要 */}
        <div className="stats-bar">
          <div className="stat-item">
            <span className="stat-number">{pendingRequests.length}</span>
            <span className="stat-label">待處理</span>
          </div>
          <div className="stat-item">
            <span className="stat-number accepted">{processedRequests.filter((r) => r.order_status === "03").length}</span>
            <span className="stat-label">已接受</span>
          </div>
          <div className="stat-item">
            <span className="stat-number rejected">{processedRequests.filter((r) => r.order_status === "90").length}</span>
            <span className="stat-label">已拒絕</span>
          </div>
        </div>

        {/* 待處理預約列表 */}
        <div className="dashboard-list">
          {loading ? (
            <div className="loading-state">載入中...</div>
          ) : pendingRequests.length === 0 && processedRequests.length === 0 ? (
            <div className="empty-state">
              <span className="empty-icon">✅</span>
              <p>目前沒有待處理的預約</p>
            </div>
          ) : (
            <>
              {pendingRequests.length > 0 && (
                <h3 className="list-section-title">待處理（{pendingRequests.length}）</h3>
              )}
              {pendingRequests.map((req) => (
                <div key={req.record_id} className="request-card pending">
                  <div className="request-card-header">
                    <span className="request-type">{ORDER_TYPE_MAP[req.order_type] || "其他"}</span>
                    <span className="request-time">提交：{formatDate(req.order_time)}</span>
                  </div>
                  <div className="request-card-body">
                    <h4 className="request-service">{req.service_name}</h4>
                    <div className="request-detail">
                      <span>👤 {req.customer_name}　📱 {req.customer_phone}</span>
                    </div>
                    {req.address && (
                      <div className="request-detail">
                        <span>📍 {req.address}</span>
                      </div>
                    )}
                    <div className="request-detail">
                      <span>📅 預約時間：{req.service_time ? formatDate(req.service_time) : "待確認"}</span>
                    </div>
                    {req.final_amount > 0 && (
                      <div className="request-detail amount">
                        <span>💰 NT$ {req.final_amount.toLocaleString()}</span>
                      </div>
                    )}
                    {req.note && (
                      <div className="request-note">
                        <span>📝 備註：{req.note}</span>
                      </div>
                    )}
                  </div>
                  <div className="request-actions">
                    <button className="action-btn reject" onClick={() => handleReject(req.record_id)}>
                      拒絕
                    </button>
                    <button className="action-btn accept" onClick={() => handleAccept(req.record_id)}>
                      接受
                    </button>
                  </div>
                </div>
              ))}

              {processedRequests.length > 0 && (
                <>
                  <h3 className="list-section-title">已處理（{processedRequests.length}）</h3>
                  {processedRequests.map((req) => (
                    <div key={req.record_id} className={`request-card ${req.order_status === "03" ? "accepted" : "rejected"}`}>
                      <div className="request-card-header">
                        <span className="request-type">{ORDER_TYPE_MAP[req.order_type] || "其他"}</span>
                        <span className={`request-badge ${req.order_status === "03" ? "badge-accepted" : "badge-rejected"}`}>
                          {req.order_status === "03" ? "已接受" : "已拒絕"}
                        </span>
                      </div>
                      <div className="request-card-body">
                        <h4 className="request-service">{req.service_name}</h4>
                        <div className="request-detail">
                          <span>👤 {req.customer_name}　📅 {req.service_time ? formatDate(req.service_time) : "待確認"}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
