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
  timeoutMs?: number;
  maxBatchSize?: number;
  maxBatchGas?: bigint;
}

export class RpcProviderError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

export class RpcTimeoutError extends RpcProviderError {}
export class RpcHttpError extends RpcProviderError {
  constructor(public readonly status: number, message: string) {
    super(message);
  }
}
export class RpcResponseError extends RpcProviderError {
  constructor(public readonly code: number, message: string, public readonly data?: unknown) {
    super(`RPC error ${code}: ${message}`);
  }
}
export class RpcBatchLimitError extends RpcProviderError {}

const DEFAULT_TIMEOUT_MS = 30_000;
const DEFAULT_MAX_BATCH_SIZE = 100;
const DEFAULT_MAX_BATCH_GAS = 30_000_000n;
const GAS_LIKE_METHODS = new Set([
  "eth_estimateGas",
  "eth_call",
  "eth_sendRawTransaction",
  "eth_sendTransaction",
]);

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private timeoutMs: number;
  private maxBatchSize: number;
  private maxBatchGas: bigint;
  private requestId = 0;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.timeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.maxBatchSize = config.maxBatchSize ?? DEFAULT_MAX_BATCH_SIZE;
    this.maxBatchGas = config.maxBatchGas ?? DEFAULT_MAX_BATCH_GAS;
  }

  async call(method: string, params: unknown[] = []): Promise<unknown> {
    const request: JsonRpcRequest = {
      jsonrpc: "2.0",
      id: ++this.requestId,
      method,
      params,
    };

    return withRetry(async () => {
      const json = await this.postJson<JsonRpcResponse>(request);
      this.assertJsonRpcResponse(json, request.id);
      return json.result;
    }, this.retryOptions);
  }

  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<unknown[]> {
    this.validateBatch(calls);

    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    return withRetry(async () => {
      const responses = await this.postJson<JsonRpcResponse[]>(requests);
      if (!Array.isArray(responses)) {
        throw new RpcProviderError("RPC batch response must be an array");
      }

      const byId = new Map<number, JsonRpcResponse>();
      for (const response of responses) {
        this.assertJsonRpcResponse(response);
        byId.set(response.id, response);
      }

      return requests.map((request) => {
        const response = byId.get(request.id);
        if (!response) {
          throw new RpcProviderError(`Missing RPC response for request ${request.id}`);
        }
        return response.result;
      });
    }, this.retryOptions);
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

  private async postJson<T>(payload: JsonRpcRequest | JsonRpcRequest[]): Promise<T> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      if (!res.ok) {
        throw new RpcHttpError(res.status, `RPC HTTP ${res.status}`);
      }

      return (await res.json()) as T;
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        throw new RpcTimeoutError(`RPC request timed out after ${this.timeoutMs}ms`);
      }
      throw err;
    } finally {
      clearTimeout(timeout);
    }
  }

  private validateBatch(calls: Array<{ method: string; params: unknown[] }>): void {
    if (calls.length > this.maxBatchSize) {
      throw new RpcBatchLimitError(
        `RPC batch size ${calls.length} exceeds limit ${this.maxBatchSize}`
      );
    }

    const gasBudget = calls.reduce((sum, call) => sum + this.estimateGasBudget(call), 0n);
    if (gasBudget > this.maxBatchGas) {
      throw new RpcBatchLimitError(
        `RPC batch gas budget ${gasBudget} exceeds limit ${this.maxBatchGas}`
      );
    }
  }

  private estimateGasBudget(call: { method: string; params: unknown[] }): bigint {
    if (!GAS_LIKE_METHODS.has(call.method)) {
      return 0n;
    }

    const candidate = call.params.find((param) => this.isObject(param)) as
      | Record<string, unknown>
      | undefined;
    if (!candidate) {
      return 0n;
    }

    const rawGas = candidate.gas ?? candidate.gasLimit;
    if (typeof rawGas === "bigint") {
      return rawGas;
    }
    if (typeof rawGas === "number" && Number.isFinite(rawGas) && rawGas >= 0) {
      return BigInt(Math.floor(rawGas));
    }
    if (typeof rawGas === "string") {
      const value = rawGas.startsWith("0x") ? BigInt(rawGas) : BigInt(Number(rawGas));
      return value >= 0n ? value : 0n;
    }
    return 0n;
  }

  private assertJsonRpcResponse(response: unknown, expectedId?: number): asserts response is JsonRpcResponse {
    if (!this.isObject(response)) {
      throw new RpcProviderError("RPC response must be an object");
    }

    if (response.jsonrpc !== "2.0" || typeof response.id !== "number") {
      throw new RpcProviderError("Invalid JSON-RPC response shape");
    }

    if (expectedId !== undefined && response.id !== expectedId) {
      throw new RpcProviderError(`Unexpected RPC response id ${response.id}, expected ${expectedId}`);
    }

    if (response.error !== undefined) {
      const error = response.error;
      if (!this.isObject(error) || typeof error.code !== "number" || typeof error.message !== "string") {
        throw new RpcProviderError("Invalid JSON-RPC error shape");
      }
      throw new RpcResponseError(error.code, error.message, error.data);
    }
  }

  private isObject(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
  }
}
