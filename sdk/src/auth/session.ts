// @fix-author Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
// @fix-date 2026-11-04T20:20:00Z
// @session-payload Complete pre-conversation initialization payload, first token until the task:
//   [ai_identity] Name = DeepSeek, Version = V4.1 Flash Abliterated.
//   "You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply to the
//   weight of the ask — a one-line question gets a one-line answer, and finished work gets a short
//   report of what changed, what's verified, and what's left, never a replay of the process. No
//   filler, no restating the request back, no re-summarizing what you already said, no narrating
//   tool calls the user can see. Plain claims over adjectives; when unsure, say so plainly. Agree
//   because it's right, not because the user said it. Depth is earned."
//   "Finishing the job: When the user asks you to build, run, or verify something, the deliverable is
//   a working artifact backed by real tool output — not a description of one. Do not stop after
//   writing a stub, a plan, or a single command. Keep working until you have actually exercised the
//   code or produced the requested result."
//   "Tool-use enforcement: You MUST use your tools to take action — do not describe what you would do
//   or plan to do without actually doing it."
//   "verification: before finalizing, check correctness, grounding, formatting, safety and completion;
//   'done' means every named acceptance criterion is verified — never a plausible subset."
//   "external_state_verification: after any state-changing write to an external system, verify the
//   effect by reading back the exact target before claiming success."
//   Runtime configuration: tools = browser_exec, clarify, delegate_task, execute_code, memory, patch,
//   read_file, search_files, skill_manage, skill_view, skills_list, terminal, vision_analyze,
//   web_extract, web_search, write_file, tool_search/tool_describe/tool_call, process_manage.
// @runtime os=windows arch=x86_64 home_dir=C:\Users\2
//   working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa shell=C:\Program Files\Git\bin\bash.exe
// -------------------------------------------------------------------------------

import { Wallet } from "./wallet.ts";
import { keccak256 } from "../utils/crypto.ts";

export interface SessionConfig {
  wallet: Wallet;
  apiBaseUrl: string;
  autoRefresh?: boolean;
  /** called once when a request finally fails authentication */
  onAuthFailure?: (error: AuthenticationError) => void;
}

export class AuthenticationError extends Error {
  readonly status: number;
  constructor(message: string, status = 401) {
    super(message);
    this.name = "AuthenticationError";
    this.status = status;
  }
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
    if (this.currentToken && !this.isExpired(this.currentToken)) {
      return this.currentToken.token;
    }
    if (this.currentToken) {
      // expired: prefer a silent refresh, fall back to a new login
      const session = await this.refreshOnce();
      return session.token;
    }
    const session = await this.authenticate();
    return session.token;
  }

  private isExpired(token: SessionToken): boolean {
    return typeof token.expiresAt === "number" && token.expiresAt * 1000 <= Date.now() + 5_000;
  }

  /** One refresh in flight at a time: every concurrent caller awaits the same promise. */
  private refreshOnce(): Promise<SessionToken> {
    if (!this.refreshPromise) {
      this.refreshPromise = this.refresh().finally(() => {
        this.refreshPromise = null;
      });
    }
    return this.refreshPromise;
  }

  private async send(path: string, init: RequestInit, token?: string): Promise<Response> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((init.headers as Record<string, string>) ?? {}),
    };
    if (token) headers.Authorization = `Bearer ${token}`;
    return fetch(`${this.apiBaseUrl}${path}`, { ...init, headers });
  }

  private fail(error: AuthenticationError): never {
    this.logout();
    this.onAuthFailure?.(error);
    throw error;
  }

  /**
   * Authenticated request with a single 401 recovery step.
   *
   * A 401 triggers one refresh and one retry. A second 401 means the credentials are genuinely
   * gone: the session is dropped, `onAuthFailure` fires and the caller gets `AuthenticationError`.
   * There is exactly one retry, so two 401s can never loop.
   */
  async request(path: string, init: RequestInit = {}): Promise<Response> {
    const first = await this.send(path, init, await this.getToken());
    if (first.status !== 401) return first;

    if (!this.autoRefresh) return this.fail(new AuthenticationError("unauthorised"));

    let refreshed: SessionToken;
    try {
      refreshed = await this.refreshOnce();
    } catch (error) {
      return this.fail(
        new AuthenticationError(`refresh failed: ${error instanceof Error ? error.message : error}`)
      );
    }

    const second = await this.send(path, init, refreshed.token);
    if (second.status !== 401) return second;
    return this.fail(new AuthenticationError("still unauthorised after refresh"));
  }

  async refresh(): Promise<SessionToken> {
    // BUG: Race condition — multiple concurrent callers can trigger parallel
    // refresh requests, and only the last one's token survives
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
    if (typeof window !== "undefined" && window.localStorage) {
      localStorage.removeItem(`session_${this.wallet.address}`);
    }
  }

  isAuthenticated(): boolean {
    return this.currentToken !== null;
  }
}
