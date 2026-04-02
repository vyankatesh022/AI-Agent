/**
 * Conversations Module
 * Manages conversation list loading, creation, selection, and sidebar state.
 */

import { api } from "./api.js";
import { ui } from "./ui.js";

class ConversationsService {
  constructor() {
    this.conversations = [];
    this.activeId = null;
    this.onSelectCallback = null;
  }

  /**
   * Register a callback triggered when an active conversation is selected.
   */
  onSelect(callback) {
    this.onSelectCallback = callback;
  }

  /**
   * Fetch all conversations for the authenticated caller.
   */
  async loadConversations() {
    try {
      const list = await api.get("/conversations");
      this.conversations = Array.isArray(list) ? list : [];
      return this.conversations;
    } catch (err) {
      ui.showToast(`Failed to load conversations: ${err.message}`, "error");
      this.conversations = [];
      return [];
    }
  }

  /**
   * Create a new conversation thread via POST /conversations.
   */
  async createConversation(title = "New Conversation") {
    const payload = { title: title.trim() || "New Conversation" };
    try {
      const conv = await api.post("/conversations", payload);
      this.conversations.unshift(conv);
      await this.selectConversation(conv.id);
      return conv;
    } catch (err) {
      ui.showToast(`Failed to create conversation: ${err.message}`, "error");
      throw err;
    }
  }

  /**
   * Select a conversation by ID, update state, and trigger listener.
   */
  async selectConversation(conversationId) {
    this.activeId = conversationId;
    this.render();

    // Close mobile sidebar on selection
    ui.toggleSidebar(false);

    if (this.onSelectCallback) {
      const activeConv = this.getActiveConversation();
      await this.onSelectCallback(activeConv);
    }
  }

  /**
   * Get active conversation model.
   */
  getActiveConversation() {
    return this.conversations.find((c) => c.id === this.activeId) || null;
  }

  /**
   * Render conversation list in DOM container.
   */
  render(containerId = "conversation-list") {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = "";

    if (this.conversations.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.style.padding = "var(--space-6) var(--space-2)";

      const heading = document.createElement("h3");
      heading.textContent = "No conversations";
      heading.style.fontSize = "0.95rem";

      const desc = document.createElement("p");
      desc.textContent = "Start a new conversation to begin.";
      desc.style.fontSize = "0.8rem";

      empty.appendChild(heading);
      empty.appendChild(desc);
      container.appendChild(empty);
      return;
    }

    this.conversations.forEach((conv) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = `conversation-item ${conv.id === this.activeId ? "active" : ""}`;
      item.setAttribute("data-id", conv.id);

      const titleSpan = document.createElement("span");
      titleSpan.className = "conversation-title-text";
      titleSpan.textContent = conv.title || "Untitled Chat";

      const dateSpan = document.createElement("span");
      dateSpan.className = "conversation-meta-date";
      dateSpan.textContent = ui.formatDate(conv.created_at);

      item.appendChild(titleSpan);
      item.appendChild(dateSpan);

      item.addEventListener("click", () => {
        if (this.activeId !== conv.id) {
          this.selectConversation(conv.id);
        }
      });

      container.appendChild(item);
    });
  }
}

export const conversations = new ConversationsService();
