/**
 * @contributor rafaio1
 * @timestamp 2026-08-20T00:00:00Z
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
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
  batchTimeoutMs?: number;
  maxBatchSize?: number;
}

const DEFAULT_BATCH_TIMEOUT_MS = 30000;
const DEFAULT_MAX_BATCH_SIZE = 100;

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private requestId = 0;
  private batchTimeoutMs: number;
  private maxBatchSize: number;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.batchTimeoutMs = config.batchTimeoutMs ?? DEFAULT_BATCH_TIMEOUT_MS;
    this.maxBatchSize = config.maxBatchSize ?? DEFAULT_MAX_BATCH_SIZE;
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

    // Enforce max batch size to prevent node OOM/payload limit issues
    if (calls.length > this.maxBatchSize) {
      throw new Error(
        `Batch size ${calls.length} exceeds maximum ${this.maxBatchSize}`
      );
    }

    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    // Build a map from request id -> index for O(1) response matching
    const idToIndex = new Map<number, number>();
    for (let i = 0; i < requests.length; i++) {
      idToIndex.set(requests[i].id, i);
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.batchTimeoutMs);

    let responses: JsonRpcResponse[];
    try {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(requests),
        signal: controller.signal,
      });

      const raw = await res.json();

      // Handle case where node returns single error instead of array
      if (!Array.isArray(raw)) {
        if (raw.error) {
          throw new Error(
            `RPC batch error ${raw.error.code}: ${raw.error.message}`
          );
        }
        throw new Error("Unexpected non-array batch response");
      }

      responses = raw as JsonRpcResponse[];
    } catch (err: any) {
      if (err.name === "AbortError") {
        throw new Error(
          `Batch RPC request timed out after ${this.batchTimeoutMs}ms`
        );
      }
      throw err;
    } finally {
      clearTimeout(timeout);
    }

    // Match responses to requests by id field (JSON-RPC spec allows any order)
    const results: unknown[] = new Array(requests.length);
    const matched = new Set<number>();

    for (const response of responses) {
      const idx = idToIndex.get(response.id);
      if (idx !== undefined) {
        matched.add(response.id);
        if (response.error) {
          // Individual failure: store error object instead of throwing
          // This allows partial batch success
          results[idx] = {
            __rpcError: true,
            code: response.error.code,
            message: response.error.message,
            data: response.error.data,
          };
        } else {
          results[idx] = response.result;
        }
      }
    }

    // Fill unmatched request slots with timeout/error indicator
    for (const req of requests) {
      if (!matched.has(req.id)) {
        const idx = idToIndex.get(req.id)!;
        results[idx] = {
          __rpcError: true,
          code: -32000,
          message: "Response missing from batch (possible timeout or node error)",
        };
      }
    }

    return results;
  }

  async getBlockNumber(): Promise<number> {
    const hex = (await this.call("eth_blockNumber")) as string;
    return parseInt(hex, 16);
  }

  async getBalance(address: string): Promise<bigint> {
    const hex = (await this.call("eth_getBalance", [
      address,
      "latest",
    ])) as string;
    return BigInt(hex);
  }

  getChainId(): number {
    return this.chainId;
  }
}
