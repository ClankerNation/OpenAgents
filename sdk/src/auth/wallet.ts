import { ethers } from "ethers";
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
  maxFeePerGas?: bigint;
  maxPriorityFeePerGas?: bigint;
  nonce?: number;
  chainId?: number;
  type?: 0 | 1 | 2;
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

  constructor(config: WalletConfig) {
    if (config.privateKey) {
      this.privateKey = config.privateKey;
    } else {
      this.privateKey = ethers.Wallet.createRandom().privateKey;
    }
    this.address = this.deriveAddress(this.privateKey);
    this.provider = config.provider;
  }

  private deriveAddress(privateKey: string): string {
    return new ethers.Wallet(this.normalizePrivateKey(privateKey)).address;
  }

  async signTransaction(tx: Transaction): Promise<SignedTransaction> {
    const nonce = tx.nonce ?? await this.getNonce();
    const chainId = tx.chainId ?? this.provider.getChainId();
    const type = tx.type ?? (tx.maxFeePerGas !== undefined ? 2 : 0);
    const signer = new ethers.Wallet(this.normalizePrivateKey(this.privateKey));

    const request: ethers.TransactionRequest = {
      to: tx.to,
      value: tx.value,
      data: tx.data,
      gasLimit: tx.gasLimit,
      nonce,
      chainId,
      type,
    };

    if (type === 2) {
      if (tx.maxFeePerGas === undefined || tx.maxPriorityFeePerGas === undefined) {
        throw new Error("EIP-1559 transactions require maxFeePerGas and maxPriorityFeePerGas");
      }
      request.maxFeePerGas = tx.maxFeePerGas;
      request.maxPriorityFeePerGas = tx.maxPriorityFeePerGas;
    } else {
      request.gasPrice = tx.gasPrice ?? BigInt(await this.provider.call("eth_gasPrice") as string);
    }

    const raw = await signer.signTransaction(request);

    return {
      raw,
      hash: ethers.keccak256(raw),
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

  private normalizePrivateKey(privateKey: string): string {
    return privateKey.startsWith("0x") ? privateKey : `0x${privateKey}`;
  }
}
