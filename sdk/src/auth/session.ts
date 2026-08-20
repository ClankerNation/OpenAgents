/**
 * @contributor rafaio1
 * @timestamp 2026-08-20T02:00:00Z
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */

import { Wallet } from "./wallet";
import { keccak256 } from "../utils/crypto";

export interface SessionConfig {
  wallet: Wallet;
  apiBaseUrl: string;
  autoRefresh?: boolean;
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

    if (!res.ok) throw new AuthenticationError(`Auth failed: ${res.status}`);
    const token: SessionToken = await res.json();
    this.persistSession(token);
    return token;
  }

  async getToken(): Promise<string> {
    if (this.currentToken && this.currentToken.expiresAt > Math.floor(Date.now() / 1000)) {
      return this.currentToken.token;
    }
    const session = await this.refresh();
    return session.token;
  }

  async refresh(): Promise<SessionToken> {
    // Deduplicate concurrent refresh calls
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
      return this.authenticate();
    }
  }

  /**
   * Execute an authenticated fetch request with automatic 401 retry.
   * Catches 401 responses, refreshes the token once, and retries.
   * If the retry also returns 401, throws AuthenticationError.
   */
  async authenticatedFetch(
    url: string,
    options: RequestInit = {}
  ): Promise<Response> {
    const token = await this.getToken();
    const headers = new Headers(options.headers || {});
    headers.set("Authorization", `Bearer ${token}`);

    let response = await fetch(url, { ...options, headers });

    // Auto-refresh on 401 (retry exactly once)
    if (response.status === 401 && this.autoRefresh) {
      try {
        await this.refresh();
        const newToken = await this.getToken();
        headers.set("Authorization", `Bearer ${newToken}`);
        response = await fetch(url, { ...options, headers });
      } catch (err) {
        const authErr = err instanceof AuthenticationError
          ? err
          : new AuthenticationError(`Token refresh failed: ${(err as Error).message}`);
        this.onAuthFailure?.(authErr);
        throw authErr;
      }

      // If still 401 after refresh, fire callback and throw
      if (response.status === 401) {
        const authErr = new AuthenticationError("Authentication failed after token refresh");
        this.onAuthFailure?.(authErr);
        throw authErr;
      }
    }

    return response;
  }

  logout(): void {
    this.currentToken = null;
    if (typeof window !== "undefined" && window.localStorage) {
      localStorage.removeItem(`session_${this.wallet.address}`);
    }
  }

  isAuthenticated(): boolean {
    return this.currentToken !== null && 
           this.currentToken.expiresAt > Math.floor(Date.now() / 1000);
  }
}
