import { useEffect, useRef, useState } from "react";
import Message from "./Message";
import Composer from "./Composer";
import Header from "../piagam/template/Header.jsx";
import BackgroundMain from "../piagam/template/BackgroundMain.jsx";

function getTimeGreeting() {
  const hour = new Date().getHours();
  if (hour >= 4 && hour < 11) return "Selamat pagi";
  if (hour >= 11 && hour < 15) return "Selamat siang";
  if (hour >= 15 && hour < 18) return "Selamat sore";
  return "Selamat malam";
}

const EMPTY_STATE_PROMPTS = [
  "Upload CSV atau pakai link Google Sheet untuk mulai membaca data produk.",
  "Tanyakan nama produk, vendor, ukuran, dieline, atau detail lain dari sheet.",
  "Minta ringkasan produk tertentu dari data yang sudah diproses.",
  "Gunakan menu lain untuk membuat description, instruction manual, atau image.",
];

export default function ChatArea({
  activeConversation,
  sidebarOpen,
  onToggleSidebar,
  messages,
  isProcessing,
  error,
  onUpload,
  onSheetUrl,
  onAsk,
  onGenerateImage,
  onEditMessage,
}) {
  const endRef = useRef(null);
  const scrollContainerRef = useRef(null);
  const scrollTimerRef = useRef(null);
  const greeting = getTimeGreeting();
  const [promptIndex, setPromptIndex] = useState(0);
  const [isScrolling, setIsScrolling] = useState(false);

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const NEAR_BOTTOM_THRESHOLD = 120;
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    const isNearBottom = distanceFromBottom <= NEAR_BOTTOM_THRESHOLD;

    if (isNearBottom) {
      endRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isProcessing]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setPromptIndex((current) => (current + 1) % EMPTY_STATE_PROMPTS.length);
    }, 3600);

    return () => window.clearInterval(intervalId);
  }, []);

  useEffect(() => {
    return () => {
      if (scrollTimerRef.current) {
        window.clearTimeout(scrollTimerRef.current);
      }
    };
  }, []);

  const handleChatScroll = () => {
    setIsScrolling(true);
    if (scrollTimerRef.current) {
      window.clearTimeout(scrollTimerRef.current);
    }
    scrollTimerRef.current = window.setTimeout(() => {
      setIsScrolling(false);
    }, 850);
  };

  return (
    <main className="chat-area">
      <BackgroundMain />
      <Header
        title={activeConversation?.title || "Product Piagam AI"}
        showMenuButton
        onMenuToggle={onToggleSidebar}
        showBreadcrumbBar={false}
      />

      <div
        ref={scrollContainerRef}
        className={
          "chat-scroll" +
          (messages.length === 0 && !isProcessing ? " chat-scroll-empty" : "") +
          (isScrolling ? " chat-scroll-scrolling" : "")
        }
        onScroll={handleChatScroll}
      >
        {messages.length === 0 && !isProcessing && (
          <div className="empty-state">
            <div className="empty-state-card">
              <span className="empty-state-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="24" height="24" fill="none">
                  <path
                    d="M5.25 5.75h13.5v9.5a3 3 0 0 1-3 3H9.3L5.25 21v-2.75a3 3 0 0 1-3-3v-6.5a3 3 0 0 1 3-3Z"
                    stroke="currentColor"
                    strokeWidth="1.75"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M7.75 10h8.5M7.75 13.25h5.5"
                    stroke="currentColor"
                    strokeWidth="1.75"
                    strokeLinecap="round"
                  />
                </svg>
              </span>
              <div className="empty-state-kicker">{greeting}</div>
              <div className="empty-state-title">Chat data produk</div>
              <p className="empty-state-subtitle" key={promptIndex}>
                {EMPTY_STATE_PROMPTS[promptIndex]}
              </p>
              <div className="empty-state-prompts" aria-label="Contoh bantuan">
                {EMPTY_STATE_PROMPTS.map((prompt) => (
                  <span key={prompt} className="empty-state-prompt">
                    {prompt}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}

        {messages.map((message, index) => (
          <Message
            key={message.id || index}
            message={message}
            onEditMessage={onEditMessage}
            onAsk={onAsk}
          />
        ))}

        {isProcessing && (
          <div className="message message-assistant">
            <div className="avatar avatar-assistant">AI</div>
            <div className="message-body">
              <div className="typing-indicator">
                <span />
                <span />
                <span />
              </div>
            </div>
          </div>
        )}

        {error && <div className="error-banner">{error}</div>}
        <div ref={endRef} />
      </div>

      <Composer
        onUpload={onUpload}
        onSheetUrl={onSheetUrl}
        onAsk={onAsk}
        onGenerateImage={onGenerateImage}
        isProcessing={isProcessing}
        isEmpty={messages.length === 0}
      />
    </main>
  );
}
