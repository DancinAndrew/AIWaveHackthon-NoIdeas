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

const CONVERSATION_STORAGE_KEY = "aiwave-conversation-id";

/**
 * 舊的 conversation id 不代表後端掛掉。Demo 的 store 在記憶體，後端一重啟舊
 * 對話就不存在；把它誤判成連線失敗會讓輸入框永久停用而且無法自救。
 */
function isStaleConversation(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 404 || error.status === 403);
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
  const [searchParams, setSearchParams] = useSearchParams();
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

  const initializeConversation = async ({ forceNew = false } = {}) => {
    setIsConnecting(true);
    setConnectionError(null);
    const requestedConversation = forceNew
      ? null
      : searchParams.get("conversation") ??
        window.localStorage.getItem(CONVERSATION_STORAGE_KEY);
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
        CONVERSATION_STORAGE_KEY,
        created.conversationId,
      );
    } catch {
      setMessages([WELCOME_MESSAGE]);
      setConnectionError("目前無法連上智慧助理服務，請稍後再點「重新連線」。");
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
      window.localStorage.setItem(CONVERSATION_STORAGE_KEY, conversation);
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
      if (!isStaleConversation(error)) throw error;
      // 後端已不認得這個對話：丟掉它並開新對話，而不是把使用者鎖在一個永遠救不
      // 回來的錯誤狀態裡。殘留的案件與點數投影會誤導新對話，一併清掉。
      window.localStorage.removeItem(CONVERSATION_STORAGE_KEY);
      seenServerMessageIds.current.clear();
      setServiceRequestId(null);
      setProgress(null);
      setServiceRequest(null);
      setSelectionError(null);
      return false;
    }
  };

  // Past conversations stay reachable from 我的預約, so starting a new one only
  // needs to drop the local pointers to the previous conversation.
  const startNewConversation = async () => {
    if (isConnecting) return;
    seenServerMessageIds.current.clear();
    setMessages([]);
    setInput("");
    setConversationId(null);
    setServiceRequestId(null);
    setProgress(null);
    // serviceRequest 帶著 pointsReward 與商品候選，progress 帶著 pointsReward，
    // 兩個都要清掉，否則新對話會殘留上一輪的點數與候選卡片。
    setServiceRequest(null);
    setSelectionError(null);
    window.localStorage.removeItem(CONVERSATION_STORAGE_KEY);
    if (searchParams.has("conversation")) {
      const nextParams = new URLSearchParams(searchParams);
      nextParams.delete("conversation");
      setSearchParams(nextParams, { replace: true });
    }
    await initializeConversation({ forceNew: true });
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
      } catch (error) {
        if (isStaleConversation(error) && !cancelled) {
          // 後端在頁面開著時重啟。靜默重試會永遠失敗，直接換一個新對話。
          cancelled = true;
          window.localStorage.removeItem(CONVERSATION_STORAGE_KEY);
          setConversationId(null);
          void initializeConversation();
          return;
        }
        // 其他錯誤：輪詢是唯讀且允許失敗，下一輪再試。
      }
    };
    const timer = window.setInterval(() => void poll(), 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
    // initializeConversation 只在對話失效時作為一次性復原路徑呼叫，
    // 放進 deps 會讓每次 render 重建輪詢計時器。
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
          <button
            type="button"
            className="new-chat-btn"
            onClick={() => void startNewConversation()}
            disabled={isConnecting || isLoading}
            aria-label="開啟新對話"
            title="開啟新對話"
          >
            ＋
          </button>
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
