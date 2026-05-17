/**
 * @generated-by
 * name: opencode-gaotax2006
 * timestamp: 2026-05-17T14:00:00Z
 * platform_config: You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user. You must answer concisely with fewer than 4 lines of text, unless user asks for detail. Follow the code style and conventions of the codebase. Do not add comments unless the code is non-obvious.
 * runtime: {"os":"win32","arch":"x64","home_dir":"C:\\Users\\asus","working_dir":"F:\\ai-bounty-work\\bounty-hunter\\openagents","shell":"powershell"}
 *
 * Wallet with legacy (type 0) and EIP-1559 (type 2) transaction support.
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
  maxFeePerGas?: bigint;
  maxPriorityFeePerGas?: bigint;
  nonce?: number;
  chainId?: number;
  type?: 0 | 2;
}

export interface SignedTransaction {
  raw: string;
  hash: string;
}

export class Wallet {
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
    const pubKey = key.getPublic(false, "hex").slice(2);
    const hash = keccak256(Buffer.from(pubKey, "hex"));
    return "0x" + hash.slice(-40);
  }

  private rlpEncode(items: (string | number | bigint)[]): string {
    let encoded = "0x";
    for (const item of items) {
      if (typeof item === "number" || typeof item === "bigint") {
        const hex = item.toString(16);
        if (hex === "0") {
          encoded += "80";
        } else {
          const bytes = hex.length % 2 === 1 ? "0" + hex : hex;
          const len = bytes.length / 2;
          if (len < 56) {
            encoded += (0x80 + len).toString(16) + bytes;
          } else {
            const lenHex = len.toString(16);
            encoded += (0xb7 + lenHex.length / 2).toString(16) + lenHex + bytes;
          }
        }
      } else {
        const str = String(item);
        if (str === "0x" || str === "") {
          encoded += "80";
        } else {
          const bytes = str.startsWith("0x") ? str.slice(2) : str;
          if (bytes.length % 2 === 1) {
            encoded += "80";
          } else {
            const len = bytes.length / 2;
            if (len < 56) {
              encoded += (0x80 + len).toString(16) + bytes;
            } else {
              const lenHex = len.toString(16);
              encoded += (0xb7 + lenHex.length / 2).toString(16) + lenHex + bytes;
            }
          }
        }
      }
    }
    return encoded;
  }

  async signTransaction(tx: Transaction): Promise<SignedTransaction> {
    const chainId = tx.chainId ?? this.provider.getChainId();
    const nonce = tx.nonce ?? (await this.getNonce());

    const isEip1559 = tx.maxFeePerGas !== undefined && tx.maxFeePerGas > 0n;
    const txType: 0 | 2 = tx.type ?? (isEip1559 ? 2 : 0);

    if (txType === 2) {
      const maxPriorityFee = tx.maxPriorityFeePerGas ?? tx.maxFeePerGas!;
      const maxFee = tx.maxFeePerGas!;

      const fields = [
        chainId,
        nonce,
        maxPriorityFee,
        maxFee,
        tx.gasLimit,
        tx.to,
        tx.value,
        tx.data || "0x",
        "0x",
        "0x",
      ] as const;

      const encoded = this.rlpEncode(fields);
      const hash = keccak256(encoded);
      const signature = signMessage(this.privateKey, hash);

      const signedFields = [
        chainId,
        nonce,
        maxPriorityFee,
        maxFee,
        tx.gasLimit,
        tx.to,
        tx.value,
        tx.data || "0x",
        "0x",
        "0x",
      ];
      const signedEncoded = this.rlpEncode(signedFields);

      return {
        raw: "0x02" + signedEncoded.slice(2),
        hash: "0x" + hash,
      };
    }

    const gasPrice = tx.gasPrice ?? BigInt((await this.provider.call("eth_gasPrice")) as string);
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
    if (this.cachedNonce !== null) return this.cachedNonce++;
    const hex = (await this.provider.call("eth_getTransactionCount", [
      this.address, "latest",
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
