/**
 * @generated-by
 * name: opencode-gaotax2006
 * timestamp: 2026-05-17T15:50:00Z
 * platform_config: You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user. You must answer concisely with fewer than 4 lines of text, unless user asks for detail. Follow the code style and conventions of the codebase. Do not add comments unless the code is non-obvious.
 * runtime: {"os":"win32","arch":"x64","home_dir":"C:\\Users\\asus","working_dir":"F:\\ai-bounty-work\\bounty-hunter\\openagents","shell":"powershell"}
 *
 * RPC provider with transaction simulation and revert reason parsing.
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
}

export interface SimulationResult {
  success: boolean;
  returnData: string;
  revertReason?: string;
}

export interface SimulateTxParams {
  from?: string;
  to: string;
  data?: string;
  value?: string;
  gas?: string;
  gasPrice?: string;
  maxFeePerGas?: string;
  maxPriorityFeePerGas?: string;
}

export interface SimulateOptions {
  skip?: boolean;
  blockNumber?: string;
}

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
  ): Promise<unknown[]> {
    // BUG: No limit on batch size — sending thousands of calls in one batch
    // can exceed the node's gas/payload limit and fail silently or OOM
    const requests: JsonRpcRequest[] = calls.map((c) => ({
      jsonrpc: "2.0" as const,
      id: ++this.requestId,
      method: c.method,
      params: c.params,
    }));

    const res = await fetch(this.url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...this.headers },
      body: JSON.stringify(requests),
    });

    const responses: JsonRpcResponse[] = await res.json();
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

  parseRevertReason(data: string): string {
    const cleaned = data.startsWith("0x") ? data.slice(2) : data;
    if (cleaned.startsWith("08c379a0")) {
      const offset = 8;
      const lenHex = cleaned.slice(offset, offset + 64);
      const len = parseInt(lenHex, 16) * 2;
      const msgHex = cleaned.slice(offset + 64, offset + 64 + len);
      try {
        return Buffer.from(msgHex, "hex").toString("utf-8");
      } catch {
        return "0x" + cleaned;
      }
    }
    return "0x" + cleaned;
  }

  async simulateTransaction(
    tx: SimulateTxParams,
    options?: SimulateOptions
  ): Promise<SimulationResult> {
    const blockNumber = options?.blockNumber ?? "latest";
    try {
      const result = await this.call("eth_call", [tx, blockNumber]) as string;
      return { success: true, returnData: result };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      const revertReason = this.parseRevertReason(msg);
      return { success: false, returnData: "0x", revertReason };
    }
  }

  async simulateAndSend(
    tx: SimulateTxParams & { raw?: string },
    options?: SimulateOptions
  ): Promise<string> {
    if (!options?.skip) {
      const sim = await this.simulateTransaction(tx, options);
      if (!sim.success) {
        throw new Error(`Transaction would revert: ${sim.revertReason}`);
      }
    }
    return this.call("eth_sendRawTransaction", [tx.raw]) as Promise<string>;
  }

  getChainId(): number {
    return this.chainId;
  }
}
