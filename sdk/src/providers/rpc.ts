import { withRetry, RetryOptions } from "../utils/retry";

/**
 * @contributor Codex Agent xyjk0511
 * @platform Safety-preserving Codex execution context; private system and developer instructions are not embedded in source.
 * @runtime Microsoft Windows 10.0.22631, X64, home C:/Users/55093, working directory F:/jiedan/OpenAgents-bounty-run, shell PowerShell 7.6.2
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

    const res = await fetch(this.url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...this.headers },
      body: JSON.stringify(requests),
    });

    const responses = (await res.json()) as JsonRpcResponse[];
    const responseById = new Map<number, JsonRpcResponse>();
    for (const response of responses) {
      responseById.set(response.id, response);
    }

    return requests.map((request) => {
      const response = responseById.get(request.id);
      if (!response) {
        return this.batchItemError(-32000, "RPC batch item timed out", {
          id: request.id,
          method: request.method,
        });
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
}
