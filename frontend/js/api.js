/**
 * Centralized API Client Module
 * Provides standardized HTTP communication with the FastAPI backend.
 * All sensitive authorization is kept strictly isolated; tokens are never logged.
 */

import { CONFIG } from "./config.js";

class ApiClient {
  constructor() {
    this.baseUrl = CONFIG.API_BASE_URL;
  }

  /**
   * Resolve stored authentication token safely without logging.
   * @private
   */
  _getToken() {
    try {
      return sessionStorage.getItem(CONFIG.TOKEN_STORAGE_KEY) || localStorage.getItem(CONFIG.TOKEN_STORAGE_KEY);
    } catch {
      return null;
    }
  }

  /**
   * Build headers, injecting bearer authorization if token is present.
   * @private
   */
  _buildHeaders(customHeaders = {}, isFormData = false) {
    const headers = { ...customHeaders };
    if (!isFormData && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    const token = this._getToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    return headers;
  }

  /**
   * Handle session expiration (401 Unauthorized) by safely clearing session
   * and redirecting to the login view if not already there.
   * @private
   */
  _handleUnauthorized() {
    try {
      sessionStorage.removeItem(CONFIG.TOKEN_STORAGE_KEY);
      sessionStorage.removeItem(CONFIG.USER_STORAGE_KEY);
      localStorage.removeItem(CONFIG.TOKEN_STORAGE_KEY);
      localStorage.removeItem(CONFIG.USER_STORAGE_KEY);
    } catch {
      // Ignore storage access errors
    }

    const currentPath = window.location.pathname;
    if (!currentPath.endsWith("login.html") && !currentPath.endsWith("register.html")) {
      // Append return URL parameter safely
      const redirectTarget = currentPath.startsWith("/ui/") ? "/ui/login.html" : "login.html";
      window.location.href = redirectTarget;
    }
  }

  /**
   * Core request dispatcher with timeout and standardized error handling.
   * @private
   */
  async _request(endpoint, options = {}) {
    const {
      method = "GET",
      body = null,
      headers = {},
      isFormData = false,
      timeout = CONFIG.REQUEST_TIMEOUT_MS,
    } = options;

    const url = endpoint.startsWith("http") ? endpoint : `${this.baseUrl}${endpoint}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    const fetchConfig = {
      method,
      headers: this._buildHeaders(headers, isFormData),
      signal: controller.signal,
    };

    if (body) {
      fetchConfig.body = isFormData ? body : JSON.stringify(body);
    }

    try {
      const response = await fetch(url, fetchConfig);
      clearTimeout(timeoutId);

      // Handle HTTP 401 Unauthorized globally
      if (response.status === 401) {
        this._handleUnauthorized();
        throw new Error("Authentication session has expired. Please sign in again.");
      }

      // Handle 204 No Content
      if (response.status === 204) {
        return null;
      }

      // Parse JSON body or read text fallback
      let data = null;
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        data = await response.json();
      } else {
        const text = await response.text();
        data = text ? { detail: text } : null;
      }

      if (!response.ok) {
        let errorMessage = "An unexpected error occurred.";
        if (data && typeof data.detail === "string") {
          errorMessage = data.detail;
        } else if (data && Array.isArray(data.detail)) {
          // Pydantic validation error array
          errorMessage = data.detail.map((err) => `${err.loc?.join(".") || "field"}: ${err.msg}`).join("; ");
        } else if (response.statusText) {
          errorMessage = `${response.status} ${response.statusText}`;
        }
        const error = new Error(errorMessage);
        error.status = response.status;
        error.data = data;
        throw error;
      }

      return data;
    } catch (err) {
      clearTimeout(timeoutId);
      if (err.name === "AbortError") {
        const timeoutError = new Error("The request timed out. Please try again.");
        timeoutError.status = 408;
        throw timeoutError;
      }
      throw err;
    }
  }

  /**
   * GET request wrapper.
   */
  async get(endpoint, options = {}) {
    return this._request(endpoint, { ...options, method: "GET" });
  }

  /**
   * POST request wrapper.
   */
  async post(endpoint, body, options = {}) {
    return this._request(endpoint, { ...options, method: "POST", body });
  }

  /**
   * Upload request wrapper for multipart/form-data.
   */
  async upload(endpoint, formData, options = {}) {
    return this._request(endpoint, {
      ...options,
      method: "POST",
      body: formData,
      isFormData: true,
    });
  }

  /**
   * DELETE request wrapper.
   */
  async delete(endpoint, options = {}) {
    return this._request(endpoint, { ...options, method: "DELETE" });
  }
}

export const api = new ApiClient();
