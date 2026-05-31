/**
 * @contributor Codex Agent xyjk0511
 * @platform Safety-preserving Codex execution context; private system and developer instructions are not embedded in source.
 * @runtime Microsoft Windows 10.0.22631, X64, redacted local paths, shell PowerShell 7.6.2
 * @date 2026-05-31T00:00:00-07:00
 */

export interface SessionWallet {
  address: string;
  sendTransaction(tx: {
    to: string;
    value: bigint;
    data: string;
    gasLimit: bigint;
  }): Promise<string>;
}

export interface SessionConfig {
  wallet: SessionWallet;
  apiBaseUrl: string;
  autoRefresh?: boolean;
  expirySkewSeconds?: number;
}

export interface SessionToken {
  token: string;
  expiresAt: number; // unix timestamp in seconds
  refreshToken: string;
  walletAddress: string;
}

export class SessionManager {
  private wallet: SessionWallet;
  private apiBaseUrl: string;
  private autoRefresh: boolean;
  private expirySkewSeconds: number;
  private currentToken: SessionToken | null = null;
  private refreshPromise: Promise<SessionToken> | null = null;

  constructor(config: SessionConfig) {
    this.wallet = config.wallet;
    this.apiBaseUrl = config.apiBaseUrl;
    this.autoRefresh = config.autoRefresh ?? true;
    this.expirySkewSeconds = config.expirySkewSeconds ?? 30;
  }

  private persistSession(token: SessionToken): void {
    this.currentToken = token;
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
    if (!this.currentToken) {
      const session = await this.authenticate();
      return session.token;
    }

    if (!this.isExpired(this.currentToken)) {
      return this.currentToken.token;
    }

    const session = this.autoRefresh ? await this.refresh() : await this.authenticate();
    return session.token;
  }

  async refresh(): Promise<SessionToken> {
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    this.refreshPromise = this.performRefresh().finally(() => {
      this.refreshPromise = null;
    });

    return this.refreshPromise;
  }

  private async performRefresh(): Promise<SessionToken> {
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
      return this.authenticate();
    }

    const token: SessionToken = await res.json();
    this.persistSession(token);
    return token;
  }

  logout(): void {
    this.currentToken = null;
  }

  isAuthenticated(): boolean {
    return this.currentToken !== null && !this.isExpired(this.currentToken);
  }

  private isExpired(token: SessionToken): boolean {
    const now = Math.floor(Date.now() / 1000);
    return token.expiresAt <= now + this.expirySkewSeconds;
  }
}
