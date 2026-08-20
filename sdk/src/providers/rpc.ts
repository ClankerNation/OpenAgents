// @contributor-info rafaio1
// @session-init Agentic bounty-hunter workflow for ClankerNation/OpenAgents. Identify high-value bounties, implement fixes, update CONTRIBUTORS.json, submit PRs, and claim via issue comments. USDC: 0x9D0E3D34CB4b618e789F8B017239DaEE99eb3c8C (Polygon/Base).
// @os linux
// @arch x64
// @home-dir /root
// @working-dir /tmp/OpenAgents
// @shell /bin/bash
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
}

export const RPC_TIMEOUT_MS = 30_000;
export const MAX_BATCH_SIZE = 100;

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
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), RPC_TIMEOUT_MS);

      let res: Response;
      try {
        res = await fetch(this.url, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...this.headers },
          body: JSON.stringify(request),
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeoutId);
      }

      // Retry on rate-limit or service unavailable
      if (res.status === 429 || res.status === 503) {
        throw new Error(`RPC HTTP ${res.status}`);
      }

      const json = (await res.json()) as JsonRpcResponse;

      // Type-check error response
      if (json.error && typeof json.error.code === "number" && typeof json.error.message === "string") {
        throw new Error(`RPC error ${json.error.code}: ${json.error.message}`);
      }

      return json.result;
    }, this.retryOptions);
  }

  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<unknown[]> {
    if (calls.length > MAX_BATCH_SIZE) {
      throw new Error(`Batch size ${calls.length} exceeds max ${MAX_BATCH_SIZE}`);
    }

    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), RPC_TIMEOUT_MS);

    let res: Response;
    try {
      res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(requests),
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timeoutId);
    }

    if (res.status === 429 || res.status === 503) {
      throw new Error(`RPC batch HTTP ${res.status}`);
    }

    const responses = (await res.json()) as JsonRpcResponse[];
    return responses
      .sort((a, b) => a.id - b.id)
      .map((r) => r.result);
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
