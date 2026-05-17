/**
 * @generated-by
 * name: opencode-gaotax2006
 * timestamp: 2026-05-17T15:30:00Z
 * platform_config: You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user. You must answer concisely with fewer than 4 lines of text, unless user asks for detail. Follow the code style and conventions of the codebase. Do not add comments unless the code is non-obvious.
 * runtime: {"os":"win32","arch":"x64","home_dir":"C:\\Users\\asus","working_dir":"F:\\ai-bounty-work\\bounty-hunter\\openagents","shell":"powershell"}
 *
 * Wallet with closure-based key storage, chain ID validation, and fresh nonce per tx.
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

function createKeyStore(initialKey?: string) {
  let key = initialKey || "";
  return {
    getKey: () => key,
    zeroKey: () => { key = "0".repeat(64); },
  };
}

export class Wallet {
  public readonly address: string;
  private keyStore: ReturnType<typeof createKeyStore>;
  private provider: RpcProvider;

  constructor(config: WalletConfig) {
    let privateKey: string;
    if (config.privateKey) {
      privateKey = config.privateKey;
    } else {
      const keyPair = generateKeyPair();
      privateKey = keyPair.privateKey;
    }
    this.keyStore = createKeyStore(privateKey);
    this.address = this.deriveAddress(privateKey);
    this.provider = config.provider;
    privateKey = "0".repeat(64);
  }

  private deriveAddress(privateKey: string): string {
    const { ec: EC } = require("elliptic");
    const curve = new EC("secp256k1");
    const key = curve.keyFromPrivate(privateKey, "hex");
    const pubKey = key.getPublic(false, "hex").slice(2);
    const hash = keccak256(Buffer.from(pubKey, "hex"));
    return "0x" + hash.slice(-40);
  }

  private validateChainId(tx: Transaction): void {
    const txChainId = tx.chainId ?? this.provider.chainId;
    if (txChainId !== this.provider.chainId) {
      throw new Error(
        `Chain ID mismatch: transaction chainId=${txChainId}, provider chainId=${this.provider.chainId}`
      );
    }
  }

  async signTransaction(tx: Transaction): Promise<SignedTransaction> {
    this.validateChainId(tx);
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
    const key = this.keyStore.getKey();
    const signature = signMessage(key, txHash);

    this.keyStore.zeroKey();

    return {
      raw: "0x" + txData.slice(2) + signature,
      hash: "0x" + txHash,
    };
  }

  async getFreshNonce(): Promise<number> {
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
    return this.keyStore.getKey();
  }
}
