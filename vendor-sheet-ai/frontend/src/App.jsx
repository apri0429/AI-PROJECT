import { useEffect, useMemo, useState } from "react";
import Sidebar from "./piagam/template/Sidebar.jsx";
import ChatArea from "./components/ChatArea";
import { buildPrimaryNavItems } from "./sidebarNav.jsx";
import InstructionManualPage from "./components/InstructionManualPage";
import ImagePage from "./components/ImagePage";
import TranslatePage from "./components/TranslatePage";
import DescriptionPage from "./components/DescriptionPage";
import AutomationPage from "./components/AutomationPage";
import {
  API_BASE,
  askQuestion,
  createConversation,
  deleteConversation,
  editConversationMessage,
  fetchConversationMessages,
  fetchConversations,
  imageChatGenerate,
  processSheetUrl,
  updateConversation,
  uploadSheet,
} from "./api";
import "./App.css";

function toChatAssetUrl(url) {
  if (!url) return "";
  if (/^https?:\/\//i.test(url)) return url;
  return `${API_BASE}${url}`;
}

let imageGenMessageCounter = 0;
function nextImageGenId() {
  imageGenMessageCounter += 1;
  return `image-gen-${Date.now()}-${imageGenMessageCounter}`;
}

const ACTIVE_CONVERSATION_KEY = "vendor-sheet-ai:active-conversation";

export default function App() {
  const [conversations, setConversations] = useState([]);
  const [archivedConversations, setArchivedConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isLoadingConversation, setIsLoadingConversation] = useState(true);
  const [error, setError] = useState(null);
  const [showInstructionManual, setShowInstructionManual] = useState(false);
  const [showGallery, setShowGallery] = useState(false);
  const [showTranslatePdf, setShowTranslatePdf] = useState(false);
  const [showDescription, setShowDescription] = useState(false);
  const [showAutomation, setShowAutomation] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", "light");
  }, []);

  const refreshConversations = () => {
    fetchConversations()
      .then((data) => setConversations(data.conversations || []))
      .catch(() => {});
    fetchConversations({ archived: true })
      .then((data) => setArchivedConversations(data.conversations || []))
      .catch(() => {});
  };

  const openConversation = async (id) => {
    setActiveConversationId(id);
    localStorage.setItem(ACTIVE_CONVERSATION_KEY, String(id));
    try {
      const data = await fetchConversationMessages(id);
      setMessages(data.messages || []);
    } catch {
      setMessages([]);
    }
  };

  useEffect(() => {
    async function init() {
      setIsLoadingConversation(true);
      try {
        const data = await fetchConversations();
        fetchConversations({ archived: true })
          .then((archivedData) => setArchivedConversations(archivedData.conversations || []))
          .catch(() => {});
        const convs = data.conversations || [];
        setConversations(convs);

        const storedId = Number(localStorage.getItem(ACTIVE_CONVERSATION_KEY));
        const stillExists = convs.find((c) => c.id === storedId);

        let target = stillExists || convs[0];
        if (!target) {
          target = await createConversation();
          setConversations([target]);
        }

        await openConversation(target.id);
      } catch {
        setError("Couldn't reach the server. Is the backend running?");
      } finally {
        setIsLoadingConversation(false);
      }
    }
    init();
  }, []);

  const handleUpload = async (file) => {
    setError(null);
    setIsProcessing(true);
    setMessages((prev) => [
      ...prev,
      { role: "user", type: "text", text: `Process product sheet "${file.name}".` },
    ]);

    try {
      const result = await uploadSheet(file, activeConversationId);
      const data = await fetchConversationMessages(activeConversationId).catch(() => null);
      setMessages(data?.messages || ((prev) => [...prev, ...result.messages.slice(1)]));
      refreshConversations();
    } catch (err) {
      setError(err.message || "Something went wrong.");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleSheetUrl = async (url) => {
    setError(null);
    setIsProcessing(true);
    setMessages((prev) => [
      ...prev,
      { role: "user", type: "text", text: `Read this Google Sheet: ${url}` },
    ]);

    try {
      const result = await processSheetUrl(url, activeConversationId);
      const data = await fetchConversationMessages(activeConversationId).catch(() => null);
      setMessages(data?.messages || ((prev) => [...prev, ...result.messages.slice(1)]));
      refreshConversations();
    } catch (err) {
      setError(err.message || "Something went wrong.");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleAsk = async (question) => {
    setError(null);
    setIsProcessing(true);
    setMessages((prev) => [...prev, { role: "user", type: "text", text: question }]);

    try {
      const result = await askQuestion(question, activeConversationId);
      const data = await fetchConversationMessages(activeConversationId);
      setMessages(data.messages || [
        { role: "assistant", type: "text", text: result.answer },
      ]);
      refreshConversations();
    } catch (err) {
      setError(err.message || "Something went wrong.");
    } finally {
      setIsProcessing(false);
    }
  };

  // Attached photos + instruction go straight to the image-chat endpoint,
  // one call per photo (same sequential pattern as Automation's batch
  // pipeline). Each call that includes conversation_id gets persisted
  // server-side as its own user/assistant turn, so once at least one
  // succeeds we resync from the conversation's real history instead of
  // leaving the optimistic local-only bubbles in place — same as the plain
  // Q&A flow, so a reload or switching chats doesn't lose the result.
  const handleGenerateImage = async (text, files, previews) => {
    if (!files || files.length === 0 || !activeConversationId) return;
    setError(null);
    const trimmedText = text.trim() || "Generate gambar produk ini.";
    const assistantMessageId = nextImageGenId();

    setMessages((prev) => [
      ...prev,
      { id: nextImageGenId(), role: "user", type: "image_gen", text: trimmedText, previews },
      {
        id: assistantMessageId,
        role: "assistant",
        type: "image_gen",
        status: "generating",
        total: files.length,
        images: [],
      },
    ]);
    setIsProcessing(true);

    const results = [];
    let failure = null;
    try {
      for (const file of files) {
        // eslint-disable-next-line no-await-in-loop
        const result = await imageChatGenerate(trimmedText, {
          referenceFile: file,
          conversationId: activeConversationId,
        });
        results.push({ url: toChatAssetUrl(result.image_url) });
        const snapshot = [...results];
        setMessages((prev) =>
          prev.map((message) =>
            message.id === assistantMessageId ? { ...message, images: snapshot } : message
          )
        );
      }
    } catch (err) {
      failure = err.message || "Gagal generate gambar";
    }

    if (results.length > 0) {
      try {
        const data = await fetchConversationMessages(activeConversationId);
        setMessages(data.messages || []);
        refreshConversations();
      } catch {
        // Resync failed — keep the optimistic bubbles already showing.
      }
      if (failure) setError(failure);
    } else if (failure) {
      setMessages((prev) =>
        prev.map((message) =>
          message.id === assistantMessageId ? { ...message, status: "error", error: failure } : message
        )
      );
    }

    previews.forEach((url) => URL.revokeObjectURL(url));
    setIsProcessing(false);
  };

  const handleNewChat = async () => {
    setError(null);
    try {
      const created = await createConversation();
      setConversations((prev) => [created, ...prev]);
      setActiveConversationId(created.id);
      localStorage.setItem(ACTIVE_CONVERSATION_KEY, String(created.id));
      setMessages([]);
    } catch (err) {
      setError(err.message || "Failed to start a new chat.");
    }
  };

  const handleSelectConversation = (id) => {
    if (id === activeConversationId) return;
    setError(null);
    openConversation(id);
  };

  const handleDeleteConversation = async (id) => {
    try {
      await deleteConversation(id);
      const remaining = conversations.filter((c) => c.id !== id);
      setConversations(remaining);
      setArchivedConversations((prev) => prev.filter((c) => c.id !== id));

      if (id === activeConversationId) {
        if (remaining.length > 0) {
          openConversation(remaining[0].id);
        } else {
          const created = await createConversation();
          setConversations([created]);
          openConversation(created.id);
        }
      }
    } catch (err) {
      setError(err.message || "Failed to delete conversation.");
    }
  };

  const handleUpdateConversation = async (id, updates) => {
    try {
      const updated = await updateConversation(id, updates);
      if (updates.archived) {
        const remaining = conversations.filter((c) => c.id !== id);
        setConversations(remaining);
        setArchivedConversations((prev) => [{ ...updated, archived: 1 }, ...prev]);

        if (id === activeConversationId) {
          if (remaining.length > 0) {
            openConversation(remaining[0].id);
          } else {
            const created = await createConversation();
            setConversations([created]);
            openConversation(created.id);
          }
        }
        return;
      }

      if (updates.archived === false) {
        setArchivedConversations((prev) => prev.filter((conv) => conv.id !== id));
        setConversations((prev) =>
          [{ ...updated, archived: 0 }, ...prev.filter((conv) => conv.id !== id)].sort((a, b) => {
            if (Number(b.pinned) !== Number(a.pinned)) {
              return Number(b.pinned) - Number(a.pinned);
            }
            return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
          })
        );
        return;
      }

      setConversations((prev) =>
        prev
          .map((conv) => (conv.id === id ? { ...conv, ...updated } : conv))
          .sort((a, b) => {
            if (Number(b.pinned) !== Number(a.pinned)) {
              return Number(b.pinned) - Number(a.pinned);
            }
            return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
          })
      );
    } catch (err) {
      setError(err.message || "Failed to update conversation.");
    }
  };

  const handleEditMessage = async (messageId, text) => {
    if (!activeConversationId || !messageId) return;
    setError(null);
    setIsProcessing(true);
    try {
      setMessages((prev) =>
        prev
          .map((message) =>
            message.id === messageId ? { ...message, text } : message
          )
          .slice(0, prev.findIndex((message) => message.id === messageId) + 1)
      );
      const result = await editConversationMessage(activeConversationId, messageId, text);
      setMessages(result.messages || []);
      refreshConversations();
    } catch (err) {
      setError(err.message || "Failed to edit message.");
      const data = await fetchConversationMessages(activeConversationId).catch(() => null);
      if (data) setMessages(data.messages || []);
    } finally {
      setIsProcessing(false);
    }
  };

  const activeConversation =
    conversations.find((c) => c.id === activeConversationId) ||
    archivedConversations.find((c) => c.id === activeConversationId);

  const primaryNavItems = useMemo(
    () =>
      buildPrimaryNavItems({
        conversations,
        archivedConversations,
        onUpdateConversation: handleUpdateConversation,
        onDeleteConversation: handleDeleteConversation,
      }),
    [conversations, archivedConversations],
  );

  const closeOverlays = () => {
    setShowInstructionManual(false);
    setShowGallery(false);
    setShowTranslatePdf(false);
    setShowDescription(false);
    setShowAutomation(false);
  };

  const handleSidebarAction = (action, item) => {
    switch (action) {
      case "new-chat":
        closeOverlays();
        handleNewChat();
        break;
      case "automation":
        closeOverlays();
        setShowAutomation(true);
        break;
      case "instruction-manual":
        closeOverlays();
        setShowInstructionManual(true);
        break;
      case "gallery":
        closeOverlays();
        setShowGallery(true);
        break;
      case "translate":
        closeOverlays();
        setShowTranslatePdf(true);
        break;
      case "description":
        closeOverlays();
        setShowDescription(true);
        break;
      case "select-conversation":
        if (item.conversationId) {
          closeOverlays();
          handleSelectConversation(item.conversationId);
        }
        break;
      default:
        break;
    }
  };

  const activePath = showAutomation
    ? "/automation"
    : showInstructionManual
    ? "/instruction-manual"
    : showGallery
    ? "/gallery"
    : showTranslatePdf
    ? "/translate"
    : showDescription
    ? "/description"
    : activeConversationId
    ? `/chat/${activeConversationId}`
    : undefined;

  return (
    <div className="app-shell">
      <Sidebar
        activePath={activePath}
        userName="Piagam AI"
        userRole="Vendor Sheet Assistant"
        primaryItems={primaryNavItems}
        secondaryItems={[]}
        onAction={handleSidebarAction}
        collapsed={!sidebarOpen}
        onToggleCollapse={() => setSidebarOpen((prev) => !prev)}
        mobileOpen={mobileSidebarOpen}
        onCloseMobile={() => setMobileSidebarOpen(false)}
      />
      {showAutomation ? (
        <AutomationPage onToggleSidebar={() => setMobileSidebarOpen((prev) => !prev)} />
      ) : showGallery ? (
        <ImagePage onToggleSidebar={() => setMobileSidebarOpen((prev) => !prev)} />
      ) : showInstructionManual ? (
        <InstructionManualPage
          onClose={() => setShowInstructionManual(false)}
          onToggleSidebar={() => setMobileSidebarOpen((prev) => !prev)}
        />
      ) : showTranslatePdf ? (
        <TranslatePage onToggleSidebar={() => setMobileSidebarOpen((prev) => !prev)} />
      ) : showDescription ? (
        <DescriptionPage onToggleSidebar={() => setMobileSidebarOpen((prev) => !prev)} />
      ) : (
        <ChatArea
          activeConversation={activeConversation}
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setMobileSidebarOpen((prev) => !prev)}
          messages={messages}
          isProcessing={isProcessing || isLoadingConversation}
          error={error}
          onUpload={handleUpload}
          onSheetUrl={handleSheetUrl}
          onAsk={handleAsk}
          onGenerateImage={handleGenerateImage}
          onEditMessage={handleEditMessage}
        />
      )}
    </div>
  );
}
