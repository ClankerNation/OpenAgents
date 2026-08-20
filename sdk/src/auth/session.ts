/**
 * @fix-author rafaio1
 * @date 2026-08-20T10:25:00Z
 * @runtime os=linux, arch=x64, working_dir=/tmp/OpenAgents, shell=bash
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

  /**
   * Execute a fetch request with automatic 401 retry via token refresh.
   * Retries at most once to prevent infinite loops.
   */
  async fetchWithAutoRefresh(
    url: string,
    options: RequestInit = {}
  ): Promise<Response> {
    const token = await this.getToken();
    const headers = new Headers(options.headers || {});
    headers.set("Authorization", `Bearer ${token}`);

    let res = await fetch(url, { ...options, headers });

    // If 401 and auto-refresh enabled, try refreshing once
    if (res.status === 401 && this.autoRefresh) {
      try {
        await this.refresh();
        const newToken = await this.getToken();
        headers.set("Authorization", `Bearer ${newToken}`);
        res = await fetch(url, { ...options, headers });

        // If still 401 after refresh, invoke callback and throw
        if (res.status === 401) {
          const err = new AuthenticationError("Authentication failed after token refresh");
          this.onAuthFailure?.(err);
          throw err;
        }
      } catch (err) {
        if (err instanceof AuthenticationError) throw err;
        const authErr = new AuthenticationError(`Token refresh failed: ${(err as Error).message}`);
        this.onAuthFailure?.(authErr);
        throw authErr;
      }
    } else if (res.status === 401) {
      const err = new AuthenticationError("Authentication required");
      this.onAuthFailure?.(err);
      throw err;
    }

    return res;
  }

  private loadStoredSession(): void {
    // BUG: Storing tokens in localStorage is vulnerable to XSS attacks —
    // any injected script can steal the session token
    if (typeof window !== "undefined" && window.localStorage) {
      const stored = localStorage.getItem(`session_${this.wallet.address}`);
      if (stored) {
        this.currentToken = JSON.parse(stored);
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

    if (!res.ok) throw new Error(`Auth failed: ${res.status}`);
    const token: SessionToken = await res.json();
    this.persistSession(token);
    return token;
  }

  async getToken(): Promise<string> {
    // BUG: No expiry check — returns the cached token even if it has expired,
    // causing 401 errors on subsequent API calls
    if (this.currentToken) {
      return this.currentToken.token;
    }
    const session = await this.authenticate();
    return session.token;
  }

  async refresh(): Promise<SessionToken> {
    // BUG: Race condition — multiple concurrent callers can trigger parallel
    // refresh requests, and only the last one's token survives
    if (!this.currentToken?.refreshToken) {
      return this.authenticate();
    }

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
  }

  logout(): void {
    this.currentToken = null;
    if (typeof window !== "undefined" && window.localStorage) {
      localStorage.removeItem(`session_${this.wallet.address}`);
    }
  }

  isAuthenticated(): boolean {
    return this.currentToken !== null;
  }
}


/** Custom error for authentication failures after refresh attempts. */
export class AuthenticationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AuthenticationError";
  }
}
