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
  private rotationIntervalMs: number = 30 * 60 * 1000; // rotate every 30 min
  private rotationTimer: ReturnType<typeof setInterval> | null = null;

  constructor(config: SessionConfig) {
    this.wallet = config.wallet;
    this.apiBaseUrl = config.apiBaseUrl;
    this.autoRefresh = config.autoRefresh ?? true;
    // No localStorage load — tokens stay in memory only (XSS-safe)
    if (this.autoRefresh) {
      this.startRotation();
    }
  }

  private startRotation(): void {
    if (this.rotationTimer) clearInterval(this.rotationTimer);
    this.rotationTimer = setInterval(async () => {
      try {
        await this.refresh();
      } catch {
        // Rotation failure is non-fatal; next call will re-authenticate
      }
    }, this.rotationIntervalMs);
  }

  private stopRotation(): void {
    if (this.rotationTimer) {
      clearInterval(this.rotationTimer);
      this.rotationTimer = null;
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

  logout(): void {
    this.stopRotation();
    this.currentToken = null;
    this.refreshPromise = null;
  }

  isAuthenticated(): boolean {
    const now = Math.floor(Date.now() / 1000);
    return this.currentToken !== null && this.currentToken.expiresAt > now;
  }
}
