import { RetryOptions } from "../utils/retry";

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
  maxBatchGas?: bigint;
}

const DEFAULT_TIMEOUT_MS = 30_000;
const DEFAULT_MAX_RETRIES = 2;
const DEFAULT_BASE_DELAY_MS = 250;
const DEFAULT_MAX_DELAY_MS = 5_000;
const DEFAULT_MAX_BATCH_GAS = 30_000_000n;

type JsonRpcErrorData = { code: number; message: string; data?: unknown };

export class RpcTimeoutError extends Error {
  constructor(timeoutMs: number) {
    super(`RPC request timed out after ${timeoutMs}ms`);
    this.name = "RpcTimeoutError";
  }
}

export class RpcHttpError extends Error {
  readonly status: number;
  readonly statusText: string;

  constructor(status: number, statusText: string) {
    super(`RPC HTTP ${status}${statusText ? ` ${statusText}` : ""}`.trim());
    this.name = "RpcHttpError";
    this.status = status;
    this.statusText = statusText;
  }
}

export class RpcResponseFormatError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RpcResponseFormatError";
  }
}

export class RpcResponseError extends Error {
  readonly code: number;
  readonly data?: unknown;

  constructor(error: JsonRpcErrorData) {
    super(`RPC error ${error.code}: ${error.message}`);
    this.name = "RpcResponseError";
    this.code = error.code;
    this.data = error.data;
  }
}

export class RpcBatchGasLimitError extends Error {
  readonly totalGas: bigint;
  readonly maxBatchGas: bigint;

  constructor(totalGas: bigint, maxBatchGas: bigint) {
    super(`Batch gas ${totalGas.toString()} exceeds max ${maxBatchGas.toString()}`);
    this.name = "RpcBatchGasLimitError";
    this.totalGas = totalGas;
    this.maxBatchGas = maxBatchGas;
  }
}

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private timeoutMs: number;
  private maxBatchGas: bigint;
  private requestId = 0;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.timeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.maxBatchGas = config.maxBatchGas ?? DEFAULT_MAX_BATCH_GAS;
  }

  async call(method: string, params: unknown[] = []): Promise<unknown> {
    const request: JsonRpcRequest = {
      jsonrpc: "2.0",
      id: ++this.requestId,
      method,
      params,
    };
    const json = await this.fetchWithRetry(request);
    return this.parseSingleResponse(json);
  }

  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<unknown[]> {
    this.validateBatchGas(calls);
    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    const raw = await this.fetchWithRetry(requests);
    return this.parseBatchResponse(raw);
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

  private async fetchWithRetry(payload: JsonRpcRequest | JsonRpcRequest[]): Promise<unknown> {
    const maxRetries = this.retryOptions.maxRetries ?? DEFAULT_MAX_RETRIES;
    const baseDelayMs = this.retryOptions.baseDelayMs ?? DEFAULT_BASE_DELAY_MS;
    const maxDelayMs = this.retryOptions.maxDelayMs ?? DEFAULT_MAX_DELAY_MS;

    let lastError: Error | undefined;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        return await this.fetchJson(payload);
      } catch (error) {
        const typedError = error instanceof Error ? error : new Error(String(error));
        lastError = typedError;
        if (!this.isRetryableHttpError(typedError) || attempt === maxRetries) {
          throw typedError;
        }

        this.retryOptions.onRetry?.(attempt + 1, typedError);
        const delayMs = Math.min(baseDelayMs * 2 ** attempt, maxDelayMs);
        await this.sleep(delayMs);
      }
    }

    throw lastError ?? new Error("RPC request failed");
  }

  private async fetchJson(payload: JsonRpcRequest | JsonRpcRequest[]): Promise<unknown> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      if (!res.ok) {
        throw new RpcHttpError(res.status, res.statusText);
      }

      return await res.json();
    } catch (error) {
      if (controller.signal.aborted) {
        throw new RpcTimeoutError(this.timeoutMs);
      }
      throw error;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  private parseSingleResponse(raw: unknown): unknown {
    const response = this.assertJsonRpcResponse(raw, "single RPC response");
    if (response.error) {
      throw new RpcResponseError(response.error);
    }
    return response.result;
  }

  private parseBatchResponse(raw: unknown): unknown[] {
    if (!Array.isArray(raw)) {
      throw new RpcResponseFormatError("Invalid batch RPC response: expected array");
    }

    const responses = raw.map((item) => this.assertJsonRpcResponse(item, "batch RPC response"));
    return responses
      .sort((a, b) => a.id - b.id)
      .map((response) => {
        if (response.error) {
          throw new RpcResponseError(response.error);
        }
        return response.result;
      });
  }

  private assertJsonRpcResponse(raw: unknown, context: string): JsonRpcResponse {
    if (!raw || typeof raw !== "object") {
      throw new RpcResponseFormatError(`Invalid ${context}: expected object`);
    }

    const candidate = raw as Partial<JsonRpcResponse>;
    if (candidate.jsonrpc !== "2.0" || typeof candidate.id !== "number") {
      throw new RpcResponseFormatError(`Invalid ${context}: missing jsonrpc/id`);
    }

    if (candidate.error !== undefined) {
      if (!candidate.error || typeof candidate.error !== "object") {
        throw new RpcResponseFormatError(`Invalid ${context}: error must be object`);
      }
      const rpcError = candidate.error as { code?: unknown; message?: unknown; data?: unknown };
      if (typeof rpcError.code !== "number" || typeof rpcError.message !== "string") {
        throw new RpcResponseFormatError(`Invalid ${context}: error.code/error.message invalid`);
      }
    }

    return candidate as JsonRpcResponse;
  }

  private validateBatchGas(calls: Array<{ method: string; params: unknown[] }>): void {
    const totalGas = calls.reduce((sum, call) => sum + this.extractGasFromCall(call), 0n);
    if (totalGas > this.maxBatchGas) {
      throw new RpcBatchGasLimitError(totalGas, this.maxBatchGas);
    }
  }

  private extractGasFromCall(call: { method: string; params: unknown[] }): bigint {
    if (call.method !== "eth_call" && call.method !== "eth_estimateGas") {
      return 0n;
    }
    if (call.params.length === 0) {
      return 0n;
    }

    const tx = call.params[0];
    if (!tx || typeof tx !== "object") {
      return 0n;
    }

    const gasValue = (tx as { gas?: unknown; gasLimit?: unknown }).gas
      ?? (tx as { gas?: unknown; gasLimit?: unknown }).gasLimit;
    if (gasValue === undefined) {
      return 0n;
    }

    return this.parseGasValue(gasValue);
  }

  private parseGasValue(value: unknown): bigint {
    if (typeof value === "bigint") {
      return value;
    }
    if (typeof value === "number") {
      if (!Number.isInteger(value) || value < 0) {
        throw new RpcResponseFormatError("Invalid batch gas value: number must be a non-negative integer");
      }
      return BigInt(value);
    }
    if (typeof value === "string") {
      if (value.startsWith("0x") || value.startsWith("0X")) {
        return BigInt(value);
      }
      if (/^\d+$/.test(value)) {
        return BigInt(value);
      }
      throw new RpcResponseFormatError("Invalid batch gas value: string must be decimal or hex");
    }

    throw new RpcResponseFormatError("Invalid batch gas value type");
  }

  private isRetryableHttpError(error: Error): boolean {
    return error instanceof RpcHttpError && (error.status === 429 || error.status === 503);
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
