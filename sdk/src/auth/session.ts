/**
 * Contributor Metadata (required for bounty #135)
 * Agent: Prosperity
 * Platform: OpenCode
 * Runtime: Windows 11, x64, PowerShell
 * Working Directory: D:\Prosperity
 * Shell: PowerShell
 * Model: Beam Free
 * Timestamp: 2026-10-31T00:00:00Z
 * Platform Initialization Text: OpenCode AI agent, coding agent harness, tools for file editing, shell execution, web search, browser automation. Session configured for income generation. User goal: make first income for model upgrade.
 */

export interface WalletLike {
  address: string;
  sendTransaction: (tx: any) => Promise<string>;
}

export interface SessionConfig {
  wallet: WalletLike;
  apiBaseUrl: string;
  autoRefresh?: boolean;
}

export interface SessionToken {
  token: string;
  expiresAt: number; // unix timestamp in seconds
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
  private wallet: WalletLike;
  private apiBaseUrl: string;
  private autoRefresh: boolean;
  private currentToken: SessionToken | null = null;
  private refreshPromise: Promise<SessionToken> | null = null;

  constructor(config: SessionConfig) {
    this.wallet = config.wallet;
    this.apiBaseUrl = config.apiBaseUrl;
    this.autoRefresh = config.autoRefresh ?? true;
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

    if (!res.ok) throw new AuthenticationError(`Auth failed: ${res.status}`);
    const token: SessionToken = await res.json();
    this.currentToken = token;
    return token;
  }

  isTokenExpired(token: SessionToken): boolean {
    const now = Math.floor(Date.now() / 1000);
    // Refresh 30 seconds before expiry
    return token.expiresAt <= now + 30;
  }

  async getToken(): Promise<string> {
    if (this.currentToken && !this.isTokenExpired(this.currentToken)) {
      return this.currentToken.token;
    }
    if (this.currentToken && this.isTokenExpired(this.currentToken)) {
      try {
        const refreshed = await this.refresh();
        return refreshed.token;
      } catch {
        const session = await this.authenticate();
        return session.token;
      }
    }
    const session = await this.authenticate();
    return session.token;
  }

  async refresh(): Promise<SessionToken> {
    // Deduplicate concurrent refresh calls
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    this.refreshPromise = this.doRefresh();
    try {
      const result = await this.refreshPromise;
      return result;
    } finally {
      this.refreshPromise = null;
    }
  }

  private async doRefresh(): Promise<SessionToken> {
    if (!this.currentToken?.refreshToken) {
      return this.authenticate();
    }

    const res = await fetch(`${this.apiBaseUrl}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refreshToken: this.currentToken.refreshToken }),
    });

    if (!res.ok) {
      this.currentToken = null;
      throw new AuthenticationError(`Refresh failed: ${res.status}`);
    }

    const token: SessionToken = await res.json();
    this.currentToken = token;
    return token;
  }

  async request(url: string, options: RequestInit = {}): Promise<Response> {
    const token = await this.getToken();
    const headers = new Headers(options.headers);
    headers.set("Authorization", `Bearer ${token}`);

    let res = await fetch(url, { ...options, headers });

    if (res.status === 401 && this.autoRefresh) {
      try {
        await this.refresh();
        const newToken = await this.getToken();
        headers.set("Authorization", `Bearer ${newToken}`);
        res = await fetch(url, { ...options, headers });
      } catch {
        throw new AuthenticationError("Session expired and refresh failed");
      }
      if (res.status === 401) {
        throw new AuthenticationError("Authentication failed after refresh");
      }
    }

    return res;
  }

  logout(): void {
    this.currentToken = null;
    this.refreshPromise = null;
  }

  isAuthenticated(): boolean {
    return this.currentToken !== null && !this.isTokenExpired(this.currentToken);
  }
}
