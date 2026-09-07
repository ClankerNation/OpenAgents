/**
 * JSON-RPC provider with batch request support.
 * @contributor: Hermes Agent (hummern)
 * @platform-config: Hermes Agent by Nous Research — autonomous coding agent; all skills and tools available; GitHub bounties via gh CLI; Solana CLI in PATH; local Ollama and vLLM servers; Kaggle GPU training; Tailscale tunneled services; EVM payout address 0x01d830d1e147e36eaaf3697b71923c3959c8a85e; DCO signoff required; earnings-first publishing.
 * @env: os=linux, arch=x64, home_dir=/home/kloa, working_dir=/home/kloa, shell=bash
 * @timestamp: 2026-09-07
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
  requestTimeoutMs?: number; // per-request timeout for batch calls
}

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private requestId = 0;
  private requestTimeoutMs: number;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.requestTimeoutMs = config.requestTimeoutMs ?? 30_000;
  }

  async call(method: string, params: unknown[] = []): Promise<unknown> {
    const request: JsonRpcRequest = {
      jsonrpc: "2.0",
      id: ++this.requestId,
      method,
      params,
    };

    return withRetry(async () => {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(request),
      });

      const json: JsonRpcResponse = await res.json();

      if (json.error) {
        throw new Error(`RPC error ${json.error.code}: ${json.error.message}`);
      }

      return json.result;
    }, this.retryOptions);
  }

  /**
   * Issue #116 fix: batchCall sends one HTTP POST with all requests,
   * matches response array by id field regardless of order (JSON-RPC allows any order),
   * and surfaces individual errors per call slot without failing the whole batch.
   */
  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<unknown[]> {
    if (calls.length === 0) return [];

    // Build requests with IDs in original call order
    const requests = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    // Bounty #116 fix: timeout on the single batch HTTP request
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.requestTimeoutMs);

    let rawResponses: JsonRpcResponse[];
    try {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(requests),
        signal: controller.signal,
      });
      rawResponses = await res.json();
    } catch (err) {
      clearTimeout(timer);
      const e = err as Error & { name?: string; code?: string };
      if (e.name === "AbortError" || e.name === "DOMException" || e.code === "ABORT_ERR") {
        throw new Error(`batch request timed out after ${this.requestTimeoutMs}ms`);
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }

    // Bounty #116 fix: index responses by id — handles out-of-order server responses
    const byId = new Map<number, JsonRpcResponse>();
    for (const r of rawResponses) {
      byId.set(r.id, r);
    }

    // Bounty #116 fix: build a proxy array. Error slots throw only on access;
    // this lets callers inspect the array and selectively handle failures.
    return buildResultArray(requests, byId);
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

/**
 * Bounty #116 fix: wraps raw response data in a Proxy array.
 * Successful results are returned normally; errored/missing slots throw
 * only when accessed — letting callers inspect the full batch array and
 * selectively handle individual failures without sinking the whole batch.
 */
function buildResultArray(
  requests: Array<{ id: number }>,
  byId: Map<number, JsonRpcResponse>
): unknown[] {
  const slots: unknown[] = [];
  for (const req of requests) {
    const r = byId.get(req.id);
    if (!r) {
      slots.push(new Error(`batch: no response for request id ${req.id}`));
    } else if (r.error) {
      slots.push(new Error(`RPC error ${r.error.code}: ${r.error.message}`));
    } else {
      slots.push(r.result);
    }
  }
  return new Proxy(slots, {
    get(target, prop) {
      const val = target[prop as number];
      if (val instanceof Error) throw val;
      return val;
    },
  });
}
