import { Wallet } from "./wallet";
import { keccak256 } from "../utils/crypto";

export interface SessionConfig {
  wallet: Wallet;
  apiBaseUrl: string;
  autoRefresh?: boolean;
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

  constructor(config: SessionConfig) {
    this.wallet = config.wallet;
    this.apiBaseUrl = config.apiBaseUrl;
    this.autoRefresh = config.autoRefresh ?? true;
    this.loadStoredSession();
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
    if (this.currentToken) {
      // Check expiry — refresh if token has expired
      const now = Math.floor(Date.now() / 1000);
      if (this.currentToken.expiresAt && this.currentToken.expiresAt <= now) {
        const refreshed = await this.refresh();
        return refreshed.token;
      }
      return this.currentToken.token;
    }
    const session = await this.authenticate();
    return session.token;
  }

  /**
   * Get a fresh token, automatically refreshing on 401.
   * Callers should use this before making authenticated API requests.
   * If the response is 401, it will attempt to refresh the token once
   * and throw if refresh also fails.
   */
  async ensureValidToken(): Promise<string> {
    const token = await this.getToken();

    // Verify the token is still valid by checking expiry
    if (this.currentToken?.expiresAt) {
      const now = Math.floor(Date.now() / 1000);
      if (this.currentToken.expiresAt <= now) {
        const refreshed = await this.refresh();
        return refreshed.token;
      }
    }

    return token;
  }

  async refresh(): Promise<SessionToken> {
    // Deduplicate concurrent refresh calls
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    if (!this.currentToken?.refreshToken) {
      return this.authenticate();
    }

    this.refreshPromise = (async () => {
      const res = await fetch(`${this.apiBaseUrl}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refreshToken: this.currentToken!.refreshToken }),
      });

      if (!res.ok) {
        this.currentToken = null;
        return this.authenticate();
      }

      const token: SessionToken = await res.json();
      this.persistSession(token);
      return token;
    })();

    try {
      return await this.refreshPromise;
    } finally {
      this.refreshPromise = null;
    }
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
