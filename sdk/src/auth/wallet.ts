/**
 * @fix-author codex-xyjk0511
 * @fix-date 2026-05-31
 * @platform-init User request: evaluate and implement issue #39 transaction pre-simulation in SDK wallet send path.
 * @runtime os=windows arch=x64 working_dir=F:\jiedan\OpenAgents shell=powershell
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
    const currentBlock = await this.getCurrentBlockNumber();
    const cacheKey = this.getSimulationCacheKey(tx);
    const cachedAt = this.simulationCache.get(cacheKey);

    if (cachedAt === currentBlock) {
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
      this.simulationCache.set(cacheKey, currentBlock);
    } catch (error) {
      const reason = this.decodeSimulationError(error);
      throw new Error(`Transaction simulation failed: ${reason}`);
    }
  }

  private async getCurrentBlockNumber(): Promise<number> {
    const blockHex = (await this.provider.call("eth_blockNumber")) as string;
    return parseInt(blockHex, 16);
  }

  private getSimulationCacheKey(tx: Transaction): string {
    const gasPrice = tx.gasPrice ?? null;
    return [
      this.address.toLowerCase(),
      tx.to.toLowerCase(),
      tx.data.toLowerCase(),
      tx.value.toString(),
      tx.gasLimit.toString(),
      gasPrice === null ? "none" : gasPrice.toString(),
    ].join("|");
  }

  private toRpcHex(value: bigint): string {
    return "0x" + value.toString(16);
  }

  private decodeSimulationError(error: unknown): string {
    const fallback = error instanceof Error ? error.message : "execution reverted";
    const raw = this.extractRevertData(error);

    if (!raw) {
      return fallback;
    }

    const parsed = this.decodeRevertData(raw);
    return parsed ?? fallback;
  }

  private extractRevertData(error: unknown): string | null {
    const queue: unknown[] = [error];
    const seen = new Set<unknown>();

    while (queue.length > 0) {
      const current = queue.shift();
      if (!current || typeof current !== "object" || seen.has(current)) {
        continue;
      }
      seen.add(current);

      const obj = current as Record<string, unknown>;

      for (const key of ["data", "error", "cause"]) {
        if (obj[key]) {
          queue.push(obj[key]);
        }
      }

      const possibleHex = obj["data"];
      if (typeof possibleHex === "string" && /^0x[0-9a-fA-F]+$/.test(possibleHex)) {
        return possibleHex;
      }

      const message = obj["message"];
      if (typeof message === "string") {
        const match = message.match(/0x[0-9a-fA-F]{8,}/);
        if (match) {
          return match[0];
        }
      }
    }

    return null;
  }

  private decodeRevertData(revertHex: string): string | null {
    const normalized = revertHex.toLowerCase();

    if (normalized.startsWith("0x08c379a0")) {
      const data = normalized.slice(10);
      if (data.length < 128) {
        return "execution reverted";
      }
      const lengthHex = data.slice(64, 128);
      const length = parseInt(lengthHex, 16);
      const strHex = data.slice(128, 128 + length * 2);
      if (!strHex) {
        return "execution reverted";
      }
      const reason = Buffer.from(strHex, "hex").toString("utf8");
      return reason || "execution reverted";
    }

    if (normalized.startsWith("0x4e487b71")) {
      const codeHex = normalized.slice(10, 74);
      const code = parseInt(codeHex || "0", 16);
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
