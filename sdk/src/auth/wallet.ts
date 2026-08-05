import { generateKeyPair, signMessage, keccak256 } from "../utils/crypto";
import { encodeParams, AbiParam } from "../utils/encoding";
import { RpcProvider } from "../providers/rpc";
import { applyGasMargin, FeeData } from "../utils/gas";

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
  nonce?: number;
  chainId?: number;
}

export interface SignedTransaction {
  raw: string;
  hash: string;
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
    const { ec: EC } = require("elliptic");
    const curve = new EC("secp256k1");
    const key = curve.keyFromPrivate(privateKey, "hex");
    const pubKey = key.getPublic(false, "hex").slice(2); // remove 04 prefix
    const hash = keccak256(Buffer.from(pubKey, "hex"));
    return "0x" + hash.slice(-40);
  }

  async estimateGas(
    tx: Omit<Transaction, "gasLimit" | "gasPrice" | "maxFeePerGas" | "maxPriorityFeePerGas">
  ): Promise<bigint> {
    const estimated = await this.provider.estimateGas({
      from: this.address,
      to: tx.to,
      value: tx.value,
      data: tx.data,
    });
    const blockGasLimit = await this.provider.getBlockGasLimit();
    return applyGasMargin(estimated, blockGasLimit);
  }

  private async resolveFees(tx: Transaction): Promise<FeeData> {
    const hasLegacyFee = tx.gasPrice !== undefined;
    const hasEip1559Fee =
      tx.maxFeePerGas !== undefined || tx.maxPriorityFeePerGas !== undefined;

    if (hasLegacyFee && hasEip1559Fee) {
      throw new Error("Use either gasPrice or EIP-1559 fee fields, not both");
    }
    if (hasLegacyFee) {
      return { gasPrice: tx.gasPrice };
    }

    const feeData = await this.provider.getFeeData();
    if (!hasEip1559Fee) {
      return feeData;
    }

    if (
      feeData.maxFeePerGas === undefined ||
      feeData.maxPriorityFeePerGas === undefined
    ) {
      throw new Error("RPC provider does not expose EIP-1559 fee data");
    }

    return {
      maxFeePerGas: tx.maxFeePerGas ?? feeData.maxFeePerGas,
      maxPriorityFeePerGas:
        tx.maxPriorityFeePerGas ?? feeData.maxPriorityFeePerGas,
    };
  }

  async signTransaction(tx: Transaction): Promise<SignedTransaction> {
    // BUG: No chain ID validation — transaction could be replayed on a different
    // chain if chainId is missing or mismatched with the provider
    const nonce = tx.nonce ?? await this.getNonce();
    const gasLimit =
      tx.gasLimit ??
      (await this.estimateGas({
        to: tx.to,
        value: tx.value,
        data: tx.data,
        nonce: tx.nonce,
        chainId: tx.chainId,
      }));
    const fees = await this.resolveFees(tx);
    const gasPrice = fees.gasPrice ?? fees.maxFeePerGas;
    if (gasPrice === undefined) {
      throw new Error("RPC provider did not return a usable gas fee");
    }

    const txData = encodeParams([
      { type: "uint256", value: nonce } as AbiParam,
      { type: "uint256", value: gasPrice } as AbiParam,
      { type: "uint256", value: gasLimit } as AbiParam,
      { type: "address", value: tx.to } as AbiParam,
      { type: "uint256", value: tx.value } as AbiParam,
    ]);

    const txHash = keccak256(txData);
    const signature = signMessage(this.privateKey, txHash);

    return {
      raw: "0x" + txData.slice(2) + signature,
      hash: "0x" + txHash,
      gasLimit,
      ...fees,
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
    const signed = await this.signTransaction(tx);
    return (await this.provider.call("eth_sendRawTransaction", [signed.raw])) as string;
  }

  exportPrivateKey(): string {
    return this.privateKey;
  }
}
