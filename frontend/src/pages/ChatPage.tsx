import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ApiError, apiClient } from "../api/client";
import type {
  ApiMessage,
  ProductCandidate,
  ServiceRequestArtifact,
  ServiceRequestProjection,
  WorkflowProgress,
} from "../api/types";
import { formatTwd, orderStatusLabel } from "../api/viewModels";
import "./ChatPage.css";


interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  agent?: string | null;
  artifact?: ServiceRequestArtifact;
}

const WELCOME_MESSAGE: Message = {
  id: "local-welcome",
  role: "assistant",
  content:
    "您好！我是 OPEN POINT 智慧助理，有什麼可以幫您的嗎？\n\n您可以問我：\n• 預約清潔服務\n• 查詢訂單狀態\n• 水電修繕諮詢\n• 其他居家服務",
  timestamp: new Date(),
  agent: "supervisor",
};

const AGENT_LABELS: Record<string, string> = {
  utility_repair_agent: "水電 Agent",
  product_agent: "商品 Agent",
  supervisor: "智慧助理",
};

function agentLabel(agent: string): string {
  return AGENT_LABELS[agent] ?? "智慧助理";
}

function toMessage(message: ApiMessage): Message {
  return {
    id: message.messageId,
    role: message.role,
    content: message.content,
    timestamp: new Date(message.createdAt),
    agent: message.agent,
  };
}

export default function ChatPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [messages, setMessages] = useState<Message[]>([WELCOME_MESSAGE]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isConnecting, setIsConnecting] = useState(true);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [serviceRequestId, setServiceRequestId] = useState<string | null>(null);
  const [progress, setProgress] = useState<WorkflowProgress | null>(null);
  const [serviceRequest, setServiceRequest] =
    useState<ServiceRequestProjection | null>(null);
  const [selectingSku, setSelectingSku] = useState<string | null>(null);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const seenServerMessageIds = useRef(new Set<string>());

  const initializeConversation = async () => {
    setIsConnecting(true);
    setConnectionError(null);
    const requestedConversation =
      searchParams.get("conversation") ??
      window.localStorage.getItem("aiwave-conversation-id");
    try {
      // Resuming is best-effort. A stored conversation disappears whenever the
      // backend restarts in in-memory mode, and that is not a connection
      // problem, so it must not surface as one.
      if (requestedConversation && (await tryResume(requestedConversation))) {
        return;
      }
      const created = await apiClient.createConversation();
      seenServerMessageIds.current.add(created.assistantMessage.messageId);
      setMessages([toMessage(created.assistantMessage)]);
      setConversationId(created.conversationId);
      window.localStorage.setItem(
        "aiwave-conversation-id",
        created.conversationId,
      );
    } catch {
      setMessages([WELCOME_MESSAGE]);
      setConnectionError("目前無法連上服務，請確認 Flask 後端已啟動。 ");
    } finally {
      setIsConnecting(false);
    }
  };

  /** Returns false when the conversation is gone and a new one should start. */
  const tryResume = async (conversation: string): Promise<boolean> => {
    try {
      const history = await apiClient.listMessages(conversation);
      history.items.forEach((message) =>
        seenServerMessageIds.current.add(message.messageId),
      );
      setMessages(history.items.map(toMessage));
      setConversationId(conversation);
      const requests = await apiClient.listServiceRequests();
      const activeRequest = requests.items.find(
        (item) => item.conversationId === conversation,
      );
      if (activeRequest) {
        setServiceRequestId(activeRequest.serviceRequestId);
        setProgress(activeRequest.progress);
        setServiceRequest(activeRequest);
      }
      return true;
    } catch (error) {
      const status = error instanceof ApiError ? error.status : 0;
      if (status === 404 || status === 403) {
        window.localStorage.removeItem("aiwave-conversation-id");
        return false;
      }
      throw error;
    }
  };

  useEffect(() => {
    void initializeConversation();
    // Query string only selects the initial conversation for this mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (!conversationId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const history = await apiClient.listMessages(conversationId);
        const unseen = history.items.filter(
          (message) =>
            message.role === "assistant" &&
            !seenServerMessageIds.current.has(message.messageId),
        );
        unseen.forEach((message) =>
          seenServerMessageIds.current.add(message.messageId),
        );
        if (!cancelled && unseen.length > 0) {
          setMessages((current) => [...current, ...unseen.map(toMessage)]);
        }
        if (serviceRequestId) {
          const latestProgress = await apiClient.getProgress(serviceRequestId);
          if (!cancelled) setProgress(latestProgress);
          // The candidate list and order status live on the projection, so it
          // has to be refreshed too for the cards to stay in sync.
          const requests = await apiClient.listServiceRequests();
          const latest = requests.items.find(
            (item) => item.serviceRequestId === serviceRequestId,
          );
          if (!cancelled && latest) setServiceRequest(latest);
        }
      } catch {
        // Polling is read-only and best-effort; the next cycle retries.
      }
    };
    const timer = window.setInterval(() => void poll(), 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [conversationId, serviceRequestId]);

  const sendMessage = async () => {
    if (!input.trim() || isLoading || !conversationId) return;

    const content = input.trim();
    const userMessage: Message = {
      id: `local-${Date.now()}`,
      role: "user",
      content,
      timestamp: new Date(),
    };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const turn = await apiClient.sendMessage(conversationId, content);
      seenServerMessageIds.current.add(turn.assistantMessage.messageId);
      const assistantMessage = {
        ...toMessage(turn.assistantMessage),
        artifact: turn.artifact,
      };
      setMessages((current) => [...current, assistantMessage]);
      setSelectionError(null);
      if (turn.serviceRequest) {
        setServiceRequestId(turn.serviceRequest.serviceRequestId);
        setServiceRequest(turn.serviceRequest);
      }
      if (turn.progress) setProgress(turn.progress);
    } catch {
      setMessages((current) => [
        ...current,
        {
          id: `error-${Date.now()}`,
          role: "assistant",
          content: "訊息暫時送不出去，請確認後端連線後再試一次。",
          timestamp: new Date(),
          agent: "supervisor",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage();
    }
  };

  /**
   * Sends only the SKU and the candidate list version. Amounts shown on the
   * card come from the backend and are never echoed back, so the server stays
   * the only source of pricing.
   */
  const selectCandidate = async (candidate: ProductCandidate) => {
    if (!serviceRequestId || !serviceRequest || selectingSku) return;
    setSelectingSku(candidate.sku);
    setSelectionError(null);
    try {
      const result = await apiClient.selectProduct(
        serviceRequestId,
        candidate.sku,
        serviceRequest.candidatesVersion ?? 1,
      );
      seenServerMessageIds.current.add(result.assistantMessage.messageId);
      setMessages((current) => [
        ...current,
        { ...toMessage(result.assistantMessage), artifact: result.artifact },
      ]);
      setProgress(result.progress);
      setServiceRequest(result.serviceRequest);
    } catch (error) {
      const conflict = error instanceof ApiError && error.status === 409;
      setSelectionError(
        conflict
          ? "候選清單已更新，請往下看最新的商品清單再選擇。"
          : error instanceof ApiError
            ? error.message
            : "選擇失敗，請再試一次。",
      );
    } finally {
      setSelectingSku(null);
    }
  };

  const candidates = serviceRequest?.candidates ?? [];
  const showCandidates =
    progress?.stage === "awaiting_resident_selection" && candidates.length > 0;
  const orderLabel = orderStatusLabel(serviceRequest?.orderStatus);

  return (
    <div className="phone-frame">
      <div className="chat-page">
        <div className="chat-header">
          <button className="back-btn" onClick={() => navigate("/")}>
            ← 返回
          </button>
          <span className="chat-title">智慧助理</span>
          <div className="header-spacer" />
        </div>

        {progress && (
          <button
            className={`workflow-banner ${progress.residentActionRequired ? "action-required" : ""}`}
            onClick={() => navigate("/my-bookings")}
          >
            <span className="workflow-dot" />
            <span>{progress.displayLabel}</span>
            {orderLabel && (
              <span className="order-chip">
                {serviceRequest?.orderNo} · {orderLabel}
              </span>
            )}
            <span className="workflow-link">查看進度 ›</span>
          </button>
        )}

        {connectionError && (
          <div className="connection-banner">
            <span>{connectionError}</span>
            <button onClick={() => void initializeConversation()}>重新連線</button>
          </div>
        )}

        <div className="messages-container">
          {messages.map((message) => (
            <div key={message.id} className={`message ${message.role}`}>
              {message.role === "assistant" && (
                <div className="avatar assistant-avatar">🤖</div>
              )}
              <div className={`bubble ${message.role}`}>
                {message.role === "assistant" && message.agent && (
                  <span className="agent-label">{agentLabel(message.agent)}</span>
                )}
                <p>{message.content}</p>
                {message.artifact && (
                  <div className="artifact-preview">
                    <div className="artifact-title">
                      {message.artifact.serviceType === "product_purchase"
                        ? `🧾 訂單摘要 v${message.artifact.version}`
                        : `📄 水電需求文件 v${message.artifact.version}`}
                    </div>
                    <div className="artifact-summary">
                      {message.artifact.summary}
                    </div>
                    <span className={`artifact-status ${message.artifact.status}`}>
                      {message.artifact.status === "confirmed"
                        ? "已確認"
                        : "待確認"}
                    </span>
                  </div>
                )}
                <span className="time">
                  {message.timestamp.toLocaleTimeString("zh-TW", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>
              {message.role === "user" && (
                <div className="avatar user-avatar">👤</div>
              )}
            </div>
          ))}

          {(isLoading || isConnecting) && (
            <div className="message assistant">
              <div className="avatar assistant-avatar">🤖</div>
              <div className="bubble assistant typing">
                <span className="dot" />
                <span className="dot" />
                <span className="dot" />
              </div>
            </div>
          )}

          {showCandidates && (
            <div className="candidate-list">
              {selectionError && (
                <div className="candidate-error">{selectionError}</div>
              )}
              {candidates.map((candidate, index) => (
                <article className="candidate-card" key={candidate.sku}>
                  <header className="candidate-head">
                    <span className="candidate-rank">{index + 1}</span>
                    <div className="candidate-title">
                      <span className="candidate-name">{candidate.name}</span>
                      <span className="candidate-meta">
                        {candidate.brand} · 評分 {candidate.rating} ·{" "}
                        {candidate.supplierName}
                      </span>
                    </div>
                    {candidate.promotionApplied && candidate.promotionLabel && (
                      <span className="candidate-promo">
                        {candidate.promotionLabel}
                      </span>
                    )}
                  </header>

                  <dl className="candidate-specs">
                    {Object.entries(candidate.specs).map(([name, value]) => (
                      <div className="candidate-spec" key={name}>
                        <dt>{name}</dt>
                        <dd>{value}</dd>
                      </div>
                    ))}
                  </dl>

                  {/* Rows are ordered so they visibly add up:
                      定價 − 折扣 = 小計, 小計 + 運費 = 實付. The base row is the
                      catalogue list price, not the already-discounted unit
                      price, or the discount row would look unapplied. */}
                  <div className="candidate-amounts">
                    <div className="candidate-amount-row">
                      <span>
                        定價
                        {candidate.quantity > 1 &&
                          ` ${formatTwd(candidate.listPrice)} × ${candidate.quantity}`}
                      </span>
                      <span>{formatTwd(candidate.originalAmount)}</span>
                    </div>
                    {candidate.discountAmount > 0 && (
                      <>
                        <div className="candidate-amount-row discount">
                          <span>折扣{candidate.promotionLabel && `（${candidate.promotionLabel}）`}</span>
                          <span>-{formatTwd(candidate.discountAmount)}</span>
                        </div>
                        <div className="candidate-amount-row subtotal">
                          <span>小計</span>
                          <span>
                            {formatTwd(
                              candidate.originalAmount - candidate.discountAmount,
                            )}
                          </span>
                        </div>
                      </>
                    )}
                    <div className="candidate-amount-row">
                      <span>
                        運費
                        {candidate.freeShippingSource === "promotion"
                          ? "（本檔促銷免運）"
                          : candidate.freeShippingSource === "threshold"
                            ? "（已達免運門檻）"
                            : `（未達 ${formatTwd(candidate.freeShippingThreshold)}）`}
                      </span>
                      <span>{formatTwd(candidate.shippingFeeAmount)}</span>
                    </div>
                    <div className="candidate-amount-row total">
                      <span>實付</span>
                      <span>{formatTwd(candidate.finalAmount)}</span>
                    </div>
                  </div>

                  <div className="candidate-facts">
                    <span>
                      🚚 {candidate.deliveryLabel} 約 {candidate.estimatedDays}{" "}
                      個工作天
                    </span>
                    <span>📦 可售 {candidate.available}</span>
                    <span>🔁 {candidate.returnPolicyLabel}</span>
                  </div>

                  <ul className="candidate-reasons">
                    {candidate.reasons.slice(0, 3).map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>

                  <button
                    className="candidate-select-btn"
                    onClick={() => void selectCandidate(candidate)}
                    disabled={selectingSku !== null}
                  >
                    {selectingSku === candidate.sku ? "處理中…" : "選這個"}
                  </button>
                </article>
              ))}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        <div className="input-area">
          <input
            type="text"
            className="chat-input"
            placeholder="例如：浴室洗手台下方一直漏水"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading || isConnecting || !conversationId}
          />
          <button
            className="send-btn"
            onClick={() => void sendMessage()}
            disabled={!input.trim() || isLoading || !conversationId}
          >
            傳送
          </button>
        </div>
      </div>
    </div>
  );
}
