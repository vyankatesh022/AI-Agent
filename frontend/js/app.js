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
import { imageService } from "./image.js";
import { ui } from "./ui.js";

class App {
  constructor() {
    this.currentUser = null;
    this.availableModels = null;
    this.selectedProvider = CONFIG.DEFAULT_PROVIDER;
    this.selectedModel = CONFIG.DEFAULT_MODEL;
    this.attachedImage = null;
    this._pendingOriginalFile = null;
    this._pendingOriginalMeta = null;
    this._pendingCompressedResult = null;
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

    // 5. Load conversations
    await conversations.loadConversations();

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

      // Warn if user currently has an image attached but switched to non-vision model
      if (this.attachedImage && !this._isVisionModelSelected()) {
        ui.showToast(
          `Warning: Model "${mod}" does not support image analysis. Switching back to a vision model (e.g. gemini-2.0-flash, gpt-4o) is recommended.`,
          "warning",
          5000
        );
      }
    });
  }

  /**
   * Determine if the currently selected model supports image analysis.
   * @private
   * @returns {boolean}
   */
  _isVisionModelSelected() {
    if (!this.availableModels?.providers) return true;
    const providerData = this.availableModels.providers[this.selectedProvider];
    if (!providerData?.vision_models) return true;
    return providerData.vision_models.includes(this.selectedModel);
  }

  /**
   * Attach an image file to the chat composer tray.
   * @private
   */
  async _attachImageFile(file, isOptimized, details) {
    try {
      const dataUrl = await imageService.fileToDataUrl(file);

      this.attachedImage = {
        file,
        dataUrl,
        isOptimized,
        width: details.width,
        height: details.height,
        sizeFormatted: imageService.formatBytes(file.size),
      };

      // Populate preview tray elements
      const previewTray = document.getElementById("chat-image-preview");
      const thumbImg = document.getElementById("chat-image-thumb");
      const nameEl = document.getElementById("chat-image-name");
      const dimsEl = document.getElementById("chat-image-dimensions");
      const sizeEl = document.getElementById("chat-image-size");
      const badgeEl = document.getElementById("chat-image-status-badge");
      const reoptBtn = document.getElementById("chat-image-reoptimize-btn");

      if (thumbImg) thumbImg.src = dataUrl;
      if (nameEl) nameEl.textContent = file.name;
      if (dimsEl) dimsEl.textContent = `${details.width} × ${details.height}`;
      if (sizeEl) sizeEl.textContent = imageService.formatBytes(file.size);

      if (badgeEl) {
        if (isOptimized) {
          badgeEl.className = "badge badge-success";
          const reduction = details.reductionPercent ? ` (-${details.reductionPercent}%)` : "";
          badgeEl.textContent = `Optimized${reduction}`;
        } else {
          badgeEl.className = "badge badge-info";
          badgeEl.textContent = "Original";
        }
      }

      if (reoptBtn) {
        reoptBtn.style.display = isOptimized ? "none" : "inline-flex";
      }

      if (previewTray) {
        previewTray.style.display = "flex";
      }

      // Vision model compatibility feedback
      if (!this._isVisionModelSelected()) {
        ui.showToast(
          `Notice: Model "${this.selectedModel}" does not support vision. Please switch to a vision model (e.g. gemini-2.0-flash, gpt-4o).`,
          "warning",
          5000
        );
      } else {
        ui.showToast(
          isOptimized
            ? `Optimized image attached (${imageService.formatBytes(file.size)})`
            : `Image attached (${imageService.formatBytes(file.size)})`,
          "success",
          2500
        );
      }
    } catch (err) {
      ui.showToast(`Failed to attach image: ${err.message}`, "error");
      this._clearAttachedImage();
    }
  }

  /**
   * Reset attached image and hide preview tray.
   * @private
   */
  _clearAttachedImage() {
    this.attachedImage = null;

    const previewTray = document.getElementById("chat-image-preview");
    if (previewTray) previewTray.style.display = "none";

    const chatImageInput = document.getElementById("chat-image-input");
    if (chatImageInput) chatImageInput.value = "";
  }

  /**
   * Safely clean up modal comparison thumbnails.
   * @private
   */
  _cleanupPendingModalUrls() {
    const origImg = document.getElementById("compression-orig-img");
    const optImg = document.getElementById("compression-opt-img");
    if (origImg) origImg.src = "";
    if (optImg) optImg.src = "";
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
      const hasImage = Boolean(this.attachedImage?.dataUrl);

      if (!text.trim() && !hasImage) return;

      // Check vision capability
      if (hasImage && !this._isVisionModelSelected()) {
        ui.showToast(
          `Current model "${this.selectedModel}" does not support images. Please switch to a vision model (e.g. gemini-2.0-flash, gpt-4o).`,
          "error",
          4500
        );
        return;
      }

      const imageDataUrl = this.attachedImage ? this.attachedImage.dataUrl : null;
      this._clearAttachedImage();

      await chat.sendMessage(text, this.selectedProvider, this.selectedModel, imageDataUrl);
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

    // Image Attachment & Client-Side Compression Handlers
    const chatImageBtn = document.getElementById("chat-image-btn");
    const chatImageInput = document.getElementById("chat-image-input");
    const compressionModal = document.getElementById("image-compression-modal");
    const compressionCloseBtn = document.getElementById("compression-modal-close");
    const compressionCancelBtn = document.getElementById("compression-cancel-btn");
    const compressionKeepOrigBtn = document.getElementById("compression-keep-orig-btn");
    const compressionApplyBtn = document.getElementById("compression-apply-btn");
    const imageRemoveBtn = document.getElementById("chat-image-remove-btn");
    const imageReoptBtn = document.getElementById("chat-image-reoptimize-btn");

    if (chatImageBtn && chatImageInput) {
      chatImageBtn.addEventListener("click", () => {
        chatImageInput.click();
      });

      chatImageInput.addEventListener("change", async () => {
        const file = chatImageInput.files[0];
        if (!file) return;

        // 1. Initial client-side validation
        const val = imageService.validateFile(file);
        if (!val.valid) {
          ui.showToast(val.error, "error");
          chatImageInput.value = "";
          return;
        }

        try {
          // 2. Decode and inspect metadata
          const meta = await imageService.getImageMetadata(file);

          // 3. Determine if optimization is recommended
          if (imageService.shouldCompress(meta)) {
            ui.showToast("Calculating optimization preview...", "info", 1000);
            const compResult = await imageService.compressImage(file);

            this._pendingOriginalFile = file;
            this._pendingOriginalMeta = meta;
            this._pendingCompressedResult = compResult;

            // Populate compression comparison modal
            this._cleanupPendingModalUrls();

            const origUrl = await imageService.fileToDataUrl(file);
            const optUrl = await imageService.fileToDataUrl(compResult.file);

            const origImg = document.getElementById("compression-orig-img");
            const optImg = document.getElementById("compression-opt-img");
            if (origImg) origImg.src = origUrl;
            if (optImg) optImg.src = optUrl;

            const origSize = document.getElementById("compression-orig-size");
            const origDims = document.getElementById("compression-orig-dims");
            const origFmt = document.getElementById("compression-orig-format");
            if (origSize) origSize.textContent = meta.sizeFormatted;
            if (origDims) origDims.textContent = `${meta.width} × ${meta.height} px`;
            if (origFmt) origFmt.textContent = meta.type.replace("image/", "").toUpperCase();

            const optSize = document.getElementById("compression-opt-size");
            const optDims = document.getElementById("compression-opt-dims");
            const optSavings = document.getElementById("compression-opt-savings");
            const savingsPercent = document.getElementById("compression-savings-percent");

            if (optSize) optSize.textContent = compResult.compressedFormatted;
            if (optDims) optDims.textContent = `${compResult.width} × ${compResult.height} px`;
            if (optSavings) optSavings.textContent = `${compResult.savedFormatted} (-${compResult.reductionPercent}%)`;
            if (savingsPercent) savingsPercent.textContent = `-${compResult.reductionPercent}%`;

            ui.toggleModal("image-compression-modal", true);
          } else {
            // Optimization not needed: file is small and within bounds
            await this._attachImageFile(file, false, meta);
          }
        } catch (err) {
          ui.showToast(`Image processing error: ${err.message}`, "error");
        } finally {
          chatImageInput.value = "";
        }
      });
    }

    // Modal Confirmation: Use Optimized
    if (compressionApplyBtn) {
      compressionApplyBtn.addEventListener("click", async () => {
        if (this._pendingCompressedResult) {
          await this._attachImageFile(
            this._pendingCompressedResult.file,
            true,
            this._pendingCompressedResult
          );
        }
        ui.toggleModal("image-compression-modal", false);
        this._cleanupPendingModalUrls();
      });
    }

    // Modal Confirmation: Keep Original Uncompressed
    if (compressionKeepOrigBtn) {
      compressionKeepOrigBtn.addEventListener("click", async () => {
        if (this._pendingOriginalFile && this._pendingOriginalMeta) {
          await this._attachImageFile(
            this._pendingOriginalFile,
            false,
            this._pendingOriginalMeta
          );
        }
        ui.toggleModal("image-compression-modal", false);
        this._cleanupPendingModalUrls();
      });
    }

    // Modal Dismissal
    const closeCompressionModal = () => {
      ui.toggleModal("image-compression-modal", false);
      this._cleanupPendingModalUrls();
      this._pendingOriginalFile = null;
      this._pendingOriginalMeta = null;
      this._pendingCompressedResult = null;
    };

    if (compressionCancelBtn) compressionCancelBtn.addEventListener("click", closeCompressionModal);
    if (compressionCloseBtn) compressionCloseBtn.addEventListener("click", closeCompressionModal);
    if (compressionModal) {
      compressionModal.addEventListener("click", (e) => {
        if (e.target === compressionModal) {
          closeCompressionModal();
        }
      });
    }

    // Preview Tray Actions
    if (imageRemoveBtn) {
      imageRemoveBtn.addEventListener("click", () => {
        this._clearAttachedImage();
        ui.showToast("Image removed from message.", "info", 1500);
      });
    }

    if (imageReoptBtn) {
      imageReoptBtn.addEventListener("click", async () => {
        if (!this.attachedImage?.file) return;
        try {
          const meta = await imageService.getImageMetadata(this.attachedImage.file);
          const compResult = await imageService.compressImage(this.attachedImage.file);

          this._pendingOriginalFile = this.attachedImage.file;
          this._pendingOriginalMeta = meta;
          this._pendingCompressedResult = compResult;

          this._cleanupPendingModalUrls();
          const origUrl = await imageService.fileToDataUrl(this.attachedImage.file);
          const optUrl = await imageService.fileToDataUrl(compResult.file);

          const origImg = document.getElementById("compression-orig-img");
          const optImg = document.getElementById("compression-opt-img");
          if (origImg) origImg.src = origUrl;
          if (optImg) optImg.src = optUrl;

          const origSize = document.getElementById("compression-orig-size");
          const origDims = document.getElementById("compression-orig-dims");
          const origFmt = document.getElementById("compression-orig-format");
          if (origSize) origSize.textContent = meta.sizeFormatted;
          if (origDims) origDims.textContent = `${meta.width} × ${meta.height} px`;
          if (origFmt) origFmt.textContent = meta.type.replace("image/", "").toUpperCase();

          const optSize = document.getElementById("compression-opt-size");
          const optDims = document.getElementById("compression-opt-dims");
          const optSavings = document.getElementById("compression-opt-savings");
          const savingsPercent = document.getElementById("compression-savings-percent");

          if (optSize) optSize.textContent = compResult.compressedFormatted;
          if (optDims) optDims.textContent = `${compResult.width} × ${compResult.height} px`;
          if (optSavings) optSavings.textContent = `${compResult.savedFormatted} (-${compResult.reductionPercent}%)`;
          if (savingsPercent) savingsPercent.textContent = `-${compResult.reductionPercent}%`;

          ui.toggleModal("image-compression-modal", true);
        } catch (err) {
          ui.showToast(`Failed to open optimization dialog: ${err.message}`, "error");
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
