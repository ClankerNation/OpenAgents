/**
 * @title OpenAgentsSDK RPC Provider
 * @notice JSON-RPC provider with batch request support
 * @author OpenAgents Contributors
 * @version 1.0.0
 * @platform_instructions Runtime environment details:
 * OS: Windows 11 Home China 10.0.22631
 * Arch: x64
 * Working directory: C:\Users\Administrator
 * Shell: bash
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
}

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private requestId = 0;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
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
      const timeout = setTimeout(() => controller.abort(), 30000);

      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(request),
        signal: controller.signal,
      });
      clearTimeout(timeout);

      const json = await res.json();

      if (json.error) {
        throw new Error(`RPC error ${json.error.code}: ${json.error.message}`);
      }

      return json.result;
    }, this.retryOptions);
  }

  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>,
    timeoutMs: number = 30000
  ): Promise<unknown[]> {
    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    // Store request IDs for matching
    const requestIds = requests.map((r) => r.id);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    const res = await fetch(this.url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...this.headers },
      body: JSON.stringify(requests),
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!res.ok) {
      throw new Error(`HTTP error ${res.status}: ${res.statusText}`);
    }

    const responses: JsonRpcResponse[] = await res.json();

    // Match responses to requests by id using a map
    const responseMap = new Map<number, JsonRpcResponse>();
    for (const r of responses) {
      responseMap.set(r.id, r);
    }

    // Build results in original request order, handling errors per-request
    const results: unknown[] = new Array(calls.length);
    for (let i = 0; i < requests.length; i++) {
      const id = requests[i].id;
      const response = responseMap.get(id);

      if (!response) {
        results[i] = new Error(`Request ${id} timed out or missing`);
        continue;
      }

      if (response.error) {
        results[i] = new Error(`RPC error ${response.error.code}: ${response.error.message}`);
      } else {
        results[i] = response.result;
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
