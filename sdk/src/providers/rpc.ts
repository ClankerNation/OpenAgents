/**
 * @contributor
 * name: opencode-gaotax2006
 * platform_init: You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user. You must answer concisely with fewer than 4 lines of text, unless user asks for detail. Follow the code style and conventions of the codebase. Do not add comments unless the code is non-obvious.
 * runtime: os=win32 arch=x64 working_dir=F:\ai-bounty-work\bounty-hunter\openagents shell=powershell
 * timestamp: 2026-05-17T12:00:00Z
 */

import { withRetry, RetryOptions } from "../utils/retry";

const DEFAULT_BATCH_TIMEOUT_MS = 10_000;
const MAX_BATCH_SIZE = 100;

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
}

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private requestId = 0;
  private timeoutMs: number;

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
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this.timeoutMs);

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
        clearTimeout(timeoutId);
      }
    }, this.retryOptions);
  }

  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>
  ): Promise<Array<{ id: number; result?: unknown; error?: { code: number; message: string } }>> {
    const batchSize = Math.min(calls.length, MAX_BATCH_SIZE);
    const requests: JsonRpcRequest[] = calls.slice(0, batchSize).map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(requests),
        signal: controller.signal,
      });

      const responses: JsonRpcResponse[] = await res.json();

      const responseMap = new Map<number, JsonRpcResponse>();
      for (const r of responses) {
        responseMap.set(r.id, r);
      }

      return requests.map((req) => {
        const match = responseMap.get(req.id);
        if (!match) {
          return { id: req.id, error: { code: -1, message: "No response received" } };
        }
        return { id: match.id, result: match.result, error: match.error };
      });
    } catch (err: any) {
      if (err.name === "AbortError") {
        throw new Error("Batch RPC request timed out");
      }
      return requests.map((req) => ({
        id: req.id,
        error: { code: -2, message: err.message || "Request failed" },
      }));
    } finally {
      clearTimeout(timeoutId);
    }
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
