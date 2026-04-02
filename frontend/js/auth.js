/**
 * Authentication Module
 * Manages user credentials, login/registration lifecycle, session tokens,
 * and navigation guards.
 */

import { api } from "./api.js";
import { CONFIG } from "./config.js";

class AuthService {
  /**
   * Check if an active session token exists.
   */
  isAuthenticated() {
    return Boolean(this.getToken());
  }

  /**
   * Read stored authentication token.
   */
  getToken() {
    try {
      return sessionStorage.getItem(CONFIG.TOKEN_STORAGE_KEY) || localStorage.getItem(CONFIG.TOKEN_STORAGE_KEY);
    } catch {
      return null;
    }
  }

  /**
   * Read cached user profile information.
   */
  getUser() {
    try {
      const raw = sessionStorage.getItem(CONFIG.USER_STORAGE_KEY) || localStorage.getItem(CONFIG.USER_STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  /**
   * Store session token and optional user profile.
   */
  setSession(token, user = null, persist = false) {
    const storage = persist ? localStorage : sessionStorage;
    try {
      storage.setItem(CONFIG.TOKEN_STORAGE_KEY, token);
      if (user) {
        storage.setItem(CONFIG.USER_STORAGE_KEY, JSON.stringify(user));
      }
    } catch {
      // Storage might be restricted
    }
  }

  /**
   * Clear all stored session credentials.
   */
  clearSession() {
    try {
      sessionStorage.removeItem(CONFIG.TOKEN_STORAGE_KEY);
      sessionStorage.removeItem(CONFIG.USER_STORAGE_KEY);
      localStorage.removeItem(CONFIG.TOKEN_STORAGE_KEY);
      localStorage.removeItem(CONFIG.USER_STORAGE_KEY);
    } catch {
      // Ignore cleanup error
    }
  }

  /**
   * Authenticate user with email and password via POST /auth/login.
   */
  async login(email, password, rememberMe = false) {
    const payload = {
      email: email.trim(),
      password,
    };

    const tokenResponse = await api.post("/auth/login", payload);
    if (!tokenResponse?.access_token) {
      throw new Error("Invalid response from authentication service.");
    }

    this.setSession(tokenResponse.access_token, null, rememberMe);

    // Immediately fetch user identity to cache profile
    const user = await this.fetchCurrentUser();
    this.setSession(tokenResponse.access_token, user, rememberMe);

    return user;
  }

  /**
   * Register a new user via POST /auth/register.
   */
  async register(email, password) {
    const payload = {
      email: email.trim(),
      password,
    };

    return await api.post("/auth/register", payload);
  }

  /**
   * Fetch caller profile via GET /auth/me.
   */
  async fetchCurrentUser() {
    const user = await api.get("/auth/me");
    if (user) {
      try {
        sessionStorage.setItem(CONFIG.USER_STORAGE_KEY, JSON.stringify(user));
      } catch {
        // Storage disabled
      }
    }
    return user;
  }

  /**
   * Perform logout: clean local credentials and redirect to login page.
   */
  logout() {
    this.clearSession();
    const currentPath = window.location.pathname;
    const loginTarget = currentPath.startsWith("/ui/") ? "/ui/login.html" : "login.html";
    window.location.href = loginTarget;
  }

  /**
   * Route guard for authenticated pages (e.g. index.html).
   */
  requireAuth() {
    if (!this.isAuthenticated()) {
      const currentPath = window.location.pathname;
      const loginTarget = currentPath.startsWith("/ui/") ? "/ui/login.html" : "login.html";
      window.location.href = loginTarget;
      return false;
    }
    return true;
  }

  /**
   * Route guard for login/register pages (redirects to main page if already signed in).
   */
  redirectIfAuthenticated() {
    if (this.isAuthenticated()) {
      const currentPath = window.location.pathname;
      const indexTarget = currentPath.startsWith("/ui/") ? "/ui/index.html" : "index.html";
      window.location.href = indexTarget;
      return true;
    }
    return false;
  }
}

export const auth = new AuthService();
