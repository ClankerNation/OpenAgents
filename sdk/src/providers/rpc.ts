/**
 * @generated-by
 * name: opencode-gaotax2006
 * timestamp: 2026-05-17T15:45:00Z
 * platform_config: You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user. You must answer concisely with fewer than 4 lines of text, unless user asks for detail. Follow the code style and conventions of the codebase. Do not add comments unless the code is non-obvious.
 * runtime: {"os":"win32","arch":"x64","home_dir":"C:\\Users\\asus","working_dir":"F:\\ai-bounty-work\\bounty-hunter\\openagents","shell":"powershell"}
 *
 * RPC provider with gas estimation, EIP-1559 fee estimation, and configurable margin.
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
  gasMarginPercent?: number;
}

export interface GasEstimateOptions {
  marginPercent?: number;
  overrideGasLimit?: bigint;
}

export interface FeeEstimate {
  maxFeePerGas: bigint;
  maxPriorityFeePerGas: bigint;
  gasPrice?: bigint;
}

export interface CallTx {
  from?: string;
  to: string;
  data?: string;
  value?: string;
  gas?: string;
  gasPrice?: string;
  maxFeePerGas?: string;
  maxPriorityFeePerGas?: string;
}

const DEFAULT_GAS_MARGIN = 20;
const GAS_LIMIT_FACTOR = 0.9;

export class RpcProvider {
  private url: string;
  private chainId: number;
  private retryOptions: RetryOptions;
  private headers: Record<string, string>;
  private requestId = 0;
  private gasMarginPercent: number;
  private blockGasLimitCache: { value: bigint; block: number } | null = null;

  constructor(config: RpcProviderConfig) {
    this.url = config.url;
    this.chainId = config.chainId;
    this.retryOptions = config.retryOptions ?? {};
    this.headers = config.headers ?? {};
    this.gasMarginPercent = config.gasMarginPercent ?? DEFAULT_GAS_MARGIN;
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

  async getBlockGasLimit(): Promise<bigint> {
    const blockNum = await this.getBlockNumber();
    if (this.blockGasLimitCache && this.blockGasLimitCache.block === blockNum) {
      return this.blockGasLimitCache.value;
    }
    const block = await this.call("eth_getBlockByNumber", ["latest", false]) as Record<string, unknown>;
    const gasLimit = BigInt(block.gasLimit as string);
    this.blockGasLimitCache = { value: gasLimit, block: blockNum };
    return gasLimit;
  }

  async estimateGas(tx: CallTx, options?: GasEstimateOptions): Promise<bigint> {
    const margin = options?.marginPercent ?? this.gasMarginPercent;
    const estimated = await this.call("eth_estimateGas", [tx]) as string;
    let gasLimit = BigInt(estimated);
    gasLimit += (gasLimit * BigInt(margin)) / 100n;
    const blockGasLimit = await this.getBlockGasLimit();
    const cap = (blockGasLimit * BigInt(Math.round(GAS_LIMIT_FACTOR * 100))) / 100n;
    if (gasLimit > cap) gasLimit = cap;
    if (options?.overrideGasLimit && options.overrideGasLimit > 0n) {
      gasLimit = options.overrideGasLimit;
    }
    return gasLimit;
  }

  async estimateGasPrice(): Promise<bigint> {
    return BigInt(await this.call("eth_gasPrice") as string);
  }

  async estimateEip1559Fees(): Promise<FeeEstimate> {
    const baseFee = await this.call("eth_getBlockByNumber", ["latest", false]) as Record<string, unknown>;
    const baseFeePerGas = BigInt((baseFee as any).baseFeePerGas as string);
    const maxPriority = BigInt(await this.call("eth_maxPriorityFeePerGas") as string);
    const maxFee = baseFeePerGas * 2n + maxPriority;
    const gasPrice = await this.estimateGasPrice();
    return { maxFeePerGas: maxFee, maxPriorityFeePerGas: maxPriority, gasPrice };
  }

  getChainId(): number {
    return this.chainId;
  }
}
