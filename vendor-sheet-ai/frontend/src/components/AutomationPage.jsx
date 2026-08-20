import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { RestartAltRounded as RestartAltRoundedIcon } from "@mui/icons-material";
import Header from "../piagam/template/Header.jsx";
import BackgroundMain from "../piagam/template/BackgroundMain.jsx";
import {
  API_BASE,
  fetchGalleryStatus,
  fetchProducts,
  generateDescription,
  generateGalleryCard,
  generateInstructionManual,
  removeGalleryCardFrame,
} from "../api";

const MAX_SELECTION = 6;

const MANUAL_SECTION_OPTIONS = [
  { key: "cara_penggunaan", label: "Petunjuk Penggunaan" },
  { key: "perawatan", label: "Perhatian Penggunaan" },
  { key: "gambar_produk", label: "Gambar Produk" },
];

const CARD_TYPE_OPTIONS = [
  { key: "keypoint", label: "Key Point Cell" },
  { key: "spec", label: "Spesifikasi" },
  { key: "usage", label: "Cara Penggunaan" },
];

const KEUNGGULAN_OPTION = { key: "keunggulan", label: "Fitur Keunggulan" };

const PIPELINE_STEPS = [
  { key: "manual", label: "Instruction Manual" },
  { key: "image", label: "Image" },
  { key: "removeFrame", label: "Hapus Frame" },
  { key: "description", label: "Description" },
];

const BRAND_FILTER_OPTIONS = [
  { key: "all", label: "Semua" },
  { key: "goto", label: "Goto" },
  { key: "gosave", label: "Gosave" },
];

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

function detectBrand(product) {
  const haystack = `${product.product_name || ""} ${product.vendor_name || ""}`.toLowerCase();
  if (haystack.includes("gosave")) return "gosave";
  if (haystack.includes("goto")) return "goto";
  return "goto";
}

function initialStepState() {
  return { status: "waiting" };
}

function initialProductResult(product) {
  return {
    product_name: product.product_name,
    vendor_name: product.vendor_name,
    brand: detectBrand(product),
    manual: initialStepState(),
    image: initialStepState(),
    removeFrame: initialStepState(),
    description: initialStepState(),
  };
}

function toGalleryAssetUrl(url) {
  if (!url) return "";
  if (/^https?:\/\//i.test(url)) return url;
  return `${API_BASE}${url}`;
}

function StepStatusIcon({ status }) {
  if (status === "generating") {
    return (
      <span className="batch-status batch-status-pending automation-step-icon">
        <span className="batch-spinner" />
      </span>
    );
  }
  if (status === "done") {
    return (
      <span className="batch-status batch-status-done automation-step-icon">
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" aria-hidden="true">
          <path d="m5 12 4.2 4.2L19 6.5" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="batch-status batch-status-error automation-step-icon">
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" aria-hidden="true">
          <path d="M7 7 17 17M17 7 7 17" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
        </svg>
      </span>
    );
  }
  if (status === "skipped") {
    return (
      <span className="batch-status automation-step-icon automation-step-icon-skipped">
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" aria-hidden="true">
          <path d="M6.5 12h11" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
        </svg>
      </span>
    );
  }
  return (
    <span className="batch-status batch-status-waiting automation-step-icon">
      <span className="batch-waiting-dot" />
    </span>
  );
}

function stepProgressPercent(result) {
  const statuses = PIPELINE_STEPS.map((step) => result[step.key]?.status || "waiting");
  let lastDoneIndex = -1;
  let generatingIndex = -1;
  statuses.forEach((status, index) => {
    if (status === "done") lastDoneIndex = index;
    if (status === "generating") generatingIndex = index;
  });
  const targetIndex = generatingIndex >= 0 ? generatingIndex : lastDoneIndex;
  if (targetIndex <= 0) return 0;
  return (targetIndex / (statuses.length - 1)) * 100;
}

function isAutomationRunning(result) {
  return PIPELINE_STEPS.some((step) => result[step.key]?.status === "generating");
}

function stepStatusText(step) {
  if (step.status === "generating") return "Sedang diproses...";
  if (step.status === "done") return "Selesai";
  if (step.status === "error") return step.error || "Gagal";
  if (step.status === "skipped") return step.note || "Dilewati";
  return "Menunggu";
}

function AutomationStep({ label, step, productName, onPreview }) {
  return (
    <div className={"automation-step automation-step-" + step.status}>
      <div className="automation-step-marker">
        <StepStatusIcon status={step.status} />
      </div>
      <div className="automation-step-body">
        <span className="automation-step-label">{label}</span>
        <span className="automation-step-status-text">{stepStatusText(step)}</span>
        {step.status === "done" && step.docUrl && (
          <a className="automation-step-link" href={step.docUrl} target="_blank" rel="noreferrer">
            Buka
          </a>
        )}
        {step.status === "done" && step.cardUrls && step.cardUrls.length > 0 && (
          <span className="automation-step-thumbs">
            {step.cardUrls.map((url, index) => (
              <button
                key={url}
                type="button"
                className="automation-step-thumb"
                onClick={() => onPreview({ label: `${label} ${index + 1}`, url, productName })}
              >
                <img src={url} alt="" />
              </button>
            ))}
          </span>
        )}
      </div>
    </div>
  );
}

function ProductPicker({
  products,
  loading,
  error,
  selected,
  onToggle,
  search,
  onSearch,
  disabled,
  brandFilter,
  onBrandFilter,
}) {
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

  return (
    <>
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
              onClick={() => onBrandFilter(option.key)}
              disabled={loading}
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
          onChange={(event) => onSearch(event.target.value)}
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
        <div className="product-list">
          {filtered.length === 0 && (
            <div className="im-empty-state">
              <span>Tidak ada produk yang cocok.</span>
            </div>
          )}
          {filtered.map((product) => {
            const isChecked = selected.has(product.product_name);
            const isDisabled = disabled || (!isChecked && selected.size >= MAX_SELECTION);
            return (
              <button
                key={product.product_name}
                className={"product-list-item" + (isChecked ? " active" : "")}
                onClick={() => onToggle(product.product_name)}
                disabled={isDisabled}
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
    </>
  );
}

function GenerateTab() {
  const [products, setProducts] = useState([]);
  const [loadingProducts, setLoadingProducts] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [search, setSearch] = useState("");
  const [brandFilter, setBrandFilter] = useState("all");
  const [selected, setSelected] = useState(() => new Set());
  const [cardTypes, setCardTypes] = useState({
    keypoint: true,
    spec: true,
    usage: true,
    keunggulan: false,
  });
  const [keunggulanCount, setKeunggulanCount] = useState(3);
  const [manualSections, setManualSections] = useState({
    cara_penggunaan: true,
    perawatan: true,
    gambar_produk: true,
  });
  const [manualImageCount, setManualImageCount] = useState(1);
  const [enabledSteps, setEnabledSteps] = useState({
    manual: true,
    image: true,
    removeFrame: true,
    description: true,
  });
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState([]);
  const [showResultsModal, setShowResultsModal] = useState(false);
  const [previewImage, setPreviewImage] = useState(null);

  useEffect(() => {
    fetchProducts()
      .then((data) => setProducts(data.products || []))
      .catch((err) => setLoadError(err.message || "Failed to load products"))
      .finally(() => setLoadingProducts(false));
  }, []);

  const productByName = useMemo(
    () => Object.fromEntries(products.map((p) => [p.product_name, p])),
    [products]
  );

  const toggleSelect = (name) => {
    if (running) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else if (next.size < MAX_SELECTION) {
        next.add(name);
      }
      return next;
    });
    setResults([]);
  };

  const clearSelection = () => {
    if (running) return;
    setSelected(new Set());
    setResults([]);
  };

  const updateStep = (name, stepKey, patch) => {
    setResults((prev) =>
      prev.map((item) =>
        item.product_name === name
          ? { ...item, [stepKey]: { ...item[stepKey], ...patch } }
          : item
      )
    );
  };

  const runPipelineForProduct = async (name) => {
    const product = productByName[name] || { product_name: name };
    const brand = detectBrand(product);

    if (!enabledSteps.manual) {
      updateStep(name, "manual", { status: "skipped", note: "Langkah dimatikan" });
    } else {
      updateStep(name, "manual", { status: "generating" });
      try {
        const manualResult = await generateInstructionManual(name, manualImageCount, manualSections);
        updateStep(name, "manual", { status: "done", docUrl: manualResult.doc_url });
      } catch (err) {
        updateStep(name, "manual", { status: "error", error: err.message || "Gagal generate manual" });
      }
    }

    let generatedCardUrls = [];
    let imageDone = false;

    if (!enabledSteps.image) {
      updateStep(name, "image", { status: "skipped", note: "Langkah dimatikan" });
    } else {
      updateStep(name, "image", { status: "generating" });
      try {
        const status = await fetchGalleryStatus(name);
        const anyCardTypeSelected = Object.values(cardTypes).some(Boolean);
        if (!status.has_photo) {
          updateStep(name, "image", {
            status: "skipped",
            note: "Belum ada foto produk — upload dulu di menu Image",
          });
        } else if (!anyCardTypeSelected) {
          updateStep(name, "image", {
            status: "skipped",
            note: "Tidak ada jenis kartu yang dipilih",
          });
        } else {
          const framing = brand === "goto" ? "goto" : "gosave";
          await generateGalleryCard(name, {
            aiScene: true,
            keunggulanCount,
            framing,
            palette: "navy_yellow",
            ...cardTypes,
          });
          const refreshed = await fetchGalleryStatus(name);
          generatedCardUrls = Object.entries(refreshed.cards || {})
            .filter(([cardType]) => cardTypes[cardType])
            .map(([, card]) => card.card_url)
            .filter(Boolean);

          if (cardTypes.keunggulan) {
            const keunggulanUrls = (refreshed.card_history || [])
              .filter((item) => item.card_type === "keunggulan")
              .slice(0, keunggulanCount)
              .map((item) => item.url)
              .filter(Boolean);
            generatedCardUrls.push(...keunggulanUrls);
          }

          updateStep(name, "image", {
            status: "done",
            cardUrls: generatedCardUrls.map(toGalleryAssetUrl),
          });
          imageDone = true;
        }
      } catch (err) {
        updateStep(name, "image", { status: "error", error: err.message || "Gagal generate image" });
      }
    }

    if (!enabledSteps.removeFrame) {
      updateStep(name, "removeFrame", { status: "skipped", note: "Langkah dimatikan" });
    } else if (!imageDone) {
      updateStep(name, "removeFrame", { status: "skipped", note: "Tidak ada gambar untuk diproses" });
    } else {
      updateStep(name, "removeFrame", { status: "generating" });
      try {
        const finalUrls = [];
        for (const url of generatedCardUrls) {
          // eslint-disable-next-line no-await-in-loop
          const noFrame = await removeGalleryCardFrame(name, url).catch(() => null);
          finalUrls.push(noFrame?.url || url);
        }
        updateStep(name, "removeFrame", { status: "done", cardUrls: finalUrls.map(toGalleryAssetUrl) });
      } catch (err) {
        updateStep(name, "removeFrame", { status: "error", error: err.message || "Gagal hapus frame" });
      }
    }

    if (!enabledSteps.description) {
      updateStep(name, "description", { status: "skipped", note: "Langkah dimatikan" });
    } else {
    updateStep(name, "description", { status: "generating" });
    try {
      const descResult = await generateDescription(name, brand);
      updateStep(name, "description", { status: "done", docUrl: descResult.doc_url });
    } catch (err) {
      updateStep(name, "description", { status: "error", error: err.message || "Gagal generate deskripsi" });
    }
    }
  };

  const handleRun = async () => {
    const names = Array.from(selected);
    if (names.length === 0) return;

    setRunning(true);
    setResults(names.map((name) => initialProductResult(productByName[name] || { product_name: name })));
    setShowResultsModal(true);

    for (const name of names) {
      // eslint-disable-next-line no-await-in-loop
      await runPipelineForProduct(name);
    }

    setRunning(false);
  };

  const selectionCount = selected.size;

  return (
    <>
      <p className="im-subtitle">
        Pilih produk lalu jalankan otomasi — atur dulu langkah dan jenis kartu yang kamu mau di
        bawah ini.
      </p>

      <div className="gallery-card-types-container automation-section automation-section-steps">
      <div className="automation-inline-group-row">
        <div className="automation-inline-group automation-inline-group-wide">
          <span className="automation-inline-group-label">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
              <path d="M21 12a9 9 0 0 1-15.3 6.36L3 15" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M3 21v-6h6" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M3 12a9 9 0 0 1 15.3-6.36L21 9" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M21 3v6h-6" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Proses otomasi:
          </span>
          <div className="automation-jenis-gambar-layout">
            <div className="automation-option-row automation-card-type-grid">
              {PIPELINE_STEPS.filter((step) => step.key !== "manual").map((step) => {
                const isChecked = enabledSteps[step.key];
                return (
                  <button
                    key={step.key}
                    type="button"
                    className={"gallery-inline-toggle" + (isChecked ? " active" : "")}
                    onClick={() =>
                      setEnabledSteps((prev) => ({ ...prev, [step.key]: !prev[step.key] }))
                    }
                    disabled={running}
                  >
                    <span className={"product-checkbox" + (isChecked ? " checked" : "")}>
                      {isChecked && (
                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" aria-hidden="true">
                          <path d="M5 12.5 9.5 17 19 7" stroke="currentColor" strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      )}
                    </span>
                    <span>{step.label}</span>
                  </button>
                );
              })}
            </div>

            <div className="automation-keunggulan-row">
              <button
                type="button"
                className={"gallery-inline-toggle" + (enabledSteps.manual ? " active" : "")}
                onClick={() =>
                  setEnabledSteps((prev) => ({ ...prev, manual: !prev.manual }))
                }
                disabled={running}
              >
                <span className={"product-checkbox" + (enabledSteps.manual ? " checked" : "")}>
                  {enabledSteps.manual && (
                    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" aria-hidden="true">
                      <path d="M5 12.5 9.5 17 19 7" stroke="currentColor" strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </span>
                <span>Instruction Manual</span>
              </button>

              {enabledSteps.manual && (
                <div className="automation-manual-sections-list" role="group" aria-label="Bagian instruction manual">
                  <div className="automation-manual-sections-row">
                    {MANUAL_SECTION_OPTIONS.filter((option) => option.key !== "gambar_produk").map((option) => {
                      const isChecked = manualSections[option.key];
                      return (
                        <button
                          key={option.key}
                          type="button"
                          aria-pressed={isChecked}
                          className={"automation-manual-section-chip" + (isChecked ? " active" : "")}
                          onClick={() =>
                            setManualSections((prev) => ({ ...prev, [option.key]: !prev[option.key] }))
                          }
                          disabled={running}
                        >
                          <span className={"product-checkbox" + (isChecked ? " checked" : "")}>
                            {isChecked && (
                              <svg viewBox="0 0 24 24" width="10" height="10" fill="none" aria-hidden="true">
                                <path d="M5 12.5 9.5 17 19 7" stroke="currentColor" strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round" />
                              </svg>
                            )}
                          </span>
                          <span>{option.label}</span>
                        </button>
                      );
                    })}
                  </div>

                  <div className="automation-manual-sections-row">
                    <button
                      type="button"
                      aria-pressed={manualSections.gambar_produk}
                      className={"automation-manual-section-chip" + (manualSections.gambar_produk ? " active" : "")}
                      onClick={() =>
                        setManualSections((prev) => ({ ...prev, gambar_produk: !prev.gambar_produk }))
                      }
                      disabled={running}
                    >
                      <span className={"product-checkbox" + (manualSections.gambar_produk ? " checked" : "")}>
                        {manualSections.gambar_produk && (
                          <svg viewBox="0 0 24 24" width="10" height="10" fill="none" aria-hidden="true">
                            <path d="M5 12.5 9.5 17 19 7" stroke="currentColor" strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        )}
                      </span>
                      <span>Gambar Produk</span>
                    </button>

                    {manualSections.gambar_produk && (
                      <div className="brand-choice-options automation-keunggulan-count" role="radiogroup" aria-label="Jumlah foto produk">
                        {[1, 2, 3].map((count) => (
                          <button
                            key={count}
                            type="button"
                            role="radio"
                            aria-checked={manualImageCount === count}
                            className={"brand-choice-option" + (manualImageCount === count ? " active" : "")}
                            onClick={() => setManualImageCount(count)}
                            disabled={running}
                          >
                            {count} foto
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {enabledSteps.image && (
          <div className="automation-inline-group">
            <span className="automation-inline-group-label">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
                <rect x="3.25" y="4.75" width="17.5" height="14.5" rx="2.25" stroke="currentColor" strokeWidth="2.2" />
                <circle cx="8.25" cy="9.75" r="1.6" stroke="currentColor" strokeWidth="2.2" />
                <path
                  d="m4.5 16.75 5-5 3.5 3.5 2.5-2.5 4 4"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              Jenis gambar:
            </span>
            <div className="automation-jenis-gambar-layout">
              <div className="automation-option-row automation-card-type-grid">
                {CARD_TYPE_OPTIONS.map((option) => {
                  const isChecked = cardTypes[option.key];
                  return (
                    <button
                      key={option.key}
                      type="button"
                      className={"gallery-inline-toggle" + (isChecked ? " active" : "")}
                      onClick={() =>
                        setCardTypes((prev) => ({ ...prev, [option.key]: !prev[option.key] }))
                      }
                      disabled={running}
                    >
                      <span className={"product-checkbox" + (isChecked ? " checked" : "")}>
                        {isChecked && (
                          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" aria-hidden="true">
                            <path d="M5 12.5 9.5 17 19 7" stroke="currentColor" strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        )}
                      </span>
                      <span>{option.label}</span>
                    </button>
                  );
                })}
              </div>
              <div className="automation-keunggulan-row">
                <button
                  type="button"
                  className={"gallery-inline-toggle" + (cardTypes.keunggulan ? " active" : "")}
                  onClick={() =>
                    setCardTypes((prev) => ({ ...prev, keunggulan: !prev.keunggulan }))
                  }
                  disabled={running}
                >
                  <span className={"product-checkbox" + (cardTypes.keunggulan ? " checked" : "")}>
                    {cardTypes.keunggulan && (
                      <svg viewBox="0 0 24 24" width="12" height="12" fill="none" aria-hidden="true">
                        <path d="M5 12.5 9.5 17 19 7" stroke="currentColor" strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    )}
                  </span>
                  <span>{KEUNGGULAN_OPTION.label}</span>
                </button>

                {cardTypes.keunggulan && (
                  <div className="brand-choice-options automation-keunggulan-count" role="radiogroup" aria-label="Jumlah gambar keunggulan">
                    {[1, 2, 3, 4, 5].map((count) => (
                      <button
                        key={count}
                        type="button"
                        role="radio"
                        aria-checked={keunggulanCount === count}
                        className={"brand-choice-option" + (keunggulanCount === count ? " active" : "")}
                        onClick={() => setKeunggulanCount(count)}
                        disabled={running}
                      >
                        {count} foto
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

      </div>
      </div>

      <div className="selection-toolbar">
        <span className="automation-section-title-group">
          <span className="im-panel-eyebrow gallery-card-type-heading">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
              <path
                d="M12 3.5 20.5 8v8L12 20.5 3.5 16V8L12 3.5Z"
                stroke="currentColor"
                strokeWidth="1.9"
                strokeLinejoin="round"
              />
              <path
                d="M3.5 8 12 12.5 20.5 8M12 12.5V20.5"
                stroke="currentColor"
                strokeWidth="1.9"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            Pilih produk
          </span>
          <span className={"im-selection-badge" + (selectionCount > 0 ? " has-selection" : "")}>
            {selectionCount}/{MAX_SELECTION} dipilih
          </span>
        </span>
        <div className="selection-toolbar-actions">
          <button
            type="button"
            className="selection-toolbar-btn selection-toolbar-btn-danger"
            onClick={clearSelection}
            disabled={running || selectionCount === 0}
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

      <ProductPicker
        products={products}
        loading={loadingProducts}
        error={loadError}
        selected={selected}
        onToggle={toggleSelect}
        search={search}
        onSearch={setSearch}
        brandFilter={brandFilter}
        onBrandFilter={setBrandFilter}
        disabled={running}
      />

      {results.length > 0 && !showResultsModal && (
        <button
          type="button"
          className="automation-results-reopen"
          onClick={() => setShowResultsModal(true)}
        >
          <span className={"automation-results-status-icon" + (running ? "" : " is-done")} aria-hidden="true">
            {running ? (
              <span className="button-spinner" />
            ) : (
              <svg viewBox="0 0 24 24" width="12" height="12" fill="none">
                <path d="m5 12 4.2 4.2L19 6.5" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </span>
          <span>{running ? "Otomasi sedang berjalan" : "Otomasi selesai"} — Lihat hasil</span>
        </button>
      )}

      {showResultsModal &&
        results.length > 0 &&
        createPortal(
          <div
            className="image-preview-overlay"
            onClick={() => setShowResultsModal(false)}
          >
            <div
              className="image-preview-box automation-results-modal-box"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="image-preview-header">
                <div className="image-preview-title">
                  <span className="modal-header-icon" aria-hidden="true">
                    {running ? (
                      <span className="button-spinner" />
                    ) : (
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
                        <path d="m5 12 4.2 4.2L19 6.5" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    )}
                  </span>
                  <span className="image-preview-title-text">
                    <span>{running ? "Otomasi sedang berjalan" : "Otomasi selesai"}</span>
                    <small>
                      {running
                        ? "Jangan tutup halaman ini sampai semua produk selesai diproses."
                        : "Semua produk terpilih sudah diproses."}
                    </small>
                  </span>
                </div>
                <button
                  className="modal-close-btn"
                  onClick={() => setShowResultsModal(false)}
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

              <div className="automation-results-modal-list">
                {results.map((result) => (
                  <div key={result.product_name} className="automation-product-row">
                    <div className="automation-product-head">
                      <span className="im-product-avatar" aria-hidden="true">
                        {getProductInitials(result.product_name)}
                      </span>
                      <span className="product-list-text">
                        <span className="product-list-name">{result.product_name}</span>
                        {result.vendor_name && (
                          <span className="product-list-vendor">{result.vendor_name}</span>
                        )}
                      </span>
                    </div>
                    <div className="automation-steps">
                      <div className="automation-steps-track">
                        <span
                          className={"automation-steps-track-fill" + (isAutomationRunning(result) ? " is-flowing" : "")}
                          style={{ width: `${stepProgressPercent(result)}%` }}
                        />
                      </div>
                      {PIPELINE_STEPS.map((step) => (
                        <AutomationStep
                          key={step.key}
                          label={step.label}
                          step={result[step.key]}
                          productName={result.product_name}
                          onPreview={setPreviewImage}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>,
          document.body
        )}

      {previewImage &&
        createPortal(
          <div className="image-preview-overlay" onClick={() => setPreviewImage(null)}>
            <div className="image-preview-box" onClick={(event) => event.stopPropagation()}>
              <div className="image-preview-header">
                <div className="image-preview-title">
                  <span className="modal-header-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
                      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" stroke="currentColor" strokeWidth="1.7" />
                      <circle cx="8.5" cy="9.5" r="1.5" stroke="currentColor" strokeWidth="1.7" />
                      <path
                        d="m5 17 4.5-4.5a1.5 1.5 0 0 1 2.12 0L15 15.87M14.5 14 16.4 12.1a1.5 1.5 0 0 1 2.12 0L21 14.6"
                        stroke="currentColor"
                        strokeWidth="1.7"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </span>
                  <span className="image-preview-title-text">
                    <span>{previewImage.label}</span>
                    <small>{previewImage.productName}</small>
                  </span>
                </div>
                <button
                  className="modal-close-btn"
                  onClick={() => setPreviewImage(null)}
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
                src={previewImage.url}
                alt={`${previewImage.productName} ${previewImage.label}`}
              />
              <div className="modal-actions image-preview-actions">
                <a className="modal-cancel-btn gallery-download-link" href={previewImage.url} download>
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
            </div>
          </div>,
          document.body
        )}

      <div className="im-actions">
        <button
          className={"im-generate-btn" + (running ? " is-loading" : "")}
          onClick={handleRun}
          disabled={selectionCount === 0 || running || !Object.values(enabledSteps).some(Boolean)}
        >
          {running ? (
            <>
              <span className="button-spinner button-spinner-invert" />
              <span>Menjalankan otomasi</span>
            </>
          ) : (
            <>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true">
                <path d="M21 12a9 9 0 0 1-15.3 6.36L3 15" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M3 21v-6h6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M3 12a9 9 0 0 1 15.3-6.36L21 9" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M21 3v6h-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span>Jalankan otomasi{selectionCount > 0 ? ` (${selectionCount})` : ""}</span>
            </>
          )}
        </button>
      </div>
    </>
  );
}

export default function AutomationPage({ onToggleSidebar }) {
  const [resetKey, setResetKey] = useState(0);

  return (
    <div className="gallery-panel im-panel">
      <BackgroundMain />
      <Header
        title="Automation"
        showMenuButton
        onMenuToggle={onToggleSidebar}
        showBreadcrumbBar={false}
      />

      <div className="im-panel-content">
        <div className="im-content-body automation-content-body">
          <div className="page-tabs-row automation-page-tabs-row">
            <span className="im-panel-eyebrow">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
                <path d="M21 12a9 9 0 0 1-15.3 6.36L3 15" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M3 21v-6h6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M3 12a9 9 0 0 1 15.3-6.36L21 9" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M21 3v6h-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Otomasi batch
            </span>
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

          <GenerateTab key={`automation-${resetKey}`} />
        </div>
      </div>
    </div>
  );
}
