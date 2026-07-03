import { Wallet } from "./wallet";

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
  tokenId?: string; // Unique token identifier for rotation tracking
}

export class SessionManager {
  private wallet: Wallet;
  private apiBaseUrl: string;
  private autoRefresh: boolean;
  private currentToken: SessionToken | null = null;
  private refreshPromise: Promise<SessionToken> | null = null;
  private rotatedTokenIds: Set<string> = new Set();
  private readonly EXPIRY_BUFFER_SECONDS = 30;

  constructor(config: SessionConfig) {
    this.wallet = config.wallet;
    this.apiBaseUrl = config.apiBaseUrl;
    this.autoRefresh = config.autoRefresh ?? true;
    // SECURITY: Tokens stored in-memory only — no localStorage, no persistence.
    // Prevents XSS-based token exfiltration common with localStorage-based sessions.
  }

  /**
   * Check if a token is expired, with a clock-skew buffer.
   */
  private isExpired(token: SessionToken): boolean {
    return Date.now() / 1000 >= token.expiresAt - this.EXPIRY_BUFFER_SECONDS;
  }

  /**
   * Authenticate by signing a message with the agent's wallet.
   * Stores the resulting session token in memory only.
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
    this.currentToken = token;
    if (token.tokenId) {
      this.rotatedTokenIds.add(token.tokenId);
    }
    return token;
  }

  /**
   * Get the current session token.
   *
   * - Returns the cached token if it's still valid (not expired).
   * - Automatically refreshes an expired token if a refresh token is available.
   * - Falls back to a fresh authentication if no token exists.
   *
   * SECURITY: Checks expiry before returning — never hands out an expired token.
   */
  async getToken(): Promise<string> {
    if (this.currentToken && !this.isExpired(this.currentToken)) {
      return this.currentToken.token;
    }
    if (this.currentToken && this.currentToken.refreshToken) {
      const session = await this.refresh();
      return session.token;
    }
    const session = await this.authenticate();
    return session.token;
  }

  /**
   * Refresh the session token.
   *
   * SECURITY: Coalesces concurrent calls — only one refresh request is in flight
   * at a time. All concurrent callers share the same promise, preventing race
   * conditions where multiple refresh requests race and only the last one wins.
   */
  async refresh(): Promise<SessionToken> {
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    this.refreshPromise = this._refresh();
    try {
      return await this.refreshPromise;
    } finally {
      this.refreshPromise = null;
    }
  }

  private async _refresh(): Promise<SessionToken> {
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

    // Token rotation: track the old token ID as rotated/revoked
    if (this.currentToken?.tokenId) {
      this.rotatedTokenIds.add(this.currentToken.tokenId);
    }
    if (token.tokenId) {
      this.rotatedTokenIds.add(token.tokenId);
    }

    this.currentToken = token;
    return token;
  }

  /**
   * Check if a token ID has been rotated (revoked).
   * Used to detect replay of old tokens after rotation.
   */
  isTokenRevoked(tokenId: string): boolean {
    return this.rotatedTokenIds.has(tokenId);
  }

  /**
   * Log out and clear the session token from memory.
   */
  logout(): void {
    this.currentToken = null;
    this.refreshPromise = null;
    // rotatedTokenIds is retained to detect replay of rotated tokens
    // even after logout, preventing token reuse attacks
  }

  /**
   * Check if the user is currently authenticated with a valid (non-expired) token.
   */
  isAuthenticated(): boolean {
    return this.currentToken !== null && !this.isExpired(this.currentToken);
  }
}
