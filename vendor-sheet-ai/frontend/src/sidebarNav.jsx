import {
  AlignLeft01,
  Archive01,
  Clock01,
  FileText01,
  Image01,
  Languages01,
  MessageCircle01,
  RefreshCw05,
  SquarePen01,
} from "./piagam/template/TemplateIcons.jsx";
import ConversationNavLabel from "./components/ConversationNavLabel.jsx";

function conversationToNavItem(conv, { onUpdateConversation, onDeleteConversation }) {
  return {
    id: `conv-${conv.id}`,
    label: (
      <ConversationNavLabel
        conv={conv}
        onUpdateConversation={onUpdateConversation}
        onDeleteConversation={onDeleteConversation}
      />
    ),
    icon: MessageCircle01,
    href: `/chat/${conv.id}`,
    action: "select-conversation",
    conversationId: conv.id,
  };
}

export function buildPrimaryNavItems({
  conversations,
  archivedConversations,
  onUpdateConversation,
  onDeleteConversation,
}) {
  const handlers = { onUpdateConversation, onDeleteConversation };
  const pinned = conversations.filter((conv) => conv.pinned);
  const regular = conversations.filter((conv) => !conv.pinned);
  const historyChildren = [...pinned, ...regular].map((conv) => conversationToNavItem(conv, handlers));
  const archivedChildren = (archivedConversations ?? []).map((conv) => conversationToNavItem(conv, handlers));

  return [
    { id: "new-chat", label: "New Chat", icon: SquarePen01, action: "new-chat" },
    {
      id: "automation",
      label: "Automation",
      icon: RefreshCw05,
      href: "/automation",
      action: "automation",
    },
    {
      id: "instruction-manual",
      label: "Instruction Manual",
      icon: FileText01,
      href: "/instruction-manual",
      action: "instruction-manual",
    },
    { id: "image", label: "Revisi Gambar", icon: Image01, href: "/gallery", action: "gallery" },
    { id: "translate", label: "Translate", icon: Languages01, href: "/translate", action: "translate" },
    { id: "description", label: "Description", icon: AlignLeft01, href: "/description", action: "description" },
    {
      id: "history",
      label: "History",
      icon: Clock01,
      children: historyChildren.length
        ? historyChildren
        : [{ id: "history-empty", label: "No chats yet", icon: MessageCircle01 }],
    },
    {
      id: "archived",
      label: "Archived",
      icon: Archive01,
      children: archivedChildren.length
        ? archivedChildren
        : [{ id: "archived-empty", label: "No archived chats", icon: MessageCircle01 }],
    },
  ];
}
