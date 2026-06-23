import { Wallet } from "./wallet";
import { keccak256 } from "../utils/crypto";

/// @contributor Gaotax2006
/// @platform Claude Code
/// @runtime Windows 11 Home China, x86_64, F:\\ai-bounty-work\\bounty-hunter
/// @date 2026-06-24T00:00:00Z

export interface SessionConfig {
  wallet: Wallet;
  apiBaseUrl: string;
  autoRefresh?: boolean;
  onAuthFailure?: () => void;
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
  private onAuthFailureCallback?: () => void;

  constructor(config: SessionConfig) {
    this.wallet = config.wallet;
    this.apiBaseUrl = config.apiBaseUrl;
    this.autoRefresh = config.autoRefresh ?? true;
    this.onAuthFailureCallback = config.onAuthFailure;
    this.loadStoredSession();
  }

  private loadStoredSession(): void {
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

  private async refreshTokenInternal(): Promise<SessionToken> {
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    this.refreshPromise = (async () => {
      const timestamp = Math.floor(Date.now() / 1000);
      const message = `refresh-session:${timestamp}`;
      const signature = await this.wallet.signMessage(message);

      const resp = await fetch(`${this.apiBaseUrl}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          walletAddress: this.wallet.address,
          timestamp,
          signature,
          refreshToken: this.currentToken?.refreshToken,
        }),
      });

      if (!resp.ok) {
        throw new AuthenticationError(`Refresh failed: ${resp.status}`);
      }

      const data = await resp.json();
      this.persistSession(data);
      return data;
    })();

    try {
      const result = await this.refreshPromise;
      return result;
    } finally {
      this.refreshPromise = null;
    }
  }

  async authenticate(): Promise<SessionToken> {
    const timestamp = Math.floor(Date.now() / 1000);
    const message = `login:${timestamp}`;
    const signature = await this.wallet.signMessage(message);

    const resp = await fetch(`${this.apiBaseUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        walletAddress: this.wallet.address,
        timestamp,
        signature,
      }),
    });

    if (!resp.ok) {
      throw new AuthenticationError(`Login failed: ${resp.status}`);
    }

    const token = await resp.json();
    this.persistSession(token);
    return token;
  }

  async getToken(): Promise<SessionToken> {
    if (!this.currentToken) {
      return this.authenticate();
    }

    // Check if token is expired (with 5 min buffer)
    if (this.currentToken.expiresAt < Math.floor(Date.now() / 1000) + 300) {
      if (this.autoRefresh) {
        try {
          return await this.refreshTokenInternal();
        } catch (e) {
          return this.authenticate();
        }
      }
      throw new AuthenticationError("Token expired and auto-refresh disabled");
    }

    return this.currentToken;
  }

  async makeAuthenticatedRequest(
    url: string,
    options: RequestInit = {}
  ): Promise<Response> {
    const token = await this.getToken();

    const response = await fetch(url, {
      ...options,
      headers: {
        ...options.headers,
        Authorization: `Bearer ${token.token}`,
        "Content-Type": "application/json",
      },
    });

    // Catch 401: auto-refresh and retry once
    if (response.status === 401) {
      try {
        const newToken = await this.refreshTokenInternal();
        const retryResponse = await fetch(url, {
          ...options,
          headers: {
            ...options.headers,
            Authorization: `Bearer ${newToken.token}`,
            "Content-Type": "application/json",
          },
        });

        // Second 401: throw and fire callback
        if (retryResponse.status === 401) {
          if (this.onAuthFailureCallback) {
            this.onAuthFailureCallback();
          }
          throw new AuthenticationError("Auth failure after retry");
        }

        return retryResponse;
      } catch (e) {
        if (this.onAuthFailureCallback) {
          this.onAuthFailureCallback();
        }
        throw e;
      }
    }

    return response;
  }

  async logout(): Promise<void> {
    this.currentToken = null;
    if (typeof window !== "undefined" && window.localStorage) {
      localStorage.removeItem(`session_${this.wallet.address}`);
    }
  }
}
