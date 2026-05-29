export interface SessionConfig {
  wallet: SessionWallet;
  apiBaseUrl: string;
  autoRefresh?: boolean;
  onAuthFailure?: (error: AuthenticationError) => void | Promise<void>;
}

export interface SessionWallet {
  address: string;
  sendTransaction(tx: {
    to: string;
    value: bigint;
    data: string;
    gasLimit: bigint;
  }): Promise<string>;
}

export interface SessionToken {
  token: string;
  expiresAt: number; // unix timestamp in seconds
  refreshToken: string;
  walletAddress: string;
}

export class AuthenticationError extends Error {
  readonly cause?: unknown;

  constructor(message: string, cause?: unknown) {
    super(message);
    this.name = "AuthenticationError";
    this.cause = cause;
  }
}

export class SessionManager {
  private wallet: SessionWallet;
  private apiBaseUrl: string;
  private autoRefresh: boolean;
  private onAuthFailure?: (error: AuthenticationError) => void | Promise<void>;
  private currentToken: SessionToken | null = null;
  private refreshPromise: Promise<SessionToken> | null = null;

  constructor(config: SessionConfig) {
    this.wallet = config.wallet;
    this.apiBaseUrl = config.apiBaseUrl;
    this.autoRefresh = config.autoRefresh ?? true;
    this.onAuthFailure = config.onAuthFailure;
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
    // BUG: No expiry check — returns the cached token even if it has expired,
    // causing 401 errors on subsequent API calls
    if (this.currentToken) {
      return this.currentToken.token;
    }
    const session = await this.authenticate();
    return session.token;
  }

  async request(input: string, init: RequestInit = {}): Promise<Response> {
    const token = await this.getToken();
    const first = await fetch(this.resolveUrl(input), this.withAuth(init, token));
    if (first.status !== 401) {
      return first;
    }

    if (!this.autoRefresh) {
      throw await this.failAuth("Authentication failed", first);
    }

    let refreshed: SessionToken;
    try {
      refreshed = await this.refresh();
    } catch (error) {
      throw await this.failAuth("Token refresh failed", error);
    }

    const retry = await fetch(this.resolveUrl(input), this.withAuth(init, refreshed.token));
    if (retry.status === 401) {
      throw await this.failAuth("Authentication failed after refresh", retry);
    }

    return retry;
  }

  async fetch(input: string, init: RequestInit = {}): Promise<Response> {
    return this.request(input, init);
  }

  async refresh(): Promise<SessionToken> {
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
        throw new AuthenticationError(`Refresh failed: ${res.status}`, res);
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

  private resolveUrl(input: string): string {
    if (/^https?:\/\//i.test(input)) return input;
    return `${this.apiBaseUrl}${input.startsWith("/") ? "" : "/"}${input}`;
  }

  private withAuth(init: RequestInit, token: string): RequestInit {
    const headers = new Headers(init.headers);
    headers.set("Authorization", `Bearer ${token}`);
    return { ...init, headers };
  }

  private async failAuth(message: string, cause: unknown): Promise<AuthenticationError> {
    const error = cause instanceof AuthenticationError ? cause : new AuthenticationError(message, cause);
    await this.onAuthFailure?.(error);
    return error;
  }
}
