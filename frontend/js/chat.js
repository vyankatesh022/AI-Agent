/**
 * Chat Subsystem Module
 * Handles message history retrieval, message submission to /agent/chat,
 * typing animations, safe text rendering, and verifiable citation displays.
 */

import { api } from "./api.js";
import { ui } from "./ui.js";

class ChatService {
  constructor() {
    this.currentConversationId = null;
    this.messages = [];
    this.isSending = false;
  }

  /**
   * Load chronological message history for a conversation.
   */
  async loadConversationMessages(conversationId) {
    this.currentConversationId = conversationId;
    const container = document.getElementById("chat-messages");
    if (!container) return;

    container.innerHTML = "";

    // Show temporary skeleton/loading spinner
    const spinnerWrapper = document.createElement("div");
    spinnerWrapper.className = "empty-state";
    const spinner = document.createElement("div");
    spinner.className = "spinner";
    spinnerWrapper.appendChild(spinner);
    container.appendChild(spinnerWrapper);

    try {
      const history = await api.get(`/conversations/${conversationId}/messages`);
      this.messages = Array.isArray(history) ? history : [];
      this.render();
    } catch (err) {
      container.innerHTML = "";
      const errorState = document.createElement("div");
      errorState.className = "empty-state";
      const heading = document.createElement("h3");
      heading.textContent = "Failed to load messages";
      const desc = document.createElement("p");
      desc.textContent = err.message;
      errorState.appendChild(heading);
      errorState.appendChild(desc);
      container.appendChild(errorState);
    }
  }

  /**
   * Safe parser for markdown text.
   * Defends against XSS injection by escaping HTML first,
   * then converting safe formatting tokens (code blocks, bold, italics).
   * @param {string} text - Raw model response.
   * @returns {string} Safe HTML string.
   */
  _formatSafeContent(text) {
    if (!text) return "";

    // 1. Strict HTML escape
    let safe = ui.escapeHtml(text);

    // 2. Format fenced code blocks: ```lang ... ```
    safe = safe.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (_match, _lang, code) => {
      return `<pre><code>${code.trim()}</code></pre>`;
    });

    // 3. Format inline code: `code`
    safe = safe.replace(/`([^`]+)`/g, "<code>$1</code>");

    // 4. Format bold text: **text**
    safe = safe.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

    // 5. Format italic text: *text*
    safe = safe.replace(/\*([^*]+)\*/g, "<em>$1</em>");

    // 6. Format line breaks
    safe = safe.replace(/\n/g, "<br>");

    return safe;
  }

  /**
   * Send a user message to the LangGraph agent.
   * @param {string} text - User message content.
   * @param {string|null} [provider=null] - Optional LLM provider override.
   * @param {string|null} [model=null] - Optional LLM model override.
   * @param {string|null} [imageDataUrl=null] - Optional base64 data URL for multimodal input.
   */
  async sendMessage(text, provider = null, model = null, imageDataUrl = null) {
    const trimmedText = (text || "").trim();
    if (!this.currentConversationId || (!trimmedText && !imageDataUrl) || this.isSending) {
      return;
    }

    this.isSending = true;
    this._setControlsDisabled(true);

    // 1. Optimistically append user message to UI
    const optimisticUserMsg = {
      id: `temp-${Date.now()}`,
      role: "user",
      content: trimmedText,
      image: imageDataUrl || null,
      created_at: new Date().toISOString(),
    };
    this.messages.push(optimisticUserMsg);
    this.appendMessageToDom(optimisticUserMsg);

    // 2. Append typing indicator
    const typingIndicatorEl = this._showTypingIndicator();
    this._scrollToBottom();

    // 3. Clear message input
    const textarea = document.getElementById("chat-input");
    if (textarea) {
      textarea.value = "";
      ui.autoResizeTextarea(textarea);
    }

    try {
      const payload = {
        conversation_id: this.currentConversationId,
        message: trimmedText,
      };
      if (imageDataUrl) {
        payload.image = imageDataUrl;
      }
      if (provider) payload.provider = provider;
      if (model) payload.model = model;

      const response = await api.post("/agent/chat", payload);

      // Remove typing indicator
      if (typingIndicatorEl && typingIndicatorEl.parentNode) {
        typingIndicatorEl.parentNode.removeChild(typingIndicatorEl);
      }

      // Append assistant message
      const assistantMsg = {
        id: `resp-${Date.now()}`,
        role: "assistant",
        content: response.message,
        intent: response.intent,
        provider: response.provider,
        model: response.model,
        citations: response.citations,
        sources: response.sources,
        created_at: new Date().toISOString(),
      };
      this.messages.push(assistantMsg);
      this.appendMessageToDom(assistantMsg);
    } catch (err) {
      // Remove typing indicator
      if (typingIndicatorEl && typingIndicatorEl.parentNode) {
        typingIndicatorEl.parentNode.removeChild(typingIndicatorEl);
      }

      // Show error toast
      ui.showToast(`Message failed: ${err.message}`, "error");

      // Retain message in textarea if user wishes to retry
      if (textarea && !textarea.value) {
        textarea.value = trimmedText;
        ui.autoResizeTextarea(textarea);
      }

      // Append an error callout bubble in chat
      const errorMsg = {
        id: `err-${Date.now()}`,
        role: "assistant",
        content: `Error: ${err.message}. Your message has been restored to the input box so you can retry.`,
        isError: true,
        created_at: new Date().toISOString(),
      };
      this.appendMessageToDom(errorMsg);
    } finally {
      this.isSending = false;
      this._setControlsDisabled(false);
      this._scrollToBottom();
      if (textarea) textarea.focus();
    }
  }

  /**
   * Append a single message element into the chat DOM.
   */
  appendMessageToDom(msg) {
    const container = document.getElementById("chat-messages");
    if (!container) return;

    // Clear empty state if present
    const emptyState = container.querySelector(".empty-state");
    if (emptyState) {
      emptyState.remove();
    }

    const row = document.createElement("div");
    row.className = `message-row message-${msg.role}`;

    // Avatar
    const avatar = document.createElement("div");
    avatar.className = `message-avatar avatar-${msg.role}`;
    if (msg.role === "user") {
      avatar.innerHTML = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;
    } else {
      avatar.innerHTML = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" y1="16" x2="8.01" y2="16"/><line x1="16" y1="16" x2="16.01" y2="16"/></svg>`;
    }

    // Content wrapper
    const wrapper = document.createElement("div");
    wrapper.className = "message-content-wrapper";

    // Header line
    const headerLine = document.createElement("div");
    headerLine.className = "message-header-line";

    const senderSpan = document.createElement("span");
    senderSpan.textContent = msg.role === "user" ? "You" : "AI Assistant";
    headerLine.appendChild(senderSpan);

    if (msg.intent) {
      const intentPill = document.createElement("span");
      intentPill.className = "badge badge-info";
      intentPill.textContent = msg.intent.replace("_", " ");
      headerLine.appendChild(intentPill);
    }

    if (msg.model) {
      const modelPill = document.createElement("span");
      modelPill.className = "badge badge-primary";
      modelPill.textContent = msg.model;
      headerLine.appendChild(modelPill);
    }

    const timeSpan = document.createElement("span");
    timeSpan.textContent = ui.formatDate(msg.created_at);
    headerLine.appendChild(timeSpan);

    wrapper.appendChild(headerLine);

    // Message text bubble
    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    if (msg.isError) {
      bubble.style.borderColor = "var(--status-error-border)";
      bubble.style.backgroundColor = "var(--status-error-bg)";
      bubble.style.color = "var(--status-error)";
    }

    // Multimodal attached image rendering
    if (msg.image) {
      const imgContainer = document.createElement("div");
      imgContainer.className = "message-image-container";
      const imgEl = document.createElement("img");
      imgEl.className = "message-image-thumb";
      imgEl.src = msg.image;
      imgEl.alt = "Attached image";
      imgEl.loading = "lazy";
      imgEl.title = "Click to open full image";
      imgEl.addEventListener("click", () => {
        window.open(msg.image, "_blank");
      });
      imgContainer.appendChild(imgEl);
      bubble.appendChild(imgContainer);
    }

    if (msg.content) {
      const textSpan = document.createElement("div");
      textSpan.innerHTML = this._formatSafeContent(msg.content);
      bubble.appendChild(textSpan);
    }

    // Citations / Sources rendering
    const citationsList = msg.citations || msg.sources;
    if (Array.isArray(citationsList) && citationsList.length > 0) {
      const citationsBox = this._renderCitationsBox(citationsList);
      bubble.appendChild(citationsBox);
    }

    wrapper.appendChild(bubble);

    row.appendChild(avatar);
    row.appendChild(wrapper);

    container.appendChild(row);
  }

  /**
   * Safely render citations card block.
   * @private
   */
  _renderCitationsBox(citations) {
    const box = document.createElement("div");
    box.className = "citations-box";

    const label = document.createElement("div");
    label.className = "citations-label";
    label.innerHTML = `
      <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
      </svg>
      Grounded Sources (${citations.length})
    `;
    box.appendChild(label);

    const list = document.createElement("div");
    list.className = "citation-list";

    citations.forEach((c, idx) => {
      const card = document.createElement("div");
      card.className = "citation-card";

      const header = document.createElement("div");
      header.className = "citation-header";

      const tag = c.source_id ? `[${c.source_id}]` : `[${idx + 1}]`;
      const filename = c.filename || "document.pdf";
      const page = c.page_number ? ` — Page ${c.page_number}` : "";

      header.textContent = `${tag} ${filename}${page}`;
      card.appendChild(header);

      if (c.snippet) {
        const snippet = document.createElement("div");
        snippet.className = "citation-snippet";
        snippet.textContent = `"... ${c.snippet.trim()} ..."`;
        card.appendChild(snippet);
      }

      list.appendChild(card);
    });

    box.appendChild(list);
    return box;
  }

  /**
   * Show animated typing indicator row.
   * @private
   */
  _showTypingIndicator() {
    const container = document.getElementById("chat-messages");
    if (!container) return null;

    const row = document.createElement("div");
    row.className = "message-row message-assistant typing-row";

    const avatar = document.createElement("div");
    avatar.className = "message-avatar avatar-assistant";
    avatar.innerHTML = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/></svg>`;

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";

    const indicator = document.createElement("div");
    indicator.className = "typing-indicator";
    indicator.innerHTML = `<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>`;

    bubble.appendChild(indicator);
    row.appendChild(avatar);
    row.appendChild(bubble);

    container.appendChild(row);
    return row;
  }

  /**
   * Render all loaded messages or empty state.
   */
  render() {
    const container = document.getElementById("chat-messages");
    if (!container) return;

    container.innerHTML = "";

    if (this.messages.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.innerHTML = `
        <svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
        <h3>No messages yet</h3>
        <p>Ask a question, analyze an image, or request account data.</p>
      `;
      container.appendChild(empty);
      return;
    }

    this.messages.forEach((msg) => this.appendMessageToDom(msg));
    this._scrollToBottom();
  }

  /**
   * Enable/disable send input controls.
   * @private
   */
  _setControlsDisabled(disabled) {
    const textarea = document.getElementById("chat-input");
    const sendBtn = document.getElementById("send-btn");
    if (textarea) textarea.disabled = disabled;
    if (sendBtn) sendBtn.disabled = disabled;
  }

  /**
   * Scroll chat message viewport to the bottom.
   * @private
   */
  _scrollToBottom() {
    const container = document.getElementById("chat-messages");
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  }
}

export const chat = new ChatService();
