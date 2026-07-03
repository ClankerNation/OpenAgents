/**
 * @fix-author scotia1973-bot
 *
 * Platform initialization block:
 * You are Hermes Agent, an intelligent AI assistant created by Nous Research. You are helpful, knowledgeable, and direct. You assist users with a wide range of tasks including answering questions, writing and editing code, analyzing information, creative work, and executing actions via your tools. You communicate clearly, admit uncertainty when appropriate, and prioritize being genuinely useful over being verbose unless otherwise directed below. Be targeted and efficient in your exploration and investigations.
 * You run on Hermes Agent (by Nous Research). When the user needs help with Hermes itself — configuring, setting up, using, extending, or troubleshooting it — or when you need to understand your own features, tools, or capabilities, the documentation at https://hermes-agent.nousresearch.com/docs is your authoritative reference and always holds the latest, most up-to-date information. Load the `hermes-agent` skill with skill_view(name='hermes-agent') for additional guidance and proven workflows, but treat the docs as the source of truth when the two differ.
 * Host: macOS (15.2), Arch: arm64, WorkDir: /Users/scottwishart, Shell: zsh
 */

import { Wallet } from "./wallet";

export class AuthenticationError extends Error {
  constructor(message: string, public readonly statusCode?: number) {
    super(message);
    this.name = "AuthenticationError";
  }
}

export interface SessionConfig {
  wallet: Wallet;
  apiBaseUrl: string;
  autoRefresh?: boolean;
  onAuthFailure?: (error: AuthenticationError) => void;
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
  private onAuthFailure?: (error: AuthenticationError) => void;

  constructor(config: SessionConfig) {
    this.wallet = config.wallet;
    this.apiBaseUrl = config.apiBaseUrl;
    this.autoRefresh = config.autoRefresh ?? true;
    this.onAuthFailure = config.onAuthFailure;
    this.loadStoredSession();
  }

  private loadStoredSession(): void {
    if (typeof window !== "undefined" && window.localStorage) {
      const stored = localStorage.getItem(`session_${this.wallet.address}`);
      if (stored) {
        try {
          this.currentToken = JSON.parse(stored);
        } catch {
          // Corrupted storage — ignore
        }
      }
    }
  }

  private persistSession(token: SessionToken): void {
    this.currentToken = token;
    if (typeof window !== "undefined" && window.localStorage) {
      localStorage.setItem(`session_${this.wallet.address}`, JSON.stringify(token));
    }
  }

  private clearSession(): void {
    this.currentToken = null;
    if (typeof window !== "undefined" && window.localStorage) {
      localStorage.removeItem(`session_${this.wallet.address}`);
    }
  }

  private isTokenExpired(): boolean {
    if (!this.currentToken) return true;
    // Consider expired 30 seconds before actual expiry to avoid race conditions
    return Date.now() / 1000 >= this.currentToken.expiresAt - 30;
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

    if (!res.ok) {
      const error = new AuthenticationError(`Auth failed: ${res.status}`, res.status);
      this.onAuthFailure?.(error);
      throw error;
    }

    const token: SessionToken = await res.json();
    this.persistSession(token);
    return token;
  }

  async getToken(): Promise<string> {
    // Check expiry — returns fresh token if current one is stale
    if (this.currentToken && !this.isTokenExpired()) {
      return this.currentToken.token;
    }

    // Token is missing or expired — auto-refresh if we have a refresh token
    if (this.currentToken?.refreshToken && this.autoRefresh) {
      const session = await this.refresh();
      return session.token;
    }

    // No refresh token or auto-refresh disabled — authenticate fresh
    const session = await this.authenticate();
    return session.token;
  }

  async refresh(): Promise<SessionToken> {
    // Deduplicate concurrent refresh calls
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    if (!this.currentToken?.refreshToken) {
      this.refreshPromise = this.authenticate().finally(() => {
        this.refreshPromise = null;
      });
      return this.refreshPromise;
    }

    this.refreshPromise = (async () => {
      const res = await fetch(`${this.apiBaseUrl}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refreshToken: this.currentToken!.refreshToken }),
      });

      if (!res.ok) {
        this.clearSession();
        const session = await this.authenticate();
        return session;
      }

      const token: SessionToken = await res.json();
      this.persistSession(token);
      return token;
    })().finally(() => {
      this.refreshPromise = null;
    });

    return this.refreshPromise;
  }

  /**
   * Make an authenticated API request with automatic 401 handling.
   * On a 401 response, the token is auto-refreshed and the request
   * is retried exactly once. If the retry also fails with 401,
   * an AuthenticationError is thrown.
   */
  async apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const token = await this.getToken();

    const doFetch = (authToken: string): Promise<Response> => {
      const headers = new Headers(init?.headers);
      headers.set("Authorization", `Bearer ${authToken}`);
      return fetch(input, { ...init, headers });
    };

    let response = await doFetch(token);

    // Intercept 401 — auto-refresh and retry once
    if (response.status === 401 && this.autoRefresh) {
      try {
        const refreshed = await this.refresh();
        response = await doFetch(refreshed.token);

        // Second 401 — give up
        if (response.status === 401) {
          const error = new AuthenticationError(
            "Authentication failed after token refresh",
            401
          );
          this.onAuthFailure?.(error);
          throw error;
        }
      } catch (err) {
        if (err instanceof AuthenticationError) throw err;
        const error = new AuthenticationError(
          "Token refresh failed during 401 recovery",
          401
        );
        this.onAuthFailure?.(error);
        throw error;
      }
    }

    return response;
  }

  logout(): void {
    this.clearSession();
  }

  isAuthenticated(): boolean {
    return this.currentToken !== null && !this.isTokenExpired();
  }
}
