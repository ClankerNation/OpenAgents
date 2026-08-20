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
    this.loadStoredSession();
  }

  private loadStoredSession(): void {
    if (typeof window !== "undefined" && window.localStorage) {
      const stored = localStorage.getItem(`session_${this.wallet.address}`);
      if (stored) {
        try {
          this.currentToken = JSON.parse(stored);
        } catch {
          localStorage.removeItem(`session_${this.wallet.address}`);
        }
      }
    }
  }

  private persistSession(token: SessionToken): void {
    this.currentToken = token;
    if (typeof window !== "undefined" && window.localStorage) {
      localStorage.setItem(`session_${this.wallet.address}`, JSON.stringify(token));
    }
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
    this.persistSession(token);
    return token;
  }

  async getToken(): Promise<string> {
    if (this.currentToken && this.currentToken.expiresAt > Math.floor(Date.now() / 1000)) {
      return this.currentToken.token;
    }
    // Token expired or missing — refresh proactively
    const session = await this.refresh();
    return session.token;
  }

  async refresh(): Promise<SessionToken> {
    // Deduplicate concurrent refresh calls to prevent race conditions
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
        this.currentToken = null;
        return this.authenticate();
      }

      const token: SessionToken = await res.json();
      this.persistSession(token);
      return token;
    } catch (err) {
      this.currentToken = null;
      throw err;
    }
  }

  /**
   * Execute an authenticated API request with automatic 401 retry.
   * Catches 401 responses, refreshes the token once, and retries the original request.
   * If the retry also returns 401, throws AuthenticationError and fires onAuthFailure callback.
   *
   * @param url The API endpoint URL
   * @param options Fetch options (method, headers, body, etc.)
   * @returns The Response object from the successful request
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

  logout(): void {
    this.currentToken = null;
    this.refreshPromise = null;
    if (typeof window !== "undefined" && window.localStorage) {
      localStorage.removeItem(`session_${this.wallet.address}`);
    }
  }

  isAuthenticated(): boolean {
    return this.currentToken !== null && this.currentToken.expiresAt > Math.floor(Date.now() / 1000);
  }
}
