import { createPortal } from "react-dom";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  MoreVertRounded as MoreVertRoundedIcon,
  PushPinRounded as PushPinRoundedIcon,
  PushPinOutlined as PushPinOutlinedIcon,
  EditRounded as EditRoundedIcon,
  DeleteRounded as DeleteRoundedIcon,
} from "@mui/icons-material";

function stop(event) {
  event.preventDefault();
  event.stopPropagation();
}

const TITLE_STOPWORDS = new Set([
  "aku",
  "ambil",
  "apa",
  "apakah",
  "arah",
  "bantu",
  "bisa",
  "buat",
  "buatkan",
  "coba",
  "dari",
  "di",
  "dong",
  "ga",
  "gak",
  "ini",
  "itu",
  "jadi",
  "jalan",
  "kak",
  "kalau",
  "ke",
  "lagi",
  "mau",
  "pakai",
  "please",
  "saya",
  "si",
  "the",
  "this",
  "tolong",
  "untuk",
  "yang",
]);

function smartCapitalize(text) {
  const trimmed = text.trim();
  if (!trimmed) return "New chat";
  if (/[A-Z]{2,}|\d/.test(trimmed)) return trimmed;
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
}

function compactConversationTitle(title) {
  const raw = String(title || "").trim();
  if (!raw || raw.toLowerCase() === "new chat") return "New chat";

  const withoutUrls = raw.replace(/https?:\/\/\S+/gi, " ");
  const quoted = withoutUrls.match(/["“”']([^"“”']{3,})["“”']/);
  const source = quoted?.[1] || withoutUrls;
  const normalized = source
    .replace(/\.(xlsx?|csv|pdf|docx?|png|jpe?g|webp)\b/gi, "")
    .replace(/[^\p{L}\p{N}\s-]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();

  const words = normalized
    .split(" ")
    .map((word) => word.trim())
    .filter(Boolean);

  const coreWords = words.filter((word) => {
    const lower = word.toLowerCase();
    return lower.length > 2 && !TITLE_STOPWORDS.has(lower);
  });

  const selected = (coreWords.length >= 2 ? coreWords : words).slice(0, 4).join(" ");
  return smartCapitalize(selected || raw).slice(0, 48);
}

export default function ConversationNavLabel({ conv, onUpdateConversation, onDeleteConversation }) {
  const [isRenaming, setIsRenaming] = useState(false);
  const [draftTitle, setDraftTitle] = useState(conv.title);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState(null);
  const [titleOverflow, setTitleOverflow] = useState(false);
  const [titleScrollDistance, setTitleScrollDistance] = useState(0);
  const rowRef = useRef(null);
  const titleRef = useRef(null);
  const titleTrackRef = useRef(null);
  const triggerRef = useRef(null);
  const menuRef = useRef(null);
  const displayTitle = compactConversationTitle(conv.title);

  useEffect(() => {
    if (!isMenuOpen) return undefined;

    const handlePointerDown = (event) => {
      if (triggerRef.current?.contains(event.target)) return;
      if (menuRef.current?.contains(event.target)) return;
      setIsMenuOpen(false);
    };
    const handleKeyDown = (event) => {
      if (event.key === "Escape") setIsMenuOpen(false);
    };

    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isMenuOpen]);

  useLayoutEffect(() => {
    if (!isMenuOpen) return undefined;

    const updatePosition = () => {
      const trigger = triggerRef.current;
      if (!trigger) return;

      const bounds = trigger.getBoundingClientRect();
      const menuWidth = 190;
      const viewportWidth = window.innerWidth;
      const left = Math.min(bounds.right - menuWidth, Math.max(8, viewportWidth - menuWidth - 8));

      setMenuStyle({
        top: bounds.bottom + 6,
        left: Math.max(8, left),
        minWidth: menuWidth,
      });
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [isMenuOpen]);

  useLayoutEffect(() => {
    const titleNode = titleRef.current;
    const trackNode = titleTrackRef.current;
    if (!titleNode || !trackNode) return undefined;

    const updateOverflow = () => {
      const overflowDistance = Math.max(0, trackNode.scrollWidth - titleNode.clientWidth);
      const shouldMove = overflowDistance > 4 || displayTitle.length > 12;
      setTitleOverflow(shouldMove);
      setTitleScrollDistance(overflowDistance > 4 ? overflowDistance + 12 : 14);
    };

    updateOverflow();
    const observer = new ResizeObserver(updateOverflow);
    observer.observe(titleNode);
    observer.observe(trackNode);
    window.addEventListener("resize", updateOverflow);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", updateOverflow);
    };
  }, [displayTitle, conv.pinned]);

  const finishRename = () => {
    const title = draftTitle.trim();
    if (title) {
      onUpdateConversation(conv.id, { title });
    }
    setIsRenaming(false);
  };

  if (isRenaming) {
    return (
      <input
        className="nav-chat-rename-input"
        value={draftTitle}
        onChange={(e) => setDraftTitle(e.target.value)}
        onClick={stop}
        onMouseDown={stop}
        onBlur={finishRename}
        onKeyDown={(e) => {
          if (e.key === "Enter") finishRename();
          if (e.key === "Escape") setIsRenaming(false);
        }}
        autoFocus
      />
    );
  }

  const menuPortal =
    isMenuOpen && menuStyle
      ? createPortal(
          <div className="nav-chat-menu" role="menu" ref={menuRef} style={menuStyle}>
            <button
              type="button"
              className="nav-chat-menu__item"
              role="menuitem"
              onMouseDown={stop}
              onClick={(e) => {
                stop(e);
                setIsMenuOpen(false);
                setDraftTitle(conv.title);
                setIsRenaming(true);
              }}
            >
              <EditRoundedIcon fontSize="small" />
              <span>Rename</span>
            </button>

            <button
              type="button"
              className="nav-chat-menu__item nav-chat-menu__item--danger"
              role="menuitem"
              onMouseDown={stop}
              onClick={(e) => {
                stop(e);
                setIsMenuOpen(false);
                onDeleteConversation(conv.id);
              }}
            >
              <DeleteRoundedIcon fontSize="small" />
              <span>Delete</span>
            </button>
          </div>,
          document.body,
        )
      : null;

  return (
    <span className="nav-chat-row" ref={rowRef} title={conv.title}>
      <span
        className={"nav-chat-title" + (titleOverflow ? " nav-chat-title--overflow" : "")}
        ref={titleRef}
        style={{ "--nav-chat-scroll-distance": `${titleScrollDistance}px` }}
      >
        {conv.pinned ? <span className="nav-chat-pin-dot" aria-hidden="true" /> : null}
        <span className="nav-chat-title-track" ref={titleTrackRef}>{displayTitle}</span>
      </span>
      <span className={"nav-chat-actions" + (isMenuOpen ? " nav-chat-actions--open" : "")}>
        <button
          type="button"
          className={"nav-chat-pin-btn" + (conv.pinned ? " nav-chat-pin-btn--pinned" : "")}
          title={conv.pinned ? "Unpin chat" : "Pin chat"}
          aria-label={conv.pinned ? "Unpin chat" : "Pin chat"}
          aria-pressed={conv.pinned}
          onMouseDown={stop}
          onClick={(e) => {
            stop(e);
            onUpdateConversation(conv.id, { pinned: !conv.pinned });
          }}
        >
          {conv.pinned ? <PushPinRoundedIcon fontSize="small" /> : <PushPinOutlinedIcon fontSize="small" />}
        </button>

        <button
          ref={triggerRef}
          type="button"
          className={"nav-chat-menu-trigger" + (isMenuOpen ? " nav-chat-menu-trigger--active" : "")}
          title="More options"
          aria-label="More options"
          aria-haspopup="menu"
          aria-expanded={isMenuOpen}
          onMouseDown={stop}
          onClick={(e) => {
            stop(e);
            setIsMenuOpen((open) => !open);
          }}
        >
          <MoreVertRoundedIcon fontSize="small" />
        </button>
      </span>

      {menuPortal}
    </span>
  );
}
