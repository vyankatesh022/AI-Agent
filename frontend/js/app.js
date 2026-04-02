/**
 * Application Bootstrap & Coordinator Module
 * Initializes views, binds global DOM events, wires model selectors,
 * and orchestrates conversation/document state on index.html.
 */

import { api } from "./api.js";
import { auth } from "./auth.js";
import { chat } from "./chat.js";
import { CONFIG } from "./config.js";
import { conversations } from "./conversations.js";
import { documents } from "./documents.js";
import { ui } from "./ui.js";

class App {
  constructor() {
    this.currentUser = null;
    this.availableModels = null;
    this.selectedProvider = CONFIG.DEFAULT_PROVIDER;
    this.selectedModel = CONFIG.DEFAULT_MODEL;
  }

  async init() {
    // 1. Guard route: require authenticated user
    if (!auth.requireAuth()) {
      return;
    }

    // 2. Fetch and render user identity
    await this._loadUserProfile();

    // 3. Load available LLM models
    await this._loadModelOptions();

    // 4. Wire conversation selection listener
    conversations.onSelect(async (conv) => {
      const titleEl = document.getElementById("chat-conversation-title");
      if (titleEl) {
        titleEl.textContent = conv ? conv.title : "Select or start a chat";
      }
      if (conv) {
        await chat.loadConversationMessages(conv.id);
      }
    });

    // 5. Load conversations and documents
    await conversations.loadConversations();
    await documents.loadDocuments();

    // 6. Select first conversation or prompt for new one
    if (conversations.conversations.length > 0) {
      await conversations.selectConversation(conversations.conversations[0].id);
    } else {
      await conversations.createConversation("New Chat");
    }

    // 7. Wire all UI event listeners
    this._bindEvents();
  }

  /**
   * Load and render current user info in header.
   * @private
   */
  async _loadUserProfile() {
    try {
      this.currentUser = await auth.fetchCurrentUser();
      const userEmailEl = document.getElementById("user-email-badge");
      if (userEmailEl && this.currentUser?.email) {
        userEmailEl.textContent = this.currentUser.email;
      }
    } catch (err) {
      ui.showToast("Failed to verify user profile. Please re-authenticate.", "warning");
    }
  }

  /**
   * Fetch approved LLM models allowlist and populate dropdown.
   * @private
   */
  async _loadModelOptions() {
    const selectEl = document.getElementById("model-select");
    if (!selectEl) return;

    try {
      const data = await api.get("/agent/models");
      this.availableModels = data;
      this.selectedProvider = data.default_provider || CONFIG.DEFAULT_PROVIDER;
      this.selectedModel = data.default_model || CONFIG.DEFAULT_MODEL;

      selectEl.innerHTML = "";

      Object.entries(data.providers || {}).forEach(([providerKey, providerInfo]) => {
        const optgroup = document.createElement("optgroup");
        optgroup.label = providerInfo.name || providerKey;

        (providerInfo.models || []).forEach((modelName) => {
          const option = document.createElement("option");
          option.value = `${providerKey}::${modelName}`;
          option.textContent = `${modelName}`;
          if (providerKey === this.selectedProvider && modelName === this.selectedModel) {
            option.selected = true;
          }
          optgroup.appendChild(option);
        });

        selectEl.appendChild(optgroup);
      });
    } catch {
      // Fallback default options
      selectEl.innerHTML = `
        <optgroup label="Google Gemini">
          <option value="gemini::gemini-2.0-flash" selected>gemini-2.0-flash</option>
          <option value="gemini::gemini-1.5-flash">gemini-1.5-flash</option>
        </optgroup>
        <optgroup label="OpenAI">
          <option value="openai::gpt-4o">gpt-4o</option>
          <option value="openai::gpt-4o-mini">gpt-4o-mini</option>
        </optgroup>
      `;
    }

    selectEl.addEventListener("change", (e) => {
      const [prov, mod] = e.target.value.split("::");
      this.selectedProvider = prov;
      this.selectedModel = mod;
      ui.showToast(`Active model changed to: ${mod}`, "info", 2000);
    });
  }

  /**
   * Bind all DOM interactions.
   * @private
   */
  _bindEvents() {
    // New Chat Button
    const newChatBtn = document.getElementById("new-chat-btn");
    if (newChatBtn) {
      newChatBtn.addEventListener("click", async () => {
        await conversations.createConversation(`Chat ${conversations.conversations.length + 1}`);
      });
    }

    // Message Input & Submit
    const chatInput = document.getElementById("chat-input");
    const sendBtn = document.getElementById("send-btn");

    const submitCurrentMessage = async () => {
      if (!chatInput) return;
      const text = chatInput.value;
      if (!text.trim()) return;

      await chat.sendMessage(text, this.selectedProvider, this.selectedModel);
    };

    if (sendBtn) {
      sendBtn.addEventListener("click", submitCurrentMessage);
    }

    // Direct Chat Input Document Attachment
    const chatAttachBtn = document.getElementById("chat-attach-btn");
    const chatFileInput = document.getElementById("chat-file-input");
    const uploadStatusBar = document.getElementById("chat-upload-status");
    const uploadStatusText = document.getElementById("chat-upload-status-text");

    if (chatAttachBtn && chatFileInput) {
      chatAttachBtn.addEventListener("click", () => {
        chatFileInput.click();
      });

      chatFileInput.addEventListener("change", async () => {
        const file = chatFileInput.files[0];
        if (!file) return;

        // Reset input for repeat selection
        chatFileInput.value = "";

        // Show upload indicator in input area
        if (uploadStatusBar && uploadStatusText) {
          uploadStatusText.textContent = `Uploading & indexing "${file.name}"...`;
          uploadStatusBar.style.display = "flex";
        }
        if (chatAttachBtn) chatAttachBtn.disabled = true;

        try {
          const doc = await documents.uploadFile(file);
          ui.showToast(`Document "${doc.original_filename}" indexed and ready for RAG query!`, "success");

          // Insert a friendly notice in the chat messages
          chat.appendMessageToDom({
            id: `sys-${Date.now()}`,
            role: "assistant",
            content: `Document **${doc.original_filename}** (${doc.page_count} pages, ${doc.chunk_count} chunks) has been processed and indexed into your knowledge base. You can now ask questions about it!`,
            intent: "document_search",
            created_at: new Date().toISOString(),
          });

          // If chat input is empty, prefill a helpful prompt
          if (chatInput && !chatInput.value.trim()) {
            chatInput.value = `What does ${doc.original_filename} cover?`;
            ui.autoResizeTextarea(chatInput);
            chatInput.focus();
          }
        } catch (err) {
          ui.showToast(`Attachment upload failed: ${err.message}`, "error");
        } finally {
          if (uploadStatusBar) uploadStatusBar.style.display = "none";
          if (chatAttachBtn) chatAttachBtn.disabled = false;
        }
      });
    }

    if (chatInput) {
      chatInput.addEventListener("input", () => ui.autoResizeTextarea(chatInput));
      chatInput.addEventListener("keydown", (e) => {
        // Enter to submit, Shift+Enter for newline
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          submitCurrentMessage();
        }
      });
    }

    // Documents Modal Open/Close
    const docsModalBtn = document.getElementById("docs-modal-btn");
    const docsModalCloseBtn = document.getElementById("docs-modal-close");
    const docsModalOverlay = document.getElementById("docs-modal");

    if (docsModalBtn) {
      docsModalBtn.addEventListener("click", () => {
        documents.loadDocuments();
        ui.toggleModal("docs-modal", true);
      });
    }
    if (docsModalCloseBtn) {
      docsModalCloseBtn.addEventListener("click", () => ui.toggleModal("docs-modal", false));
    }
    if (docsModalOverlay) {
      docsModalOverlay.addEventListener("click", (e) => {
        if (e.target === docsModalOverlay) {
          ui.toggleModal("docs-modal", false);
        }
      });
    }

    // Document Upload Form
    const docUploadForm = document.getElementById("doc-upload-form");
    const docFileInput = document.getElementById("doc-file-input");

    if (docUploadForm && docFileInput) {
      docUploadForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const file = docFileInput.files[0];
        if (!file) {
          ui.showToast("Please choose a PDF file first.", "warning");
          return;
        }
        try {
          await documents.uploadFile(file);
        } catch {
          // Handled in documents.js
        }
      });
    }

    // Mobile Sidebar Drawer Toggle & Backdrop
    const menuToggleBtn = document.getElementById("menu-toggle-btn");
    const sidebarBackdrop = document.querySelector(".sidebar-backdrop");

    if (menuToggleBtn) {
      menuToggleBtn.addEventListener("click", () => ui.toggleSidebar());
    }
    if (sidebarBackdrop) {
      sidebarBackdrop.addEventListener("click", () => ui.toggleSidebar(false));
    }

    // Logout Action
    const logoutBtn = document.getElementById("logout-btn");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", () => {
        if (confirm("Are you sure you want to log out?")) {
          auth.logout();
        }
      });
    }
  }
}

// Bootstrap on DOM readiness
document.addEventListener("DOMContentLoaded", () => {
  const app = new App();
  app.init();
});
