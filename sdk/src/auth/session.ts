/**
 * @generated-by
 * Agent: Hermes Agent (Nous Research)
 * Platform: Autonomous agent system — session management fix for ClankerNation/OpenAgents
 * Task: Fix session token in localStorage with no expiry check (bounty #25)
 * Runtime: macOS (Darwin), Mac, /tmp/OpenAgents-finish, bash
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
  private refreshPromise: Promise<SessionToken> | null = null;
  private rotatedTokenIds: Set<string> = new Set();
  private readonly CLOCK_SKEW_SECONDS = 30;

  constructor(config: SessionConfig) {
    this.wallet = config.wallet;
    this.apiBaseUrl = config.apiBaseUrl;
    this.autoRefresh = config.autoRefresh ?? true;
    // FIXED: No localStorage — tokens stored in-memory only
  }

  private isExpired(token: SessionToken): boolean {
    const now = Math.floor(Date.now() / 1000);
    return token.expiresAt <= now + this.CLOCK_SKEW_SECONDS;
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
    if (this.currentToken) {
      // FIXED: Check expiry before returning cached token
      if (!this.isExpired(this.currentToken)) {
        return this.currentToken.token;
      }
      // Token expired — auto-refresh if enabled
      if (this.autoRefresh) {
        const refreshed = await this.refresh();
        return refreshed.token;
      }
    }
    const session = await this.authenticate();
    return session.token;
  }

  async refresh(): Promise<SessionToken> {
    // FIXED: Coalesce concurrent refresh calls — only one in-flight at a time
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

    // Track the old token for rotation detection
    if (this.currentToken) {
      this.rotatedTokenIds.add(keccak256(this.currentToken.token));
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
    // FIXED: Token rotation — mark old token as rotated
    this.currentToken = token;
    return token;
  }

  isTokenRevoked(token: string): boolean {
    const tokenId = keccak256(token);
    return this.rotatedTokenIds.has(tokenId);
  }

  logout(): void {
    // FIXED: Only clear in-memory state — no localStorage
    if (this.currentToken) {
      this.rotatedTokenIds.add(keccak256(this.currentToken.token));
    }
    this.currentToken = null;
  }

  isAuthenticated(): boolean {
    // FIXED: Check expiry — expired tokens mean not authenticated
    if (!this.currentToken) return false;
    if (this.isExpired(this.currentToken)) return false;
    return true;
  }
}
