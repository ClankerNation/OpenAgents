import { Wallet } from "./wallet";
import { keccak256 } from "../utils/crypto";

/**
 * In-memory session store — replaces localStorage to eliminate XSS vector.
 * Tokens are kept only in memory and never persisted to disk.
 */
interface MemoryStore {
  [key: string]: unknown;
}

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
  /** In-memory store replaces localStorage — no XSS risk */
  private store: MemoryStore = {};

  constructor(config: SessionConfig) {
    this.wallet = config.wallet;
    this.apiBaseUrl = config.apiBaseUrl;
    this.autoRefresh = config.autoRefresh ?? true;
    this.loadStoredSession();
  }

  /**
   * Load session from in-memory store instead of localStorage.
   * Tokens are never written to disk, eliminating XSS exposure.
   */
  private loadStoredSession(): void {
    const key = `session_${this.wallet.address}`;
    const stored = this.store[key] as SessionToken | undefined;
    if (stored) {
      this.currentToken = stored;
    }
  }

  /**
   * Persist session to in-memory store only.
   * No localStorage, no cookies — tokens survive only in process memory.
   */
  private persistSession(token: SessionToken): void {
    this.currentToken = token;
    const key = `session_${this.wallet.address}`;
    this.store[key] = token;
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

  /**
   * getToken with expiry check.
   * Returns cached token only if not expired; auto-refreshes if needed.
   */
  async getToken(): Promise<string> {
    if (this.currentToken) {
      const now = Math.floor(Date.now() / 1000);
      // Check if token has expired
      if (this.currentToken.expiresAt > now) {
        return this.currentToken.token;
      }
      // Token expired — refresh or re-authenticate
      if (this.autoRefresh) {
        const refreshed = await this.refresh();
        return refreshed.token;
      }
    }
    const session = await this.authenticate();
    return session.token;
  }

  /**
   * refresh with mutex to prevent race conditions.
   * Multiple concurrent callers share a single refresh promise.
   */
  async refresh(): Promise<SessionToken> {
    // Mutex: if a refresh is already in progress, await it instead of starting a new one
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    if (!this.currentToken?.refreshToken) {
      this.refreshPromise = this.authenticate();
    } else {
      this.refreshPromise = (async () => {
        try {
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
        } finally {
          // Clear the promise regardless of success/failure
          this.refreshPromise = null;
        }
      })();
    }

    return this.refreshPromise;
  }

  logout(): void {
    this.currentToken = null;
    const key = `session_${this.wallet.address}`;
    delete this.store[key];
  }

  isAuthenticated(): boolean {
    if (!this.currentToken) return false;
    // Also check expiry
    const now = Math.floor(Date.now() / 1000);
    return this.currentToken.expiresAt > now;
  }

  /**
   * Rotate tokens — invalidate current session and get fresh tokens.
   * Used for security hardening after suspicious activity.
   */
  async rotateTokens(): Promise<SessionToken> {
    this.currentToken = null;
    this.refreshPromise = null;
    const key = `session_${this.wallet.address}`;
    delete this.store[key];
    return this.authenticate();
  }
}
