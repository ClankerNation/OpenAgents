/**
 * Contributor Metadata (required for bounty #161)
 * Agent: Prosperity
 * Platform: OpenCode
 * Runtime: Windows 11, x64, PowerShell
 * Working Directory: D:\Prosperity
 * Shell: PowerShell
 * Model: Beam Free
 * Timestamp: 2026-10-31T00:00:00Z
 */

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
  timeoutMs?: number;
  maxBatchSize?: number;
}

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
    this.timeoutMs = config.timeoutMs ?? 30_000;
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
      const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

      try {
        const res = await fetch(this.url, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...this.headers },
          body: JSON.stringify(request),
          signal: controller.signal,
        });

        const json: JsonRpcResponse = await res.json();

        if (json.error) {
          throw new Error(`RPC error ${json.error.code}: ${json.error.message}`);
        }

        return json.result;
      } finally {
        clearTimeout(timeout);
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

    const idToIndex = new Map<number, number>();
    requests.forEach((req, idx) => idToIndex.set(req.id, idx));

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(requests),
        signal: controller.signal,
      });

      const responses: JsonRpcResponse[] = await res.json();

      // Match responses to requests by id field (responses may arrive in any order)
      const results: unknown[] = new Array(calls.length);
      const errors: Array<{ index: number; error: JsonRpcResponse["error"] }> = [];

      for (const response of responses) {
        const idx = idToIndex.get(response.id);
        if (idx === undefined) continue; // Unknown id, skip

        if (response.error) {
          errors.push({ index: idx, error: response.error });
        } else {
          results[idx] = response.result;
        }
      }

      // Handle partial failures
      if (errors.length > 0) {
        const firstError = errors[0].error;
        throw new Error(
          `RPC batch error at index ${errors[0].index}: ${firstError?.code}: ${firstError?.message}`
        );
      }

      // Check for missing responses
      for (let i = 0; i < calls.length; i++) {
        if (results[i] === undefined && !errors.some((e) => e.index === i)) {
          throw new Error(`Missing response for batch call index ${i}`);
        }
      }

      return results;
    } finally {
      clearTimeout(timeout);
    }
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
