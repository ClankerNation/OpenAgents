/**
 * @fix-author codex-xyjk0511
 * @fix-date 2026-05-31
 * @platform-init User request: complete issue #39 by adding SDK transaction simulation before sending.
 * @runtime os=windows arch=x64 working_dir=F:\jiedan\OpenAgents-bounty-run shell=powershell
 */
import { generateKeyPair, signMessage, keccak256 } from "../utils/crypto";
import { encodeParams, AbiParam } from "../utils/encoding";
import { RpcError, RpcProvider } from "../providers/rpc";

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

export class Wallet {
  // BUG: Private key stored as plaintext string in memory — should use
  // a secure enclave, encrypted storage, or at minimum a Buffer that can be zeroed
  public readonly address: string;
  private privateKey: string;
  private provider: RpcProvider;
  private cachedNonce: number | null = null;
  private simulationCache = new Map<string, number>();

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
    const { ec: EC } = require("elliptic");
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

  async sendTransaction(tx: Transaction): Promise<string> {
    if (!tx.skipSimulation) {
      await this.simulateTransaction(tx);
    }

    const signed = await this.signTransaction(tx);
    return (await this.provider.call("eth_sendRawTransaction", [signed.raw])) as string;
  }

  async simulateTransaction(tx: Transaction): Promise<void> {
    const blockNumber = await this.provider.getBlockNumber();
    const cacheKey = this.getSimulationCacheKey(tx);

    if (this.simulationCache.get(cacheKey) === blockNumber) {
      return;
    }

    try {
      await this.provider.call("eth_call", [
        {
          from: this.address,
          to: tx.to,
          value: this.toRpcHex(tx.value),
          data: tx.data,
          gas: this.toRpcHex(tx.gasLimit),
        },
        "latest",
      ]);
      this.simulationCache.set(cacheKey, blockNumber);
    } catch (error) {
      throw new Error(`Transaction simulation failed: ${this.decodeSimulationError(error)}`);
    }
  }

  private getSimulationCacheKey(tx: Transaction): string {
    return [
      this.address.toLowerCase(),
      tx.to.toLowerCase(),
      tx.value.toString(),
      tx.data.toLowerCase(),
      tx.gasLimit.toString(),
      tx.gasPrice?.toString() ?? "",
      tx.nonce?.toString() ?? "",
      tx.chainId?.toString() ?? "",
    ].join("|");
  }

  private toRpcHex(value: bigint): string {
    return "0x" + value.toString(16);
  }

  private decodeSimulationError(error: unknown): string {
    const fallback = error instanceof Error ? error.message : "execution reverted";
    const revertData = this.extractRevertData(error);

    if (!revertData) {
      return fallback;
    }

    return this.decodeRevertData(revertData) ?? fallback;
  }

  private extractRevertData(error: unknown): string | null {
    if (error instanceof RpcError && typeof error.data === "string") {
      return this.normalizeRevertHex(error.data);
    }

    const stack: unknown[] = [error];
    const seen = new Set<unknown>();

    while (stack.length > 0) {
      const current = stack.pop();
      if (!current || typeof current !== "object" || seen.has(current)) {
        continue;
      }
      seen.add(current);

      const record = current as Record<string, unknown>;
      for (const key of ["data", "error", "cause", "body", "response"]) {
        const value = record[key];
        if (typeof value === "string") {
          const normalized = this.normalizeRevertHex(value);
          if (normalized) {
            return normalized;
          }
          continue;
        }
        if (value && typeof value === "object") {
          stack.push(value);
        }
      }

      if (typeof record.message === "string") {
        const normalized = this.normalizeRevertHex(record.message);
        if (normalized) {
          return normalized;
        }
      }
    }

    return null;
  }

  private normalizeRevertHex(value: string): string | null {
    const match = value.match(/0x[0-9a-fA-F]{8,}/);
    return match ? match[0] : null;
  }

  private decodeRevertData(revertData: string): string | null {
    const data = revertData.toLowerCase();

    if (data.startsWith("0x08c379a0")) {
      const payload = data.slice(10);
      const length = parseInt(payload.slice(64, 128), 16);
      const messageHex = payload.slice(128, 128 + length * 2);
      const message = Buffer.from(messageHex, "hex").toString("utf8");
      return message || "execution reverted";
    }

    if (data.startsWith("0x4e487b71")) {
      const code = parseInt(data.slice(10, 74), 16);
      const label = this.getPanicLabel(code);
      return label ? `panic(${code}): ${label}` : `panic(${code})`;
    }

    return "execution reverted";
  }

  private getPanicLabel(code: number): string | null {
    const labels: Record<number, string> = {
      0x01: "assert(false)",
      0x11: "arithmetic overflow/underflow",
      0x12: "division or modulo by zero",
      0x21: "invalid enum conversion",
      0x22: "storage byte array decoding error",
      0x31: "pop on empty array",
      0x32: "array index out of bounds",
      0x41: "memory overflow",
      0x51: "call to uninitialized function",
    };
    return labels[code] ?? null;
  }

  exportPrivateKey(): string {
    return this.privateKey;
  }
}
