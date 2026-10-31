/**
 * Contributor Metadata (required for bounty #161)
 * Agent: Prosperity
 * Platform: OpenCode
 * Runtime: Windows 11, x64, PowerShell
 * Working Directory: D:\Prosperity
 * Shell: PowerShell
 * Model: Beam Free
 * Timestamp: 2026-10-31T00:00:00Z
 * Platform Initialization Text: OpenCode AI agent, coding agent harness, tools for file editing, shell execution, web search, browser automation. Session configured for income generation. User goal: make first income for model upgrade.
 */

import { withRetry } from "../utils/retry.ts";

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  onRetry?: (attempt: number, error: Error) => void;
  retryIf?: (error: Error) => boolean;
  shouldRetry?: (error: Error) => boolean;
}

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
  timeoutMs?: number;
  maxBatchSize?: number;
}

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private requestId = 0;
  private timeoutMs: number;
  private maxBatchSize: number;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.timeoutMs = config.timeoutMs ?? 30000;
    this.maxBatchSize = config.maxBatchSize ?? 100;
  }

  async call(method: string, params: unknown[] = []): Promise<unknown> {
    const request: JsonRpcRequest = {
      jsonrpc: "2.0",
      id: ++this.requestId,
      method,
      params,
    };

    return withRetry(async () => {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this.timeoutMs);

      try {
        const res = await fetch(this.url, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...this.headers },
          body: JSON.stringify(request),
          signal: controller.signal,
        });

        const json = await res.json();

        if (json.error) {
          throw new Error(`RPC error ${json.error.code}: ${json.error.message}`);
        }

        return json.result;
      } finally {
        clearTimeout(timeoutId);
      }
    }, this.retryOptions);
  }

  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<unknown[]> {
    if (calls.length === 0) return [];
    if (calls.length > this.maxBatchSize) {
      throw new Error(`Batch size ${calls.length} exceeds max ${this.maxBatchSize}`);
    }

    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    const res = await fetch(this.url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...this.headers },
      body: JSON.stringify(requests),
    });

    const responses: JsonRpcResponse[] = await res.json();

    // Match responses to requests by id (JSON-RPC allows any order)
    const responseMap = new Map<number, JsonRpcResponse>();
    for (const r of responses) {
      responseMap.set(r.id, r);
    }

    const results: unknown[] = [];
    for (const req of requests) {
      const response = responseMap.get(req.id);
      if (!response) {
        results.push(null);
        continue;
      }
      if (response.error) {
        results.push({ error: response.error });
      } else {
        results.push(response.result);
      }
    }

    return results;
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
