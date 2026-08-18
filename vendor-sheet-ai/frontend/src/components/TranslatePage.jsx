import { useEffect, useMemo, useState } from "react";
import { RestartAltRounded as RestartAltRoundedIcon } from "@mui/icons-material";
import Header from "../piagam/template/Header.jsx";
import BackgroundMain from "../piagam/template/BackgroundMain.jsx";
import { deletePdfTranslateHistoryItem, fetchPdfTranslateHistory, translatePdf } from "../api";

async function copyToClipboard(text) {
  if (!text) return;
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

function formatFileSize(bytes) {
  if (!bytes) return "";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function StatusIcon({ status }) {
  if (status === "generating") {
    return (
      <span className="batch-status batch-status-pending">
        <span className="batch-spinner" />
      </span>
    );
  }
  if (status === "done") {
    return (
      <span className="batch-status batch-status-done">
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" aria-hidden="true">
          <path d="m5 12 4.2 4.2L19 6.5" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="batch-status batch-status-error">
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" aria-hidden="true">
          <path d="M7 7 17 17M17 7 7 17" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
        </svg>
      </span>
    );
  }
  return (
    <span className="batch-status batch-status-waiting">
      <span className="batch-waiting-dot" />
    </span>
  );
}

function CopyLinkButton({ url, copied, onCopy }) {
  return (
    <button
      type="button"
      className={"copy-link-btn" + (copied ? " copied" : "")}
      onClick={onCopy}
      disabled={!url}
      title={copied ? "Link copied" : "Copy link"}
      aria-label={copied ? "Link copied" : "Copy link"}
    >
      {copied ? (
        <>
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
            <path d="m5 12.25 4.25 4.25L19 6.75" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>Copied</span>
        </>
      ) : (
        <>
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
            <path
              d="M9.25 14.75 8 16a4.24 4.24 0 0 1-6-6l2.25-2.25a4.24 4.24 0 0 1 6 0M14.75 9.25 16 8a4.24 4.24 0 0 1 6 6l-2.25 2.25a4.24 4.24 0 0 1-6 0M8.75 15.25l6.5-6.5"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span>Copy Link</span>
        </>
      )}
    </button>
  );
}

function TranslateTab({ onDone }) {
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("idle"); // idle | working | done | error
  const [docUrl, setDocUrl] = useState(null);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  function handleFileChange(event) {
    const picked = event.target.files?.[0] || null;
    setFile(picked);
    setStatus("idle");
    setDocUrl(null);
    setError(null);
    setCopied(false);
  }

  async function handleTranslate() {
    if (!file) return;
    setStatus("working");
    setError(null);
    setCopied(false);
    try {
      const result = await translatePdf(file);
      setDocUrl(result.doc_url);
      setStatus("done");
      onDone?.();
    } catch (err) {
      setError(err.message || "Gagal menerjemahkan dokumen");
      setStatus("error");
    }
  }

  async function handleCopyResult() {
    await copyToClipboard(docUrl);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  return (
    <>
      <p className="im-subtitle">
        Upload file PDF, gambar (JPG/PNG/dll), atau Word (.docx) — hasil terjemahan (Bahasa
        Indonesia) akan dibuat sebagai Google Doc baru.
      </p>

      <label className={"translate-upload-box" + (status === "working" ? " disabled" : "")}>
        <input
          type="file"
          accept=".pdf,application/pdf,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/*"
          onChange={handleFileChange}
          disabled={status === "working"}
        />
        <span className="translate-upload-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="21" height="21" fill="none">
            <path
              d="M7.25 3.75h6.5l4 4v11.5a1 1 0 0 1-1 1H7.25a1 1 0 0 1-1-1V4.75a1 1 0 0 1 1-1Z"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinejoin="round"
            />
            <path
              d="M13.75 3.75V7.2a.55.55 0 0 0 .55.55h3.7"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinejoin="round"
            />
            <path
              d="M12 12v5.25M9.5 14.5 12 12l2.5 2.5"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <span className="translate-upload-text">
          <span className="translate-upload-title">{file ? file.name : "Pilih file PDF, gambar, atau Word"}</span>
          <span className="translate-upload-meta">{file ? formatFileSize(file.size) : "Klik untuk upload dokumen"}</span>
        </span>
      </label>

      <div className="im-actions">
        <button
          type="button"
          className={"im-generate-btn" + (status === "working" ? " is-loading" : "")}
          onClick={handleTranslate}
          disabled={!file || status === "working"}
        >
          {status === "working" ? (
            <>
              <span className="button-spinner button-spinner-invert" />
              <span>Menerjemahkan...</span>
            </>
          ) : (
            <>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true">
                <path
                  d="M4.5 5.75h8.75M8.9 4.25v1.5M6.25 9.25c.82 1.68 2.22 3.1 4.35 4.25M11.75 7.75c-.62 2.28-2.33 4.57-5.25 6.75"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M12.75 18.75 16 10.25l3.25 8.5M13.75 16.25h4.5"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span>Generate Translate</span>
            </>
          )}
        </button>
      </div>

      {status === "error" && <div className="error-banner">{error}</div>}

      {status === "done" && docUrl && (
        <div className="batch-results is-complete">
          <div className="batch-results-header">
            <StatusIcon status="done" />
            <div className="batch-results-title">
              <span>Translate selesai</span>
              <small>Google Doc sudah dibuat.</small>
            </div>
          </div>
          <div className="batch-result-row batch-done">
            <StatusIcon status="done" />
            <span className="batch-result-copy">
              <span className="batch-result-name">{file?.name || "Dokumen"}</span>
              <span className="batch-result-status-text">Selesai diterjemahkan</span>
            </span>
            <div className="batch-result-actions">
              <CopyLinkButton url={docUrl} copied={copied} onCopy={handleCopyResult} />
              <a className="batch-open-link" href={docUrl} target="_blank" rel="noreferrer">
                <svg viewBox="0 0 24 24" width="13" height="13" fill="none" aria-hidden="true">
                  <path
                    d="M9.75 5.75h-3a2 2 0 0 0-2 2v9.5a2 2 0 0 0 2 2h9.5a2 2 0 0 0 2-2v-3M13.75 4.75h5.5v5.5M19 5l-8.25 8.25"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <span>Buka</span>
              </a>
            </div>
          </div>
        </div>
      )}

      {status === "__legacy_done__" && docUrl && (
        <p>
          Selesai —{" "}
          <a href={docUrl} target="_blank" rel="noreferrer">
            Buka Google Doc
          </a>
        </p>
      )}
    </>
  );
}

function HistoryTab() {
  const [docs, setDocs] = useState([]);
  const [folderUrl, setFolderUrl] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [deletingId, setDeletingId] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [copiedId, setCopiedId] = useState(null);

  const load = () => {
    setLoading(true);
    setError(null);
    fetchPdfTranslateHistory()
      .then((data) => {
        setDocs(data.docs || []);
        setFolderUrl(data.folder_url || null);
      })
      .catch((err) => setError(err.message || "Failed to load history"))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const filteredDocs = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return docs;
    return docs.filter((doc) => doc.name?.toLowerCase().includes(term));
  }, [docs, search]);
  const pendingDeleteDoc = useMemo(() => docs.find((doc) => doc.id === confirmDeleteId), [confirmDeleteId, docs]);

  const handleDeleteDoc = async (doc) => {
    if (!doc.id || deletingId) return;
    setDeletingId(doc.id);
    setConfirmDeleteId(null);
    setError(null);
    try {
      await deletePdfTranslateHistoryItem(doc.id);
      setDocs((prev) => prev.filter((item) => item.id !== doc.id));
    } catch (err) {
      setError(err.message || "Failed to delete document");
    } finally {
      setDeletingId(null);
    }
  };

  const handleCopyLink = async (doc) => {
    await copyToClipboard(doc.url);
    const key = doc.id || doc.url;
    setCopiedId(key);
    window.setTimeout(() => setCopiedId((current) => (current === key ? null : current)), 1400);
  };

  return (
    <>
      <p className="im-subtitle">Semua dokumen yang pernah diterjemahkan, diambil langsung dari folder history di Google Drive.</p>

      <div className="history-toolbar">
        {folderUrl && (
          <a href={folderUrl} target="_blank" rel="noreferrer" className="history-folder-link">
            <svg className="google-drive-icon" viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
              <path
                d="M8.55 3.75h6.9l5.55 9.62-3.45 5.98H6.45L3 13.37 8.55 3.75Z"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinejoin="round"
              />
              <path
                d="M8.55 3.75 12 9.73m3.45-5.98-3.45 5.98m0 0-5.55 9.62M12 9.73l2.1 3.64H21M9.9 13.37H21"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                opacity="0.72"
              />
            </svg>
            <span>Buka folder di Drive</span>
          </a>
        )}
        <button
          className="history-refresh-btn"
          onClick={load}
          disabled={loading}
          title={loading ? "Memuat history" : "Refresh history"}
          aria-label={loading ? "Memuat history" : "Refresh history"}
        >
          {loading ? (
            <>
              <span className="button-spinner" />
              <span>Loading</span>
            </>
          ) : (
            <>
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true">
                <path
                  d="M20 11a8 8 0 0 0-14.6-4.5M4 5v4h4M4 13a8 8 0 0 0 14.6 4.5M20 19v-4h-4"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span>Refresh</span>
            </>
          )}
        </button>
      </div>

      <div className="im-search-box history-search-box">
        <svg className="im-search-icon" viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true">
          <path d="M10.75 18.5a7.75 7.75 0 1 1 0-15.5 7.75 7.75 0 0 1 0 15.5ZM16.5 16.5 21 21" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
        </svg>
        <input
          className="im-search-input"
          type="text"
          placeholder="Cari history dokumen..."
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          disabled={loading}
        />
      </div>

      {error && <div className="error-banner">{error}</div>}

      {!loading && filteredDocs.length > 0 && (
        <div className="doc-history-header">
          <span className="doc-history-header-label">Nama Dokumen</span>
          <span className="doc-history-header-label doc-history-header-date">Tanggal Translate</span>
          <span className="doc-history-header-label doc-history-header-actions">Aksi</span>
        </div>
      )}

      {!loading && (
        <div className="doc-history-list">
          {docs.length === 0 && (
            <div className="im-empty-state">
              <span>Belum ada dokumen yang diterjemahkan.</span>
            </div>
          )}
          {docs.length > 0 && filteredDocs.length === 0 && (
            <div className="im-empty-state">
              <span>Tidak ada history yang cocok.</span>
            </div>
          )}
          {filteredDocs.map((doc) => (
            <div key={doc.id || doc.url} className="doc-history-item">
              <a className="doc-history-main" href={doc.url} target="_blank" rel="noreferrer">
                <span className="im-doc-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="17" height="17" fill="none" aria-hidden="true">
                    <path d="M6.25 3.75h8l3.5 3.5v13H6.25V3.75Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
                    <path d="M14.25 3.75v3.5h3.5" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
                    <path d="M9 13.25h6M9 16.25h4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                  </svg>
                </span>
                <span className="doc-history-name">{doc.name}</span>
                <span className="doc-history-date">
                  <span className="doc-history-date-pill">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
                      <rect
                        x="4.75"
                        y="5.75"
                        width="14.5"
                        height="13.5"
                        rx="2.25"
                        stroke="currentColor"
                        strokeWidth="1.65"
                      />
                      <path
                        d="M8 3.75v3M16 3.75v3M4.75 9.5h14.5M8.25 13h.01M12 13h.01M15.75 13h.01M8.25 16h.01M12 16h.01"
                        stroke="currentColor"
                        strokeWidth="1.65"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                    <span>{formatDate(doc.modified_at)}</span>
                  </span>
                </span>
              </a>
              <div className="doc-history-actions">
                <CopyLinkButton url={doc.url} copied={copiedId === (doc.id || doc.url)} onCopy={() => handleCopyLink(doc)} />
                <button
                  type="button"
                  className="doc-history-delete-btn"
                  onClick={() => setConfirmDeleteId(doc.id)}
                  disabled={deletingId === doc.id}
                  title="Hapus history"
                  aria-label="Hapus history"
                >
                  {deletingId === doc.id ? (
                    <span className="doc-delete-dot" />
                  ) : (
                    <>
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
                        <path
                          d="M3.75 6.25h16.5M9 6.25V4.8c0-.58.47-1.05 1.05-1.05h3.9c.58 0 1.05.47 1.05 1.05v1.45m3 0-.63 12c-.05.84-.74 1.5-1.58 1.5H8.21c-.84 0-1.53-.66-1.58-1.5L6 6.25m4.25 4.5v5.5m3.5-5.5v5.5"
                          stroke="currentColor"
                          strokeWidth="1.7"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                      <span>Hapus</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {pendingDeleteDoc && (
        <div className="doc-delete-confirm doc-delete-confirm-floating" role="dialog" aria-label="Konfirmasi hapus">
          <span>Hapus dokumen ini?</span>
          <div className="doc-delete-confirm-actions">
            <button type="button" className="confirm-no" onClick={() => setConfirmDeleteId(null)}>
              No
            </button>
            <button type="button" className="confirm-yes" onClick={() => handleDeleteDoc(pendingDeleteDoc)}>
              Yes
            </button>
          </div>
        </div>
      )}
    </>
  );
}

export default function TranslatePage({ onToggleSidebar }) {
  const [tab, setTab] = useState("translate");
  const [resetKey, setResetKey] = useState(0);

  return (
    <div className="gallery-panel im-panel">
      <BackgroundMain />
      <Header
        title="Translate"
        showMenuButton
        onMenuToggle={onToggleSidebar}
        showBreadcrumbBar={false}
      />

      <div className="im-panel-content">
        <div className="im-content-body">
          <div className="page-tabs-row">
            <div className="page-tabs">
              <button
                className={"page-tab" + (tab === "translate" ? " active" : "")}
                onClick={() => setTab("translate")}
              >
                Translate
              </button>
              <button
                className={"page-tab" + (tab === "history" ? " active" : "")}
                onClick={() => setTab("history")}
              >
                Riwayat
              </button>
            </div>
            <button
              type="button"
              className="im-reset-btn"
              onClick={() => setResetKey((prev) => prev + 1)}
              title="Reset halaman"
              aria-label="Reset halaman"
            >
              <RestartAltRoundedIcon fontSize="inherit" />
              <span>Reset</span>
            </button>
          </div>

          {tab === "translate" ? (
            <TranslateTab key={`translate-${resetKey}`} onDone={() => {}} />
          ) : (
            <HistoryTab key={`history-${resetKey}`} />
          )}
        </div>
      </div>
    </div>
  );
}
