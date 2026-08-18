const apiHost = window.location.hostname || "127.0.0.1";
export const API_BASE = `http://${apiHost}:8000`;

export async function createConversation() {
  const res = await fetch(`${API_BASE}/api/conversations`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to create a new chat");
  return res.json();
}

export async function fetchConversations({ archived = false } = {}) {
  const query = archived ? "?archived=true" : "";
  const res = await fetch(`${API_BASE}/api/conversations${query}`);
  if (!res.ok) throw new Error("Failed to load conversations");
  return res.json();
}

export async function fetchConversationMessages(conversationId) {
  const res = await fetch(`${API_BASE}/api/conversations/${conversationId}/messages`);
  if (!res.ok) throw new Error("Failed to load conversation");
  return res.json();
}

export async function deleteConversation(conversationId) {
  const res = await fetch(`${API_BASE}/api/conversations/${conversationId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete conversation");
  return res.json();
}

export async function updateConversation(conversationId, updates) {
  const res = await fetch(`${API_BASE}/api/conversations/${conversationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error("Failed to update conversation");
  return res.json();
}

export async function uploadSheet(file, conversationId) {
  const form = new FormData();
  form.append("file", file);
  form.append("conversation_id", conversationId);

  const res = await fetch(`${API_BASE}/api/upload`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to process file");
  }

  return res.json();
}

export async function askQuestion(message, conversationId) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, conversation_id: conversationId }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to get an answer");
  }

  return res.json();
}

export async function editConversationMessage(conversationId, messageId, message) {
  const res = await fetch(`${API_BASE}/api/conversations/${conversationId}/messages/${messageId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to edit message");
  }

  return res.json();
}

export async function fetchProducts() {
  const res = await fetch(`${API_BASE}/api/products`);
  if (!res.ok) throw new Error("Failed to load products");
  return res.json();
}

export async function generateInstructionManual(productName, imageCount = 1, sections = null) {
  const res = await fetch(`${API_BASE}/api/products/generate-doc`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      product_name: productName,
      image_count: imageCount,
      sections,
    }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to generate instruction manual");
  }

  return res.json();
}

export async function generateDescription(productName, brand) {
  const res = await fetch(`${API_BASE}/api/products/generate-description`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_name: productName, brand }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to generate description");
  }

  return res.json();
}

export async function fetchDescriptionHistory() {
  const res = await fetch(`${API_BASE}/api/products/description-history`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to load description history");
  }
  return res.json();
}

export async function deleteDescriptionHistoryItem(fileId) {
  const res = await fetch(`${API_BASE}/api/products/description-history/${fileId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to delete document");
  }
  return res.json();
}

export async function fetchDocHistory() {
  const res = await fetch(`${API_BASE}/api/products/doc-history`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to load document history");
  }
  return res.json();
}

export async function deleteDocHistoryItem(fileId) {
  const res = await fetch(`${API_BASE}/api/products/doc-history/${fileId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to delete document");
  }
  return res.json();
}

export async function fetchGalleryStatus(productName) {
  const res = await fetch(`${API_BASE}/api/gallery/${encodeURIComponent(productName)}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to load gallery status");
  }
  return res.json();
}

export async function fetchGalleryHistory() {
  const res = await fetch(`${API_BASE}/api/gallery-history`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to load image history");
  }
  return res.json();
}

export async function deleteGalleryHistoryItem(productName, url) {
  const filename = url.split("/").pop();
  const res = await fetch(
    `${API_BASE}/api/gallery/${encodeURIComponent(productName)}/cards/${encodeURIComponent(filename)}`,
    { method: "DELETE" }
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to delete image history");
  }
  return res.json();
}

export async function removeGalleryCardFrame(productName, url) {
  const filename = url.split("/").pop();
  const res = await fetch(
    `${API_BASE}/api/gallery/${encodeURIComponent(productName)}/cards/${encodeURIComponent(filename)}/remove-frame`,
    { method: "POST" }
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to remove frame");
  }
  return res.json();
}

export async function refineGalleryCard(productName, url, instruction = "") {
  const filename = url.split("/").pop();
  const form = new FormData();
  form.append("instruction", instruction);
  const res = await fetch(
    `${API_BASE}/api/gallery/${encodeURIComponent(productName)}/cards/${encodeURIComponent(filename)}/refine`,
    { method: "POST", body: form }
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to refine card");
  }
  return res.json();
}

export async function uploadGalleryPhoto(productName, file) {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/api/gallery/${encodeURIComponent(productName)}/photo`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to upload photo");
  }

  return res.json();
}

export async function refreshGalleryPhotoFromSheet(productName) {
  const res = await fetch(
    `${API_BASE}/api/gallery/${encodeURIComponent(productName)}/refresh-photo`,
    { method: "POST" }
  );

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to refresh photo from sheet");
  }

  return res.json();
}

export async function generateGalleryCard(
  productName,
  {
    aiScene = false,
    withModel = false,
    keypoint = true,
    spec = true,
    usage = true,
    keunggulan = false,
    keunggulanCount = 3,
    palette = "navy_yellow",
    framing = "gosave",
    customScene = "",
    customPrimary = "",
    customAccent = "",
    specManual = false,
    specManualText = "",
    keypointManual = false,
    keypointManualText = "",
    aiFullDesign = true,
    usageFullDesign = true,
    specFullDesign = true,
    customPrompt = "",
  } = {}
) {
  const params = new URLSearchParams({
    ai_scene: aiScene,
    with_model: withModel,
    keypoint,
    spec,
    usage,
    keunggulan,
    keunggulan_count: keunggulanCount,
    palette,
    framing,
    spec_manual: specManual,
    keypoint_manual: keypointManual,
    ai_full_design: aiFullDesign,
    spec_full_design: specFullDesign,
    usage_full_design: usageFullDesign,
  });
  if (customScene.trim()) params.set("custom_scene", customScene.trim());
  if (customPrimary) params.set("custom_primary", customPrimary);
  if (customAccent) params.set("custom_accent", customAccent);
  if (specManualText.trim()) params.set("spec_manual_text", specManualText.trim());
  if (keypointManualText.trim()) params.set("keypoint_manual_text", keypointManualText.trim());
  if (customPrompt.trim()) params.set("custom_prompt", customPrompt.trim());
  const res = await fetch(
    `${API_BASE}/api/gallery/${encodeURIComponent(productName)}/generate?${params}`,
    { method: "POST" }
  );

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to generate gallery card");
  }

  return res.json();
}

export async function imageChatGenerate(
  message,
  { productName = "", referenceUrl = "", referenceFile = null, conversationId = null } = {}
) {
  const form = new FormData();
  form.append("message", message);
  if (productName) form.append("product_name", productName);
  if (referenceUrl) form.append("reference_url", referenceUrl);
  if (referenceFile) form.append("reference_file", referenceFile);
  if (conversationId) form.append("conversation_id", conversationId);

  const res = await fetch(`${API_BASE}/api/image-chat/generate`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Gagal generate gambar");
  }

  return res.json();
}

export async function translatePdf(file) {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/api/pdf/translate`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to translate document");
  }

  return res.json();
}

export async function fetchPdfTranslateHistory() {
  const res = await fetch(`${API_BASE}/api/pdf/translate-history`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to load translation history");
  }
  return res.json();
}

export async function deletePdfTranslateHistoryItem(fileId) {
  const res = await fetch(`${API_BASE}/api/pdf/translate-history/${fileId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to delete document");
  }
  return res.json();
}

export async function processSheetUrl(url, conversationId) {
  const res = await fetch(`${API_BASE}/api/sheets/process`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, conversation_id: conversationId }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to process sheet");
  }

  return res.json();
}
