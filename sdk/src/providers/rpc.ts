/**
 * Contributor: Feltchy
 * Platform initialization: OpenClaw Gateway — agent=main, channel=whatsapp, model=deepseek-v4-pro
 * Runtime: Linux 6.6.114.1-microsoft-standard-WSL2 (x64), node=v22.22.2, bash, workspace=/home/owner/.openclaw/workspace
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
  readonly requestId: number;
  readonly method: string;
  readonly code?: number;
  readonly data?: unknown;

  constructor(
    request: JsonRpcRequest,
    message: string,
    options: { code?: number; data?: unknown } = {}
  ) {
    super(message);
    this.name = "JsonRpcBatchItemError";
    this.requestId = request.id;
    this.method = request.method;
    this.code = options.code;
    this.data = options.data;
  }
}

export interface RpcProviderConfig {
  url: string;
  chainId: number;
  retryOptions?: RetryOptions;
  headers?: Record<string, string>;
  requestTimeoutMs?: number;
}

export interface BatchCallOptions {
  timeoutMs?: number;
}

const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;
const BATCH_SIZE_LIMIT = 100;

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private requestTimeoutMs: number;
  private requestId = 0;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.requestTimeoutMs = config.requestTimeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;
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
    calls: Array<{ method: string; params: unknown[] }>,
    options?: BatchCallOptions
  ): Promise<unknown[]> {
    if (calls.length === 0) {
      return [];
    }

    if (calls.length > BATCH_SIZE_LIMIT) {
      throw new Error(
        `Batch size ${calls.length} exceeds limit of ${BATCH_SIZE_LIMIT}`
      );
    }

    const timeoutMs = options?.timeoutMs ?? this.requestTimeoutMs;

    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    // Time the entire batch fetch
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    let rawResponses: JsonRpcResponse[];
    try {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(requests),
        signal: controller.signal,
      });

      rawResponses = await res.json();
    } catch (err: unknown) {
      clearTimeout(timeout);
      // Entire batch failed — return per-item errors
      const isTimeout = (err as Error)?.name === "AbortError";
      const message = isTimeout
        ? `Batch request timed out after ${timeoutMs}ms`
        : `Batch fetch failed: ${(err as Error).message}`;
      return requests.map(
        (req) =>
          new JsonRpcBatchItemError(req, message, {
            code: isTimeout ? -32000 : -32603,
          })
      );
    } finally {
      clearTimeout(timeout);
    }

    // Index responses by id (first response per id wins if duplicate)
    const responseById = new Map<number, JsonRpcResponse>();
    for (const r of rawResponses) {
      if (!responseById.has(r.id)) {
        responseById.set(r.id, r);
      }
    }

    // Map each request to its result, preserving original order
    return requests.map((req) => {
      const resp = responseById.get(req.id);

      if (!resp) {
        return new JsonRpcBatchItemError(
          req,
          `No response for request id ${req.id}`,
          { code: -32000 }
        );
      }

      if (resp.error) {
        return new JsonRpcBatchItemError(
          req,
          resp.error.message,
          { code: resp.error.code, data: resp.error.data }
        );
      }

      return resp.result;
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
