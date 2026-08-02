import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient, createApiClient } from "../api/client";
import type { DemoProvider, ProviderTask } from "../api/types";
import { providerTaskPresentation } from "../api/viewModels";
import "./DashboardPage.css";


/**
 * Fallback so the dashboard still works if the demo provider list cannot be
 * fetched. The live list comes from the backend, which derives suppliers from
 * the catalogue, so these two utility providers are only a safety net.
 */
const FALLBACK_PROVIDERS: DemoProvider[] = [
  {
    providerId: "31324fe0-9899-5382-8211-d0122c20bda0",
    name: "京鑫水電工程行",
    serviceType: "utility_repair",
    serviceName: "水電修繕",
  },
  {
    providerId: "29722c58-1d40-5dd9-9bf3-4cfcdfefb60a",
    name: "新旺水電工程行",
    serviceType: "utility_repair",
    serviceName: "水電修繕",
  },
];

/** Two business days out, matching the placeholder suppliers usually pick. */
function defaultShipDate(): string {
  const date = new Date();
  date.setDate(date.getDate() + 2);
  return date.toISOString().slice(0, 10);
}

function shortProviderName(name: string): string {
  return name.replace("水電工程行", "").replace("選品商城", "");
}

interface ProcessedTask {
  task: ProviderTask;
  action: "accepted" | "declined" | "needs_information" | "expired";
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const [providers, setProviders] =
    useState<DemoProvider[]>(FALLBACK_PROVIDERS);
  const [providerId, setProviderId] = useState<string>(
    FALLBACK_PROVIDERS[0].providerId,
  );
  const api = useMemo(() => createApiClient({ providerId }), [providerId]);
  const [tasks, setTasks] = useState<ProviderTask[]>([]);
  const [processed, setProcessed] = useState<ProcessedTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);
  const [questions, setQuestions] = useState<Record<string, string>>({});
  const [arrivalWindows, setArrivalWindows] = useState<Record<string, string>>(
    {},
  );
  const [shipDates, setShipDates] = useState<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const result = await api.listProviderTasks();
        if (!cancelled) {
          setTasks(result.items);
          setError(null);
        }
      } catch {
        if (!cancelled) setError("無法取得廠商任務，請確認後端連線。 ");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    setLoading(true);
    void load();
    const timer = window.setInterval(() => void load(), 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [api]);

  useEffect(() => {
    let cancelled = false;
    const loadProviders = async () => {
      try {
        const result = await apiClient.listDemoProviders();
        if (!cancelled && result.items.length > 0) setProviders(result.items);
      } catch {
        // Keep the fallback list; role switching still works for utility.
      }
    };
    void loadProviders();
    return () => {
      cancelled = true;
    };
  }, []);

  const providersByService = useMemo(() => {
    const grouped: Record<string, DemoProvider[]> = {};
    for (const provider of providers) {
      (grouped[provider.serviceName] ??= []).push(provider);
    }
    return grouped;
  }, [providers]);

  const respond = async (
    task: ProviderTask,
    action: "accept" | "decline" | "needs_information",
  ) => {
    const question = questions[task.taskId]?.trim();
    // Accepting requires a different field per service type: utility providers
    // commit to an arrival window, product suppliers to a ship date.
    const isProduct = task.brief?.serviceType === "product_purchase";
    const arrivalWindow =
      arrivalWindows[task.taskId]?.trim() || "2026-08-03 14:00-17:00";
    const estimatedShipDate =
      shipDates[task.taskId]?.trim() || defaultShipDate();
    if (action === "needs_information" && !question) {
      setError("請先輸入要詢問住戶的問題。 ");
      return;
    }
    setBusyTaskId(task.taskId);
    setError(null);
    try {
      await api.respondToProviderTask(task.taskId, {
        action,
        expectedVersion: task.version,
        message:
          action === "needs_information"
            ? question
            : action === "decline"
              ? "目前滿單，請平台改派。"
              : isProduct
                ? "確認庫存與地址無誤，將依約出貨。"
                : "到場先檢測問題與報價，住戶確認後才施工。",
        arrivalWindow:
          action === "accept" && !isProduct ? arrivalWindow : undefined,
        estimatedShipDate:
          action === "accept" && isProduct ? estimatedShipDate : undefined,
      });
      setProcessed((current) => [
        {
          task,
          action:
            action === "accept"
              ? "accepted"
              : action === "decline"
                ? "declined"
                : "needs_information",
        },
        ...current.filter((item) => item.task.taskId !== task.taskId),
      ]);
      setTasks((current) =>
        current.filter((item) => item.taskId !== task.taskId),
      );
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "操作失敗，請稍後再試。",
      );
    } finally {
      setBusyTaskId(null);
    }
  };

  const simulateTimeout = async (task: ProviderTask) => {
    setBusyTaskId(task.taskId);
    setError(null);
    try {
      await api.simulateTimeout(task.taskId, "Demo 展示廠商逾時後自動改派");
      setProcessed((current) => [
        { task, action: "expired" },
        ...current.filter((item) => item.task.taskId !== task.taskId),
      ]);
      setTasks((current) =>
        current.filter((item) => item.taskId !== task.taskId),
      );
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "操作失敗，請稍後再試。",
      );
    } finally {
      setBusyTaskId(null);
    }
  };

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
      <div className="dashboard-page">
        <div className="dashboard-header">
          <button className="back-btn" onClick={() => navigate("/")}>
            ← 返回
          </button>
          <span className="dashboard-title">後台管理</span>
          <div className="header-spacer" />
        </div>

        <div className="stats-bar">
          <div className="stat-item">
            <span className="stat-number">{tasks.length}</span>
            <span className="stat-label">待處理</span>
          </div>
          <div className="stat-item">
            <span className="stat-number accepted">
              {processed.filter((item) => item.action === "accepted").length}
            </span>
            <span className="stat-label">已接受</span>
          </div>
          <div className="stat-item">
            <span className="stat-number rejected">
              {processed.filter((item) => item.action !== "accepted").length}
            </span>
            <span className="stat-label">其他處理</span>
          </div>
        </div>

        <div className="provider-switcher">
          <span className="provider-switcher-label">Demo 登入：</span>
          <select
            className="provider-select"
            value={providerId}
            onChange={(event) => setProviderId(event.target.value)}
            aria-label="選擇要登入的廠商或供應商"
          >
            {Object.entries(providersByService).map(([serviceName, group]) => (
              <optgroup key={serviceName} label={serviceName}>
                {group.map((provider) => (
                  <option key={provider.providerId} value={provider.providerId}>
                    {shortProviderName(provider.name)}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>

        {error && <div className="dashboard-error">{error}</div>}

        <div className="dashboard-list">
          {loading ? (
            <div className="loading-state">載入中...</div>
          ) : tasks.length === 0 && processed.length === 0 ? (
            <div className="empty-state">
              <span className="empty-icon">✅</span>
              <p>目前沒有待處理的預約</p>
            </div>
          ) : (
            <>
              {tasks.length > 0 && (
                <h3 className="list-section-title">待處理（{tasks.length}）</h3>
              )}
              {tasks.map((task) => {
                const request = providerTaskPresentation(task);
                const busy = busyTaskId === task.taskId;
                return (
                  <div key={task.taskId} className="request-card pending">
                    <div className="request-card-header">
                      <span className="request-type">候選派工</span>
                      <span className="request-time">
                        提交：{formatDate(request.createdAt)}
                      </span>
                    </div>
                    <div className="request-card-body">
                      <h4 className="request-service">{request.serviceName}</h4>
                      <div className="request-detail">
                        <span>📄 {request.summary}</span>
                      </div>
                      <div className="request-detail">
                        <span>🔢 案件：{request.serviceRequestId}</span>
                      </div>
                      <div className="request-note">📝 {request.note}</div>
                      <label className="dashboard-field">
                        <span>需要住戶補充</span>
                        <input
                          value={questions[task.taskId] ?? ""}
                          onChange={(event) =>
                            setQuestions((current) => ({
                              ...current,
                              [task.taskId]: event.target.value,
                            }))
                          }
                          placeholder="例如：總水閥是否能關閉？"
                        />
                      </label>
                      {request.serviceType === "product_purchase" ? (
                        <label className="dashboard-field">
                          <span>預計出貨日</span>
                          <input
                            value={shipDates[task.taskId] ?? ""}
                            onChange={(event) =>
                              setShipDates((current) => ({
                                ...current,
                                [task.taskId]: event.target.value,
                              }))
                            }
                            placeholder={defaultShipDate()}
                          />
                        </label>
                      ) : (
                        <label className="dashboard-field">
                          <span>可到場時段</span>
                          <input
                            value={arrivalWindows[task.taskId] ?? ""}
                            onChange={(event) =>
                              setArrivalWindows((current) => ({
                                ...current,
                                [task.taskId]: event.target.value,
                              }))
                            }
                            placeholder="2026-08-03 14:00-17:00"
                          />
                        </label>
                      )}
                    </div>
                    <div className="request-actions four-actions">
                      <button
                        className="action-btn timeout"
                        disabled={busy}
                        onClick={() => void simulateTimeout(task)}
                      >
                        模擬逾時
                      </button>
                      <button
                        className="action-btn question"
                        disabled={busy}
                        onClick={() => void respond(task, "needs_information")}
                      >
                        補問
                      </button>
                      <button
                        className="action-btn reject"
                        disabled={busy}
                        onClick={() => void respond(task, "decline")}
                      >
                        拒絕
                      </button>
                      <button
                        className="action-btn accept"
                        disabled={busy}
                        onClick={() => void respond(task, "accept")}
                      >
                        接受
                      </button>
                    </div>
                  </div>
                );
              })}

              {processed.length > 0 && (
                <>
                  <h3 className="list-section-title">
                    本次已處理（{processed.length}）
                  </h3>
                  {processed.map(({ task, action }) => (
                    <div
                      key={task.taskId}
                      className={`request-card ${action === "accepted" ? "accepted" : "rejected"}`}
                    >
                      <div className="request-card-header">
                        <span className="request-type">水電修繕</span>
                        <span
                          className={`request-badge ${action === "accepted" ? "badge-accepted" : "badge-rejected"}`}
                        >
                          {action === "accepted"
                            ? "已接受"
                            : action === "declined"
                              ? "已拒絕"
                              : action === "expired"
                                ? "已改派"
                                : "待住戶補充"}
                        </span>
                      </div>
                      <div className="request-card-body">
                        <h4 className="request-service">
                          {task.brief?.summary ?? "水電修繕需求"}
                        </h4>
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
