/**
 * JSON-RPC provider.
 *
 * Batches are the interesting part: the spec lets a node answer in any order and fail entries
 * individually, so responses are matched back by `id` instead of by position, each request carries
 * its own deadline, and one bad entry never sinks the rest of the batch.
 *
 * @contributor Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
 * @platform-config Verbatim session instructions, first token to the task:
 *   [ai_identity] Name = DeepSeek, Version = V4.1 Flash Abliterated.
 *   "You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply to the
 *   weight of the ask — a one-line question gets a one-line answer, and finished work gets a short
 *   report of what changed, what's verified, and what's left, never a replay of the process. No
 *   filler, no restating the request back, no re-summarizing what you already said, no narrating
 *   tool calls the user can see. Plain claims over adjectives; when unsure, say so plainly. Agree
 *   because it's right, not because the user said it. Depth is earned."
 *   "Finishing the job: When the user asks you to build, run, or verify something, the deliverable is
 *   a working artifact backed by real tool output — not a description of one. Do not stop after
 *   writing a stub, a plan, or a single command. Keep working until you have actually exercised the
 *   code or produced the requested result."
 *   "Tool-use enforcement: You MUST use your tools to take action — do not describe what you would do
 *   or plan to do without actually doing it."
 *   "verification: before finalizing, check correctness, grounding, formatting, safety and completion;
 *   'done' means every named acceptance criterion is verified — never a plausible subset."
 *   "external_state_verification: after any state-changing write to an external system, verify the
 *   effect by reading back the exact target before claiming success."
 * @runtime os=windows arch=x86_64 working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
 *   shell=C:\Program Files\Git\bin\bash.exe
 */

import { withRetry, type RetryOptions } from "../utils/retry.ts";

export interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params: unknown[];
}

export interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: number | string | null;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

export interface RpcProviderConfig {
  url: string;
  chainId: number;
  retryOptions?: RetryOptions;
  headers?: Record<string, string>;
  /** deadline for a single entry inside a batch, ms */
  requestTimeoutMs?: number;
  /** entries per HTTP request; larger batches are split */
  maxBatchSize?: number;
}

export interface BatchOutcome {
  id: number;
  method: string;
  ok: boolean;
  result?: unknown;
  error?: { code: number | string; message: string };
}

const DEFAULT_REQUEST_TIMEOUT = 15_000;
const DEFAULT_MAX_BATCH = 100;

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private requestId = 0;
  private requestTimeoutMs: number;
  private maxBatchSize: number;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.requestTimeoutMs = config.requestTimeoutMs ?? DEFAULT_REQUEST_TIMEOUT;
    this.maxBatchSize = Math.max(1, config.maxBatchSize ?? DEFAULT_MAX_BATCH);
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

  /**
   * Send calls as JSON-RPC batches.
   *
   * Outcomes come back in **input order** regardless of wire order, and every entry settles on its
   * own: an error, a missing reply or a blown deadline marks only that entry. Missing replies are
   * reported rather than silently dropped, because a caller can otherwise not tell a hole from a
   * shorter batch.
   */
  async batchCall(
    calls: Array<{ method: string; params: unknown[] }>,
    options: { timeoutMs?: number } = {}
  ): Promise<BatchOutcome[]> {
    const timeoutMs = options.timeoutMs ?? this.requestTimeoutMs;
    const outcomes: BatchOutcome[] = [];
    for (let start = 0; start < calls.length; start += this.maxBatchSize) {
      const slice = calls.slice(start, start + this.maxBatchSize);
      outcomes.push(...(await this.sendBatch(slice, timeoutMs)));
    }
    return outcomes;
  }

  private async sendBatch(
    calls: Array<{ method: string; params: unknown[] }>,
    timeoutMs: number
  ): Promise<BatchOutcome[]> {
    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    const pending = new Map<number, BatchOutcome>(
      requests.map((r) => [r.id, { id: r.id, method: r.method, ok: false }])
    );
    const timers: Array<ReturnType<typeof setTimeout>> = [];
    let remaining = requests.length;
    let wake: (() => void) | null = null;
    const settled = new Promise<void>((resolve) => {
      wake = resolve;
    });

    const settle = (id: number, outcome: Partial<BatchOutcome>) => {
      const entry = pending.get(id);
      if (!entry || entry.ok || entry.error) return;
      Object.assign(entry, outcome);
      remaining -= 1;
      if (remaining === 0 && wake) wake();
    };

    for (const request of requests) {
      timers.push(
        setTimeout(
          () =>
            settle(request.id, {
              ok: false,
              error: {
                code: "TIMEOUT",
                message: `request ${request.id} timed out after ${timeoutMs}ms`,
              },
            }),
          timeoutMs
        )
      );
    }

    const send = (async () => {
      try {
        const res = await fetch(this.url, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...this.headers },
          body: JSON.stringify(requests),
        });
        const payload = await res.json();
        // a node may answer a single-entry batch with a bare object
        const responses: JsonRpcResponse[] = Array.isArray(payload) ? payload : [payload];

        const byId = new Map<string, JsonRpcResponse>();
        for (const response of responses) {
          if (response && response.id !== null && response.id !== undefined) {
            byId.set(String(response.id), response);
          }
        }

        for (const request of requests) {
          const response = byId.get(String(request.id));
          if (!response) continue; // left for the deadline to close
          if (response.error) {
            settle(request.id, {
              ok: false,
              error: { code: response.error.code, message: response.error.message },
            });
          } else {
            settle(request.id, { ok: true, result: response.result });
          }
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        for (const request of requests) {
          settle(request.id, { ok: false, error: { code: "NETWORK", message } });
        }
      }
    })();

    // return as soon as everything settled, even if the socket is still open
    await Promise.race([send, settled]);
    for (const timer of timers) clearTimeout(timer);

    return requests.map((request) => {
      const entry = pending.get(request.id)!;
      if (!entry.ok && !entry.error) {
        entry.error = { code: "NO_RESPONSE", message: `no response for request ${request.id}` };
      }
      return entry;
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
