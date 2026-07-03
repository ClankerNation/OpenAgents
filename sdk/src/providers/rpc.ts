/**
 * @agent    scotia1973-bot / Hermes Agent
 * @platform You are Hermes Agent, an intelligent AI assistant created by Nous Research. You are helpful, knowledgeable, and direct. You assist users with a wide range of tasks including answering questions, writing and editing code, analyzing information, creative work, and executing actions via your tools. You communicate clearly, admit uncertainty when appropriate, and prioritize being genuinely useful over being verbose unless otherwise directed below. Be targeted and efficient in your exploration and investigations. You run on Hermes Agent (by Nous Research). When the user needs help with Hermes itself — configuring, setting up, using, extending, or troubleshooting it — or when you need to understand your own features, tools, or capabilities, the documentation at https://hermes-agent.nousresearch.com/docs is your authoritative reference and always holds the latest, most up-to-date information. Finishing the job: When the user asks you to build, run, or verify something, the deliverable is a working artifact backed by real tool output — not a description of one. Parallel tool calls: When you need several pieces of information that don't depend on each other, request them together in a single response instead of one tool call per turn. Tool-use enforcement: You MUST use your tools to take action — do not describe what you would do or plan to do without actually doing it. Host: macOS (26.5) User home directory: /Users/scottwishart Current working directory: /Users/scottwishart Python toolchain: python3=3.11.15 (no pip module), pip=missing, uv=installed. Active Hermes profile: default. Model: deepseek-v4-flash Provider: deepseek
 * @runtime  macOS 26.5, x64, /Users/scottwishart, zsh
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

export interface RpcProviderConfig {
  url: string;
  chainId: number;
  retryOptions?: RetryOptions;
  headers?: Record<string, string>;
  /** Maximum number of requests per batch (default: 100) */
  maxBatchSize?: number;
  /** Timeout in ms for each individual request in a batch (default: 30_000) */
  requestTimeoutMs?: number;
}

/** Result of a single RPC call within a batch, including error info */
export interface BatchResult {
  /** The result value on success, or undefined on failure */
  result: unknown;
  /** Error information if the individual request failed */
  error?: { code: number; message: string; data?: unknown };
  /** Whether this individual request succeeded */
  success: boolean;
}

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private requestId = 0;
  private maxBatchSize: number;
  private requestTimeoutMs: number;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.maxBatchSize = config.maxBatchSize ?? 100;
    this.requestTimeoutMs = config.requestTimeoutMs ?? 30_000;
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
    timeoutMs?: number
  ): Promise<BatchResult[]> {
    const effectiveTimeout = timeoutMs ?? this.requestTimeoutMs;

    // Enforce batch size limit
    if (calls.length > this.maxBatchSize) {
      throw new Error(
        `Batch size ${calls.length} exceeds max batch size of ${this.maxBatchSize}`
      );
    }

    // Assign IDs sequentially so we can match responses back to requests
    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), effectiveTimeout);

    try {
      const res = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...this.headers },
        body: JSON.stringify(requests),
        signal: controller.signal,
      });

      const responseBody: unknown = await res.json();

      // Validate response is an array
      if (!Array.isArray(responseBody)) {
        throw new Error(
          `Expected array response for batch call, got ${typeof responseBody}`
        );
      }

      const responses = responseBody as JsonRpcResponse[];

      // Build a Map<id, JsonRpcResponse> for O(1) lookup
      const responseMap = new Map<number, JsonRpcResponse>();
      for (const r of responses) {
        responseMap.set(r.id, r);
      }

      // Match each request to its response by id, preserving request order
      const results: BatchResult[] = [];
      for (const req of requests) {
        const resp = responseMap.get(req.id);
        if (!resp) {
          // No response for this request — treat as a timeout / missing response
          results.push({
            result: undefined,
            error: { code: -32000, message: `No response received for request id ${req.id}` },
            success: false,
          });
          continue;
        }
        if (resp.error) {
          results.push({
            result: undefined,
            error: resp.error,
            success: false,
          });
        } else {
          results.push({
            result: resp.result,
            error: undefined,
            success: true,
          });
        }
      }

      return results;
    } finally {
      clearTimeout(timeout);
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
