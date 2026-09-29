/**
 * @contributor doubao-agent (spiritwanghs fork)
 * @platform-config Autonomous coding agent executing GitHub bounties; user provides a fine-grained GitHub PAT.
 * @env os=linux arch=x64 home_dir=/home/user working_dir=/home/user/Doubao/chats/38444718400345090/OpenAgents shell=bash
 * @timestamp 2026-09-29T02:10:00Z
 */
import { Wallet } from "./wallet";

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
  // Tokens kept in memory only — never persisted to localStorage, which is
  // readable by any injected script and thus vulnerable to XSS theft.
  private currentToken: SessionToken | null = null;
  private refreshPromise: Promise<SessionToken> | null = null;

  private static EXPIRY_SKEW_SEC = 30;

  constructor(config: SessionConfig) {
    this.wallet = config.wallet;
    this.apiBaseUrl = config.apiBaseUrl;
    this.autoRefresh = config.autoRefresh ?? true;
  }

  private isCurrentTokenFresh(): boolean {
    if (!this.currentToken) return false;
    const now = Math.floor(Date.now() / 1000);
    return this.currentToken.expiresAt - SessionManager.EXPIRY_SKEW_SEC > now;
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
    this.currentToken = token;
    return token;
  }

  async getToken(): Promise<string> {
    if (this.currentToken && this.isCurrentTokenFresh()) {
      return this.currentToken.token;
    }
    const session = this.currentToken ? await this.refresh() : await this.authenticate();
    return session.token;
  }

  async refresh(): Promise<SessionToken> {
    // De-duplicate concurrent refreshes: all waiters share one in-flight call.
    if (this.refreshPromise) {
      return this.refreshPromise;
    }
    if (!this.currentToken?.refreshToken) {
      return this.authenticate();
    }

    this.refreshPromise = (async () => {
      try {
        const res = await fetch(`${this.apiBaseUrl}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refreshToken: this.currentToken!.refreshToken }),
        });

        if (!res.ok) {
          this.currentToken = null;
          return await this.authenticate();
        }

        // Rotation: the server returns a brand-new token + refresh token;
        // we drop the old one in memory immediately.
        const token: SessionToken = await res.json();
        this.currentToken = token;
        return token;
      } finally {
        this.refreshPromise = null;
      }
    })();

    return this.refreshPromise;
  }

  logout(): void {
    this.currentToken = null;
  }

  isAuthenticated(): boolean {
    return this.currentToken !== null && this.isCurrentTokenFresh();
  }
}
