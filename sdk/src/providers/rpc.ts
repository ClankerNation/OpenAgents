import { withRetry, RetryOptions } from "../utils/retry";

/**
 * @contributor 0xjc65eth
 * @platform Private system/developer initialization text is not embedded in public source; public reproducibility is provided by commit history, tests, and verification commands.
 * @runtime Darwin arm64, working directory /Users/juliocesar/Documents/Codex/2026-05-24/precisamos-criar-um-firmaware-fork-ou/bounty-work/openagents/OpenAgents, shell zsh
 * @date 2026-05-31
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

export interface JsonRpcBatchError {
  error: { code: number; message: string; data?: unknown };
}

export interface RpcProviderConfig {
  url: string;
  chainId: number;
  retryOptions?: RetryOptions;
  headers?: Record<string, string>;
  timeoutMs?: number;
}

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
    this.timeoutMs = config.timeoutMs ?? 30_000;
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
  ): Promise<Array<unknown | JsonRpcBatchError>> {
    // BUG: No limit on batch size — sending thousands of calls in one batch
    // can exceed the node's gas/payload limit and fail silently or OOM
    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    const timeoutError = (request: JsonRpcRequest): JsonRpcBatchError => ({
      error: {
        code: -32000,
        message: `RPC response timed out for request id ${request.id}`,
      },
    });

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    let responses: JsonRpcResponse[];

    try {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(requests),
        signal: controller.signal,
      });

      responses = await res.json();
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        return requests.map(timeoutError);
      }
      throw err;
    } finally {
      clearTimeout(timeout);
    }

    const responsesById = new Map<number, JsonRpcResponse>();
    for (const response of responses) {
      responsesById.set(response.id, response);
    }

    return requests.map((request) => {
      const response = responsesById.get(request.id);
      if (!response) {
        return timeoutError(request);
      }
      if (response.error) {
        return { error: response.error };
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
}
