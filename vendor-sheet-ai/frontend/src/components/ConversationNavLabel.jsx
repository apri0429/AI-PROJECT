import { createPortal } from "react-dom";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  MoreVertRounded as MoreVertRoundedIcon,
  PushPinRounded as PushPinRoundedIcon,
  PushPinOutlined as PushPinOutlinedIcon,
  EditRounded as EditRoundedIcon,
  Inventory2Rounded as Inventory2RoundedIcon,
  UnarchiveRounded as UnarchiveRoundedIcon,
  DeleteRounded as DeleteRoundedIcon,
} from "@mui/icons-material";

function stop(event) {
  event.preventDefault();
  event.stopPropagation();
}

export default function ConversationNavLabel({ conv, onUpdateConversation, onDeleteConversation }) {
  const [isRenaming, setIsRenaming] = useState(false);
  const [draftTitle, setDraftTitle] = useState(conv.title);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState(null);
  const rowRef = useRef(null);
  const triggerRef = useRef(null);
  const menuRef = useRef(null);

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
              className="nav-chat-menu__item"
              role="menuitem"
              onMouseDown={stop}
              onClick={(e) => {
                stop(e);
                setIsMenuOpen(false);
                onUpdateConversation(conv.id, { archived: !conv.archived });
              }}
            >
              {conv.archived ? (
                <UnarchiveRoundedIcon fontSize="small" />
              ) : (
                <Inventory2RoundedIcon fontSize="small" />
              )}
              <span>{conv.archived ? "Restore chat" : "Archive"}</span>
            </button>

            <div className="nav-chat-menu__divider" role="separator" />

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
    <span className="nav-chat-row" ref={rowRef}>
      <span className="nav-chat-title">
        {conv.pinned ? <span className="nav-chat-pin-dot" aria-hidden="true" /> : null}
        {conv.title}
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
