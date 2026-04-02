/**
 * Documents Subsystem Module
 * Manages PDF document uploads, listing, deletion, and client-side validation.
 */

import { api } from "./api.js";
import { CONFIG } from "./config.js";
import { ui } from "./ui.js";

class DocumentsService {
  constructor() {
    this.documents = [];
    this.isUploading = false;
  }

  /**
   * Fetch all documents uploaded by caller via GET /documents.
   */
  async loadDocuments() {
    try {
      const response = await api.get("/documents");
      this.documents = Array.isArray(response?.documents) ? response.documents : [];
      this.render();
      return this.documents;
    } catch (err) {
      ui.showToast(`Failed to load documents: ${err.message}`, "error");
      this.documents = [];
      this.render();
      return [];
    }
  }

  /**
   * Perform client-side PDF file validation.
   * Note: Client-side validation is solely for user feedback;
   * the backend performs authoritative byte, MIME, and structural inspection.
   * @param {File} file
   */
  validateFile(file) {
    if (!file) {
      throw new Error("Please select a file to upload.");
    }
    const name = file.name.toLowerCase();
    if (!name.endsWith(".pdf") && file.type !== "application/pdf") {
      throw new Error("Only PDF documents (.pdf) are supported.");
    }
    if (file.size <= 0) {
      throw new Error("Selected file is empty.");
    }
    if (file.size > CONFIG.MAX_UPLOAD_SIZE_BYTES) {
      throw new Error(
        `File size (${ui.formatFileSize(file.size)}) exceeds maximum limit of ${ui.formatFileSize(CONFIG.MAX_UPLOAD_SIZE_BYTES)}.`
      );
    }
  }

  /**
   * Upload and process a PDF file via POST /documents/upload.
   */
  async uploadFile(file) {
    this.validateFile(file);

    this.isUploading = true;
    const submitBtn = document.getElementById("doc-upload-btn");
    const fileInput = document.getElementById("doc-file-input");
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = "Uploading & Indexing...";
    }

    try {
      const formData = new FormData();
      formData.append("file", file);

      const doc = await api.upload("/documents/upload", formData);
      ui.showToast(`Document "${doc.original_filename}" processed and indexed successfully!`, "success");

      // Reset file input
      if (fileInput) fileInput.value = "";

      // Refresh list
      await this.loadDocuments();
      return doc;
    } catch (err) {
      ui.showToast(`Upload failed: ${err.message}`, "error");
      throw err;
    } finally {
      this.isUploading = false;
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = "Upload & Index";
      }
    }
  }

  /**
   * Delete document by ID via DELETE /documents/{id}.
   */
  async deleteDocument(documentId, filename = "document") {
    if (!confirm(`Are you sure you want to delete "${filename}"? All indexed chunks and vector data will be purged.`)) {
      return;
    }

    try {
      await api.delete(`/documents/${documentId}`);
      ui.showToast(`Document "${filename}" deleted.`, "info");
      await this.loadDocuments();
    } catch (err) {
      ui.showToast(`Failed to delete document: ${err.message}`, "error");
    }
  }

  /**
   * Render document list inside the documents modal/drawer.
   */
  render() {
    const container = document.getElementById("documents-list");
    const countBadge = document.getElementById("docs-count-badge");
    if (countBadge) {
      countBadge.textContent = this.documents.length;
    }

    if (!container) return;
    container.innerHTML = "";

    if (this.documents.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.style.padding = "var(--space-8) var(--space-4)";
      empty.innerHTML = `
        <svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
        <h3>No documents indexed</h3>
        <p>Upload PDF manuals, policies, or specifications to enable hybrid RAG search.</p>
      `;
      container.appendChild(empty);
      return;
    }

    const table = document.createElement("table");
    table.style.width = "100%";
    table.style.borderCollapse = "collapse";
    table.style.fontSize = "0.88rem";

    const thead = document.createElement("thead");
    thead.innerHTML = `
      <tr style="border-bottom: 1px solid var(--border-medium); text-align: left; color: var(--text-muted);">
        <th style="padding: var(--space-2) var(--space-3);">File</th>
        <th style="padding: var(--space-2) var(--space-3);">Pages</th>
        <th style="padding: var(--space-2) var(--space-3);">Chunks</th>
        <th style="padding: var(--space-2) var(--space-3);">Size</th>
        <th style="padding: var(--space-2) var(--space-3); text-align: right;">Action</th>
      </tr>
    `;
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    this.documents.forEach((doc) => {
      const tr = document.createElement("tr");
      tr.style.borderBottom = "1px solid var(--border-subtle)";

      // Filename
      const tdName = document.createElement("td");
      tdName.style.padding = "var(--space-3)";
      tdName.style.fontWeight = "500";
      tdName.textContent = doc.original_filename;

      // Pages
      const tdPages = document.createElement("td");
      tdPages.style.padding = "var(--space-3)";
      tdPages.textContent = doc.page_count;

      // Chunks
      const tdChunks = document.createElement("td");
      tdChunks.style.padding = "var(--space-3)";
      tdChunks.textContent = doc.chunk_count;

      // Size
      const tdSize = document.createElement("td");
      tdSize.style.padding = "var(--space-3)";
      tdSize.textContent = ui.formatFileSize(doc.file_size);

      // Action (Delete)
      const tdAction = document.createElement("td");
      tdAction.style.padding = "var(--space-3)";
      tdAction.style.textAlign = "right";

      const delBtn = document.createElement("button");
      delBtn.className = "btn btn-icon btn-danger";
      delBtn.title = "Delete document";
      delBtn.innerHTML = `
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="3 6 5 6 21 6"/>
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
        </svg>
      `;
      delBtn.addEventListener("click", () => this.deleteDocument(doc.id, doc.original_filename));
      tdAction.appendChild(delBtn);

      tr.appendChild(tdName);
      tr.appendChild(tdPages);
      tr.appendChild(tdChunks);
      tr.appendChild(tdSize);
      tr.appendChild(tdAction);

      tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    container.appendChild(table);
  }
}

export const documents = new DocumentsService();
