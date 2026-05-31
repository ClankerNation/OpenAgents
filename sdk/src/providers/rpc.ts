import { withRetry, RetryOptions } from "../utils/retry";

/**
 * @contributor Codex Agent xyjk0511
 * @platform Safety-preserving Codex execution context; private system and developer instructions are not embedded in source.
 * @runtime Microsoft Windows 10.0.22631, X64, redacted local paths, shell PowerShell 7.6.2
 * @date 2026-05-31T00:00:00-07:00
 */

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
  error: {
    code: number;
    message: string;
    data?: unknown;
  };
}

export interface RpcProviderConfig {
  url: string;
  chainId: number;
  retryOptions?: RetryOptions;
  headers?: Record<string, string>;
  batchTimeoutMs?: number;
}

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private batchTimeoutMs: number;
  private requestId = 0;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.batchTimeoutMs = config.batchTimeoutMs ?? 30000;
  }

  async call(method: string, params: unknown[] = []): Promise<unknown> {
    const request: JsonRpcRequest = {
      jsonrpc: "2.0",
      id: ++this.requestId,
      method,
      params,
    };

    return withRetry(async () => {
      // BUG: No timeout — fetch can hang indefinitely if the RPC node is unresponsive
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(request),
      });

      const json = await res.json();

      // BUG: Error response is not type-checked — json.error could have unexpected
      // shape and json.result is returned even when error is present
      if (json.error) {
        throw new Error(`RPC error ${json.error.code}: ${json.error.message}`);
      }

      return json.result;
    }, this.retryOptions);
  }

  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<unknown[]> {
    // BUG: No limit on batch size — sending thousands of calls in one batch
    // can exceed the node's gas/payload limit and fail silently or OOM
    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    let responses: JsonRpcResponse[];
    try {
      responses = await this.withBatchTimeout(async (signal) => {
        const res = await fetch(this.url, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...this.headers },
          body: JSON.stringify(requests),
          signal,
        });

        return (await res.json()) as JsonRpcResponse[];
      });
    } catch (error) {
      if (this.isTimeoutError(error)) {
        return requests.map((request) => this.batchTimeoutError(request));
      }
      throw error;
    }
    const responseById = new Map<number, JsonRpcResponse>();
    for (const response of responses) {
      responseById.set(response.id, response);
    }

    return requests.map((request) => {
      const response = responseById.get(request.id);
      if (!response) {
        return this.batchTimeoutError(request);
      }
      if (response.error) {
        return this.batchItemError(response.error.code, response.error.message, response.error.data);
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

  private batchItemError(
    code: number,
    message: string,
    data?: unknown
  ): JsonRpcBatchItemError {
    return {
      error: {
        code,
        message,
        data,
      },
    };
  }

  private batchTimeoutError(request: JsonRpcRequest): JsonRpcBatchItemError {
    return this.batchItemError(-32000, "RPC batch item timed out", {
      id: request.id,
      method: request.method,
      timeoutMs: this.batchTimeoutMs,
    });
  }

  private async withBatchTimeout<T>(
    operation: (signal: AbortSignal) => Promise<T>
  ): Promise<T> {
    const controller = new AbortController();
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    try {
      return await Promise.race([
        operation(controller.signal),
        new Promise<T>((_resolve, reject) => {
          timeoutId = setTimeout(() => {
            controller.abort();
            reject(new Error("RPC batch request timed out"));
          }, this.batchTimeoutMs);
        }),
      ]);
    } finally {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    }
  }

  private isTimeoutError(error: unknown): boolean {
    return error instanceof Error && (
      error.message === "RPC batch request timed out" ||
      error.name === "AbortError"
    );
  }
}
