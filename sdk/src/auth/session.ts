/**
 * Session management for OpenAgents SDK.
 *
 * @fix-author Claude Fable 5 (Autonomous Agent)
 * @date 2026-08-20
 * @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform_instructions [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
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

  constructor(config: SessionConfig) {
    this.wallet = config.wallet;
    this.apiBaseUrl = config.apiBaseUrl;
    this.autoRefresh = config.autoRefresh ?? true;
    // Tokens are kept in memory only to prevent XSS theft via localStorage
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
    if (this.currentToken && this.currentToken.expiresAt > now) {
      return this.currentToken.token;
    }
    
    // Token is missing or expired, refresh it
    const session = await this.refresh();
    return session.token;
  }

  async refresh(): Promise<SessionToken> {
    // Coalesce concurrent refresh requests to prevent race conditions and token rotation issues
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    this.refreshPromise = (async () => {
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
        // Token rotation: update the stored token with the new refresh token
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
    const now = Math.floor(Date.now() / 1000);
    return this.currentToken !== null && this.currentToken.expiresAt > now;
  }
}
