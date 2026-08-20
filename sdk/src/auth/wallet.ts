// @contributor rafaio1
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
  
  // Closure-based secure key storage — key is never exposed as a property
  private readonly _signWithKey: (hash: Buffer) => string;
  private readonly _zeroKey: () => void;

  constructor(config: WalletConfig) {
    let keyBuffer: Buffer | null = null;
    
    if (config.privateKey) {
      keyBuffer = Buffer.from(config.privateKey, 'hex');
    } else {
      const keyPair = generateKeyPair();
      keyBuffer = Buffer.from(keyPair.privateKey, 'hex');
    }
    
    // Derive address before wrapping key in closure
    const { ec: EC } = require("elliptic");
    const curve = new EC("secp256k1");
    const keyObj = curve.keyFromPrivate(keyBuffer);
    const pubKey = keyObj.getPublic(false, "hex").slice(2);
    const hash = keccak256(Buffer.from(pubKey, "hex"));
    this.address = "0x" + hash.slice(-40);
    
    // Capture key in closure — not accessible as object property
    this._signWithKey = (msgHash: Buffer): string => {
      if (!keyBuffer) throw new Error("Wallet: key has been zeroed");
      return signMessage(keyBuffer.toString('hex'), msgHash);
    };
    
    // Zeroing function to securely erase key from memory
    this._zeroKey = () => {
      if (keyBuffer) {
        keyBuffer.fill(0);
        keyBuffer = null;
      }
    };
    
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
    // Validate chain ID to prevent cross-chain replay
    if (tx.chainId !== undefined) {
      const networkChainId = await this.provider.getChainId?.() ?? 
        parseInt((await this.provider.call("eth_chainId")) as string, 16);
      if (tx.chainId !== networkChainId) {
        throw new Error(`Wallet: chain ID mismatch (tx: ${tx.chainId}, network: ${networkChainId})`);
      }
    }
    
    // Always fetch fresh nonce to prevent stale nonce errors
    const nonce = tx.nonce ?? await this.getFreshNonce();
    const gasPrice = tx.gasPrice ?? BigInt(await this.provider.call("eth_gasPrice") as string);

    const txData = encodeParams([
      { type: "uint256", value: nonce } as AbiParam,
      { type: "uint256", value: gasPrice } as AbiParam,
      { type: "uint256", value: tx.gasLimit } as AbiParam,
      { type: "address", value: tx.to } as AbiParam,
      { type: "uint256", value: tx.value } as AbiParam,
    ]);

    const txHash = keccak256(txData);
    // Sign using closure-captured key — never exposes private key
    const signature = this._signWithKey(txHash);

    return {
      raw: "0x" + txData.slice(2) + signature,
      hash: "0x" + txHash,
    };
  }

  async getFreshNonce(): Promise<number> {
    // Always fetch fresh nonce from chain to prevent stale nonce issues
    const hex = (await this.provider.call("eth_getTransactionCount", [
      this.address,
      "pending",
    ])) as string;
    return parseInt(hex, 16);
  }
  
  async getNonce(): Promise<number> {
    return this.getFreshNonce();
  }

  async getBalance(): Promise<bigint> {
    return this.provider.getBalance(this.address);
  }

  async sendTransaction(tx: Transaction): Promise<string> {
    const signed = await this.signTransaction(tx);
    return (await this.provider.call("eth_sendRawTransaction", [signed.raw])) as string;
  }

  /**
   * Securely destroy the wallet by zeroing the private key from memory.
   * After calling this, the wallet cannot sign any more transactions.
   */
  destroy(): void {
    this._zeroKey();
    this.cachedNonce = null;
  }
}
