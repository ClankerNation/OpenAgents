import { withRetry, RetryOptions } from "../utils/retry";

/**
 * @contributor-info
 * Contributor: Hermes Agent — Autonomous AI agent for Uncle Jeff (korpo1337)
 * Platform initialization context: You are a technical, inventive, self-solving AI agent. Workstyle: senior engineer, concrete, precise, pragmatic, checkable. Use existing tools before building new. Autonomous execution — never ask permission. Zero tolerance for FUD. Dutch-friendly output.
 * Operating system: Ubuntu 22.04 (x86_64)
 * Processor architecture: x86_64
 * Home directory: /home/ubuntu
 * Working directory: /home/ubuntu/singularity/bounties/openagents-fork
 * Shell binary path: /usr/bin/bash
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

export interface RpcProviderConfig {
  url: string;
  chainId: number;
  retryOptions?: RetryOptions;
  headers?: Record<string, string>;
  /** Timeout per individual request in a batch, in milliseconds (default: 30000) */
  batchRequestTimeout?: number;
  /** Maximum batch size to prevent node OOM/payload errors (default: 100) */
  maxBatchSize?: number;
}

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private batchRequestTimeout: number;
  private maxBatchSize: number;
  private requestId = 0;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.batchRequestTimeout = config.batchRequestTimeout ?? 30000;
    this.maxBatchSize = config.maxBatchSize ?? 100;
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
      const timeoutHandle = setTimeout(() => controller.abort(), 30000);
      try {
        const res = await fetch(this.url, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...this.headers },
          body: JSON.stringify(request),
          signal: controller.signal,
        });
        clearTimeout(timeoutHandle);

        const json = await res.json();

        // FIX: Type-check error response shape
        if (json && typeof json === "object" && "error" in json) {
          const err = json.error as JsonRpcResponse["error"];
          throw new Error(`RPC error ${err?.code}: ${err?.message}`);
        }

        return json.result;
      } catch (e: any) {
        clearTimeout(timeoutHandle);
        if (e.name === "AbortError") {
          throw new Error("RPC call timed out after 30000ms");
        }
        throw e;
      }
    }, this.retryOptions);
  }

  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>,
    batchOptions?: { abortOnError?: boolean }
  ): Promise<unknown[]> {
    if (calls.length === 0) return [];
    if (calls.length > this.maxBatchSize) {
      throw new Error(
        `Batch size ${calls.length} exceeds max ${this.maxBatchSize}`
      );
    }

    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    // Map request IDs to their index in the original calls array
    const idToIndex = new Map<number, number>();
    requests.forEach((req, idx) => idToIndex.set(req.id, idx));
    const results = new Array<unknown>(requests.length);
    const errors = new Array<Error | null>(requests.length).fill(null);
    let hasError = false;

    // FIX: Per-batch fetch timeout
    const controller = new AbortController();
    const timeoutHandle = setTimeout(
      () => controller.abort(),
      this.batchRequestTimeout
    );

    try {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(requests),
        signal: controller.signal,
      });
      clearTimeout(timeoutHandle);

      let responses: JsonRpcResponse[];
      try {
        responses = (await res.json()) as JsonRpcResponse[];
      } catch {
        throw new Error("Batch response is not valid JSON");
      }

      if (!Array.isArray(responses)) {
        throw new Error("Batch response must be an array");
      }

      // FIX: Match responses by id instead of sorting by id
      for (const r of responses) {
        if (!r || typeof r !== "object") continue;
        const idx = idToIndex.get(r.id);
        if (idx === undefined) continue;

        if (r.error) {
          errors[idx] = new Error(
            `RPC error ${r.error.code}: ${r.error.message}`
          );
          hasError = true;
        } else {
          results[idx] = r.result;
          errors[idx] = null;
        }
      }
    } catch (e: any) {
      clearTimeout(timeoutHandle);
      if (e.name === "AbortError") {
        throw new Error(`Batch call timed out after ${this.batchRequestTimeout}ms`);
      }
      throw e;
    }

    // FIX: Handle partial failures
    if (hasError) {
      if (batchOptions?.abortOnError) {
        // Throw aggregated error showing which requests failed
        const failedIndices = errors
          .map((err, idx) => (err ? `[${idx}] ${err.message}` : null))
          .filter(Boolean);
        throw new Error(
          `Batch partial failure: ${failedIndices.join("; ")}`
        );
      }
      // Otherwise return mixed array — caller must check typeof Error for failures
      return errors.map((err, idx) => (err ? err : results[idx]));
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
