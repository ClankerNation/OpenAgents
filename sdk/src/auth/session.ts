// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow

import { Wallet } from "./wallet";
import { keccak256 } from "../utils/crypto";

export interface SessionConfig {
  wallet: Wallet;
  apiBaseUrl: string;
  autoRefresh?: boolean;
  /** Callback invoked when authentication fails after refresh attempt */
  onAuthFailure?: (error: Error) => void;
}

export interface SessionToken {
  token: string;
  expiresAt: number; // unix timestamp in seconds
  refreshToken: string;
  walletAddress: string;
}

export class AuthenticationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AuthenticationError";
  }
}

/**
 * Secure session manager that stores tokens exclusively in memory.
 * 
 * Security improvements over previous implementation:
 * - No localStorage usage (prevents XSS token theft)
 * - Proactive expiry checking before token use
 * - Mutex-based refresh coalescing (prevents race conditions)
 * - Token rotation on refresh (old refresh token invalidated)
 * - Typed AuthenticationError for failure handling
 */
export class SessionManager {
  private wallet: Wallet;
  private apiBaseUrl: string;
  private autoRefresh: boolean;
  private currentToken: SessionToken | null = null;
  private refreshPromise: Promise<SessionToken> | null = null;
  private onAuthFailure?: (error: Error) => void;

  constructor(config: SessionConfig) {
    this.wallet = config.wallet;
    this.apiBaseUrl = config.apiBaseUrl;
    this.autoRefresh = config.autoRefresh ?? true;
    this.onAuthFailure = config.onAuthFailure;
    // No loadStoredSession() — tokens are never persisted to disk/browser storage
  }

  async authenticate(): Promise<SessionToken> {
    const timestamp = Math.floor(Date.now() / 1000);
    const message = `Sign in to OpenAgents: ${timestamp}`;
    const signature = await this.wallet.sendTransaction({
      to: "0x0000000000000000000000000000000000000000",
      value: 0n,
      data: "0x",
      gasLimit: 0n,
    });

    const res = await fetch(`${this.apiBaseUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        address: this.wallet.address,
        message,
        signature,
        timestamp,
      }),
    });

    if (!res.ok) throw new AuthenticationError(`Auth failed: ${res.status}`);
    const token: SessionToken = await res.json();
    this.currentToken = token;
    return token;
  }

  /**
   * Get a valid access token, refreshing proactively if expired.
   * Tokens are held in memory only — never read from or written to localStorage.
   */
  async getToken(): Promise<string> {
    const now = Math.floor(Date.now() / 1000);
    
    // Check expiry before returning cached token
    if (this.currentToken && this.currentToken.expiresAt > now) {
      return this.currentToken.token;
    }

    // Token expired or missing — refresh
    if (this.autoRefresh) {
      try {
        const session = await this.refresh();
        return session.token;
      } catch (err) {
        const authError = err instanceof AuthenticationError 
          ? err 
          : new AuthenticationError(err instanceof Error ? err.message : String(err));
        this.onAuthFailure?.(authError);
        throw authError;
      }
    }

    // No auto-refresh and no valid token — must re-authenticate
    if (!this.currentToken) {
      const session = await this.authenticate();
      return session.token;
    }

    throw new AuthenticationError("Session expired and auto-refresh is disabled");
  }

  /**
   * Refresh the session token with mutex-based coalescing.
   * Multiple concurrent callers share a single refresh request to prevent
   * race conditions and redundant network calls.
   * Implements token rotation: the old refresh token is consumed and replaced.
   */
  async refresh(): Promise<SessionToken> {
    // Mutex: if a refresh is already in flight, wait for it instead of starting another
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    this.refreshPromise = this._doRefresh().finally(() => {
      this.refreshPromise = null;
    });

    return this.refreshPromise;
  }

  private async _doRefresh(): Promise<SessionToken> {
    if (!this.currentToken?.refreshToken) {
      return this.authenticate();
    }

    try {
      const res = await fetch(`${this.apiBaseUrl}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refreshToken: this.currentToken.refreshToken }),
      });

      if (!res.ok) {
        // Refresh token rejected — clear state and re-authenticate
        this.currentToken = null;
        return this.authenticate();
      }

      // Token rotation: server returns new access + refresh tokens
      // Old refresh token is invalidated server-side
      const token: SessionToken = await res.json();
      this.currentToken = token;
      return token;
    } catch (err) {
      this.currentToken = null;
      throw new AuthenticationError(
        `Token refresh failed: ${err instanceof Error ? err.message : String(err)}`
      );
    }
  }

  /**
   * Execute an authenticated API request with automatic 401 retry.
   * Catches 401 responses, refreshes the token once, and retries the original request.
   * If the retry also returns 401, throws AuthenticationError and fires onAuthFailure callback.
   */
  async fetchWithAutoRefresh(url: string, options: RequestInit = {}): Promise<Response> {
    const token = await this.getToken();

    const headers = new Headers(options.headers || {});
    headers.set("Authorization", `Bearer ${token}`);

    let response = await fetch(url, { ...options, headers });

    // If 401 and auto-refresh is enabled, attempt one refresh + retry
    if (response.status === 401 && this.autoRefresh) {
      try {
        await this.refresh();
        const newToken = await this.getToken();
        headers.set("Authorization", `Bearer ${newToken}`);
        response = await fetch(url, { ...options, headers });
      } catch (refreshErr) {
        const authError = new AuthenticationError(
          `Authentication failed after refresh: ${refreshErr instanceof Error ? refreshErr.message : String(refreshErr)}`
        );
        this.onAuthFailure?.(authError);
        throw authError;
      }

      // If still 401 after retry, fire callback and throw
      if (response.status === 401) {
        const authError = new AuthenticationError("Authentication failed: token rejected after refresh");
        this.onAuthFailure?.(authError);
        throw authError;
      }
    }

    return response;
  }

  /**
   * Clear session state from memory.
   * No localStorage cleanup needed since tokens are never persisted.
   */
  logout(): void {
    this.currentToken = null;
    this.refreshPromise = null;
  }

  /**
   * Check if session is currently authenticated with a non-expired token.
   */
  isAuthenticated(): boolean {
    const now = Math.floor(Date.now() / 1000);
    return this.currentToken !== null && this.currentToken.expiresAt > now;
  }
}
