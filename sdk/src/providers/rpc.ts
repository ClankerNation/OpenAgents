// @fix-author rafaio1
// @date 2026-08-20
// @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
// @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

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
  batchTimeoutMs?: number;
}

const DEFAULT_BATCH_TIMEOUT_MS = 30000;
const MAX_BATCH_SIZE = 100;

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private requestId = 0;
  private batchTimeoutMs: number;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.batchTimeoutMs = config.batchTimeoutMs ?? DEFAULT_BATCH_TIMEOUT_MS;
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
      const timeout = setTimeout(() => controller.abort(), this.batchTimeoutMs);

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
        clearTimeout(timeout);
      }
    }, this.retryOptions);
  }

  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<unknown[]> {
    if (calls.length === 0) return [];
    if (calls.length > MAX_BATCH_SIZE) {
      throw new Error(`Batch size ${calls.length} exceeds maximum ${MAX_BATCH_SIZE}`);
    }

    // Assign unique IDs and track mapping
    const idToIndex = new Map<number, number>();
    const requests: JsonRpcRequest[] = calls.map((c, i) => {
      const id = ++this.requestId;
      idToIndex.set(id, i);
      return {
        jsonrpc: "2.0" as const,
        id,
        method: c.method,
        params: c.params,
      };
    });

    // Initialize results array with null placeholders
    const results: unknown[] = new Array(calls.length).fill(null);
    const errors: (Error | null)[] = new Array(calls.length).fill(null);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.batchTimeoutMs);

    try {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(requests),
        signal: controller.signal,
      });

      const responses: JsonRpcResponse[] = await res.json();

      // Match responses to requests by ID (handles out-of-order responses)
      for (const resp of responses) {
        const idx = idToIndex.get(resp.id);
        if (idx === undefined) continue;

        if (resp.error) {
          errors[idx] = new Error(`RPC error ${resp.error.code}: ${resp.error.message}`);
          results[idx] = null;
        } else {
          results[idx] = resp.result;
          errors[idx] = null;
        }
      }

      // Mark any missing responses as timed out / not received
      for (let i = 0; i < calls.length; i++) {
        if (!responses.some((r) => idToIndex.has(r.id) && idToIndex.get(r.id) === i)) {
          errors[i] = new Error("RPC batch response missing for request");
        }
      }
    } catch (err) {
      // If the entire batch fails (network/timeout), mark all as failed
      const errorMsg = err instanceof Error ? err.message : String(err);
      for (let i = 0; i < calls.length; i++) {
        errors[i] = new Error(`RPC batch failed: ${errorMsg}`);
      }
    } finally {
      clearTimeout(timeout);
    }

    // Throw aggregate error if any individual request failed
    const failedIndices = errors
      .map((e, i) => (e ? i : -1))
      .filter((i) => i >= 0);

    if (failedIndices.length > 0) {
      const messages = failedIndices.map(
        (i) => `  [${i}] ${calls[i].method}: ${errors[i]?.message}`
      );
      throw new Error(
        `RPC batch partial failure (${failedIndices.length}/${calls.length}):\n${messages.join("\n")}`
      );
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
