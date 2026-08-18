import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { IconButton } from "@mui/material";
import {
  RestartAltRounded as RestartAltRoundedIcon,
  SwapHorizRounded as SwapHorizRoundedIcon,
  ChevronLeftRounded as ChevronLeftRoundedIcon,
  ChevronRightRounded as ChevronRightRoundedIcon,
} from "@mui/icons-material";
import Header from "../piagam/template/Header.jsx";
import BackgroundMain from "../piagam/template/BackgroundMain.jsx";
import {
  API_BASE,
  deleteGalleryHistoryItem,
  fetchGalleryHistory,
  fetchGalleryStatus,
  fetchProducts,
  generateGalleryCard,
  refineGalleryCard,
  refreshGalleryPhotoFromSheet,
  removeGalleryCardFrame,
  uploadGalleryPhoto,
} from "../api";

const FRAMING_OPTIONS = [
  { value: "gosave", label: "GOSAVE", image: "/assets/Framing GOSAVE.png" },
  { value: "goto", label: "GOTO", image: "/assets/Framing GOTO.png" },
];

const GALLERY_BRANDS = [
  { key: "gosave", label: "GOSAVE", match: "gosave" },
  { key: "goto", label: "GOTO", match: "goto" },
  { key: "safety_bro", label: "SAFETY BRO", match: "gosave" },
  { key: "ladder_bro", label: "LADDER BRO", match: "gosave" },
];

const PALETTE_OPTIONS = [
  { value: "navy_yellow", label: "Navy & Kuning", primary: "#1a2a57", accent: "#ffc861" },
  { value: "red_white", label: "Merah & Putih", primary: "#b91c1c", accent: "#ffffff" },
  { value: "forest_cream", label: "Hijau & Krem", primary: "#14532d", accent: "#f5e6c8" },
  { value: "purple_gold", label: "Ungu & Emas", primary: "#4c1d95", accent: "#ffc800" },
  { value: "charcoal_orange", label: "Charcoal & Oranye", primary: "#1f2937", accent: "#ff7a1a" },
  { value: "custom", label: "Custom" },
];

const pagerButtonSx = {
  width: 32,
  height: 32,
  borderRadius: "10px",
  border: "1px solid rgba(42, 157, 143, 0.24)",
  color: "var(--pg-teal-dark)",
  background: "rgba(42, 157, 143, 0.1)",
  boxShadow: "none",
  transition: "background 0.16s ease, transform 0.16s ease, box-shadow 0.16s ease, border-color 0.16s ease",
  "&:hover": {
    borderColor: "var(--pg-teal)",
    background: "linear-gradient(135deg, var(--pg-teal) 0%, var(--pg-teal-dark) 100%)",
    color: "#ffffff",
    transform: "translateY(-1px) scale(1.06)",
    boxShadow: "0 8px 16px rgba(42, 157, 143, 0.28)",
  },
  "&:active": {
    transform: "translateY(0) scale(0.96)",
  },
  "&.Mui-disabled": {
    opacity: 0.38,
    color: "var(--pg-text-faint)",
    background: "var(--pg-soft)",
    borderColor: "var(--pg-border)",
    boxShadow: "none",
  },
};

function formatDate(value) {
  if (!value) return "";
  return new Date(value).toLocaleDateString("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

const BRAND_INITIALS = [
  { match: "goto", label: "GT" },
  { match: "gosave", label: "GS" },
];

function getProductInitials(name) {
  const lower = name?.trim().toLowerCase() || "";
  const brand = BRAND_INITIALS.find(({ match }) => lower.includes(match));
  if (brand) return brand.label;
  return name?.trim().slice(0, 2).toUpperCase() || "?";
}

function ToggleOption({ checked, onToggle, disabled, label, inline = false, variant = "checkbox" }) {
  if (variant === "switch") {
    return (
      <button
        type="button"
        className={"gallery-toggle-switch-option" + (checked ? " active" : "")}
        onClick={onToggle}
        disabled={disabled}
        role="switch"
        aria-checked={checked}
      >
        <span className="gallery-toggle-switch" aria-hidden="true">
          <span className="gallery-toggle-switch-knob" />
        </span>
        <span>{label}</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      className={
        (inline ? "gallery-inline-toggle" : "manual-section-option") + (checked ? " active" : "")
      }
      onClick={onToggle}
      disabled={disabled}
    >
      <span className={"product-checkbox" + (checked ? " checked" : "")}>
        {checked && (
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" aria-hidden="true">
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
}

function FramingPicker({ selected, onSelect }) {
  return (
    <>
      <p className="im-subtitle">
        Pilih frame yang mau dipakai buat gambar galeri. Pilihan ini dipakai buat semua kartu
        yang di-generate nanti — bisa diganti lagi belakangan.
      </p>
      <span className="im-panel-eyebrow gallery-framing-eyebrow">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
          <rect x="3.75" y="3.75" width="16.5" height="16.5" rx="3" stroke="currentColor" strokeWidth="1.8" />
          <path d="M8.25 15.25 11 12l2 2.25 3-3.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Pilih Frame
      </span>
      <div className="gallery-framing-options gallery-framing-options-wide">
        {FRAMING_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            className={`gallery-framing-option${selected === option.value ? " gallery-framing-option-selected" : ""}`}
            onClick={() => onSelect(option.value)}
            aria-pressed={selected === option.value}
            title={option.label}
          >
            <span className="gallery-framing-option-thumb">
              <img src={option.image} alt={option.label} />
              {selected === option.value && (
                <span className="gallery-framing-option-check" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="13" height="13" fill="none">
                    <path
                      d="M5 12.5 9.5 17 19 7"
                      stroke="currentColor"
                      strokeWidth="3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
              )}
            </span>
            <span className="gallery-framing-option-footer">
              <span className="gallery-framing-option-label">{option.label}</span>
              <span className="gallery-framing-option-tag">
                {selected === option.value ? "Terpilih" : "Pilih"}
              </span>
            </span>
          </button>
        ))}
      </div>
    </>
  );
}

function ProductPicker({ selected, onSelect, framing }) {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  // Products that already have at least one generated card — these are the
  // ones this page is really for (revising/fixing an existing result), so
  // they get a badge and float to the top of the list.
  const [productsWithResults, setProductsWithResults] = useState(new Set());

  useEffect(() => {
    fetchProducts()
      .then((data) => setProducts(data.products || []))
      .catch((err) => setError(err.message || "Failed to load products"))
      .finally(() => setLoading(false));
    fetchGalleryHistory()
      .then((data) => {
        const names = new Set((data.items || []).map((item) => item.product_name));
        setProductsWithResults(names);
      })
      .catch(() => {});
  }, []);

  const selectedBrand = GALLERY_BRANDS.find((option) => option.key === framing);

  const filtered = useMemo(() => {
    const brandTerm = selectedBrand?.match || "";
    const byBrand = brandTerm
      ? products.filter(
          (p) =>
            p.product_name?.toLowerCase().includes(brandTerm) ||
            p.vendor_name?.toLowerCase().includes(brandTerm)
        )
      : products;

    const term = search.trim().toLowerCase();
    const bySearch = !term
      ? byBrand
      : byBrand.filter(
          (p) =>
            p.product_name?.toLowerCase().includes(term) ||
            p.vendor_name?.toLowerCase().includes(term)
        );

    // Products with an existing result first — this page is for revising
    // those, so they shouldn't get buried under everything else.
    return [...bySearch].sort((a, b) => {
      const aHas = productsWithResults.has(a.product_name) ? 1 : 0;
      const bHas = productsWithResults.has(b.product_name) ? 1 : 0;
      return bHas - aHas;
    });
  }, [products, search, selectedBrand, productsWithResults]);

  return (
    <>
      <p className="im-subtitle">
        Pilih produk yang mau direvisi — ganti foto, ubah tampilan, atau regenerate ulang kartu
        tertentu dari hasil yang sudah pernah dibuat (lewat Automasi atau di sini sebelumnya).
        Produk yang sudah punya hasil ditandai dan ditaruh di atas. Produk otomatis difilter
        sesuai brand {selectedBrand ? <strong>{selectedBrand.label}</strong> : ""} dari frame yang
        dipilih.
      </p>

      <div className="im-search-box">
        <svg className="im-search-icon" viewBox="0 0 24 24" width="17" height="17" fill="none" aria-hidden="true">
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
          disabled={loading}
        />
      </div>

      {loading && (
        <div className="im-empty-state">
          <span className="button-spinner" />
          <span>Memuat daftar produk...</span>
        </div>
      )}
      {error && <div className="error-banner">{error}</div>}

      {!loading && !error && (
        <div className="product-list image-product-list">
          {filtered.length === 0 && (
            <div className="im-empty-state">
              <span>Tidak ada produk yang cocok.</span>
            </div>
          )}
          {filtered.map((product) => {
            const isChecked = selected === product.product_name;
            return (
              <button
                key={product.product_name}
                className={"product-list-item" + (isChecked ? " active" : "")}
                onClick={() => onSelect(product.product_name)}
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
                {productsWithResults.has(product.product_name) && (
                  <span className="im-has-result-badge">Sudah ada hasil</span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </>
  );
}

function ImageHistory({ onSelectProduct }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [previewItem, setPreviewItem] = useState(null);
  const [deletingKey, setDeletingKey] = useState(null);
  const [removingFrameKey, setRemovingFrameKey] = useState(null);
  const [openGroupName, setOpenGroupName] = useState(null);
  const [search, setSearch] = useState("");
  const groupedItems = useMemo(() => {
    const groups = [];
    const indexByProduct = new Map();
    for (const item of items) {
      const key = item.product_name;
      if (!indexByProduct.has(key)) {
        indexByProduct.set(key, groups.length);
        groups.push({
          productName: item.product_name,
          vendorName: item.vendor_name,
          items: [],
        });
      }
      groups[indexByProduct.get(key)].items.push(item);
    }
    return groups;
  }, [items]);
  const filteredGroups = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return groupedItems;
    return groupedItems.filter((group) => group.productName.toLowerCase().includes(term));
  }, [groupedItems, search]);
  const openGroup = groupedItems.find((group) => group.productName === openGroupName);

  const load = () => {
    setLoading(true);
    setError(null);
    fetchGalleryHistory()
      .then((data) => setItems(data.items || []))
      .catch((err) => setError(err.message || "Failed to load image history"))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleDelete = async (item) => {
    if (!window.confirm("Hapus image ini dari history?")) return;
    const key = `${item.product_name}-${item.url}`;
    setDeletingKey(key);
    setError(null);
    try {
      await deleteGalleryHistoryItem(item.product_name, item.url);
      setItems((current) => current.filter((historyItem) => historyItem.url !== item.url));
      setPreviewItem((current) => (current?.url === item.url ? null : current));
    } catch (err) {
      setError(err.message || "Failed to delete image history");
    } finally {
      setDeletingKey(null);
    }
  };

  const handleRemoveFrame = async (item) => {
    const key = `${item.product_name}-${item.url}`;
    setRemovingFrameKey(key);
    setError(null);
    try {
      const result = await removeGalleryCardFrame(item.product_name, item.url);
      const newItem = { ...item, url: result.url, generated_at: new Date().toISOString() };
      setItems((current) => [newItem, ...current]);
      setPreviewItem(newItem);
    } catch (err) {
      setError(err.message || "Gagal menghapus frame");
    } finally {
      setRemovingFrameKey(null);
    }
  };

  return (
    <div className="image-history-panel">
      <div className="history-toolbar">
        <p className="im-subtitle image-history-subtitle">
          Riwayat gambar keypoint card yang pernah dibuat.
        </p>
        <button className="history-refresh-btn" onClick={load} disabled={loading}>
          Refresh
        </button>
      </div>

      {!openGroup && (
        <div className="im-search-box image-history-search-box">
          <svg className="im-search-icon" viewBox="0 0 24 24" width="17" height="17" fill="none" aria-hidden="true">
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
            placeholder="Cari nama produk..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            disabled={loading}
          />
        </div>
      )}

      {loading && (
        <div className="im-empty-state">
          <span className="button-spinner" />
          <span>Memuat history image...</span>
        </div>
      )}
      {error && <div className="error-banner">{error}</div>}

      {!loading && !error && items.length === 0 && (
        <div className="gallery-photo-empty image-history-empty">
          Belum ada image history. Pilih produk lalu generate gambar dulu.
        </div>
      )}

      {!loading && !error && items.length > 0 && filteredGroups.length === 0 && !openGroup && (
        <div className="gallery-photo-empty image-history-empty">
          Produk tidak ditemukan.
        </div>
      )}

      {!loading && !error && filteredGroups.length > 0 && (
        openGroup ? (
          <div className="image-history-folder-view">
            <button className="gallery-back-btn" onClick={() => setOpenGroupName(null)}>
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true">
                <path
                  d="M15 5 8 12l7 7"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span>Kembali ke folder</span>
            </button>
            <div className="image-history-folder-header">
              <div className="image-history-group-title">
                <span>{openGroup.productName}</span>
                {openGroup.vendorName && <small>{openGroup.vendorName}</small>}
              </div>
              <span className="image-history-count">{openGroup.items.length} image</span>
            </div>
            <div className="image-history-grid">
              {openGroup.items.map((item) => (
                <div key={`${item.product_name}-${item.url}`} className="image-history-card-wrap">
                  <button
                    type="button"
                    className="image-history-card"
                    onClick={() => setPreviewItem(item)}
                    title={item.product_name}
                  >
                    <img src={`${API_BASE}${item.url}`} alt={item.product_name} />
                    <span className="image-history-meta">
                      <span className="image-history-date">{formatDate(item.generated_at)}</span>
                    </span>
                  </button>
                  <button
                    type="button"
                    className="image-history-frame-btn"
                    onClick={() => handleRemoveFrame(item)}
                    disabled={removingFrameKey === `${item.product_name}-${item.url}`}
                    title="Hapus frame (pakai AI)"
                    aria-label="Hapus frame (pakai AI)"
                  >
                    {removingFrameKey === `${item.product_name}-${item.url}` ? (
                      <span className="button-spinner" />
                    ) : (
                      <svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true">
                        <path
                          d="M4 4h16v16H4z M4 4l16 16"
                          stroke="currentColor"
                          strokeWidth="1.7"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    )}
                  </button>
                  <button
                    type="button"
                    className="image-history-delete-btn"
                    onClick={() => handleDelete(item)}
                    disabled={deletingKey === `${item.product_name}-${item.url}`}
                    title="Hapus history"
                    aria-label="Hapus history"
                  >
                    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true">
                      <path
                        d="M3 6h18M8 6V4.5C8 3.67 8.67 3 9.5 3h5c.83 0 1.5.67 1.5 1.5V6m2 0-.7 13.25c-.05.98-.86 1.75-1.84 1.75H8.54c-.98 0-1.79-.77-1.84-1.75L6 6m4 5v6m4-6v6"
                        stroke="currentColor"
                        strokeWidth="1.7"
                        strokeLinecap="round"
                      />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="image-folder-grid">
            {filteredGroups.map((group) => (
              <button
                key={group.productName}
                type="button"
                className="image-folder-card"
                onClick={() => setOpenGroupName(group.productName)}
                title={group.productName}
              >
                <span className="image-folder-cover">
                  <img src={`${API_BASE}${group.items[0].url}`} alt="" />
                </span>
                <span className="image-folder-meta">
                  <span className="image-folder-name">{group.productName}</span>
                  {group.vendorName && <span className="image-folder-vendor">{group.vendorName}</span>}
                  <span className="image-folder-count">{group.items.length} image</span>
                </span>
              </button>
            ))}
          </div>
        )
      )}

      {previewItem &&
        createPortal(
          <div className="image-preview-overlay" onClick={() => setPreviewItem(null)}>
            <div className="image-preview-box" onClick={(event) => event.stopPropagation()}>
              <div className="image-preview-header">
                <div className="image-preview-title">
                  <span className="modal-header-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
                      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" stroke="currentColor" strokeWidth="1.7" />
                      <circle cx="8.5" cy="9.5" r="1.5" stroke="currentColor" strokeWidth="1.7" />
                      <path d="m5 17 4.5-4.5a1.5 1.5 0 0 1 2.12 0L15 15.87M14.5 14 16.4 12.1a1.5 1.5 0 0 1 2.12 0L21 14.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </span>
                  <span className="image-preview-title-text">
                    <span>{previewItem.product_name}</span>
                    <small>{formatDate(previewItem.generated_at)}</small>
                  </span>
                </div>
                <button
                  className="modal-close-btn"
                  onClick={() => setPreviewItem(null)}
                  title="Close preview"
                  aria-label="Close preview"
                >
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
                    <path
                      d="M6.75 6.75 17.25 17.25M17.25 6.75 6.75 17.25"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                    />
                  </svg>
                </button>
              </div>
              <img
                className="image-preview-large"
                src={`${API_BASE}${previewItem.url}`}
                alt={previewItem.product_name}
              />
              <div className="modal-actions image-preview-actions">
                <a
                  className="modal-cancel-btn gallery-download-link"
                  href={`${API_BASE}${previewItem.url}`}
                  download
                >
                  Download
                </a>
                <button
                  type="button"
                  className="modal-generate-btn"
                  onClick={() => onSelectProduct(previewItem.product_name)}
                >
                  Buka produk
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
}

const CARD_TYPE_OPTIONS = [
  { key: "keypoint", label: "Keypoint card" },
  { key: "spec", label: "Spesifikasi" },
  { key: "usage", label: "Cara penggunaan" },
  { key: "keunggulan", label: "Fitur Keunggulan" },
];

const CARD_TYPE_LABELS = Object.fromEntries(
  CARD_TYPE_OPTIONS.filter((option) => option.key !== "keunggulan").map((option) => [
    option.key,
    option.label,
  ])
);

const KEUNGGULAN_LABEL = CARD_TYPE_OPTIONS.find((option) => option.key === "keunggulan").label;

function GalleryWorkspace({ productName, framing, onChangeFraming, onBack, onOpenHistory }) {
  const [status, setStatus] = useState(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [refreshingPhoto, setRefreshingPhoto] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [withModel, setWithModel] = useState(false);
  const [useAiScene, setUseAiScene] = useState(true);
  const [cardTypes, setCardTypes] = useState({ keypoint: true, spec: true, usage: true, keunggulan: true });
  const [keunggulanCount, setKeunggulanCount] = useState(3);
  const [palette, setPalette] = useState("navy_yellow");
  const selectedFraming = FRAMING_OPTIONS.find((option) => option.value === framing);
  const [customPrimary, setCustomPrimary] = useState("#1e3a8a");
  const [customAccent, setCustomAccent] = useState("#ffd500");
  const [useCustomScene, setUseCustomScene] = useState(false);
  const [customScene, setCustomScene] = useState("");
  const [useCustomPosition, setUseCustomPosition] = useState(false);
  const [customPosition, setCustomPosition] = useState("");
  const [useCustomPrompt, setUseCustomPrompt] = useState(false);
  const [customPrompt, setCustomPrompt] = useState("");
  const [useManualSpec, setUseManualSpec] = useState(false);
  const [specManualText, setSpecManualText] = useState("");
  const [useManualKeypoints, setUseManualKeypoints] = useState(false);
  const [keypointManualText, setKeypointManualText] = useState("");
  const [showAdvancedModal, setShowAdvancedModal] = useState(false);
  const [previewCard, setPreviewCard] = useState(null);
  const [toast, setToast] = useState(null);
  const [removingFrameKey, setRemovingFrameKey] = useState(null);
  const [refiningKey, setRefiningKey] = useState(null);
  // Which result card's revise-via-prompt box is open — holds the card's
  // key, or null when closed.
  const [refineCard, setRefineCard] = useState(null);
  const [refineInstruction, setRefineInstruction] = useState("");
  // Card types from the generate that just finished — non-null shows the
  // "hapus frame?" confirmation modal; null keeps it hidden.
  const [framePromptTypes, setFramePromptTypes] = useState(null);
  const fileInputRef = useRef(null);
  const anyCardTypeSelected = cardTypes.keypoint || cardTypes.spec || cardTypes.usage || cardTypes.keunggulan;
  const keunggulanHistory = (status?.card_history || []).filter((item) => item.card_type === "keunggulan");
  const keunggulanCards = keunggulanHistory.slice(0, keunggulanCount);
  const selectedPalette = PALETTE_OPTIONS.find((option) => option.value === palette) || PALETTE_OPTIONS[0];
  const palettePreviewPrimary = selectedPalette.value === "custom" ? customPrimary : selectedPalette.primary;
  const palettePreviewAccent = selectedPalette.value === "custom" ? customAccent : selectedPalette.accent;
  const [resultPage, setResultPage] = useState(0);
  const RESULT_PAGE_SIZE = 3;

  const allResultCards = useMemo(() => {
    if (!status) return [];
    // Every card here is just the latest saved file for its type/slot,
    // whichever page (Automasi or this one) generated it last — so a
    // timestamp is included to make that plain instead of leaving it
    // ambiguous whether what's shown is fresh or from an earlier run.
    const generatedAtByUrl = new Map(
      (status.card_history || []).map((item) => [item.url, item.generated_at])
    );
    const list = Object.entries(CARD_TYPE_LABELS).map(([type, label]) => {
      const url = status.cards[type]?.card_url || null;
      return { key: type, label, url, generatedAt: url ? generatedAtByUrl.get(url) : null };
    });
    if (cardTypes.keunggulan) {
      for (let i = 0; i < keunggulanCount; i += 1) {
        const url = keunggulanCards[i]?.url || null;
        list.push({
          key: `keunggulan-${i}`,
          label: `${KEUNGGULAN_LABEL} ${i + 1}`,
          url,
          generatedAt: keunggulanCards[i]?.generated_at || null,
        });
      }
    }
    return list;
  }, [status, cardTypes.keunggulan, keunggulanCount, keunggulanCards]);

  const resultTotalPages = Math.max(1, Math.ceil(allResultCards.length / RESULT_PAGE_SIZE));
  const clampedResultPage = Math.min(resultPage, resultTotalPages - 1);
  const visibleResultCards = allResultCards.slice(
    clampedResultPage * RESULT_PAGE_SIZE,
    clampedResultPage * RESULT_PAGE_SIZE + RESULT_PAGE_SIZE
  );

  const loadStatus = () => {
    setLoadingStatus(true);
    setError(null);
    fetchGalleryStatus(productName)
      .then(setStatus)
      .catch((err) => setError(err.message || "Failed to load status"))
      .finally(() => setLoadingStatus(false));
  };

  useEffect(loadStatus, [productName]);
  useEffect(() => setResultPage(0), [productName]);
  useEffect(() => {
    if (!toast) return undefined;
    const timeoutId = window.setTimeout(() => setToast(null), 4200);
    return () => window.clearTimeout(timeoutId);
  }, [toast]);

  const handleFileChange = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await uploadGalleryPhoto(productName, file);
      loadStatus();
    } catch (err) {
      setError(err.message || "Gagal upload foto");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  };

  const handleRefreshPhotoFromSheet = async () => {
    setRefreshingPhoto(true);
    setError(null);
    try {
      await refreshGalleryPhotoFromSheet(productName);
      loadStatus();
    } catch (err) {
      setError(err.message || "Gagal menarik foto dari sheet");
    } finally {
      setRefreshingPhoto(false);
    }
  };

  const toggleManualSpec = () => {
    setUseManualSpec((v) => !v);
  };

  const toggleManualKeypoints = () => {
    setUseManualKeypoints((v) => !v);
  };

  const handleKeypointManualChange = (event) => {
    // Cap to 3 non-empty lines — matches the fixed 3 badge slots on the
    // card, so what's in the box is exactly what ends up on it.
    const lines = event.target.value.split("\n");
    const nonEmptyCount = lines.filter((line) => line.trim()).length;
    if (nonEmptyCount > 3) return;
    setKeypointManualText(event.target.value);
  };

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    try {
      const positionInstruction =
        useCustomPosition && customPosition.trim()
          ? `Posisi produk: ${customPosition.trim()}.`
          : "";
      const combinedPrompt = [positionInstruction, useCustomPrompt ? customPrompt.trim() : ""]
        .filter(Boolean)
        .join(" ");
      await generateGalleryCard(productName, {
        aiScene: useAiScene,
        withModel: useAiScene ? withModel : false,
        palette,
        framing,
        customPrimary: palette === "custom" ? customPrimary : "",
        customAccent: palette === "custom" ? customAccent : "",
        customScene: useCustomScene ? customScene : "",
        specManual: useManualSpec,
        specManualText: useManualSpec ? specManualText : "",
        keypointManual: useManualKeypoints,
        keypointManualText: useManualKeypoints ? keypointManualText : "",
        customPrompt: combinedPrompt,
        aiFullDesign: true,
        usageFullDesign: true,
        specFullDesign: true,
        keunggulanCount,
        ...cardTypes,
      });
      // The generate call above already succeeded at this point — the
      // success toast and the "hapus frame?" prompt below must not depend
      // on anything after it, or a hiccup in that follow-up work would
      // wrongly report the whole generate as failed even though the cards
      // are already saved. loadStatus() refreshes the visible result grid;
      // handleRemoveFrameForGenerated fetches its own fresh URLs lazily,
      // only if/when the modal is actually confirmed.
      const generatedTypes = Object.entries(cardTypes)
        .filter(([, enabled]) => enabled)
        .map(([type]) => type);
      setToast({
        type: "success",
        title: "Generate berhasil",
        message: "Gambar sudah dibuat dan tampil di hasil generate.",
      });
      loadStatus();
      setFramePromptTypes(generatedTypes);
    } catch (err) {
      const message = err.message || "Gagal generate gambar galeri";
      setToast({
        type: "error",
        title: "Generate gagal",
        message,
      });
    } finally {
      setGenerating(false);
    }
  };

  const handleRemoveFrameForGenerated = async (types) => {
    setFramePromptTypes(null);
    setRemovingFrameKey("__batch__");
    try {
      const freshStatus = await fetchGalleryStatus(productName);
      for (const type of types) {
        if (type === "keunggulan") {
          const items = (freshStatus.card_history || [])
            .filter((entry) => entry.card_type === "keunggulan")
            .slice(0, keunggulanCount);
          for (const item of items) {
            // Sequential on purpose — each call is itself a full AI image
            // edit, so firing all of them at once would just queue up the
            // same rate limit/latency behind the scenes.
            await removeGalleryCardFrame(productName, item.url);
          }
        } else {
          const url = freshStatus.cards[type]?.card_url;
          if (url) await removeGalleryCardFrame(productName, url);
        }
      }
      setToast({
        type: "success",
        title: "Frame dihapus",
        message: "Versi tanpa frame sudah dibuat dan tampil di hasil generate.",
      });
      loadStatus();
    } catch (err) {
      const message = err.message || "Gagal menghapus frame";
      setToast({ type: "error", title: "Hapus frame gagal", message });
      loadStatus();
    } finally {
      setRemovingFrameKey(null);
    }
  };

  const handleRemoveFrame = async (card) => {
    if (!card.url) return;
    setRemovingFrameKey(card.key);
    try {
      await removeGalleryCardFrame(productName, card.url);
      setToast({
        type: "success",
        title: "Frame dihapus",
        message: "Versi tanpa frame sudah dibuat dan tampil di hasil generate.",
      });
      loadStatus();
    } catch (err) {
      const message = err.message || "Gagal menghapus frame";
      setToast({ type: "error", title: "Hapus frame gagal", message });
    } finally {
      setRemovingFrameKey(null);
    }
  };

  const openRefine = (card) => {
    setRefineInstruction("");
    setRefineCard(card.key);
  };

  const closeRefine = () => {
    setRefineCard(null);
    setRefineInstruction("");
  };

  const handleRefineCard = async (card) => {
    if (!card.url) return;
    setRefiningKey(card.key);
    try {
      await refineGalleryCard(productName, card.url, refineInstruction);
      setToast({
        type: "success",
        title: "Kartu diperbaiki",
        message: "Versi baru sudah dibuat dan tampil di hasil generate.",
      });
      closeRefine();
      loadStatus();
    } catch (err) {
      const message = err.message || "Gagal memperbaiki kartu";
      setToast({ type: "error", title: "Perbaiki gagal", message });
    } finally {
      setRefiningKey(null);
    }
  };

  const toggleCardType = (type) => {
    setCardTypes((current) => ({ ...current, [type]: !current[type] }));
  };

  return (
    <>
      <div className="gallery-workspace-hero">
        <div className="gallery-workspace-product-summary">
          <span className="im-product-avatar gallery-workspace-product-avatar" aria-hidden="true">
            {getProductInitials(productName)}
          </span>
          <span className="gallery-workspace-product-copy">
            <span className="gallery-workspace-product-eyebrow">Produk dipilih</span>
            <span className="gallery-product-name">{productName}</span>
          </span>
        </div>

        <div className="gallery-workspace-actions">
          <button type="button" className="gallery-framing-change-btn" onClick={onChangeFraming}>
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
              <path
                d="M4 12a8 8 0 0 1 13.66-5.66M20 12a8 8 0 0 1-13.66 5.66M17 4v4h-4M7 20v-4h4"
                stroke="currentColor"
                strokeWidth="1.9"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span>{selectedFraming ? `Ganti frame: ${selectedFraming.label}` : "Ganti frame"}</span>
          </button>

          <button className="gallery-back-btn gallery-product-back-btn" onClick={onBack}>
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true">
              <path
                d="M15 5 8 12l7 7"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span>Pilih produk lain</span>
          </button>
        </div>
      </div>

      {loadingStatus && (
        <div className="im-empty-state">
          <span className="button-spinner" />
          <span>Memuat status...</span>
        </div>
      )}
      {error && <div className="error-banner">{error}</div>}

      {!loadingStatus && status && (
        <div className="gallery-workspace piagam-generate-workspace">
          <div className="gallery-workspace-left piagam-generate-left">
            <div className="gallery-workspace-left-row">
              <div className="gallery-photo-wrap">
                <div className="gallery-photo-section piagam-generate-panel piagam-photo-panel">
                  <div className="gallery-section-label gallery-photo-title">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
                      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" stroke="currentColor" strokeWidth="1.7" />
                      <circle cx="8.5" cy="9.5" r="1.5" stroke="currentColor" strokeWidth="1.7" />
                      <path d="m5 17 4.5-4.5a1.5 1.5 0 0 1 2.12 0L15 15.87M14.5 14 16.4 12.1a1.5 1.5 0 0 1 2.12 0L21 14.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    <span className="gallery-photo-title-text">Referensi produk</span>
                    {status.photo_source === "sheet" && (
                      <span className="gallery-source-badge">dari sheet</span>
                    )}
                    {status.photo_source === "instruction_manual" && (
                      <span className="gallery-source-badge">otomatis</span>
                    )}
                    {status.photo_source === "uploaded" && (
                      <span className="gallery-source-badge gallery-source-badge-manual">
                        manual
                      </span>
                    )}
                  </div>
                  {status.photo_url ? (
                    <button
                      type="button"
                      className="gallery-photo-preview-frame"
                      onClick={() => setPreviewCard({ label: "Foto produk", url: status.photo_url })}
                      title="Preview foto produk"
                      style={{ backgroundImage: `url(${API_BASE}${status.photo_url}?t=${Date.now()})` }}
                    >
                      <img
                        className="gallery-photo-preview"
                        src={`${API_BASE}${status.photo_url}?t=${Date.now()}`}
                        alt={productName}
                      />
                    </button>
                  ) : (
                    <div className="gallery-photo-empty">
                      Belum ada foto
                    </div>
                  )}

                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    hidden
                    onChange={handleFileChange}
                  />
                  <div className="gallery-photo-actions">
                    <button
                      type="button"
                      className="modal-cancel-btn gallery-loading-btn gallery-upload-photo-btn"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={uploading}
                    >
                      {uploading ? (
                        <>
                          <span className="button-spinner" />
                          <span>...</span>
                        </>
                      ) : (
                        status.photo_url ? "Ganti foto" : "Upload foto"
                      )}
                    </button>
                    {status.has_sheet_photo_link && (
                      <button
                        type="button"
                        className="modal-cancel-btn gallery-loading-btn gallery-refresh-photo-btn"
                        onClick={handleRefreshPhotoFromSheet}
                        disabled={refreshingPhoto || uploading}
                        title="Tarik ulang foto terbaru dari link di sheet"
                      >
                        {refreshingPhoto ? (
                          <>
                            <span className="button-spinner" />
                            <span>...</span>
                          </>
                        ) : (
                          "Tarik dari sheet"
                        )}
                      </button>
                    )}
                  </div>
                </div>
              </div>

              <div className="gallery-card-types-container piagam-generate-panel piagam-output-panel">
                <div className="manual-options-header gallery-card-type-header">
                  <span className="im-panel-eyebrow gallery-card-type-heading">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
                      <path
                        d="M6.25 3.75h8l3.5 3.5v13H6.25V3.75Z"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinejoin="round"
                      />
                      <path d="M9 12h6M9 15.5h6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                    </svg>
                    Jenis output
                  </span>
                  <span className={"gallery-output-count" + (anyCardTypeSelected ? " has-selection" : "")}>
                    {Object.values(cardTypes).filter(Boolean).length} aktif
                  </span>
                </div>
                <div className="gallery-card-type-options">
                  {CARD_TYPE_OPTIONS.map((option) => {
                    const isChecked = cardTypes[option.key];
                    return (
                      <button
                        key={option.key}
                        type="button"
                        className={"gallery-inline-toggle" + (isChecked ? " active" : "")}
                        onClick={() => toggleCardType(option.key)}
                        disabled={generating}
                      >
                        <span className={"product-checkbox" + (isChecked ? " checked" : "")}>
                          {isChecked && (
                            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" aria-hidden="true">
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
                        <span>{option.label}</span>
                      </button>
                    );
                  }
                  )}
                </div>

                {cardTypes.keunggulan && (
                  <div className="image-count-toggle">
                    <span className="image-count-label">
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
                        <path
                          d="m12 3.75 2.25 4.56 5.04.73-3.64 3.55.86 5.02L12 15.24l-4.51 2.37.86-5.02-3.64-3.55 5.04-.73L12 3.75Z"
                          stroke="currentColor"
                          strokeWidth="1.7"
                          strokeLinejoin="round"
                        />
                      </svg>
                      <span>Foto Keunggulan</span>
                    </span>
                    <div
                      className="brand-choice-options automation-keunggulan-count"
                      role="radiogroup"
                      aria-label="Jumlah gambar keunggulan"
                    >
                      {[1, 2, 3].map((count) => (
                        <button
                          key={count}
                          type="button"
                          role="radio"
                          aria-checked={keunggulanCount === count}
                          className={"brand-choice-option" + (keunggulanCount === count ? " active" : "")}
                          onClick={() => setKeunggulanCount(count)}
                          disabled={generating}
                        >
                          {count} foto
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="gallery-control-panel piagam-generate-panel piagam-theme-panel">
              <span className="im-panel-eyebrow gallery-control-eyebrow">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
                  <path
                    d="M12 3.5c-4.7 0-8.5 3.8-8.5 8.5 0 3.6 2.9 6.5 6.5 6.5.9 0 1.6-.72 1.6-1.6 0-.4-.16-.77-.4-1.06-.24-.3-.4-.66-.4-1.04 0-.9.72-1.6 1.6-1.6h1.9c2.9 0 5.2-2.3 5.2-5.2 0-2.9-3.6-4.55-7.5-4.55Z"
                    stroke="currentColor"
                    strokeWidth="1.7"
                    strokeLinejoin="round"
                  />
                  <circle cx="7.6" cy="10.6" r="1.05" fill="currentColor" />
                  <circle cx="10.4" cy="7.4" r="1.05" fill="currentColor" />
                  <circle cx="14.3" cy="7.6" r="1.05" fill="currentColor" />
                  <circle cx="16.6" cy="10.8" r="1.05" fill="currentColor" />
                </svg>
                Tampilan &amp; tema
              </span>
              <div className="gallery-control-grid piagam-theme-grid">
                <label className="gallery-control-field piagam-theme-field">
                  <span className="image-count-label">Warna tema</span>
                  <span className="gallery-palette-select-row">
                    <span className="gallery-palette-swatch-colors gallery-palette-select-preview" aria-hidden="true">
                      <span style={{ background: palettePreviewPrimary }} />
                      <span style={{ background: palettePreviewAccent }} />
                    </span>
                    <select
                      className="gallery-select gallery-palette-select"
                      value={palette}
                      onChange={(event) => setPalette(event.target.value)}
                      disabled={generating}
                    >
                      {PALETTE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </span>
                </label>

                <label className={"gallery-control-field piagam-theme-field gallery-scene-field" + (useCustomScene ? " is-active" : "")}>
                  <span className="image-count-label">Scene background</span>
                  <span className="gallery-scene-row">
                    <ToggleOption
                      variant="switch"
                      checked={useCustomScene}
                      onToggle={() => setUseCustomScene((v) => !v)}
                      disabled={generating}
                      label="Custom scene"
                    />
                    <input
                      type="text"
                      className="gallery-scene-input"
                      placeholder="mis. di kelas, di dapur..."
                      value={customScene}
                      onChange={(event) => setCustomScene(event.target.value)}
                      disabled={generating || !useCustomScene}
                    />
                  </span>
                </label>

                <label className={"gallery-control-field piagam-theme-field gallery-scene-field" + (useCustomPosition ? " is-active" : "")}>
                  <span className="image-count-label">Posisi produk</span>
                  <span className="gallery-scene-row">
                    <ToggleOption
                      variant="switch"
                      checked={useCustomPosition}
                      onToggle={() => setUseCustomPosition((v) => !v)}
                      disabled={generating}
                      label="Custom posisi"
                    />
                    <input
                      type="text"
                      className="gallery-scene-input"
                      placeholder="mis. geser kanan, perbesar..."
                      value={customPosition}
                      onChange={(event) => setCustomPosition(event.target.value)}
                      disabled={generating || !useCustomPosition}
                    />
                  </span>
                </label>
              </div>

              <div className={"gallery-manual-prompt-field piagam-theme-field" + (useCustomPrompt ? " is-active" : "")}>
                <span className="gallery-manual-prompt-row">
                  <ToggleOption
                    variant="switch"
                    checked={useCustomPrompt}
                    onToggle={() => setUseCustomPrompt((v) => !v)}
                    disabled={generating}
                    label="Prompt manual"
                  />
                  <input
                    type="text"
                    className="gallery-scene-input gallery-manual-prompt-input"
                    placeholder="Instruksi tambahan buat AI, mis. 'geser ke kanan'."
                    value={customPrompt}
                    onChange={(event) => setCustomPrompt(event.target.value)}
                    disabled={generating || !useCustomPrompt}
                  />
                </span>
              </div>

              {palette === "custom" && (
                <div className="gallery-custom-color-fields">
                  <label className="gallery-color-field">
                    <span>Warna utama</span>
                    <input
                      type="color"
                      value={customPrimary}
                      onChange={(event) => setCustomPrimary(event.target.value)}
                      disabled={generating}
                    />
                  </label>
                  <label className="gallery-color-field">
                    <span>Warna aksen</span>
                    <input
                      type="color"
                      value={customAccent}
                      onChange={(event) => setCustomAccent(event.target.value)}
                      disabled={generating}
                    />
                  </label>
                </div>
              )}

              <div className="gallery-advanced-launcher">
                <button
                  type="button"
                  className="gallery-advanced-open-btn"
                  onClick={() => setShowAdvancedModal(true)}
                  disabled={generating}
                >
                  <span className="im-panel-eyebrow">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
                      <path
                        d="M4 7h11M4 12h16M9 17h11"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                      />
                      <circle cx="15" cy="7" r="2" stroke="currentColor" strokeWidth="1.8" />
                      <circle cx="6" cy="17" r="2" stroke="currentColor" strokeWidth="1.8" />
                    </svg>
                    Pengaturan lanjutan
                  </span>
                  <span className="gallery-advanced-open-meta">
                    {useAiScene ? "AI scene" : "Foto asli"}
                    {withModel ? " + model" : ""}
                  </span>
                  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true">
                    <path
                      d="M9 5l7 7-7 7"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
              </div>

            </div>

          </div>

          <div className="gallery-workspace-right piagam-generate-right">
            <div className="gallery-results-panel piagam-generate-panel piagam-results-panel">
              <div className="gallery-result-topbar">
                <div className="gallery-section-label">
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
                    <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" stroke="currentColor" strokeWidth="1.7" />
                    <circle cx="8.5" cy="9.5" r="1.5" stroke="currentColor" strokeWidth="1.7" />
                    <path d="m5 17 4.5-4.5a1.5 1.5 0 0 1 2.12 0L15 15.87M14.5 14 16.4 12.1a1.5 1.5 0 0 1 2.12 0L21 14.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  Hasil generate
                </div>
              </div>
              <p className="im-subtitle gallery-result-subtitle">
                Hasil terakhir untuk produk ini. Ganti setting lalu generate ulang, atau klik ikon <strong>Perbaiki</strong> di kartu buat revisi langsung.
              </p>
              <div className="gallery-card-results">
                {visibleResultCards.map((card) => (
                  <div key={card.key} className="gallery-card-result">
                    <div className="gallery-card-result-title">
                      <span
                        className="gallery-card-result-label"
                        title={
                          card.generatedAt
                            ? `Digenerate ${new Date(card.generatedAt).toLocaleString("id-ID")}`
                            : undefined
                        }
                      >
                        {card.label}
                      </span>
                      {card.url && (
                        <button
                          type="button"
                          className="gallery-card-download-btn"
                          onClick={(event) => {
                            event.stopPropagation();
                            if (refineCard === card.key) {
                              closeRefine();
                            } else {
                              openRefine(card);
                            }
                          }}
                          disabled={refiningKey === card.key}
                          title="Perbaiki kartu (pakai AI, ketik instruksi bebas)"
                          aria-label="Perbaiki kartu (pakai AI, ketik instruksi bebas)"
                        >
                          {refiningKey === card.key ? (
                            <span className="button-spinner" />
                          ) : (
                            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" aria-hidden="true">
                              <path
                                d="M4 20l1.1-3.9a3 3 0 0 1 .78-1.32l9.3-9.3a1.9 1.9 0 0 1 2.69 0l1.65 1.65a1.9 1.9 0 0 1 0 2.69l-9.3 9.3a3 3 0 0 1-1.32.78L4 20Z"
                                stroke="currentColor"
                                strokeWidth="1.6"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                              />
                              <path d="M13 5.5 18.5 11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                            </svg>
                          )}
                        </button>
                      )}
                      {card.url && (
                        <button
                          type="button"
                          className="gallery-card-download-btn"
                          onClick={(event) => {
                            event.stopPropagation();
                            handleRemoveFrame(card);
                          }}
                          disabled={removingFrameKey === card.key}
                          title="Hapus frame (pakai AI)"
                          aria-label="Hapus frame (pakai AI)"
                        >
                          {removingFrameKey === card.key ? (
                            <span className="button-spinner" />
                          ) : (
                            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" aria-hidden="true">
                              <path
                                d="M4 4h16v16H4z M4 4l16 16"
                                stroke="currentColor"
                                strokeWidth="1.7"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                              />
                            </svg>
                          )}
                        </button>
                      )}
                      {card.url && (
                        <a
                          className="gallery-card-download-btn"
                          href={`${API_BASE}${card.url}`}
                          download
                          title="Download"
                          aria-label="Download"
                          onClick={(event) => event.stopPropagation()}
                        >
                          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" aria-hidden="true">
                            <path
                              d="M12 3v11m0 0 4-4m-4 4-4-4M5 19h14"
                              stroke="currentColor"
                              strokeWidth="1.9"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                          </svg>
                        </a>
                      )}
                    </div>
                    {refineCard === card.key && (
                      <div className="gallery-card-refine-box" onClick={(event) => event.stopPropagation()}>
                        <textarea
                          className="gallery-card-refine-textarea"
                          placeholder="Ketik perbaikan yang mau dilakukan, mis. 'geser produk ke tengah', 'ganti warna aksen jadi biru', 'perbaiki tulisan spec'. Tetap ikut format template — kosongkan untuk perbaikan umum otomatis."
                          value={refineInstruction}
                          onChange={(event) => setRefineInstruction(event.target.value)}
                          rows={2}
                          disabled={refiningKey === card.key}
                          autoFocus
                        />
                        <div className="gallery-card-refine-actions">
                          <button
                            type="button"
                            className="modal-cancel-btn gallery-card-refine-cancel"
                            onClick={closeRefine}
                            disabled={refiningKey === card.key}
                          >
                            Batal
                          </button>
                          <button
                            type="button"
                            className="modal-generate-btn gallery-card-refine-submit"
                            onClick={() => handleRefineCard(card)}
                            disabled={refiningKey === card.key}
                          >
                            {refiningKey === card.key ? (
                              <>
                                <span className="button-spinner button-spinner-invert" />
                                <span>Memperbaiki...</span>
                              </>
                            ) : (
                              <span>Perbaiki</span>
                            )}
                          </button>
                        </div>
                      </div>
                    )}
                    {card.url ? (
                      <button
                        type="button"
                        className="gallery-card-preview-link"
                        onClick={() =>
                          setPreviewCard({ label: card.label, url: card.url, generatedAt: card.generatedAt })
                        }
                        title={`Preview ${card.label}`}
                      >
                        <img
                          className="gallery-card-preview"
                          src={`${API_BASE}${card.url}?t=${Date.now()}`}
                          alt={`${productName} ${card.label}`}
                        />
                      </button>
                    ) : (
                      <div className="gallery-card-empty">Belum ada preview</div>
                    )}
                  </div>
                ))}
              </div>

              <div className="gallery-results-pager">
                <IconButton
                  size="small"
                  onClick={() => setResultPage((p) => Math.max(0, p - 1))}
                  disabled={clampedResultPage === 0}
                  aria-label="Hasil sebelumnya"
                  sx={pagerButtonSx}
                >
                  <ChevronLeftRoundedIcon fontSize="small" />
                </IconButton>

                <span className="gallery-results-pager-count">
                  <strong>{clampedResultPage + 1}</strong>
                  <span className="gallery-results-pager-count-sep">/</span>
                  <span>{resultTotalPages}</span>
                </span>

                <IconButton
                  size="small"
                  onClick={() => setResultPage((p) => Math.min(resultTotalPages - 1, p + 1))}
                  disabled={clampedResultPage === resultTotalPages - 1}
                  aria-label="Hasil berikutnya"
                  sx={pagerButtonSx}
                >
                  <ChevronRightRoundedIcon fontSize="small" />
                </IconButton>
              </div>
            </div>

            {status.card_history?.length > 0 && (
              <div className="gallery-history-strip">
                {status.card_history.map((item, index) => (
                  <a
                    key={item.url}
                    href={`${API_BASE}${item.url}`}
                    target="_blank"
                    rel="noreferrer"
                    className="gallery-history-thumb"
                    title={`${CARD_TYPE_LABELS[item.card_type] || item.card_type} · ${new Date(item.generated_at).toLocaleString()}`}
                  >
                    <img src={`${API_BASE}${item.url}`} alt={`Riwayat generate ${index + 1}`} />
                  </a>
                ))}
              </div>
            )}

            <div className="gallery-bottom-actions">
              <button
                type="button"
                className="gallery-command-btn gallery-command-btn-secondary"
                onClick={onOpenHistory}
              >
                <svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true">
                  <path
                    d="M12 8v5l3 2M4.5 12a7.5 7.5 0 1 0 2.2-5.3M4.5 5v4h4"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <span>Riwayat</span>
              </button>

              <button
                className={"gallery-command-btn gallery-command-btn-primary" + (generating ? " is-loading" : "")}
                onClick={handleGenerate}
                disabled={!status?.has_photo || generating || !anyCardTypeSelected}
              >
                {generating ? (
                  <>
                    <span className="button-spinner button-spinner-invert" />
                    <span>Membuat</span>
                  </>
                ) : (
                  <>
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true">
                      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" stroke="currentColor" strokeWidth="1.7" />
                      <circle cx="8.5" cy="9.5" r="1.5" stroke="currentColor" strokeWidth="1.7" />
                      <path d="m5 17 4.5-4.5a1.5 1.5 0 0 1 2.12 0L15 15.87M14.5 14 16.4 12.1a1.5 1.5 0 0 1 2.12 0L21 14.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    <span>Generate Gambar</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {previewCard &&
            createPortal(
              <div className="image-preview-overlay" onClick={() => setPreviewCard(null)}>
                <div className="image-preview-box" onClick={(event) => event.stopPropagation()}>
                  <div className="image-preview-header">
                    <div className="image-preview-title">
                      <span className="modal-header-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
                          <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" stroke="currentColor" strokeWidth="1.7" />
                          <circle cx="8.5" cy="9.5" r="1.5" stroke="currentColor" strokeWidth="1.7" />
                          <path d="m5 17 4.5-4.5a1.5 1.5 0 0 1 2.12 0L15 15.87M14.5 14 16.4 12.1a1.5 1.5 0 0 1 2.12 0L21 14.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </span>
                      <span className="image-preview-title-text">
                        <span>{previewCard.label}</span>
                        <small>
                          {productName}
                          {previewCard.generatedAt
                            ? ` · Digenerate ${new Date(previewCard.generatedAt).toLocaleString("id-ID")}`
                            : ""}
                        </small>
                      </span>
                    </div>
                    <button
                      className="modal-close-btn"
                      onClick={() => setPreviewCard(null)}
                      title="Close preview"
                      aria-label="Close preview"
                    >
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
                        <path
                          d="M6.75 6.75 17.25 17.25M17.25 6.75 6.75 17.25"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                        />
                      </svg>
                    </button>
                  </div>
                  <img
                    className="image-preview-large"
                    src={`${API_BASE}${previewCard.url}?t=${Date.now()}`}
                    alt={`${productName} ${previewCard.label}`}
                  />
                  {previewCard.label !== "Foto produk" && (
                    <div className="modal-actions image-preview-actions">
                      <a
                        className="modal-cancel-btn gallery-download-link"
                        href={`${API_BASE}${previewCard.url}`}
                        download
                      >
                        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true">
                          <path
                            d="M12 3v11m0 0 4-4m-4 4-4-4M5 19h14"
                            stroke="currentColor"
                            strokeWidth="1.9"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                        <span>Download</span>
                      </a>
                    </div>
                  )}
                </div>
              </div>,
              document.body
            )}
        </div>
      )}

      {showAdvancedModal &&
        createPortal(
          <div className="image-preview-overlay" onClick={() => setShowAdvancedModal(false)}>
            <div className="image-preview-box gallery-advanced-modal-box" onClick={(event) => event.stopPropagation()}>
              <div className="image-preview-header">
                <div className="image-preview-title">
                  <span className="modal-header-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
                      <path
                        d="M4 7h11M4 12h16M9 17h11"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                      />
                      <circle cx="15" cy="7" r="2" stroke="currentColor" strokeWidth="1.8" />
                      <circle cx="6" cy="17" r="2" stroke="currentColor" strokeWidth="1.8" />
                    </svg>
                  </span>
                  <span className="image-preview-title-text">
                    <span>Pengaturan lanjutan</span>
                  </span>
                </div>
                <button
                  className="modal-close-btn"
                  onClick={() => setShowAdvancedModal(false)}
                  title="Close"
                  aria-label="Close"
                >
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
                    <path
                      d="M6.75 6.75 17.25 17.25M17.25 6.75 6.75 17.25"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                    />
                  </svg>
                </button>
              </div>

              <div className="gallery-advanced-modal-grid">
                <div className="gallery-option-group">
                  <div className="gallery-section-label">
                    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" aria-hidden="true">
                      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" stroke="currentColor" strokeWidth="1.7" />
                      <circle cx="8.5" cy="9.5" r="1.5" stroke="currentColor" strokeWidth="1.7" />
                      <path d="m5 17 4.5-4.5a1.5 1.5 0 0 1 2.12 0L15 15.87M14.5 14 16.4 12.1a1.5 1.5 0 0 1 2.12 0L21 14.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    Mode render
                  </div>
                  <div className="gallery-ai-scene-options">
                    <ToggleOption
                      checked={useAiScene}
                      onToggle={() => setUseAiScene((v) => !v)}
                      disabled={generating}
                      label="Posisi produk diatur AI (uncheck = foto aslinya)"
                    />
                    <ToggleOption
                      checked={withModel}
                      onToggle={() => setWithModel((v) => !v)}
                      disabled={generating || !useAiScene}
                      label="Sertakan model manusia"
                    />
                  </div>
                </div>

                <div className="gallery-option-group gallery-manual-section">
                  <div className="gallery-section-label">
                    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" aria-hidden="true">
                      <path
                        d="M6.25 3.75h8l3.5 3.5v13H6.25V3.75Z"
                        stroke="currentColor"
                        strokeWidth="1.7"
                        strokeLinejoin="round"
                      />
                      <path d="M14.25 3.75v3.5h3.5" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
                      <path d="M9 13.25h6M9 16.25h4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
                    </svg>
                    Isi manual (opsional)
                  </div>
                  <div className="gallery-manual-spec-columns">
                    <div className="gallery-manual-spec-column">
                      <div className="gallery-manual-spec-options">
                        <ToggleOption
                          inline
                          checked={useManualSpec}
                          onToggle={toggleManualSpec}
                          disabled={generating || !cardTypes.spec}
                          label="Spesifikasi manual"
                        />
                      </div>
                      {useManualSpec && (
                        <div className="gallery-manual-spec-inline">
                          <p className="im-subtitle">
                            Satu baris satu poin. Dipakai apa adanya di kartu Spesifikasi, tidak
                            ada campur AI.
                          </p>
                          <textarea
                            className="gallery-manual-spec-textarea"
                            placeholder={"Misal:\nMerek: GOSAVE\nBahan kulit sintetis premium\nUkuran all size"}
                            value={specManualText}
                            onChange={(event) => setSpecManualText(event.target.value)}
                            rows={5}
                            disabled={generating || !cardTypes.spec}
                            autoFocus
                          />
                          <div className="gallery-manual-spec-counter">
                            {specManualText.split("\n").filter((line) => line.trim()).length} baris terisi
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="gallery-manual-spec-column">
                      <div className="gallery-manual-spec-options">
                        <ToggleOption
                          inline
                          checked={useManualKeypoints}
                          onToggle={toggleManualKeypoints}
                          disabled={generating || !cardTypes.keypoint}
                          label="Keypoint manual"
                        />
                      </div>
                      {useManualKeypoints && (
                        <div className="gallery-manual-spec-inline">
                          <p className="im-subtitle">
                            Maksimal 3 keypoint, satu baris satu keypoint. Dipakai apa adanya,
                            tidak ada campur AI.
                          </p>
                          <textarea
                            className="gallery-manual-spec-textarea"
                            placeholder={"Misal:\nTahan Air\nAnti Slip\nGaransi 1 Tahun"}
                            value={keypointManualText}
                            onChange={handleKeypointManualChange}
                            rows={5}
                            disabled={generating || !cardTypes.keypoint}
                            autoFocus
                          />
                          <div className="gallery-manual-spec-counter">
                            {keypointManualText.split("\n").filter((line) => line.trim()).length}/3 keypoint terisi
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              <div className="modal-actions">
                <button type="button" className="modal-generate-btn" onClick={() => setShowAdvancedModal(false)}>
                  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true">
                    <path
                      d="M5 5.75A1.75 1.75 0 0 1 6.75 4h9.19c.46 0 .91.19 1.24.51l2.31 2.31c.33.33.51.78.51 1.24v10.19A1.75 1.75 0 0 1 18.25 20H6.75A1.75 1.75 0 0 1 5 18.25V5.75Z"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinejoin="round"
                    />
                    <path d="M8 4.5v4.25c0 .41.34.75.75.75h5.5c.41 0 .75-.34.75-.75V4.5" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
                    <path d="M8.5 20v-5.25c0-.41.34-.75.75-.75h5.5c.41 0 .75.34.75.75V20" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
                  </svg>
                  <span>Simpan</span>
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}


      {framePromptTypes &&
        createPortal(
          <div className="image-preview-overlay" onClick={() => setFramePromptTypes(null)}>
            <div className="image-preview-box gallery-frame-prompt-box" onClick={(event) => event.stopPropagation()}>
              <div className="image-preview-header">
                <div className="image-preview-title">
                  <span className="modal-header-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
                      <rect x="4" y="4" width="16" height="16" rx="3" stroke="currentColor" strokeWidth="1.7" />
                      <path d="M8 8h8M8 16h8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
                    </svg>
                  </span>
                  <span className="image-preview-title-text">
                    <span>Hapus frame?</span>
                  </span>
                </div>
                <button
                  className="modal-close-btn"
                  onClick={() => setFramePromptTypes(null)}
                  title="Close"
                  aria-label="Close"
                >
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
                    <path
                      d="M6.75 6.75 17.25 17.25M17.25 6.75 6.75 17.25"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                    />
                  </svg>
                </button>
              </div>
              <p className="im-subtitle">
                Gambar sudah selesai dibuat dengan frame + logo. Mau langsung dibuatkan juga versi tanpa
                frame (pakai AI)? Hasilnya bisa saja kurang rapi — cek dulu sebelum dipakai.
              </p>
              <div className="modal-actions">
                <button
                  type="button"
                  className="modal-cancel-btn"
                  onClick={() => setFramePromptTypes(null)}
                >
                  Nggak usah
                </button>
                <button
                  type="button"
                  className="modal-generate-btn"
                  onClick={() => handleRemoveFrameForGenerated(framePromptTypes)}
                  disabled={removingFrameKey === "__batch__"}
                >
                  {removingFrameKey === "__batch__" ? "Menghapus frame..." : "Ya, hapus frame"}
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}

      {toast &&
        createPortal(
          <div className={"gallery-toast gallery-toast-" + toast.type} role="status" aria-live="polite">
            <span className="gallery-toast-icon" aria-hidden="true">
              {toast.type === "success" ? (
                <svg viewBox="0 0 24 24" width="17" height="17" fill="none">
                  <path
                    d="m5 12 4.2 4.2L19 6.5"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" width="17" height="17" fill="none">
                  <path
                    d="M12 8v5M12 17.2v.1M10.25 4.75h3.5L21 18.5H3l7.25-13.75Z"
                    stroke="currentColor"
                    strokeWidth="1.9"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              )}
            </span>
            <span className="gallery-toast-copy">
              <strong>{toast.title}</strong>
              <span>{toast.message}</span>
            </span>
            <button
              type="button"
              className="gallery-toast-close"
              onClick={() => setToast(null)}
              aria-label="Tutup notifikasi"
            >
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
                <path
                  d="M7 7l10 10M17 7 7 17"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          </div>,
          document.body
        )}
    </>
  );
}

export default function ImagePage({ onToggleSidebar }) {
  const [framing, setFraming] = useState(null);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [tab, setTab] = useState("create");
  const [resetKey, setResetKey] = useState(0);

  const handleSelectProduct = (productName) => {
    setSelectedProduct(productName);
    setTab("create");
    setFraming((current) => current || "gosave");
  };

  const handleReset = () => {
    setSelectedProduct(null);
    setFraming(null);
    setTab("create");
    setResetKey((prev) => prev + 1);
  };

  return (
    <div className="gallery-panel im-panel">
      <BackgroundMain />
      <Header
        title="Revisi Gambar"
        showMenuButton
        onMenuToggle={onToggleSidebar}
        showBreadcrumbBar={false}
      />

      <div className="im-panel-content">
        <div className={"im-content-body" + (selectedProduct ? " gallery-panel-content-workspace" : "")}>
          {!selectedProduct && (
            <div className="page-tabs-row">
              <div className="page-tabs">
                <button
                  type="button"
                  className={"page-tab" + (tab === "create" ? " active" : "")}
                  onClick={() => setTab("create")}
                >
                  Revisi
                </button>
                <button
                  type="button"
                  className={"page-tab" + (tab === "history" ? " active" : "")}
                  onClick={() => setTab("history")}
                >
                  History
                </button>
              </div>
              <div className="page-tabs-row-actions">
                {tab === "create" && framing && !selectedProduct && (
                  <button
                    type="button"
                    className="gallery-framing-change-btn"
                    onClick={() => setFraming(null)}
                  >
                    <SwapHorizRoundedIcon fontSize="inherit" />
                    <span>Pilih frame lain</span>
                  </button>
                )}
                <button
                  type="button"
                  className="im-reset-btn"
                  onClick={handleReset}
                  title="Reset halaman"
                  aria-label="Reset halaman"
                >
                  <RestartAltRoundedIcon fontSize="inherit" />
                  <span>Reset</span>
                </button>
              </div>
            </div>
          )}

          {selectedProduct ? (
            <GalleryWorkspace
              productName={selectedProduct}
              framing={framing}
              onChangeFraming={() => {
                setSelectedProduct(null);
                setFraming(null);
              }}
              onBack={() => setSelectedProduct(null)}
              onOpenHistory={() => {
                setSelectedProduct(null);
                setTab("history");
              }}
            />
          ) : tab === "history" ? (
            <ImageHistory key={`history-${resetKey}`} onSelectProduct={handleSelectProduct} />
          ) : !framing ? (
            <FramingPicker key={`framing-${resetKey}`} selected={framing} onSelect={setFraming} />
          ) : (
            <ProductPicker
              key={`product-${resetKey}`}
              selected={selectedProduct}
              onSelect={handleSelectProduct}
              framing={framing}
            />
          )}
        </div>
      </div>
    </div>
  );
}
