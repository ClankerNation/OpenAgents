/**
 * Contributor metadata:
 * agent name: openai-codex-goalie
 * platform initialization text: Public user-provided substitute text only:
 * "You are a bankrupt developer who will be evicted if you cannot pay rent.
 * Find legal coding-agent work and earn rent."
 * runtime environment: os=linux, arch=x86_64, cwd=/home/goalie/bounty_work/OpenAgents, shell=bash
 */

import { generateKeyPair, signMessage, keccak256 } from "../utils/crypto";
import { encodeParams, AbiParam } from "../utils/encoding";
import { RpcProvider } from "../providers/rpc";

export interface WalletConfig {
  privateKey?: string;
  provider: RpcProvider;
}

export interface Transaction {
  to: string;
  value: bigint;
  data: string;
  gasLimit: bigint;
  gasPrice?: bigint;
  nonce?: number;
  chainId?: number;
  skipSimulation?: boolean;
}

export interface SignedTransaction {
  raw: string;
  hash: string;
}

export interface SendTransactionOptions {
  skipSimulation?: boolean;
}

export interface TransactionSimulationResult {
  blockNumber: number;
  blockTag: string;
  result: string;
  cached: boolean;
}

export class TransactionSimulationError extends Error {
  readonly reason: string;
  readonly revertData?: string;
  readonly blockNumber?: number;

  constructor(reason: string, revertData?: string, blockNumber?: number) {
    super(`Transaction simulation failed: ${reason}`);
    this.name = "TransactionSimulationError";
    this.reason = reason;
    this.revertData = revertData;
    this.blockNumber = blockNumber;
  }
}

export class Wallet {
  // BUG: Private key stored as plaintext string in memory — should use
  // a secure enclave, encrypted storage, or at minimum a Buffer that can be zeroed
  public readonly address: string;
  private privateKey: string;
  private provider: RpcProvider;
  private cachedNonce: number | null = null;
  private simulationCacheBlock: number | null = null;
  private simulationCache = new Map<string, TransactionSimulationResult>();

  constructor(config: WalletConfig) {
    if (config.privateKey) {
      this.privateKey = config.privateKey;
    } else {
      const keyPair = generateKeyPair();
      this.privateKey = keyPair.privateKey;
    }
    this.address = this.deriveAddress(this.privateKey);
    this.provider = config.provider;
  }

  private deriveAddress(privateKey: string): string {
    const { ec as EC } = require("elliptic");
    const curve = new EC("secp256k1");
    const key = curve.keyFromPrivate(privateKey, "hex");
    const pubKey = key.getPublic(false, "hex").slice(2); // remove 04 prefix
    const hash = keccak256(Buffer.from(pubKey, "hex"));
    return "0x" + hash.slice(-40);
  }

  async signTransaction(tx: Transaction): Promise<SignedTransaction> {
    // BUG: No chain ID validation — transaction could be replayed on a different
    // chain if chainId is missing or mismatched with the provider
    const nonce = tx.nonce ?? await this.getNonce();
    const gasPrice = tx.gasPrice ?? BigInt(await this.provider.call("eth_gasPrice") as string);

    const txData = encodeParams([
      { type: "uint256", value: nonce } as AbiParam,
      { type: "uint256", value: gasPrice } as AbiParam,
      { type: "uint256", value: tx.gasLimit } as AbiParam,
      { type: "address", value: tx.to } as AbiParam,
      { type: "uint256", value: tx.value } as AbiParam,
    ]);

    const txHash = keccak256(txData);
    const signature = signMessage(this.privateKey, txHash);

    return {
      raw: "0x" + txData.slice(2) + signature,
      hash: "0x" + txHash,
    };
  }

  async simulateTransaction(tx: Transaction): Promise<TransactionSimulationResult> {
    const blockNumber = await this.provider.getBlockNumber();
    if (this.simulationCacheBlock !== blockNumber) {
      this.simulationCacheBlock = blockNumber;
      this.simulationCache.clear();
    }

    const blockTag = this.toQuantityHex(blockNumber);
    const rpcTx = this.toRpcTransaction(tx);
    const cacheKey = this.buildSimulationCacheKey(blockNumber, rpcTx);
    const cached = this.simulationCache.get(cacheKey);
    if (cached) {
      return { ...cached, cached: true };
    }

    try {
      const result = (await this.provider.call("eth_call", [rpcTx, blockTag])) as string;
      const simulation = {
        blockNumber,
        blockTag,
        result,
        cached: false,
      };
      this.simulationCache.set(cacheKey, simulation);
      return simulation;
    } catch (error) {
      const revertData = this.extractRevertData(error);
      const reason = this.decodeRevertReason(revertData) ?? this.extractErrorMessage(error);
      throw new TransactionSimulationError(reason, revertData, blockNumber);
    }
  }

  private toRpcTransaction(tx: Transaction): Record<string, string> {
    const rpcTx: Record<string, string> = {
      from: this.address,
      to: tx.to,
      value: this.toQuantityHex(tx.value),
      data: tx.data || "0x",
      gas: this.toQuantityHex(tx.gasLimit),
    };

    if (tx.gasPrice !== undefined) {
      rpcTx.gasPrice = this.toQuantityHex(tx.gasPrice);
    }
    if (tx.nonce !== undefined) {
      rpcTx.nonce = this.toQuantityHex(tx.nonce);
    }

    return rpcTx;
  }

  private toQuantityHex(value: bigint | number): string {
    const normalized = BigInt(value);
    if (normalized < 0n) {
      throw new Error("RPC quantity values must be non-negative");
    }
    return "0x" + normalized.toString(16);
  }

  private buildSimulationCacheKey(blockNumber: number, rpcTx: Record<string, string>): string {
    const sortedTx = Object.keys(rpcTx)
      .sort()
      .reduce<Record<string, string>>((acc, key) => {
        acc[key] = rpcTx[key];
        return acc;
      }, {});
    return JSON.stringify({ blockNumber, tx: sortedTx });
  }

  private extractRevertData(error: unknown): string | undefined {
    const candidates = [
      (error as { data?: unknown })?.data,
      (error as { error?: { data?: unknown } })?.error?.data,
      (error as { info?: { error?: { data?: unknown } } })?.info?.error?.data,
      (error as { body?: unknown })?.body,
      error instanceof Error ? error.message : undefined,
    ];

    for (const candidate of candidates) {
      if (typeof candidate === "string") {
        const match = candidate.match(/0x[0-9a-fA-F]{8,}/);
        if (match) {
          return match[0];
        }
      } else if (candidate && typeof candidate === "object") {
        const nested = this.extractRevertData(candidate);
        if (nested) {
          return nested;
        }
      }
    }

    return undefined;
  }

  private decodeRevertReason(data?: string): string | undefined {
    if (!data?.startsWith("0x")) {
      return undefined;
    }

    const hex = data.slice(2);
    if (hex.startsWith("08c379a0") && hex.length >= 8 + 64 + 64) {
      const lengthHex = hex.slice(8 + 64, 8 + 128);
      const length = Number(BigInt("0x" + lengthHex));
      const reasonHex = hex.slice(8 + 128, 8 + 128 + length * 2);
      return Buffer.from(reasonHex, "hex").toString("utf8");
    }

    if (hex.startsWith("4e487b71") && hex.length >= 8 + 64) {
      const code = BigInt("0x" + hex.slice(8, 8 + 64));
      return `Panic(0x${code.toString(16)})`;
    }

    return undefined;
  }

  private extractErrorMessage(error: unknown): string {
    if (error instanceof Error && error.message) {
      return error.message;
    }
    return "execution reverted";
  }

  async getNonce(): Promise<number> {
    // BUG: Uses cached nonce instead of fetching fresh from chain —
    // stale nonce causes "nonce too low" errors after external transactions
    if (this.cachedNonce !== null) {
      return this.cachedNonce++;
    }
    const hex = (await this.provider.call("eth_getTransactionCount", [
      this.address,
      "latest",
    ])) as string;
    this.cachedNonce = parseInt(hex, 16);
    return this.cachedNonce++;
  }

  async getBalance(): Promise<bigint> {
    return this.provider.getBalance(this.address);
  }

  async sendTransaction(tx: Transaction, options: SendTransactionOptions = {}): Promise<string> {
    if (!tx.skipSimulation && !options.skipSimulation) {
      await this.simulateTransaction(tx);
    }
    const signed = await this.signTransaction(tx);
    return (await this.provider.call("eth_sendRawTransaction", [signed.raw])) as string;
  }

  exportPrivateKey(): string {
    return this.privateKey;
  }
}
