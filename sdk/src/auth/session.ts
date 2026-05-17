/**
 * @agent-name opencode-gaotax2006
 * @platform-init You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user. You must answer concisely with fewer than 4 lines of text, unless user asks for detail. Follow the code style and conventions of the codebase. Do not add comments unless the code is non-obvious.
 * @runtime os=win32 arch=x64 working_dir=F:\ai-bounty-work\bounty-hunter\openagents shell=powershell
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
  expiresAt: number;
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
    this.loadStoredSession();
  }

  setAuthFailureHandler(handler: (error: Error) => void): void {
    this.onAuthFailure = handler;
  }

  private loadStoredSession(): void {
    if (typeof window !== "undefined" && window.localStorage) {
      try {
        const stored = localStorage.getItem(`session_${this.wallet.address}`);
        if (stored) this.currentToken = JSON.parse(stored);
      } catch {
        localStorage.removeItem(`session_${this.wallet.address}`);
      }
    }
  }

  private persistSession(token: SessionToken): void {
    this.currentToken = token;
    if (typeof window !== "undefined" && window.localStorage) {
      localStorage.setItem(`session_${this.wallet.address}`, JSON.stringify(token));
    }
  }

  private isExpired(): boolean {
    if (!this.currentToken) return true;
    return Date.now() >= this.currentToken.expiresAt * 1000;
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
      body: JSON.stringify({ address: this.wallet.address, message, signature, timestamp }),
    });

    if (!res.ok) throw new Error(`Auth failed: ${res.status}`);
    const token: SessionToken = await res.json();
    this.persistSession(token);
    return token;
  }

  async getToken(): Promise<string> {
    if (!this.currentToken || this.isExpired()) {
      if (this.currentToken?.refreshToken && this.autoRefresh) {
        return (await this.refresh()).token;
      }
      return (await this.authenticate()).token;
    }
    return this.currentToken.token;
  }

  async refresh(): Promise<SessionToken> {
    if (!this.currentToken?.refreshToken) return this.authenticate();

    if (this.refreshPromise) return this.refreshPromise;

    this.refreshPromise = (async () => {
      const res = await fetch(`${this.apiBaseUrl}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refreshToken: this.currentToken!.refreshToken }),
      });

      if (!res.ok) {
        this.currentToken = null;
        this.refreshPromise = null;
        return this.authenticate();
      }

      const token: SessionToken = await res.json();
      this.persistSession(token);
      this.refreshPromise = null;
      return token;
    })();

    return this.refreshPromise;
  }

  async fetchWithAuth(input: RequestInfo, init?: RequestInit): Promise<Response> {
    const token = await this.getToken();
    const headers = new Headers(init?.headers);
    headers.set("Authorization", `Bearer ${token}`);

    const res = await fetch(input, { ...init, headers });

    if (res.status === 401 && this.autoRefresh) {
      try {
        await this.refresh();
        const newToken = await this.getToken();
        headers.set("Authorization", `Bearer ${newToken}`);
        const retryRes = await fetch(input, { ...init, headers });
        return retryRes;
      } catch (err) {
        this.currentToken = null;
        const authErr = new AuthenticationError("Session expired and refresh failed");
        this.onAuthFailure?.(authErr);
        throw authErr;
      }
    }

    return res;
  }

  logout(): void {
    this.currentToken = null;
    this.refreshPromise = null;
    if (typeof window !== "undefined" && window.localStorage) {
      localStorage.removeItem(`session_${this.wallet.address}`);
    }
  }

  isAuthenticated(): boolean {
    return this.currentToken !== null && !this.isExpired();
  }
}
