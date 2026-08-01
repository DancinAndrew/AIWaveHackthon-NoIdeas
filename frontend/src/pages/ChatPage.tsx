import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { apiClient } from "../api/client";
import type {
  ApiMessage,
  ServiceRequestArtifact,
  WorkflowProgress,
} from "../api/types";
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
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const seenServerMessageIds = useRef(new Set<string>());

  const initializeConversation = async () => {
    setIsConnecting(true);
    setConnectionError(null);
    const requestedConversation =
      searchParams.get("conversation") ??
      window.localStorage.getItem("aiwave-conversation-id");
    try {
      if (requestedConversation) {
        const history = await apiClient.listMessages(requestedConversation);
        history.items.forEach((message) =>
          seenServerMessageIds.current.add(message.messageId),
        );
        setMessages(history.items.map(toMessage));
        setConversationId(requestedConversation);
        const requests = await apiClient.listServiceRequests();
        const activeRequest = requests.items.find(
          (item) => item.conversationId === requestedConversation,
        );
        if (activeRequest) {
          setServiceRequestId(activeRequest.serviceRequestId);
          setProgress(activeRequest.progress);
        }
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
      if (turn.serviceRequest) {
        setServiceRequestId(turn.serviceRequest.serviceRequestId);
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
                  <span className="agent-label">
                    {message.agent === "utility_repair_agent"
                      ? "水電 Agent"
                      : "智慧助理"}
                  </span>
                )}
                <p>{message.content}</p>
                {message.artifact && (
                  <div className="artifact-preview">
                    <div className="artifact-title">
                      📄 水電需求文件 v{message.artifact.version}
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
