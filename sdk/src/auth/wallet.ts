// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
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
  private cachedNonce: number | null = null;
  
  // Closure-based key storage to prevent plaintext exposure on instance
  private readonly getKey: () => string;
  private readonly clearKey: () => void;

  constructor(config: WalletConfig) {
    let keyBuffer: Buffer | null;
    
    if (config.privateKey) {
      keyBuffer = Buffer.from(config.privateKey, "hex");
    } else {
      const keyPair = generateKeyPair();
      keyBuffer = Buffer.from(keyPair.privateKey, "hex");
    }

    // Derive address before wrapping key in closure
    const { ec as EC } = require("elliptic");
    const curve = new EC("secp256k1");
    const ecKey = curve.keyFromPrivate(keyBuffer.toString("hex"), "hex");
    const pubKey = ecKey.getPublic(false, "hex").slice(2);
    const hash = keccak256(Buffer.from(pubKey, "hex"));
    this.address = "0x" + hash.slice(-40);

    // Secure closure-based accessors
    this.getKey = () => {
      if (!keyBuffer) throw new Error("Wallet: private key has been cleared");
      return keyBuffer.toString("hex");
    };
    
    this.clearKey = () => {
      if (keyBuffer) {
        keyBuffer.fill(0); // Zero out memory
        keyBuffer = null;
      }
    };

    this.provider = config.provider;
  }

  async signTransaction(tx: Transaction): Promise<SignedTransaction> {
    // Validate chain ID to prevent cross-chain replay attacks
    if (tx.chainId === undefined || tx.chainId <= 0) {
      throw new Error("Wallet: valid chainId required for transaction signing");
    }

    const nonce = tx.nonce ?? await this.getNonce();
    const gasPrice = tx.gasPrice ?? BigInt(await this.provider.call("eth_gasPrice") as string);

    const txData = encodeParams([
      { type: "uint256", value: nonce } as AbiParam,
      { type: "uint256", value: gasPrice } as AbiParam,
      { type: "uint256", value: tx.gasLimit } as AbiParam,
      { type: "address", value: tx.to } as AbiParam,
      { type: "uint256", value: tx.value } as AbiParam,
      { type: "uint256", value: tx.chainId } as AbiParam,
    ]);

    const txHash = keccak256(txData);
    const signature = signMessage(this.getKey(), txHash);

    return {
      raw: "0x" + txData.slice(2) + signature,
      hash: "0x" + txHash,
    };
  }

  async getNonce(): Promise<number> {
    // Always fetch fresh nonce to avoid stale state issues
    const hex = (await this.provider.call("eth_getTransactionCount", [
      this.address,
      "latest",
    ])) as string;
    const nonce = parseInt(hex, 16);
    this.cachedNonce = nonce + 1;
    return nonce;
  }

  async getBalance(): Promise<bigint> {
    return this.provider.getBalance(this.address);
  }

  async sendTransaction(tx: Transaction): Promise<string> {
    const signed = await this.signTransaction(tx);
    return (await this.provider.call("eth_sendRawTransaction", [signed.raw])) as string;
  }

  /**
   * WARNING: Exposing private keys is dangerous. Use only for testing or migration.
   * Consider using hardware wallets or secure enclaves in production.
   */
  exportPrivateKey(): string {
    return this.getKey();
  }

  /**
   * Securely wipe the private key from memory when wallet is no longer needed.
   */
  destroy(): void {
    this.clearKey();
    this.cachedNonce = null;
  }
}
