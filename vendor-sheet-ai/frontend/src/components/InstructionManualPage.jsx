import { useEffect, useMemo, useState } from "react";
import { RestartAltRounded as RestartAltRoundedIcon } from "@mui/icons-material";
import Header from "../piagam/template/Header.jsx";
import BackgroundMain from "../piagam/template/BackgroundMain.jsx";
import {
  deleteDocHistoryItem,
  fetchDocHistory,
  fetchProducts,
  generateInstructionManual,
} from "../api";

const MAX_SELECTION = 10;

const OPTIONAL_SECTIONS = [
  { key: "cara_penggunaan", label: "Petunjuk Penggunaan" },
  { key: "perawatan", label: "Perhatian Penggunaan" },
  { key: "gambar_produk", label: "Gambar Produk" },
];

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

const BRAND_INITIALS = [
  { match: "goto", label: "GT" },
  { match: "gosave", label: "GS" },
];

const BRAND_FILTER_OPTIONS = [
  { key: "all", label: "Semua" },
  { key: "goto", label: "Goto" },
  { key: "gosave", label: "Gosave" },
];

function getProductInitials(name) {
  const lower = name?.trim().toLowerCase() || "";
  const brand = BRAND_INITIALS.find(({ match }) => lower.includes(match));
  if (brand) return brand.label;
  return name?.trim().slice(0, 2).toUpperCase() || "?";
}

function detectBrand(product) {
  const haystack = `${product.product_name || ""} ${product.vendor_name || ""}`.toLowerCase();
  if (haystack.includes("gosave")) return "gosave";
  if (haystack.includes("goto")) return "goto";
  return "goto";
}

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("id-ID", {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
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
            <path
              d="m5 12.25 4.25 4.25L19 6.75"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
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

function getBatchStatusText(status) {
  if (status === "generating") return "AI sedang menyusun manual";
  if (status === "done") return "Selesai dibuat";
  if (status === "error") return "Gagal generate";
  return "Menunggu giliran";
}

function GenerateTab() {
  const [products, setProducts] = useState([]);
  const [loadingProducts, setLoadingProducts] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [search, setSearch] = useState("");
  const [brandFilter, setBrandFilter] = useState("all");
  const [selected, setSelected] = useState(() => new Set());
  const [generating, setGenerating] = useState(false);
  const [batchResults, setBatchResults] = useState([]);
  const [copiedUrl, setCopiedUrl] = useState(null);
  const [imageCount, setImageCount] = useState(1);
  const [sections, setSections] = useState(() =>
    Object.fromEntries(OPTIONAL_SECTIONS.map((s) => [s.key, true]))
  );

  const toggleSection = (key) => {
    if (generating) return;
    setSections((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // The photo-count toggle only applies when usage instructions include real product photos.
  const photoCountDisabled = !sections.gambar_produk || !sections.cara_penggunaan;

  useEffect(() => {
    fetchProducts()
      .then((data) => setProducts(data.products || []))
      .catch((err) => setLoadError(err.message || "Failed to load products"))
      .finally(() => setLoadingProducts(false));
  }, []);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return products.filter((p) => {
      const matchesTerm =
        !term ||
        p.product_name?.toLowerCase().includes(term) ||
        p.vendor_name?.toLowerCase().includes(term);
      const matchesBrand = brandFilter === "all" || detectBrand(p) === brandFilter;
      return matchesTerm && matchesBrand;
    });
  }, [products, search, brandFilter]);

  const toggleSelect = (name) => {
    if (generating) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else if (next.size < MAX_SELECTION) {
        next.add(name);
      }
      return next;
    });
    setBatchResults([]);
  };

  const selectAllVisible = () => {
    if (generating) return;
    setSelected((prev) => {
      const next = new Set(prev);
      for (const product of filtered) {
        if (next.size >= MAX_SELECTION) break;
        next.add(product.product_name);
      }
      return next;
    });
    setBatchResults([]);
  };

  const clearSelection = () => {
    if (generating) return;
    setSelected(new Set());
    setBatchResults([]);
  };

  const handleGenerate = async () => {
    const names = Array.from(selected);
    if (names.length === 0) return;

    setGenerating(true);
    setBatchResults(names.map((name) => ({ product_name: name, status: "waiting" })));

    for (const name of names) {
      setBatchResults((prev) =>
        prev.map((result) =>
          result.product_name === name ? { ...result, status: "generating" } : result
        )
      );
      try {
        const result = await generateInstructionManual(name, imageCount, sections);
        setBatchResults((prev) =>
          prev.map((item) =>
            item.product_name === name
              ? { ...item, status: "done", docUrl: result.doc_url }
              : item
          )
        );
      } catch (err) {
        setBatchResults((prev) =>
          prev.map((item) =>
            item.product_name === name
              ? { ...item, status: "error", error: err.message || "Gagal generate" }
              : item
          )
        );
      }
    }

    setGenerating(false);
  };

  const handleCopyLink = async (url) => {
    await copyToClipboard(url);
    setCopiedUrl(url);
    window.setTimeout(() => setCopiedUrl((current) => (current === url ? null : current)), 1400);
  };

  const selectionCount = selected.size;

  return (
    <>
      <p className="im-subtitle">
        Pilih produk dan section yang dibutuhkan. Dokumen akan otomatis tersimpan ke Google Drive.
      </p>

      <div className="brand-choice-panel automation-brand-filter-panel">
        <span className="image-count-label automation-brand-filter-label">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
            <path
              d="M11.4 4.5h6.1a2 2 0 0 1 2 2v6.1a2 2 0 0 1-.59 1.42l-7.5 7.5a2 2 0 0 1-2.82 0l-6.1-6.1a2 2 0 0 1 0-2.82l7.5-7.5a2 2 0 0 1 1.41-.6Z"
              stroke="currentColor"
              strokeWidth="1.9"
              strokeLinejoin="round"
            />
            <circle cx="15.25" cy="8.75" r="1.35" stroke="currentColor" strokeWidth="1.9" />
          </svg>
          BRAND
        </span>
        <div className="brand-choice-options" role="radiogroup" aria-label="Filter brand produk">
          {BRAND_FILTER_OPTIONS.map((option) => (
            <button
              key={option.key}
              type="button"
              role="radio"
              aria-checked={brandFilter === option.key}
              data-brand={option.key}
              className={"brand-choice-option" + (brandFilter === option.key ? " active" : "")}
              onClick={() => setBrandFilter(option.key)}
              disabled={loadingProducts || generating}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="im-search-box">
        <svg className="im-search-icon" viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true">
          <path
            d="M10.75 18.5a7.75 7.75 0 1 1 0-15.5 7.75 7.75 0 0 1 0 15.5ZM16.5 16.5 21 21"
            stroke="currentColor"
            strokeWidth="1.9"
            strokeLinecap="round"
          />
        </svg>
        <input
          className="im-search-input"
          type="text"
          placeholder="Cari produk atau vendor..."
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          disabled={loadingProducts}
        />
      </div>

      <div className="selection-toolbar">
        <span className={"im-selection-badge" + (selectionCount > 0 ? " has-selection" : "")}>
          {selectionCount}/{MAX_SELECTION} dipilih
        </span>
        <div className="selection-toolbar-actions">
          <button
            type="button"
            className="selection-toolbar-btn selection-toolbar-btn-primary"
            onClick={selectAllVisible}
            disabled={generating}
            title="Pilih semua produk yang tampil (maks. 10)"
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
              <path
                d="M4.75 12.25 9 16.5 19.25 6.25"
                stroke="currentColor"
                strokeWidth="2.3"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span>Pilih semua</span>
          </button>
          <button
            type="button"
            className="selection-toolbar-btn selection-toolbar-btn-danger"
            onClick={clearSelection}
            disabled={generating || selectionCount === 0}
            title="Kosongkan semua produk yang dipilih"
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
              <path
                d="M6.75 6.75 17.25 17.25M17.25 6.75 6.75 17.25"
                stroke="currentColor"
                strokeWidth="2.3"
                strokeLinecap="round"
              />
            </svg>
            <span>Kosongkan</span>
          </button>
        </div>
      </div>

      {loadingProducts && (
        <div className="im-empty-state">
          <span className="button-spinner" />
          <span>Memuat daftar produk...</span>
        </div>
      )}
      {loadError && <div className="error-banner">{loadError}</div>}

      {!loadingProducts && !loadError && (
        <div className="product-list">
          {filtered.length === 0 && (
            <div className="im-empty-state">
              <span>Tidak ada produk yang cocok.</span>
            </div>
          )}
          {filtered.map((product) => {
            const isChecked = selected.has(product.product_name);
            const disabled = generating || (!isChecked && selectionCount >= MAX_SELECTION);
            return (
              <button
                key={product.product_name}
                className={"product-list-item" + (isChecked ? " active" : "")}
                onClick={() => toggleSelect(product.product_name)}
                disabled={disabled}
              >
                <span className={"product-checkbox" + (isChecked ? " checked" : "")}>
                  {isChecked && (
                    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" aria-hidden="true">
                      <path
                        d="M5 12.5 9.5 17 19 7"
                        stroke="currentColor"
                        strokeWidth="2.7"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  )}
                </span>
                <span className="im-product-avatar" aria-hidden="true">
                  {getProductInitials(product.product_name)}
                </span>
                <span className="product-list-text">
                  <span className="product-list-name">{product.product_name}</span>
                  {product.vendor_name && (
                    <span className="product-list-vendor">{product.vendor_name}</span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {batchResults.length > 0 && (
        <div className={"batch-results" + (generating ? " is-generating" : " is-complete")}>
          <div className="batch-results-header">
            <StatusIcon status={generating ? "generating" : "done"} />
            <div className="batch-results-title">
              <span>{generating ? "Membuat instruction manual" : "Instruction manual selesai"}</span>
              <small>
                {generating
                  ? "AI sedang menyusun dokumen dan menyimpannya ke Drive."
                  : "Dokumen sudah siap dibuka atau dibagikan."}
              </small>
            </div>
          </div>
          {batchResults.map((result) => (
            <div key={result.product_name} className={"batch-result-row batch-" + result.status}>
              <StatusIcon status={result.status} />
              <span className="batch-result-copy">
                <span className="batch-result-name">{result.product_name}</span>
                <span className="batch-result-status-text">{getBatchStatusText(result.status)}</span>
              </span>
              {result.status === "done" && result.docUrl && (
                <div className="batch-result-actions">
                  <CopyLinkButton
                    url={result.docUrl}
                    copied={copiedUrl === result.docUrl}
                    onCopy={() => handleCopyLink(result.docUrl)}
                  />
                  <a className="batch-open-link" href={result.docUrl} target="_blank" rel="noreferrer">
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
              )}
              {result.status === "error" && <span className="batch-result-error">{result.error}</span>}
            </div>
          ))}
        </div>
      )}

      <div className="manual-options-panel">
        <div className="manual-options-header">
          <span className="im-panel-eyebrow">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
              <path
                d="M6.25 3.75h8l3.5 3.5v13H6.25V3.75Z"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinejoin="round"
              />
              <path d="M9 12h6M9 15.5h6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
            Section dokumen
          </span>
        </div>

        <div className="manual-section-grid">
          {OPTIONAL_SECTIONS.map(({ key, label }) => {
            const isChecked = sections[key];
            return (
              <button
                key={key}
                type="button"
                className={"manual-section-option" + (isChecked ? " active" : "")}
                onClick={() => toggleSection(key)}
                disabled={generating}
              >
                <span className={"product-checkbox" + (isChecked ? " checked" : "")}>
                  {isChecked && (
                    <svg viewBox="0 0 24 24" width="10" height="10" fill="none" aria-hidden="true">
                      <path
                        d="M5 12.5 9.5 17 19 7"
                        stroke="currentColor"
                        strokeWidth="2.7"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  )}
                </span>
                <span>{label}</span>
              </button>
            );
          })}
        </div>

        <div className={"image-count-toggle" + (photoCountDisabled ? " is-disabled" : "")}>
          <span className="image-count-label">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
              <rect
                x="4.75"
                y="5.25"
                width="14.5"
                height="13.5"
                rx="2.25"
                stroke="currentColor"
                strokeWidth="1.7"
              />
              <path
                d="m6.75 16.75 4.1-4.1a1.25 1.25 0 0 1 1.78 0l1.12 1.12.62-.62a1.25 1.25 0 0 1 1.78 0l2.1 2.1M8.75 9.25h.01"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span>Jumlah foto referensi</span>
          </span>
          <div className="image-count-options" role="radiogroup" aria-label="Jumlah foto referensi">
            {[1, 2, 3].map((count) => (
              <button
                key={count}
                type="button"
                role="radio"
                aria-checked={imageCount === count}
                className={"image-count-option" + (imageCount === count ? " active" : "")}
                onClick={() => setImageCount(count)}
                disabled={generating || photoCountDisabled}
              >
                <span className="image-count-value">{count}</span>
                <span className="image-count-unit">foto</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="im-actions">
        <button
          className={"im-generate-btn im-instruction-generate-btn" + (generating ? " is-loading" : "")}
          onClick={handleGenerate}
          disabled={selectionCount === 0 || generating}
        >
          {generating ? (
            <>
              <span className="button-spinner button-spinner-invert" />
              <span>Membuat manual</span>
            </>
          ) : (
            <>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true">
                <path
                  d="M6.25 3.75h8l3.5 3.5v13H6.25V3.75Z"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinejoin="round"
                />
                <path
                  d="M14.25 3.75v3.5h3.5M8.75 11h6.5M8.75 14h5M18.75 13.75v1.5M18.75 18.25v1.5M16.75 16.75h-1.5M22.25 16.75h-1.5"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span>Generate Instruction Manual{selectionCount > 0 ? ` (${selectionCount})` : ""}</span>
            </>
          )}
        </button>
      </div>
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
    fetchDocHistory()
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
  const pendingDeleteDoc = useMemo(
    () => docs.find((doc) => doc.id === confirmDeleteId),
    [confirmDeleteId, docs]
  );

  const handleDeleteDoc = async (doc) => {
    if (!doc.id || deletingId) return;
    setDeletingId(doc.id);
    setConfirmDeleteId(null);
    setError(null);
    try {
      await deleteDocHistoryItem(doc.id);
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
      <p className="im-subtitle">
        Semua instruction manual yang pernah dibuat, diambil langsung dari folder history di
        Google Drive.
      </p>

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
            <span>Buka folder Google Drive</span>
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
          <path
            d="M10.75 18.5a7.75 7.75 0 1 1 0-15.5 7.75 7.75 0 0 1 0 15.5ZM16.5 16.5 21 21"
            stroke="currentColor"
            strokeWidth="1.9"
            strokeLinecap="round"
          />
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
          <span className="doc-history-header-label doc-history-header-date">Tanggal Generate</span>
          <span className="doc-history-header-label doc-history-header-actions">Aksi</span>
        </div>
      )}

      {!loading && (
        <div className="doc-history-list">
          {docs.length === 0 && (
            <div className="im-empty-state">
              <span>Belum ada instruction manual yang dibuat.</span>
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
                    <path
                      d="M6.25 3.75h8l3.5 3.5v13H6.25V3.75Z"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinejoin="round"
                    />
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
                <CopyLinkButton
                  url={doc.url}
                  copied={copiedId === (doc.id || doc.url)}
                  onCopy={() => handleCopyLink(doc)}
                />
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

export default function InstructionManualPage({ onToggleSidebar }) {
  const [tab, setTab] = useState("generate");
  const [resetKey, setResetKey] = useState(0);

  return (
    <div className="gallery-panel im-panel">
      <BackgroundMain />
      <Header
        title="Instruction Manual"
        showMenuButton
        onMenuToggle={onToggleSidebar}
        showBreadcrumbBar={false}
      />

      <div className="im-panel-content">
        <div className="im-content-body">
          <div className="page-tabs-row">
            <div className="page-tabs">
              <button
                className={"page-tab" + (tab === "generate" ? " active" : "")}
                onClick={() => setTab("generate")}
              >
                Generate
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

          {tab === "generate" ? (
            <GenerateTab key={`generate-${resetKey}`} />
          ) : (
            <HistoryTab key={`history-${resetKey}`} />
          )}
        </div>
      </div>
    </div>
  );
}
