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
  gasLimit?: bigint;
  gasPrice?: bigint;
  maxFeePerGas?: bigint;
  maxPriorityFeePerGas?: bigint;
  gasMarginBps?: number;
  nonce?: number;
  chainId?: number;
}

export interface SignedTransaction {
  raw: string;
  hash: string;
}

export interface PreparedTransaction extends Transaction {
  gasLimit: bigint;
  gasPrice?: bigint;
  maxFeePerGas?: bigint;
  maxPriorityFeePerGas?: bigint;
}

export class Wallet {
  // BUG: Private key stored as plaintext string in memory — should use
  // a secure enclave, encrypted storage, or at minimum a Buffer that can be zeroed
  public readonly address: string;
  private privateKey: string;
  private provider: RpcProvider;
  private cachedNonce: number | null = null;

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
    const EC = require("elliptic").ec;
    const curve = new EC("secp256k1");
    const key = curve.keyFromPrivate(privateKey, "hex");
    const pubKey = key.getPublic(false, "hex").slice(2); // remove 04 prefix
    const hash = keccak256(Buffer.from(pubKey, "hex"));
    return "0x" + hash.slice(-40);
  }

  async signTransaction(tx: Transaction): Promise<SignedTransaction> {
    // BUG: No chain ID validation — transaction could be replayed on a different
    // chain if chainId is missing or mismatched with the provider
    const prepared = await this.prepareTransaction(tx);
    const nonce = tx.nonce ?? await this.getNonce();
    const gasPrice = prepared.gasPrice ?? prepared.maxFeePerGas ?? BigInt(await this.provider.call("eth_gasPrice") as string);

    const txData = encodeParams([
      { type: "uint256", value: nonce } as AbiParam,
      { type: "uint256", value: gasPrice } as AbiParam,
      { type: "uint256", value: prepared.gasLimit } as AbiParam,
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

  async prepareTransaction(tx: Transaction): Promise<PreparedTransaction> {
    const gasLimit = tx.gasLimit ?? await this.estimateGasWithMargin(tx, tx.gasMarginBps ?? 2000);
    const hasManualFees = tx.gasPrice !== undefined ||
      (tx.maxFeePerGas !== undefined && tx.maxPriorityFeePerGas !== undefined);
    const fees = hasManualFees
      ? {}
      : await this.getFeeData();

    return {
      ...tx,
      gasLimit,
      gasPrice: tx.gasPrice ?? fees.gasPrice,
      maxFeePerGas: tx.maxFeePerGas ?? fees.maxFeePerGas,
      maxPriorityFeePerGas: tx.maxPriorityFeePerGas ?? fees.maxPriorityFeePerGas,
    };
  }

  async estimateGasWithMargin(tx: Transaction, marginBps = 2000): Promise<bigint> {
    const estimated = BigInt(await this.provider.call("eth_estimateGas", [this.toRpcTransaction(tx)]) as string);
    const withMargin = estimated + (estimated * BigInt(marginBps)) / 10000n;
    const blockGasLimit = await this.getLatestBlockGasLimit();
    return withMargin > blockGasLimit ? blockGasLimit : withMargin;
  }

  private async getLatestBlockGasLimit(): Promise<bigint> {
    const block = await this.provider.call("eth_getBlockByNumber", ["latest", false]) as { gasLimit?: string };
    if (!block || typeof block.gasLimit !== "string") {
      throw new Error("Unable to read latest block gas limit");
    }
    return BigInt(block.gasLimit);
  }

  private async getFeeData(): Promise<{
    gasPrice?: bigint;
    maxFeePerGas?: bigint;
    maxPriorityFeePerGas?: bigint;
  }> {
    const block = await this.provider.call("eth_getBlockByNumber", ["latest", false]) as { baseFeePerGas?: string };
    if (block && typeof block.baseFeePerGas === "string") {
      const priority = await this.getPriorityFee();
      return {
        maxPriorityFeePerGas: priority,
        maxFeePerGas: BigInt(block.baseFeePerGas) * 2n + priority,
      };
    }

    return {
      gasPrice: BigInt(await this.provider.call("eth_gasPrice") as string),
    };
  }

  private async getPriorityFee(): Promise<bigint> {
    try {
      return BigInt(await this.provider.call("eth_maxPriorityFeePerGas") as string);
    } catch (_) {
      return BigInt(await this.provider.call("eth_gasPrice") as string) / 10n;
    }
  }

  private toRpcTransaction(tx: Transaction): Record<string, string> {
    const rpcTx: Record<string, string> = {
      from: this.address,
      to: tx.to,
      value: "0x" + tx.value.toString(16),
      data: tx.data || "0x",
    };
    if (tx.gasPrice !== undefined) rpcTx.gasPrice = "0x" + tx.gasPrice.toString(16);
    if (tx.maxFeePerGas !== undefined) rpcTx.maxFeePerGas = "0x" + tx.maxFeePerGas.toString(16);
    if (tx.maxPriorityFeePerGas !== undefined) {
      rpcTx.maxPriorityFeePerGas = "0x" + tx.maxPriorityFeePerGas.toString(16);
    }
    return rpcTx;
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
    const signed = await this.signTransaction(tx);
    return (await this.provider.call("eth_sendRawTransaction", [signed.raw])) as string;
  }

  exportPrivateKey(): string {
    return this.privateKey;
  }
}
