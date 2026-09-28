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
}

export interface SignedTransaction {
  raw: string;
  hash: string;
}

export class Wallet {
  public readonly address: string;
  private provider: RpcProvider;
  // Private key held in a non-enumerable field so it does not leak via
  // JSON.stringify(wallet), console.dir, or object spread. Clear with clear()
  // when the wallet is no longer needed.
  private _privateKey: string;

  constructor(config: WalletConfig) {
    const pk = config.privateKey ?? generateKeyPair().privateKey;
    Object.defineProperty(this, "_privateKey", {
      value: pk,
      enumerable: false,
      writable: true,
      configurable: true,
    });
    this._privateKey = pk;
    this.address = this.deriveAddress(pk);
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

  /** Overwrite the in-memory private key. Call when the wallet is discarded. */
  clear(): void {
    // Overwrite by assigning a new string; the old string will be GC'd.
    // This is a best-effort mitigation, not a substitute for a secure enclave.
    (this as { _privateKey: string })._privateKey = "";
  }

  async signTransaction(tx: Transaction): Promise<SignedTransaction> {
    const expectedChainId = this.provider.getChainId();
    if (tx.chainId !== undefined && tx.chainId !== expectedChainId) {
      throw new Error(
        `Chain ID mismatch: tx specifies ${tx.chainId}, provider is ${expectedChainId}`
      );
    }
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
    const signature = signMessage(this._privateKey, txHash);

    return {
      raw: "0x" + txData.slice(2) + signature,
      hash: "0x" + txHash,
    };
  }

  async getNonce(): Promise<number> {
    // Always fetch fresh from chain; caching nonces causes "nonce too low"
    // errors when external transactions land between sends.
    const hex = (await this.provider.call("eth_getTransactionCount", [
      this.address,
      "latest",
    ])) as string;
    return parseInt(hex, 16);
  }

  async getBalance(): Promise<bigint> {
    return this.provider.getBalance(this.address);
  }

  async sendTransaction(tx: Transaction): Promise<string> {
    const signed = await this.signTransaction(tx);
    return (await this.provider.call("eth_sendRawTransaction", [signed.raw])) as string;
  }

  exportPrivateKey(): string {
    return this._privateKey;
  }
}
