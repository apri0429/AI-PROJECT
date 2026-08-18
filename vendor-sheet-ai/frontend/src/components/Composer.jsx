import { useState } from "react";

export default function Composer({
  onUpload,
  onSheetUrl,
  onAsk,
  onGenerateImage,
  isProcessing,
  isEmpty,
}) {
  const [dragOver, setDragOver] = useState(false);
  const [linkMode, setLinkMode] = useState(false);
  const [sheetUrl, setSheetUrl] = useState("");
  const [question, setQuestion] = useState("");
  const [imageAttachments, setImageAttachments] = useState([]);

  const handleFile = (file) => {
    if (!file) return;
    onUpload(file);
  };

  const addImageAttachments = (fileList) => {
    const files = Array.from(fileList || []).filter((f) => f.type.startsWith("image/"));
    if (files.length === 0) return;
    setImageAttachments((prev) => [
      ...prev,
      ...files.map((file) => ({ file, previewUrl: URL.createObjectURL(file) })),
    ]);
  };

  const removeImageAttachment = (index) => {
    setImageAttachments((prev) => {
      const next = [...prev];
      const [removed] = next.splice(index, 1);
      if (removed) URL.revokeObjectURL(removed.previewUrl);
      return next;
    });
  };

  const submitLink = () => {
    const url = sheetUrl.trim();
    if (!url || isProcessing) return;
    onSheetUrl(url);
    setSheetUrl("");
    setLinkMode(false);
  };

  const submitQuestion = () => {
    if (isProcessing) return;
    const text = question.trim();

    if (imageAttachments.length > 0) {
      const files = imageAttachments.map((a) => a.file);
      const previews = imageAttachments.map((a) => a.previewUrl);
      onGenerateImage(text, files, previews);
      setImageAttachments([]);
      setQuestion("");
      return;
    }

    if (!text) return;
    onAsk(text);
    setQuestion("");
  };

  if (linkMode) {
    return (
      <div className={"composer" + (isEmpty ? " composer-empty" : "")}>
        <div className="composer-box">
          <button
            type="button"
            className="attach-btn"
            onClick={() => setLinkMode(false)}
            title="Back to chat"
            aria-label="Back to chat"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
              <path
                d="M15 6l-6 6 6 6"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>

          <input
            className="composer-link-input"
            type="url"
            placeholder={'Tempel link Google Sheet yang aksesnya "Anyone with the link can view"...'}
            value={sheetUrl}
            onChange={(e) => setSheetUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submitLink()}
            disabled={isProcessing}
            autoFocus
          />

          <button
            type="button"
            className="send-btn"
            onClick={submitLink}
            disabled={isProcessing || !sheetUrl.trim()}
            title="Read sheet"
            aria-label="Read sheet"
          >
            {isProcessing ? (
              <span className="send-loading-dot" />
            ) : (
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
                <path
                  d="M5 12h12.5M13 6.5l5.5 5.5-5.5 5.5"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </button>
        </div>
        <p className="composer-hint">
          Data dari sheet akan dibaca agar bisa ditanyakan di chat ini.
        </p>
      </div>
    );
  }

  const hasImageAttachments = imageAttachments.length > 0;

  return (
    <div className={"composer" + (isEmpty ? " composer-empty" : "")}>
      {hasImageAttachments && (
        <div className="ichat-composer-attachments">
          {imageAttachments.map((attachment, index) => (
            <div key={attachment.previewUrl} className="ichat-composer-attachment">
              <img src={attachment.previewUrl} alt="" />
              <button
                type="button"
                className="ichat-composer-attachment-remove"
                onClick={() => removeImageAttachment(index)}
                aria-label="Hapus lampiran"
              >
                <svg viewBox="0 0 24 24" width="10" height="10" fill="none" aria-hidden="true">
                  <path
                    d="M6.75 6.75 17.25 17.25M17.25 6.75 6.75 17.25"
                    stroke="currentColor"
                    strokeWidth="2.3"
                    strokeLinecap="round"
                  />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}

      <div
        className={"composer-box" + (dragOver ? " drag-over" : "")}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (e.dataTransfer.files?.[0]?.type?.startsWith("image/")) {
            addImageAttachments(e.dataTransfer.files);
          } else {
            handleFile(e.dataTransfer.files?.[0]);
          }
        }}
      >
        <input
          className="composer-link-input"
          type="text"
          placeholder={
            isProcessing
              ? "Processing..."
              : hasImageAttachments
              ? "Jelasin varian produk yang mau di-generate (opsional)..."
              : "Tanya data produk dari sheet, atau attach foto untuk generate gambar..."
          }
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submitQuestion()}
          disabled={isProcessing}
        />

        <input
          id="composer-image-attach-input"
          type="file"
          accept="image/*"
          multiple
          hidden
          onChange={(e) => {
            addImageAttachments(e.target.files);
            e.target.value = "";
          }}
        />
        <label
          className="composer-attach-image-btn"
          htmlFor="composer-image-attach-input"
          title="Attach foto produk untuk generate gambar"
          aria-label="Attach foto produk untuk generate gambar"
        >
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true">
            <path
              d="M8 12.5v-5a4 4 0 0 1 8 0v6.5a2.5 2.5 0 0 1-5 0v-6a1 1 0 0 1 2 0v5.5"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </label>

        <button
          type="button"
          className="link-toggle-btn"
          onClick={() => setLinkMode(true)}
          disabled={isProcessing}
          title="Paste a Google Sheet link instead"
        >
          Sheet link
        </button>

        <button
          type="button"
          className="send-btn"
          onClick={submitQuestion}
          disabled={isProcessing || (!question.trim() && !hasImageAttachments)}
          title="Send message"
          aria-label="Send message"
        >
          {isProcessing ? (
            <span className="send-loading-dot" />
          ) : (
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
              <path
                d="M12 19V5M6.5 10.5 12 5l5.5 5.5"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
        </button>

      </div>
      <p className="composer-hint">
        Upload CSV/link Sheet untuk tanya data produk, atau attach foto produk untuk generate
        gambar ecommerce dari chat ini.
      </p>
    </div>
  );
}
