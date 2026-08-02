import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { createApiClient } from "../api/client";
import type { ProviderActiveCase, ProviderTask } from "../api/types";
import { providerTaskPresentation } from "../api/viewModels";
import "./DashboardPage.css";


const DEMO_PROVIDERS = [
  {
    providerId: "31324fe0-9899-5382-8211-d0122c20bda0",
    name: "京鑫水電工程行",
  },
  {
    providerId: "29722c58-1d40-5dd9-9bf3-4cfcdfefb60a",
    name: "新旺水電工程行",
  },
] as const;

/** 把第一個真正的失敗原因講出來，而不是一律推給連線問題。 */
function describeFailure(...results: PromiseSettledResult<unknown>[]): string {
  const rejected = results.find((result) => result.status === "rejected");
  if (rejected?.status !== "rejected") return "未知錯誤";
  const reason = rejected.reason;
  return reason instanceof Error ? reason.message : String(reason);
}

interface ProcessedTask {
  task: ProviderTask;
  action: "accepted" | "declined" | "needs_information" | "expired";
  estimatedPoints?: number;
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const [providerId, setProviderId] = useState<string>(
    DEMO_PROVIDERS[0].providerId,
  );
  const api = useMemo(() => createApiClient({ providerId }), [providerId]);
  const [tasks, setTasks] = useState<ProviderTask[]>([]);
  const [activeCases, setActiveCases] = useState<ProviderActiveCase[]>([]);
  const [finalAmounts, setFinalAmounts] = useState<Record<string, string>>({});
  const [completionNotes, setCompletionNotes] = useState<Record<string, string>>(
    {},
  );
  const [busyCaseId, setBusyCaseId] = useState<string | null>(null);
  const [processed, setProcessed] = useState<ProcessedTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);
  const [questions, setQuestions] = useState<Record<string, string>>({});
  const [arrivalWindows, setArrivalWindows] = useState<Record<string, string>>(
    {},
  );
  const [estimatedAmounts, setEstimatedAmounts] = useState<
    Record<string, string>
  >({});

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      // 兩個查詢分別處理，否則單一端點失敗會被誤報成「連不上後端」。
      const [queue, active] = await Promise.allSettled([
        api.listProviderTasks(),
        api.listProviderActiveCases(),
      ]);
      try {
        if (cancelled) return;
        if (queue.status === "fulfilled") setTasks(queue.value.items);
        if (active.status === "fulfilled") setActiveCases(active.value.items);
        const failures = [
          queue.status === "rejected" ? "待處理派工" : null,
          active.status === "rejected" ? "進行中案件" : null,
        ].filter(Boolean);
        setError(
          failures.length === 0
            ? null
            : `無法取得${failures.join("與")}：${describeFailure(queue, active)}`,
        );
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

  const respond = async (
    task: ProviderTask,
    action: "accept" | "decline" | "needs_information",
  ) => {
    const question = questions[task.taskId]?.trim();
    const arrivalWindow =
      arrivalWindows[task.taskId]?.trim() || "2026-08-03 14:00-17:00";
    if (action === "needs_information" && !question) {
      setError("請先輸入要詢問住戶的問題。 ");
      return;
    }
    const rawAmount = estimatedAmounts[task.taskId]?.trim();
    let estimatedAmount: number | undefined;
    if (action === "accept" && rawAmount) {
      const parsed = Number(rawAmount);
      if (!Number.isInteger(parsed) || parsed < 1 || parsed > 1_000_000) {
        setError("預估金額請填 1 到 1,000,000 之間的整數（新台幣元）。 ");
        return;
      }
      estimatedAmount = parsed;
    }
    setBusyTaskId(task.taskId);
    setError(null);
    try {
      const result = await api.respondToProviderTask(task.taskId, {
        action,
        expectedVersion: task.version,
        message:
          action === "needs_information"
            ? question
            : action === "decline"
              ? "目前滿單，請平台改派。"
              : "到場先檢測問題與報價，住戶確認後才施工。",
        arrivalWindow: action === "accept" ? arrivalWindow : undefined,
        estimatedAmount,
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
          estimatedPoints: result.pointsReward?.estimatedPoints,
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

  const reportCompletion = async (activeCase: ProviderActiveCase) => {
    const rawAmount = finalAmounts[activeCase.serviceRequestId]?.trim();
    let finalAmount: number | undefined;
    if (rawAmount) {
      const parsed = Number(rawAmount);
      if (!Number.isInteger(parsed) || parsed < 1 || parsed > 1_000_000) {
        setError("完工金額請填 1 到 1,000,000 之間的整數（新台幣元）。 ");
        return;
      }
      finalAmount = parsed;
    }
    setBusyCaseId(activeCase.serviceRequestId);
    setError(null);
    try {
      await api.reportCompletion(activeCase.serviceRequestId, {
        message:
          completionNotes[activeCase.serviceRequestId]?.trim() ||
          "施工已完成，現場已清理並測試無異常。",
        finalAmount,
      });
      const active = await api.listProviderActiveCases();
      setActiveCases(active.items);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "操作失敗，請稍後再試。",
      );
    } finally {
      setBusyCaseId(null);
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
          {DEMO_PROVIDERS.map((provider) => (
            <button
              key={provider.providerId}
              className={providerId === provider.providerId ? "active" : ""}
              onClick={() => setProviderId(provider.providerId)}
            >
              {provider.name.replace("水電工程行", "")}
            </button>
          ))}
        </div>

        {error && <div className="dashboard-error">{error}</div>}

        <div className="dashboard-list">
          {loading ? (
            <div className="loading-state">載入中...</div>
          ) : tasks.length === 0 &&
            activeCases.length === 0 &&
            processed.length === 0 ? (
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
                      <label className="dashboard-field">
                        <span>預估金額（選填，計算回饋點數）</span>
                        <input
                          type="number"
                          min={1}
                          max={1000000}
                          step={1}
                          inputMode="numeric"
                          value={estimatedAmounts[task.taskId] ?? ""}
                          onChange={(event) =>
                            setEstimatedAmounts((current) => ({
                              ...current,
                              [task.taskId]: event.target.value,
                            }))
                          }
                          placeholder="2800；未填則以類別估算"
                        />
                      </label>
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

              {activeCases.length > 0 && (
                <>
                  <h3 className="list-section-title">
                    進行中（{activeCases.length}）
                  </h3>
                  {activeCases.map((activeCase) => {
                    const busy = busyCaseId === activeCase.serviceRequestId;
                    return (
                      <div
                        key={activeCase.serviceRequestId}
                        className="request-card accepted"
                      >
                        <div className="request-card-header">
                          <span className="request-type">已承接</span>
                          <span className="request-time">
                            {activeCase.displayLabel}
                          </span>
                        </div>
                        <div className="request-card-body">
                          <h4 className="request-service">
                            {activeCase.summary}
                          </h4>
                          <div className="request-detail">
                            <span>
                              🕒 到場時段：{activeCase.arrivalWindow ?? "未填"}
                            </span>
                          </div>
                          {activeCase.estimatedAmount !== null && (
                            <div className="request-detail">
                              <span>
                                💰 承接時預估：NT$
                                {activeCase.estimatedAmount.toLocaleString(
                                  "zh-TW",
                                )}
                              </span>
                            </div>
                          )}
                          {activeCase.canReportCompletion ? (
                            <>
                              <label className="dashboard-field">
                                <span>完工說明</span>
                                <input
                                  value={
                                    completionNotes[
                                      activeCase.serviceRequestId
                                    ] ?? ""
                                  }
                                  onChange={(event) =>
                                    setCompletionNotes((current) => ({
                                      ...current,
                                      [activeCase.serviceRequestId]:
                                        event.target.value,
                                    }))
                                  }
                                  placeholder="例如：已更換水管接頭並測試無滲漏"
                                />
                              </label>
                              <label className="dashboard-field">
                                <span>完工金額（選填，重算回饋點數）</span>
                                <input
                                  type="number"
                                  min={1}
                                  max={1000000}
                                  step={1}
                                  inputMode="numeric"
                                  value={
                                    finalAmounts[activeCase.serviceRequestId] ??
                                    ""
                                  }
                                  onChange={(event) =>
                                    setFinalAmounts((current) => ({
                                      ...current,
                                      [activeCase.serviceRequestId]:
                                        event.target.value,
                                    }))
                                  }
                                  placeholder="未填則沿用承接時的計算基礎"
                                />
                              </label>
                            </>
                          ) : (
                            <div className="request-note">
                              ⏳ 已回報完工，等待住戶在對話中回覆「驗收」後才會發放點數
                            </div>
                          )}
                        </div>
                        {activeCase.canReportCompletion && (
                          <div className="request-actions">
                            <button
                              className="action-btn accept"
                              disabled={busy}
                              onClick={() => void reportCompletion(activeCase)}
                            >
                              回報完工
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </>
              )}

              {processed.length > 0 && (
                <>
                  <h3 className="list-section-title">
                    本次已處理（{processed.length}）
                  </h3>
                  {processed.map(({ task, action, estimatedPoints }) => (
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
                        {estimatedPoints !== undefined && (
                          <div className="request-detail">
                            <span>
                              🎁 已告知住戶預計回饋 {estimatedPoints} 點
                              OPENPOINT（待發放）
                            </span>
                          </div>
                        )}
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
