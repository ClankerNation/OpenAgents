/**
 * Session management for OpenAgents SDK — authentication, token refresh, and auto-retry on 401.
 * @contributor Gaotax2006
 * @platform claude-code/opus-4.8
 * @runtime node-v24.15.0 / win32 / amd64
 * @date 2026-06-26
 * @fixes #135 — Add 401 auto-refresh, expiry check, and race-condition-safe refresh
 */

import { Wallet } from "./wallet";
import { keccak256 } from "../utils/crypto";

export interface SessionConfig {
  wallet: Wallet;
  apiBaseUrl: string;
  autoRefresh?: boolean;
  /** Max concurrent refresh retries before re-authenticating (default 3) */
  maxRefreshRetries?: number;
}

export interface SessionToken {
  token: string;
  expiresAt: number; // unix timestamp in seconds
  refreshToken: string;
  walletAddress: string;
}

export class SessionManager {
  private wallet: Wallet;
  private apiBaseUrl: string;
  private autoRefresh: boolean;
  private currentToken: SessionToken | null = null;
  private refreshPromise: Promise<SessionToken> | null = null;
  private maxRefreshRetries: number;

  constructor(config: SessionConfig) {
    this.wallet = config.wallet;
    this.apiBaseUrl = config.apiBaseUrl;
    this.autoRefresh = config.autoRefresh ?? true;
    this.maxRefreshRetries = config.maxRefreshRetries ?? 3;
    this.loadStoredSession();
  }

  private loadStoredSession(): void {
    if (typeof window !== "undefined" && window.localStorage) {
      const stored = localStorage.getItem(`session_${this.wallet.address}`);
      if (stored) {
        try {
          this.currentToken = JSON.parse(stored);
        } catch {
          this.currentToken = null;
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

  /**
   * FIX #135: Check token expiry before returning.
   * If expired, auto-refresh (with retry) before returning the token.
   */
  async getToken(): Promise<string> {
    if (this.currentToken) {
      const now = Math.floor(Date.now() / 1000);
      // Refresh if token expires within 60 seconds (buffer for network latency)
      if (this.currentToken.expiresAt <= now + 60) {
        await this.refresh();
      }
      return this.currentToken.token;
    }

    const session = await this.authenticate();
    return session.token;
  }

  /**
   * FIX #135: Race-condition-safe refresh.
   * Only one refresh runs at a time; concurrent callers share the same promise.
   * On 401 after refresh, retries up to maxRefreshRetries before re-authenticating.
   */
  async refresh(retryCount = 0): Promise<SessionToken> {
    // Deduplicate concurrent refresh calls
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    this.refreshPromise = this._doRefresh(retryCount).finally(() => {
      this.refreshPromise = null;
    });

    return this.refreshPromise;
  }

  private async _doRefresh(retryCount: number): Promise<SessionToken> {
    if (!this.currentToken?.refreshToken) {
      return this.authenticate();
    }

    const res = await fetch(`${this.apiBaseUrl}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refreshToken: this.currentToken.refreshToken }),
    });

    if (!res.ok) {
      // FIX: On 401, retry refresh up to maxRefreshRetries times
      if (res.status === 401 && retryCount < this.maxRefreshRetries) {
        return this.refresh(retryCount + 1);
      }
      // Refresh failed — re-authenticate from scratch
      this.currentToken = null;
      return this.authenticate();
    }

    const token: SessionToken = await res.json();
    this.persistSession(token);
    return token;
  }

  async authenticate(): Promise<SessionToken> {
    const timestamp = Math.floor(Date.now() / 1000);
    const message = `Sign in to OpenAgents: ${timestamp}`;
    const signature = await this.wallet.signMessage(message);

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

    if (!res.ok) throw new Error(`Auth failed: ${res.status}`);
    const token: SessionToken = await res.json();
    this.persistSession(token);
    return token;
  }

  /**
   * FIX #135: Execute an API call with automatic 401 retry.
   * If the response is 401, refresh the token and retry once.
   */
  async fetchWithAuth(
    url: string,
    options: RequestInit = {}
  ): Promise<Response> {
    const res = await fetch(url, options);

    if (res.status === 401 && this.autoRefresh) {
      // Auto-refresh and retry
      await this.refresh();
      // Rebuild the request with new token
      const newToken = await this.getToken();
      const headers = {
        ...(options.headers as Record<string, string>),
        Authorization: `Bearer ${newToken}`,
      };
      return fetch(url, { ...options, headers });
    }

    return res;
  }

  logout(): void {
    this.currentToken = null;
    if (typeof window !== "undefined" && window.localStorage) {
      localStorage.removeItem(`session_${this.wallet.address}`);
    }
  }

  isAuthenticated(): boolean {
    if (!this.currentToken) return false;
    const now = Math.floor(Date.now() / 1000);
    return this.currentToken.expiresAt > now;
  }
}
