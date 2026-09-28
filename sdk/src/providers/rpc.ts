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
  /** Request timeout in ms. Default 30000. */
  timeoutMs?: number;
}

/** Hard cap on the number of calls per JSON-RPC batch payload. */
const MAX_BATCH_SIZE = 100;
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

  private async post(body: unknown): Promise<unknown> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status} from RPC endpoint`);
      }
      return await res.json();
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        throw new Error(`RPC request timed out after ${this.timeoutMs}ms`);
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }

  async call(method: string, params: unknown[] = []): Promise<unknown> {
    const request: JsonRpcRequest = {
      jsonrpc: "2.0",
      id: ++this.requestId,
      method,
      params,
    };

    return withRetry(async () => {
      const json = (await this.post(request)) as JsonRpcResponse;

      if (json.error) {
        throw new Error(`RPC error ${json.error.code}: ${json.error.message}`);
      }
      return json.result;
    }, this.retryOptions);
  }

  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<unknown[]> {
    if (calls.length === 0) return [];
    if (calls.length > MAX_BATCH_SIZE) {
      throw new Error(
        `Batch size ${calls.length} exceeds maximum of ${MAX_BATCH_SIZE}; split the batch`
      );
    }

    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    const responses = (await this.post(requests)) as JsonRpcResponse[];

    // Match responses to requests by id. JSON-RPC batches may return responses
    // in arbitrary order, and some entries may be missing or carry errors, so
    // we build an id->response map and walk the original request list rather
    // than relying on array position or a sort that would silently misalign
    // missing responses with the wrong call.
    const byId = new Map<number, JsonRpcResponse>();
    for (const r of responses) {
      byId.set(r.id, r);
    }

    return requests.map((req) => {
      const resp = byId.get(req.id);
      if (!resp) {
        throw new Error(
          `RPC batch: no response for request id ${req.id} (${req.method})`
        );
      }
      if (resp.error) {
        throw new Error(
          `RPC error ${resp.error.code} on ${req.method}: ${resp.error.message}`
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
