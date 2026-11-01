/**
 * Agent: assistant
 * Platform Instructions: You are ChatGPT, a large language model trained by OpenAI.
 * Knowledge cutoff: 2024-06
 * Current date: 2026-11-01
 * Runtime: OS=linux, Arch=x64, Working Dir=/root/oss-bounty/OpenAgents/OpenAgents, Shell=bash
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

export class JsonRpcBatchItemError extends Error {
  public readonly id: number;
  public readonly rpcError: { code: number; message: string; data?: unknown };
  constructor(id: number, rpcError: { code: number; message: string; data?: unknown }) {
    super(`JSON-RPC batch item ${id} error ${rpcError.code}: ${rpcError.message}`);
    this.id = id;
    this.rpcError = rpcError;
  }
}

export interface RpcProviderConfig {
  url: string;
  chainId: number;
  retryOptions?: RetryOptions;
  headers?: Record<string, string>;
  /**
   * Timeout in milliseconds for each RPC request (including batch calls).
   * If the request does not complete within this time, it is aborted and treated as an error.
   */
  requestTimeoutMs?: number;
}

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private requestId = 0;
  private requestTimeoutMs: number;
  private static readonly BATCH_SIZE_LIMIT = 100;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.requestTimeoutMs = config.requestTimeoutMs ?? 10_000; // default 10 seconds
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
      const timeout = setTimeout(() => controller.abort(), this.requestTimeoutMs);
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
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<unknown[]> {
    if (calls.length > RpcProvider.BATCH_SIZE_LIMIT) {
      throw new Error(
        `Batch size limit exceeded: ${calls.length} > ${RpcProvider.BATCH_SIZE_LIMIT}`
      );
    }

    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    // Map request id to its original index
    const idToIndex = new Map<number, number>();
    requests.forEach((req, idx) => idToIndex.set(req.id, idx));

    const results: unknown[] = new Array(calls.length);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.requestTimeoutMs);
    let rawResponses: JsonRpcResponse[];
    try {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(requests),
        signal: controller.signal,
      });
      clearTimeout(timeout);
      rawResponses = (await res.json()) as JsonRpcResponse[];
    } catch (e) {
      // If the fetch aborts or fails, treat every item as a timeout error
      for (let i = 0; i < calls.length; i++) {
        results[i] = new JsonRpcBatchItemError(-1, {
          code: -32000,
          message: "Request timed out",
        });
      }
      return results;
    }

    // Process each response, matching by id
    for (const resp of rawResponses) {
      const idx = idToIndex.get(resp.id);
      if (idx === undefined) {
        // Unknown id – ignore
        continue;
      }
      if (resp.error) {
        results[idx] = new JsonRpcBatchItemError(resp.id, resp.error);
      } else {
        results[idx] = resp.result;
      }
      // Remove matched id so we can detect missing ones later
      idToIndex.delete(resp.id);
    }

    // Any ids left in the map did not receive a response – treat as timeout
    for (const missingId of idToIndex.keys()) {
      const idx = idToIndex.get(missingId)!;
      results[idx] = new JsonRpcBatchItemError(missingId, {
        code: -32000,
        message: "Response timed out",
      });
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
