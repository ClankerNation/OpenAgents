/**
 * @contributor-info doubao-agent (spiritwanghs fork), 2026-09-29
 * @preamble Autonomous coding agent executing GitHub bounties; user provides a fine-grained GitHub PAT.
 * @runtime os=linux arch=x64 home=/home/user working_dir=/home/user/Doubao/chats/38444718400345090/OpenAgents shell=/bin/bash
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
}

export interface SignedTransaction {
  raw: string;
  hash: string;
}

export class Wallet {
  public readonly address: string;
  private provider: RpcProvider;

  // Private key lives in a closure, NOT as an own property of `this`.
  // JSON.stringify(wallet), Object.keys(wallet), or object spread cannot
  // reach it. Call clear() to overwrite it when the wallet is discarded.
  private _sign: (txHash: string) => string;
  private _exportKey: () => string;
  private _clear: () => void;

  constructor(config: WalletConfig) {
    let privateKey: string = config.privateKey ?? generateKeyPair().privateKey;
    this.address = this.deriveAddress(privateKey);
    this.provider = config.provider;

    this._sign = (txHash) => signMessage(privateKey, txHash);
    this._exportKey = () => privateKey;
    this._clear = () => { privateKey = ""; };
  }

  private deriveAddress(privateKey: string): string {
    const elliptic = require("elliptic");
    const EC = elliptic.ec;
    const curve = new EC("secp256k1");
    const key = curve.keyFromPrivate(privateKey, "hex");
    const pubKey = key.getPublic(false, "hex").slice(2);
    const hash = keccak256(Buffer.from(pubKey, "hex"));
    return "0x" + hash.slice(-40);
  }

  /** Overwrite the in-memory private key. */
  clear(): void {
    this._clear();
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
    const signature = this._sign(txHash);

    return {
      raw: "0x" + txData.slice(2) + signature,
      hash: "0x" + txHash,
    };
  }

  async getNonce(): Promise<number> {
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
    return this._exportKey();
  }
}
