/**
 * @generated-by
 * name: oocheol
 * timestamp: 2026-05-19T05:00:00Z
 * platform_instructions: Gemini CLI engineering agent. Focus: Non-destructive, idiomatic code modifications, comprehensive testing, and secure credential handling. Follows Research-Strategy-Execution lifecycle.
 * runtime: {"os":"win32","arch":"x64","home_dir":"C:\\Users\\PC","working_dir":"C:\\chromeMCP\\OpenAgents","shell":"powershell"}
 *
 * JSON-RPC provider with batch matching, error handling, and timeout support.
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
  requestTimeoutMs?: number;
  batchSizeLimit?: number;
}

const DEFAULT_TIMEOUT = 10_000; // 10 seconds
const DEFAULT_BATCH_SIZE = 100;

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private requestTimeoutMs: number;
  private batchSizeLimit: number;
  private requestId = 0;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.requestTimeoutMs = config.requestTimeoutMs ?? DEFAULT_TIMEOUT;
    this.batchSizeLimit = config.batchSizeLimit ?? DEFAULT_BATCH_SIZE;
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
      const timeoutId = setTimeout(() => controller.abort(), this.requestTimeoutMs);

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
        clearTimeout(timeoutId);
      }
    }, this.retryOptions);
  }

  /**
   * Sends a batch of JSON-RPC requests.
   * Matches responses to requests by 'id' to handle out-of-order responses.
   * Handles partial failures where some requests in the batch fail.
   */
  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<Array<{ result?: unknown; error?: Error }>> {
    if (calls.length > this.batchSizeLimit) {
      throw new Error(`Batch size exceeds limit of ${this.batchSizeLimit}`);
    }

    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    // Mapping to track request positions for final output ordering
    const idToPosition = new Map<number, number>();
    requests.forEach((req, index) => idToPosition.set(req.id, index));

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.requestTimeoutMs);

    try {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(requests),
        signal: controller.signal,
      });

      const responses: JsonRpcResponse[] = await res.json();
      const results: Array<{ result?: unknown; error?: Error }> = new Array(calls.length);

      // Match responses to requests by ID (JSON-RPC spec allows any order)
      responses.forEach((resp) => {
        const position = idToPosition.get(resp.id);
        if (position !== undefined) {
          if (resp.error) {
            results[position] = { error: new Error(`RPC error ${resp.error.code}: ${resp.error.message}`) };
          } else {
            results[position] = { result: resp.result };
          }
          idToPosition.delete(resp.id);
        }
      });

      // Any IDs remaining in the map had no response
      idToPosition.forEach((position, id) => {
        results[position] = { error: new Error(`No response received for request ID ${id}`) };
      });

      return results;
    } catch (err: any) {
      if (err.name === "AbortError") {
        throw new Error(`Batch request timed out after ${this.requestTimeoutMs}ms`);
      }
      throw err;
    } finally {
      clearTimeout(timeoutId);
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
