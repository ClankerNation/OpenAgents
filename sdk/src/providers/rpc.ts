/**
 * Contributor traceability:
 * Agent: openai-codex-surim0n
 * Platform instructions: Private platform and session initialization instructions are confidential runtime context and are intentionally omitted.
 * Runtime: os=darwin arch=arm64 home_dir=/Users/saurabhsuri working_dir=/tmp/openagents-24 shell=zsh
 * Timestamp: 2026-05-20T11:18:09Z
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

export interface JsonRpcBatchItemError {
  id: number;
  error: { code: number; message: string; data?: unknown };
}

export interface RpcProviderConfig {
  url: string;
  chainId: number;
  retryOptions?: RetryOptions;
  headers?: Record<string, string>;
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 30_000;

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private timeoutMs: number;
  private requestId = 0;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.timeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  }

  async call(method: string, params: unknown[] = []): Promise<unknown> {
    const request: JsonRpcRequest = {
      jsonrpc: "2.0",
      id: ++this.requestId,
      method,
      params,
    };

    return withRetry(async () => {
      const json = await this.postJson<JsonRpcResponse>(
        request,
        this.timeoutMs
      );

      if (json.error) {
        throw new Error(`RPC error ${json.error.code}: ${json.error.message}`);
      }

      return json.result;
    }, this.retryOptions);
  }

  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<Array<unknown | JsonRpcBatchItemError>> {
    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    if (requests.length === 0) {
      return [];
    }

    let responses: JsonRpcResponse[];
    try {
      responses = await this.postJson<JsonRpcResponse[]>(
        requests,
        this.timeoutMs
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return requests.map((request) => this.makeBatchError(
        request,
        -32000,
        message
      ));
    }

    if (!Array.isArray(responses)) {
      return requests.map((request) => this.makeBatchError(
        request,
        -32603,
        "RPC batch response must be an array"
      ));
    }

    const responsesById = new Map<number, JsonRpcResponse>();
    for (const response of responses) {
      if (response && typeof response.id === "number") {
        responsesById.set(response.id, response);
      }
    }

    return requests.map((request) => {
      const response = responsesById.get(request.id);
      if (!response) {
        return this.makeBatchError(
          request,
          -32000,
          `RPC request ${request.id} (${request.method}) timed out after ${this.timeoutMs}ms`
        );
      }

      if (response.error) {
        return {
          id: request.id,
          error: {
            code: response.error.code,
            message: response.error.message,
            data: response.error.data,
          },
        };
      }

      return response.result;
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

  private async postJson<T>(
    body: JsonRpcRequest | JsonRpcRequest[],
    timeoutMs: number
  ): Promise<T> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      return await res.json() as T;
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        throw new Error(`RPC request timed out after ${timeoutMs}ms`);
      }
      throw err;
    } finally {
      clearTimeout(timeout);
    }
  }

  private makeBatchError(
    request: JsonRpcRequest,
    code: number,
    message: string,
    data?: unknown
  ): JsonRpcBatchItemError {
    return {
      id: request.id,
      error: { code, message, data },
    };
  }
}
