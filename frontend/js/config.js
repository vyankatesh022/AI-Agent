/**
 * Public Application Configuration
 * Contains only non-sensitive runtime parameters.
 * NO API keys, secrets, passwords, or tokens may be stored here.
 */

// Dynamically determine default API base URL
function resolveApiBaseUrl() {
  if (typeof window === "undefined") return "http://localhost:8000";
  // If served directly through FastAPI (e.g. at /ui or port 8000), use current origin
  if (window.location.port === "8000" || window.location.pathname.startsWith("/ui")) {
    return window.location.origin;
  }
  // If served from a separate development server (e.g., port 3000, 5500), point to FastAPI backend
  return "http://localhost:8000";
}

export const CONFIG = Object.freeze({
  API_BASE_URL: resolveApiBaseUrl(),
  TOKEN_STORAGE_KEY: "ai_agent_access_token",
  USER_STORAGE_KEY: "ai_agent_user_profile",
  MAX_UPLOAD_SIZE_BYTES: 10 * 1024 * 1024, // 10 MB (aligned with backend MAX_DOCUMENT_SIZE_MB)
  REQUEST_TIMEOUT_MS: 30000, // 30 seconds
  DEFAULT_PROVIDER: "gemini",
  DEFAULT_MODEL: "gemini-2.0-flash",
});
