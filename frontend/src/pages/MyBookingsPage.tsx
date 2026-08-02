import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "../api/client";
import type { ServiceRequestProjection } from "../api/types";
import {
  bookingStatusPresentation,
  orderStatusLabel,
  pointsRewardPresentation,
} from "../api/viewModels";
import "./MyBookingsPage.css";


function isProduct(booking: ServiceRequestProjection): boolean {
  return booking.serviceType === "product_purchase";
}

function UtilityBookingDetails({
  booking,
}: {
  booking: ServiceRequestProjection;
}) {
  return (
    <>
      <div className="booking-info">
        <span>📍 服務地區：{booking.districtName ?? "確認中"}</span>
      </div>
      <div className="booking-info">
        <span>📅 希望時段：{booking.preferredTime ?? "確認中"}</span>
      </div>
      <div className="booking-info">
        <span>🧑‍🔧 媒合廠商：{booking.provider?.name ?? "尚未委派"}</span>
      </div>
    </>
  );
}

function ProductBookingDetails({
  booking,
}: {
  booking: ServiceRequestProjection;
}) {
  const orderLabel = orderStatusLabel(booking.orderStatus);
  const outOfStock = booking.progress.stage === "out_of_stock";
  return (
    <>
      <div className="booking-info">
        <span>📍 收貨地區：{booking.districtName ?? "確認中"}</span>
      </div>
      <div className="booking-info">
        <span>🔢 數量：{booking.quantity ?? 1}</span>
      </div>
      <div className="booking-info">
        <span>🏪 供應商：{booking.provider?.name ?? "尚未委派"}</span>
      </div>
      {/* An order only exists after the resident confirms, so an out-of-stock or
          still-selecting case must never look like money has been committed. */}
      {booking.orderNo && orderLabel ? (
        <div className="booking-info">
          <span>
            🧾 訂單：{booking.orderNo}（{orderLabel}）
          </span>
        </div>
      ) : (
        <div className="booking-info">
          <span>🧾 {outOfStock ? "缺貨，尚未建立訂單" : "尚未建立訂單"}</span>
        </div>
      )}
    </>
  );
}


export default function MyBookingsPage() {
  const navigate = useNavigate();
  const [bookings, setBookings] = useState<ServiceRequestProjection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "upcoming" | "completed">("all");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const result = await apiClient.listServiceRequests();
        if (!cancelled) {
          setBookings(result.items);
          setError(null);
        }
      } catch {
        if (!cancelled) setError("無法取得最新進度，請確認後端連線。 ");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const filteredBookings = bookings.filter((booking) => {
    if (filter === "all") return true;
    return bookingStatusPresentation(booking.progress.stage).filter === filter;
  });

  const formatDate = (date: string) =>
    new Date(date).toLocaleDateString("zh-TW", {
      month: "numeric",
      day: "numeric",
      weekday: "short",
      hour: "2-digit",
      minute: "2-digit",
    });

  return (
    <div className="phone-frame">
      <div className="bookings-page">
        <div className="bookings-header">
          <button className="back-btn" onClick={() => navigate("/")}>
            ← 返回
          </button>
          <span className="bookings-title">我的預約</span>
          <div className="header-spacer" />
        </div>

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
            進行中
          </button>
          <button
            className={`filter-tab ${filter === "completed" ? "active" : ""}`}
            onClick={() => setFilter("completed")}
          >
            已完成
          </button>
        </div>

        {error && <div className="bookings-error">{error}</div>}

        <div className="bookings-list">
          {loading ? (
            <div className="loading-state">載入中...</div>
          ) : filteredBookings.length === 0 ? (
            <div className="empty-state">
              <span className="empty-icon">📋</span>
              <p>目前沒有預約項目</p>
              <button className="start-chat-btn" onClick={() => navigate("/chat")}>
                到智慧助理提出需求
              </button>
            </div>
          ) : (
            filteredBookings.map((booking) => {
              const status = bookingStatusPresentation(booking.progress.stage);
              const latestEvent = booking.progress.events?.at(-1);
              const reward = booking.pointsReward
                ? pointsRewardPresentation(booking.pointsReward)
                : null;
              return (
                <button
                  key={booking.serviceRequestId}
                  className="booking-card booking-card-button"
                  onClick={() =>
                    navigate(`/chat?conversation=${booking.conversationId}`)
                  }
                >
                  <div className="booking-card-header">
                    <span className="booking-type">{booking.serviceName}</span>
                    <span
                      className="booking-status"
                      style={{ background: status.color }}
                    >
                      {status.label}
                    </span>
                  </div>
                  <div className="booking-card-body">
                    <h4 className="booking-service">{booking.summary}</h4>
                    {isProduct(booking) ? (
                      <ProductBookingDetails booking={booking} />
                    ) : (
                      <UtilityBookingDetails booking={booking} />
                    )}
                    {/* 點數揭露對兩類服務都適用，所以放在分類子元件之外的共用
                        位置，否則商品訂單看不到自己的回饋。 */}
                    {reward && (
                      <div
                        className={`booking-points${reward.granted ? " granted" : ""}`}
                      >
                        <div className="booking-points-head">
                          <span className="booking-points-program">
                            {reward.program}
                          </span>
                          <span className="booking-points-value">
                            {reward.headline}
                          </span>
                          <span className="booking-points-status">
                            {reward.statusLabel}
                          </span>
                        </div>
                        <div className="booking-points-basis">
                          {reward.basis}
                        </div>
                        <div className="booking-points-note">{reward.note}</div>
                      </div>
                    )}
                    <div className="booking-progress-label">
                      {booking.progress.residentActionRequired ? "⚠️ " : "● "}
                      {booking.progress.displayLabel}
                    </div>
                    <div className="booking-updated">
                      {latestEvent?.label ?? "需求已建立"} · {formatDate(
                        booking.progress.latestEventAt,
                      )}
                    </div>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
