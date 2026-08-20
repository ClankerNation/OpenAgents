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
    // No localStorage — tokens stay in memory only (XSS-safe)
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

  async getToken(): Promise<string> {
    const now = Math.floor(Date.now() / 1000);
    if (this.currentToken && this.currentToken.expiresAt > now + 60) {
      return this.currentToken.token;
    }
    // Expired or missing — coalesce concurrent refreshes
    const session = await this.refresh();
    return session.token;
  }

  async refresh(): Promise<SessionToken> {
    // Coalesce concurrent refresh requests into a single promise
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    this.refreshPromise = (async (): Promise<SessionToken> => {
      try {
        if (!this.currentToken?.refreshToken) {
          return await this.authenticate();
        }

        const res = await fetch(`${this.apiBaseUrl}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refreshToken: this.currentToken.refreshToken }),
        });

        if (!res.ok) {
          this.currentToken = null;
          return await this.authenticate();
        }

        const token: SessionToken = await res.json();
        this.currentToken = token;
        return token;
      } finally {
        this.refreshPromise = null;
      }
    })();

    return this.refreshPromise;
  }

  /**
   * Make an authenticated API request with automatic 401 retry.
   * Catches 401 responses, refreshes the token, and retries once.
   * If the retry also returns 401, throws AuthenticationError and fires callback.
   * @param path API endpoint path (appended to apiBaseUrl)
   * @param options Fetch options (method, headers, body, etc.)
   * @returns The Response object from the successful request
   */
  async request(path: string, options: RequestInit = {}): Promise<Response> {
    const token = await this.getToken();

    const headers = new Headers(options.headers || {});
    headers.set("Authorization", `Bearer ${token}`);
    if (!headers.has("Content-Type") && options.body) {
      headers.set("Content-Type", "application/json");
    }

    let res = await fetch(`${this.apiBaseUrl}${path}`, {
      ...options,
      headers,
    });

    // Auto-refresh on 401 and retry exactly once
    if (res.status === 401) {
      try {
        await this.refresh();
        const newToken = this.currentToken?.token;
        if (!newToken) {
          throw new AuthenticationError("Token refresh returned no token");
        }
        headers.set("Authorization", `Bearer ${newToken}`);
        res = await fetch(`${this.apiBaseUrl}${path}`, {
          ...options,
          headers,
        });
      } catch (err) {
        const authErr = err instanceof AuthenticationError
          ? err
          : new AuthenticationError(`Auth refresh failed: ${(err as Error).message}`);
        this.onAuthFailure?.(authErr);
        throw authErr;
      }

      // Second 401 after refresh — final failure
      if (res.status === 401) {
        const authErr = new AuthenticationError("Authentication failed after token refresh");
        this.onAuthFailure?.(authErr);
        throw authErr;
      }
    }

    return res;
  }

  logout(): void {
    this.currentToken = null;
    this.refreshPromise = null;
  }

  isAuthenticated(): boolean {
    const now = Math.floor(Date.now() / 1000);
    return this.currentToken !== null && this.currentToken.expiresAt > now;
  }
}
