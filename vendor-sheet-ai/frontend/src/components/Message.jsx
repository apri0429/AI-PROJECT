import { useState } from "react";
import { API_BASE } from "../api";

// Image-gen messages loaded fresh from the browser (blob: object URLs) are
// already absolute; ones that came back from the server after a resync are
// relative paths like "/chat-assets/xxx.png" and need the API host prefixed
// — same convention used for gallery/card asset URLs elsewhere.
function toAssetUrl(url) {
  if (!url) return "";
  if (/^(https?|blob):/i.test(url)) return url;
  return `${API_BASE}${url}`;
}

function Avatar({ role }) {
  return (
    <div className={"avatar avatar-" + role}>
      {role === "user" ? "U" : "AI"}
    </div>
  );
}

function parseDescriptionTemplate(text) {
  const normalized = text.trim();
  if (!normalized.startsWith("DESCRIPTION_TEMPLATE")) return null;

  const lines = normalized.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const data = {
    productName: "",
    vendor: "",
    intro: "",
    keunggulan: [],
    spesifikasi: [],
    varian: [],
    faq: [],
  };
  let section = null;
  let currentFaq = null;

  for (const line of lines.slice(1)) {
    if (line.startsWith("NAMA_PRODUK:")) {
      data.productName = line.replace("NAMA_PRODUK:", "").trim();
      section = null;
      continue;
    }
    if (line.startsWith("VENDOR:")) {
      data.vendor = line.replace("VENDOR:", "").trim();
      section = null;
      continue;
    }
    if (line.startsWith("INTRO:")) {
      data.intro = line.replace("INTRO:", "").trim();
      section = "intro";
      continue;
    }
    if (line === "KEUNGGULAN:") {
      section = "keunggulan";
      continue;
    }
    if (line === "SPESIFIKASI:") {
      section = "spesifikasi";
      continue;
    }
    if (line === "VARIAN:") {
      section = "varian";
      continue;
    }
    if (line === "FAQ:") {
      section = "faq";
      continue;
    }

    if (section === "intro") {
      data.intro = [data.intro, line].filter(Boolean).join(" ");
    } else if (section === "keunggulan") {
      data.keunggulan.push(line.replace(/^\d+\.\s*/, "").trim());
    } else if (section === "spesifikasi") {
      data.spesifikasi.push(line.replace(/^-\s*/, "").trim());
    } else if (section === "varian") {
      data.varian.push(line.replace(/^-\s*/, "").trim());
    } else if (section === "faq") {
      if (/^\d+\.\s*/.test(line)) {
        currentFaq = { question: line.replace(/^\d+\.\s*/, "").trim(), answer: "" };
        data.faq.push(currentFaq);
      } else if (currentFaq) {
        currentFaq.answer = line.replace(/^-\s*/, "").trim();
      }
    }
  }

  return data;
}

function DescriptionTemplateMessage({ data }) {
  return (
    <div className="chat-description-template">
      <div className="chat-description-header">
        <span className="chat-description-eyebrow">Template description</span>
        <h3>{data.productName || "Produk"}</h3>
        {data.vendor && <small>{data.vendor}</small>}
      </div>

      {data.intro && (
        <section className="chat-description-section">
          <h4>Intro</h4>
          <p>{data.intro}</p>
        </section>
      )}

      {data.keunggulan.length > 0 && (
        <section className="chat-description-section">
          <h4>Keunggulan</h4>
          <ol>
            {data.keunggulan.map((item, index) => (
              <li key={`${item}-${index}`}>{item}</li>
            ))}
          </ol>
        </section>
      )}

      <div className="chat-description-grid">
        {data.spesifikasi.length > 0 && (
          <section className="chat-description-section">
            <h4>Spesifikasi</h4>
            <ul>
              {data.spesifikasi.map((item, index) => (
                <li key={`${item}-${index}`}>{item}</li>
              ))}
            </ul>
          </section>
        )}

        {data.varian.length > 0 && (
          <section className="chat-description-section">
            <h4>Varian</h4>
            <ul>
              {data.varian.map((item, index) => (
                <li key={`${item}-${index}`}>{item}</li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {data.faq.length > 0 && (
        <section className="chat-description-section">
          <h4>FAQ</h4>
          <div className="chat-description-faq">
            {data.faq.map((item, index) => (
              <div key={`${item.question}-${index}`} className="chat-description-faq-item">
                <strong>{item.question}</strong>
                {item.answer && <span>{item.answer}</span>}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function TextMessage({ text, role, messageId, onEditMessage }) {
  const [copied, setCopied] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(text);
  const descriptionTemplate = role === "assistant" ? parseDescriptionTemplate(text) : null;

  const copyText = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1300);
    } catch {
      setCopied(false);
    }
  };

  const canCopy = role === "assistant";
  const canEdit = role === "user" && messageId && onEditMessage;

  const submitEdit = () => {
    const nextText = draft.trim();
    if (!nextText || nextText === text) {
      setIsEditing(false);
      setDraft(text);
      return;
    }
    onEditMessage(messageId, nextText);
    setIsEditing(false);
  };

  return (
    <div className="text-message">
      {isEditing ? (
        <div className="edit-message-box">
          <textarea
            className="edit-message-input"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submitEdit();
              }
              if (event.key === "Escape") {
                setIsEditing(false);
                setDraft(text);
              }
            }}
            autoFocus
          />
          <div className="edit-message-actions">
            <button
              type="button"
              className="edit-cancel-btn"
              onClick={() => {
                setIsEditing(false);
                setDraft(text);
              }}
            >
              Cancel
            </button>
            <button type="button" className="edit-save-btn" onClick={submitEdit}>
              Send
            </button>
          </div>
        </div>
      ) : (
        descriptionTemplate ? (
          <DescriptionTemplateMessage data={descriptionTemplate} />
        ) : (
          <p className="msg-text">{text}</p>
        )
      )}
      {canCopy && (
        <button
          type="button"
          className={"copy-message-btn visible" + (copied ? " copied" : "")}
          onClick={copyText}
          title={copied ? "Copied" : "Copy"}
          aria-label={copied ? "Copied" : "Copy message"}
        >
          {copied ? (
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true">
              <path
                d="m5 12 4.2 4.2L19 6.5"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true">
              <path
                d="M8 8.5V6.75C8 5.78 8.78 5 9.75 5h7.5C18.22 5 19 5.78 19 6.75v7.5c0 .97-.78 1.75-1.75 1.75H15.5M6.75 8h7.5c.97 0 1.75.78 1.75 1.75v7.5c0 .97-.78 1.75-1.75 1.75h-7.5C5.78 19 5 18.22 5 17.25v-7.5C5 8.78 5.78 8 6.75 8Z"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
        </button>
      )}
      {canEdit && !isEditing && (
        <button
          type="button"
          className="edit-message-btn"
          onClick={() => {
            setDraft(text);
            setIsEditing(true);
          }}
          title="Edit message"
          aria-label="Edit message"
        >
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true">
            <path
              d="M4 20h4.25L19.5 8.75a2.12 2.12 0 0 0-3-3L5.25 17H4v3Z"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      )}
    </div>
  );
}

function IssuesMessage({ issues }) {
  return (
    <div className="issues-card">
      {issues.map((issue, index) => (
        <div key={index} className={"issue-row issue-" + issue.severity}>
          <span className="issue-badge">{issue.severity}</span>
          <span className="issue-field">{issue.field}</span>
          <span className="issue-message">{issue.message}</span>
        </div>
      ))}
    </div>
  );
}

function RowMessage({ row }) {
  const { vendor_name, product_name, dieline, llm_summary, ...rest } = row;
  const extraEntries = Object.entries(rest).filter(
    ([key]) => !["width", "height"].includes(key)
  );

  return (
    <div className="row-card">
      <div className="row-card-header">
        <div className="row-card-title">{product_name || "Untitled product"}</div>
        <div className="row-card-vendor">{vendor_name || "Unknown vendor"}</div>
      </div>

      {dieline && (
        <div className="row-card-stats">
          <div className="stat">
            <span className="stat-label">Width</span>
            <span className="stat-value">{dieline.width}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Height</span>
            <span className="stat-value">{dieline.height}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Bleed</span>
            <span className="stat-value">{dieline.bleed}</span>
          </div>
        </div>
      )}

      {llm_summary && <p className="row-card-summary">{llm_summary}</p>}

      {extraEntries.length > 0 && (
        <details className="row-card-extra">
          <summary>More fields</summary>
          <dl>
            {extraEntries.map(([key, value]) => (
              <div key={key} className="extra-field">
                <dt>{key}</dt>
                <dd>{String(value)}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </div>
  );
}

function DocLinkMessage({ message }) {
  return (
    <div className="chat-doc-link-card">
      <span className="chat-doc-link-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
          <path
            d="M6.25 3.75h8l3.5 3.5v13H6.25V3.75Z"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinejoin="round"
          />
          <path
            d="M14.25 3.75v3.5h3.5M8.75 12h6.5M8.75 15.25h4.5"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <span className="chat-doc-link-copy">
        <strong>{message.title || "Google Doc siap"}</strong>
        {message.meta && <small>{message.meta}</small>}
      </span>
      <a className="chat-doc-link-button" href={message.url} target="_blank" rel="noreferrer">
        {message.label || "Buka dokumen"}
      </a>
    </div>
  );
}

function DescriptionDocMessage({ message }) {
  const data = parseDescriptionTemplate(message.text || "");
  return (
    <div className="chat-description-doc-message">
      {data ? <DescriptionTemplateMessage data={data} /> : <p className="msg-text">{message.text}</p>}
      <DocLinkMessage
        message={{
          title: message.doc_title,
          url: message.doc_url,
          label: message.doc_label,
          meta: message.doc_meta,
        }}
      />
    </div>
  );
}

function DocChoiceMessage({ message, onAsk }) {
  return (
    <div className="chat-doc-choice-card">
      <div className="chat-doc-choice-header">
        <span className="chat-description-eyebrow">Google Doc</span>
        <h3>{message.title || "Pilih jenis dokumen"}</h3>
        {message.text && <p>{message.text}</p>}
      </div>
      <div className="chat-doc-choice-options">
        {(message.options || []).map((option) => (
          <button
            key={option.label}
            type="button"
            className="chat-doc-choice-option"
            onClick={() => onAsk?.(option.prompt)}
          >
            <strong>{option.label}</strong>
            <span>{option.description}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function ImageGenMessage({ message }) {
  if (message.role === "user") {
    return (
      <div className="image-gen-message">
        {message.previews?.length > 0 && (
          <div className="ichat-attachment-strip">
            {message.previews.map((src, index) => (
              <img key={src + index} src={toAssetUrl(src)} alt="" className="ichat-attachment-thumb" />
            ))}
          </div>
        )}
        {message.text && <p className="msg-text">{message.text}</p>}
      </div>
    );
  }

  return (
    <div className="image-gen-message">
      {message.status === "generating" && (
        <div className="ichat-generating">
          <span className="button-spinner" />
          <span>
            {message.total > 1
              ? `Generate ${message.images.length}/${message.total} gambar...`
              : "Generate gambar..."}
          </span>
        </div>
      )}

      {message.images?.length > 0 && (
        <div className="ichat-image-grid">
          {message.images.map((image, index) => {
            const url = toAssetUrl(image.url);
            return (
              <a key={url + index} className="ichat-image-card" href={url} download title="Download">
                <img src={url} alt={`Hasil ${index + 1}`} />
              </a>
            );
          })}
        </div>
      )}

      {(message.status === "error" || message.status === "partial") && (
        <div className="ichat-error">
          {message.status === "partial" ? `Sebagian gagal: ${message.error}` : message.error}
        </div>
      )}
    </div>
  );
}

export default function Message({ message, onEditMessage, onAsk }) {
  return (
    <div className={"message message-" + message.role}>
      <Avatar role={message.role} />
      <div className="message-body">
        {message.type === "text" && (
          <TextMessage
            text={message.text}
            role={message.role}
            messageId={message.id}
            onEditMessage={onEditMessage}
          />
        )}
        {message.type === "issues" && <IssuesMessage issues={message.issues} />}
        {message.type === "row" && <RowMessage row={message.row} />}
        {message.type === "doc_link" && <DocLinkMessage message={message} />}
        {message.type === "description_doc" && <DescriptionDocMessage message={message} />}
        {message.type === "doc_choice" && <DocChoiceMessage message={message} onAsk={onAsk} />}
        {message.type === "image_gen" && <ImageGenMessage message={message} />}
      </div>
    </div>
  );
}
