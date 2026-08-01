import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import "./ChatPage.css";

interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

const API_BASE_URL = "http://localhost:8000";

export default function ChatPage() {
  const navigate = useNavigate();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      role: "assistant",
      content: "您好！我是 OPEN POINT 智慧助理，有什麼可以幫您的嗎？\n\n您可以問我：\n• 預約清潔服務\n• 查詢訂單狀態\n• 水電修繕諮詢\n• 其他居家服務",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 自動滾動到最新訊息
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now(),
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      // TODO: 之後接真正的 AI 後端
      const res = await fetch(`${API_BASE_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMessage.content }),
      });

      if (!res.ok) throw new Error("API Error");

      const data = await res.json();

      const assistantMessage: Message = {
        id: Date.now() + 1,
        role: "assistant",
        content: data.reply || "抱歉，我暫時無法回應，請稍後再試。",
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch {
      // 暫時用假回覆
      const fallbackMessage: Message = {
        id: Date.now() + 1,
        role: "assistant",
        content: "收到您的訊息！目前 AI 功能開發中，之後會為您提供更完整的服務。",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, fallbackMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="phone-frame">
      <div className="chat-page">
        {/* 頂部導航列 */}
        <div className="chat-header">
          <button className="back-btn" onClick={() => navigate("/")}>
            ← 返回
          </button>
          <span className="chat-title">智慧助理</span>
          <div className="header-spacer" />
        </div>

        {/* 訊息區域 */}
        <div className="messages-container">
          {messages.map((msg) => (
            <div key={msg.id} className={`message ${msg.role}`}>
              {msg.role === "assistant" && (
                <div className="avatar assistant-avatar">🤖</div>
              )}
              <div className={`bubble ${msg.role}`}>
                <p>{msg.content}</p>
                <span className="time">
                  {msg.timestamp.toLocaleTimeString("zh-TW", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>
              {msg.role === "user" && (
                <div className="avatar user-avatar">👤</div>
              )}
            </div>
          ))}

          {isLoading && (
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

        {/* 輸入區域 */}
        <div className="input-area">
          <input
            type="text"
            className="chat-input"
            placeholder="輸入訊息..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
          />
          <button
            className="send-btn"
            onClick={sendMessage}
            disabled={!input.trim() || isLoading}
          >
            傳送
          </button>
        </div>
      </div>
    </div>
  );
}
