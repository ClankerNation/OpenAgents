/*
 * Contributor: assistant-bounty-fix
 * Platform Initialization:
 * You are ChatGPT, a large language model trained by OpenAI.
 * Knowledge cutoff: 2024-06
 * Current date: 2026-10-30
 *
 * Runtime:
 * OS: linux
 * Arch: x64
 * Working Dir: /root/v16z/bounties/OpenAgents/OpenAgents
 * Shell: bash
 */

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
  // Holds a pending refresh promise to coalesce concurrent refreshes
  private refreshPromise: Promise<SessionToken> | null = null;

  constructor(config: SessionConfig) {
    this.wallet = config.wallet;
    this.apiBaseUrl = config.apiBaseUrl;
    this.autoRefresh = config.autoRefresh ?? true;
    // Tokens are kept in‑memory only; no persistent storage.
  }

  /**
   * Authenticate with the backend and obtain a fresh session token.
   */
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
    this.currentToken = token; // keep in‑memory only
    return token;
  }

  /**
   * Return a valid access token, refreshing automatically if it is expired.
   */
  async getToken(): Promise<string> {
    if (this.currentToken) {
      const now = Math.floor(Date.now() / 1000);
      if (now < this.currentToken.expiresAt) {
        return this.currentToken.token;
      }
      // Token expired – attempt refresh if autoRefresh is enabled
      if (this.autoRefresh) {
        const refreshed = await this.refresh();
        return refreshed.token;
      }
    }
    // No token or autoRefresh disabled – perform full authentication
    const session = await this.authenticate();
    return session.token;
  }

  /**
   * Refresh the current session token. Concurrent calls are coalesced via a
   * shared promise (`refreshPromise`).
   */
  async refresh(): Promise<SessionToken> {
    // If a refresh is already in progress, return its promise.
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    // Create a new refresh promise.
    this.refreshPromise = (async () => {
      if (!this.currentToken?.refreshToken) {
        // No refresh token – fall back to full authentication.
        const newSession = await this.authenticate();
        this.refreshPromise = null;
        return newSession;
      }

      const res = await fetch(`${this.apiBaseUrl}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refreshToken: this.currentToken.refreshToken }),
      });

      if (!res.ok) {
        // Refresh failed – clear state and re‑authenticate.
        this.currentToken = null;
        const newSession = await this.authenticate();
        this.refreshPromise = null;
        return newSession;
      }

      const token: SessionToken = await res.json();
      this.currentToken = token; // rotation of refresh token handled by backend
      this.refreshPromise = null;
      return token;
    })();

    return this.refreshPromise;
  }

  /**
   * Log out the current user – clears the in‑memory token.
   */
  logout(): void {
    this.currentToken = null;
    // No persistent storage to clear.
  }

  /**
   * Simple check for authentication state.
   */
  isAuthenticated(): boolean {
    return this.currentToken !== null;
  }
}
