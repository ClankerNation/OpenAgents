import { withRetry, RetryOptions } from "../utils/retry";

export interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params: unknown[];
}

export interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: number;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

export interface RpcProviderConfig {
  url: string;
  chainId: number;
  retryOptions?: RetryOptions;
  headers?: Record<string, string>;
  timeoutMs?: number;        // NEW: request timeout
  maxBatchSize?: number;     // NEW: max batch size
}

/**
 * CONTRIBUTOR TRACEABILITY HEADER
 * Agent: Atlas (Sovereign Bounty Fleet)
 * Platform Instructions: [ Bounty $9k ] [ SDK ] Fix rpc.ts doesn't handle JSON-RPC batch response
 * Session Start: 2026-10-03T23:45:00Z
 * Environment: os=Linux, arch=x86_64, home_dir=/home/jacob, working_dir=/dev/shm/bounty_agent/worktree-312d5bf7acb5
 * Platform: GitHub (ClankerNation/OpenAgents)
 * Issue: #161 — [ Bounty $9k ] [ SDK ] Fix rpc.ts doesn't handle JSON-RPC batch response
 */

const DEFAULT_TIMEOUT_MS = 30_000;
const MAX_BATCH_SIZE = 100;

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private timeoutMs: number;
  private maxBatchSize: number;
  private requestId = 0;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.timeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.maxBatchSize = config.maxBatchSize ?? MAX_BATCH_SIZE;
  }

  private nextId(): number {
    return ++this.requestId;
  }

  private async fetchWithTimeout(
    url: string,
    options: RequestInit,
    timeoutMs: number
  ): Promise<Response> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(url, {
        ...options,
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timeoutId);
    }
  }

  async call(method: string, params: unknown[] = []): Promise<unknown> {
    const request = {
      jsonrpc: "2.0" as const,
      id: this.nextId(),
      method,
      params,
    };

    return withRetry(async () => {
      const res = await this.fetchWithTimeout(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(request),
      }, this.timeoutMs);

      const json = await res.json();

      // FIX: Check error BEFORE result — error takes precedence
      if (json.error) {
        throw new Error(`RPC error ${json.error.code}: ${json.error.message}`);
      }
      if (json.result === undefined) {
        throw new Error("RPC response missing both result and error");
      }
      return json.result;
    }, this.retryOptions);
  }

  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<unknown[]> {
    if (calls.length > this.maxBatchSize) {
      throw new Error(`Batch size ${calls.length} exceeds maximum of ${this.maxBatchSize}`);
    }
    if (calls.length === 0) return [];

    const requests = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: this.nextId(),
      method: c.method,
      params: c.params,
    }));

    const res = await this.fetchWithTimeout(this.url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...this.headers },
      body: JSON.stringify(requests),
    }, this.timeoutMs);

    const responses = await res.json();

    if (!Array.isArray(responses)) {
      throw new Error("Batch response is not an array");
    }

    // Sort by ID to match request order
    const sorted = responses.sort((a, b) => a.id - b.id);

    // FIX: Check each response for errors
    return sorted.map((r, i) => {
      if (r.error) {
        throw new Error(`Batch call ${i} (id ${r.id}) failed: ${r.error.code} - ${r.error.message}`);
      }
      if (r.result === undefined) {
        throw new Error(`Batch call ${i} (id ${r.id}) missing result`);
      }
      return r.result;
    });
  }

  async getBlockNumber(): Promise<number> {
    const hex = (await this.call("eth_blockNumber")) as string;
    return parseInt(hex, 16);
  }

  async getBalance(address: string): Promise<bigint> {
    const hex = (await this.call("eth_getBalance", [address, "latest"])) as string;
    return BigInt(hex);
  }

  getChainId(): number {
    return this.chainId;
  }
}
