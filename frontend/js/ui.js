/**
 * UI Utilities Module
 * Toast notifications, modal management, date formatting, and text escaping.
 */

class UiUtils {
  /**
   * Escape raw untrusted string content to prevent XSS injection.
   */
  escapeHtml(rawText) {
    if (typeof rawText !== "string") return "";
    return rawText
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  /**
   * Display a non-blocking toast notification.
   * @param {string} message - Toast text to show.
   * @param {'info'|'success'|'error'|'warning'} type - Toast aesthetic type.
   * @param {number} duration - Auto-dismiss timeout in ms.
   */
  showToast(message, type = "info", duration = 4000) {
    let container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.className = "toast-container";
      document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.setAttribute("role", "alert");
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 200);
    }, duration);
  }

  /**
   * Toggle a modal overlay by ID.
   */
  toggleModal(modalId, show = true) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    if (show) {
      modal.classList.add("active");
      // Trap focus or focus first input
      const firstInput = modal.querySelector("input, button");
      if (firstInput) firstInput.focus();
    } else {
      modal.classList.remove("active");
    }
  }

  /**
   * Toggle the mobile responsive sidebar drawer.
   */
  toggleSidebar(forceState = null) {
    const sidebar = document.querySelector(".app-sidebar");
    const backdrop = document.querySelector(".sidebar-backdrop");
    if (!sidebar || !backdrop) return;

    const isOpen = forceState !== null ? forceState : !sidebar.classList.contains("open");
    if (isOpen) {
      sidebar.classList.add("open");
      backdrop.classList.add("active");
    } else {
      sidebar.classList.remove("open");
      backdrop.classList.remove("active");
    }
  }

  /**
   * Format ISO date string into friendly localized timestamp.
   */
  formatDate(isoString) {
    if (!isoString) return "";
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffMs = now - date;
      const diffHours = diffMs / (1000 * 60 * 60);

      if (diffHours < 24 && date.getDate() === now.getDate()) {
        return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      }
      return date.toLocaleDateString([], { month: "short", day: "numeric" });
    } catch {
      return isoString;
    }
  }

  /**
   * Format byte count into human-readable size string.
   */
  formatFileSize(bytes) {
    if (typeof bytes !== "number" || isNaN(bytes)) return "0 B";
    if (bytes < 1024) return `${bytes} B`;
    const kb = bytes / 1024;
    if (kb < 1024) return `${kb.toFixed(1)} KB`;
    const mb = kb / 1024;
    return `${mb.toFixed(1)} MB`;
  }

  /**
   * Automatically expand/contract a textarea based on content.
   */
  autoResizeTextarea(textareaEl) {
    if (!textareaEl) return;
    textareaEl.style.height = "auto";
    textareaEl.style.height = `${Math.min(textareaEl.scrollHeight, 160)}px`;
  }
}

export const ui = new UiUtils();
