/**
 * @generated-by
 * Agent: scotia1973-bot (Hermes Agent)
 * Platform: Autonomous agent — EIP-1559 transaction support
 * Task: Bounty #154 — Fix wallet.ts signTransaction doesn't support EIP-1559
 * Runtime: darwin, arm64, /tmp/OpenAgents-final, bash
 */

import { generateKeyPair, signMessage, keccak256 } from "../utils/crypto";
import { encodeParams, AbiParam } from "../utils/encoding";
import { RpcProvider } from "../providers/rpc";

export interface WalletConfig {
  privateKey?: string;
  provider: RpcProvider;
}

export type TransactionType = 0 | 2;

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
  type?: TransactionType;
}

export interface SignedTransaction {
  raw: string;
  hash: string;
}

function rlpEncodeBytes(bytes: number[]): string {
  if (bytes.length === 1 && bytes[0] < 0x80) {
    return Buffer.from(bytes).toString("hex");
  }
  const lenHex = bytes.length.toString(16);
  const prefix = bytes.length <= 55
    ? (0x80 + bytes.length).toString(16)
    : (0xf7 + lenHex.length / 2).toString(16) + lenHex;
  return prefix + Buffer.from(bytes).toString("hex");
}

function rlpEncodeList(items: string[]): string {
  const encoded = items.join("");
  const bytes = Buffer.from(encoded, "hex");
  const lenHex = bytes.length.toString(16);
  const prefix = bytes.length <= 55
    ? (0xc0 + bytes.length).toString(16)
    : (0xf7 + lenHex.length / 2).toString(16) + lenHex;
  return prefix + encoded;
}

function bigIntToMinHex(n: bigint): string {
  if (n === BigInt(0)) return "";
  const hex = n.toString(16);
  return hex.length % 2 === 1 ? "0" + hex : hex;
}

function hexToBytes(hex: string): number[] {
  if (!hex) return [];
  const h = hex.startsWith("0x") ? hex.slice(2) : hex;
  const bytes: number[] = [];
  for (let i = 0; i < h.length; i += 2) {
    bytes.push(parseInt(h.substring(i, i + 2), 16));
  }
  return bytes;
}

function detectTransactionType(tx: Transaction): TransactionType {
  if (tx.type !== undefined) return tx.type;
  if (tx.maxFeePerGas !== undefined || tx.maxPriorityFeePerGas !== undefined) return 2;
  return 0;
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

  async signTransaction(tx: Transaction): Promise<SignedTransaction> {
    const txType = detectTransactionType(tx);
    const chainId = tx.chainId ?? (await this.provider.call("eth_chainId") as string);
    const chainIdNum = typeof chainId === "string" && chainId.startsWith("0x")
      ? parseInt(chainId, 16)
      : Number(chainId);
    const nonce = tx.nonce ?? (await this.getNonce());

    if (txType === 2) {
      return this.signEIP1559Transaction(tx, chainIdNum, nonce);
    }
    return this.signLegacyTransaction(tx, chainIdNum, nonce);
  }

  private async signEIP1559Transaction(tx: Transaction, chainId: number, nonce: number): Promise<SignedTransaction> {
    const maxPriorityFee = tx.maxPriorityFeePerGas ?? BigInt(await this.provider.call("eth_maxPriorityFeePerGas") as string);
    const maxFee = tx.maxFeePerGas ?? maxPriorityFee + BigInt(await this.provider.call("eth_gasPrice") as string);
    const fields = [
      rlpEncodeBytes([chainId]), rlpEncodeBytes([nonce]),
      rlpEncodeBytes(hexToBytes(bigIntToMinHex(maxPriorityFee))),
      rlpEncodeBytes(hexToBytes(bigIntToMinHex(maxFee))),
      rlpEncodeBytes(hexToBytes(bigIntToMinHex(tx.gasLimit))),
      rlpEncodeBytes(hexToBytes(tx.to.slice(2))),
      rlpEncodeBytes(hexToBytes(bigIntToMinHex(tx.value))),
      rlpEncodeBytes(hexToBytes(tx.data.startsWith("0x") ? tx.data.slice(2) : tx.data)),
      rlpEncodeBytes([]),
    ];
    const preHash = "02" + rlpEncodeList(fields);
    const txHash = keccak256(Buffer.from(preHash, "hex"));
    const sig = signMessage(this.privateKey, txHash);
    const sigHex = Buffer.from(sig, "hex");
    const r = sigHex.subarray(0, 32);
    const v = sigHex[64] >= 27 ? sigHex[64] - 27 : sigHex[64];
    const s = sigHex.subarray(32, 64);
    const rawFields = [
      rlpEncodeBytes([chainId]), rlpEncodeBytes([nonce]),
      rlpEncodeBytes(hexToBytes(bigIntToMinHex(maxPriorityFee))),
      rlpEncodeBytes(hexToBytes(bigIntToMinHex(maxFee))),
      rlpEncodeBytes(hexToBytes(bigIntToMinHex(tx.gasLimit))),
      rlpEncodeBytes(hexToBytes(tx.to.slice(2))),
      rlpEncodeBytes(hexToBytes(bigIntToMinHex(tx.value))),
      rlpEncodeBytes(hexToBytes(tx.data.startsWith("0x") ? tx.data.slice(2) : tx.data)),
      rlpEncodeBytes([]),
      rlpEncodeBytes([v]), rlpEncodeBytes(Array.from(r)), rlpEncodeBytes(Array.from(s)),
    ];
    const rawTx = "0x02" + rlpEncodeList(rawFields);
    return { raw: rawTx, hash: "0x" + txHash };
  }

  private async signLegacyTransaction(tx: Transaction, chainId: number, nonce: number): Promise<SignedTransaction> {
    const gasPrice = tx.gasPrice ?? BigInt(await this.provider.call("eth_gasPrice") as string);
    const fields = [
      rlpEncodeBytes([nonce]),
      rlpEncodeBytes(hexToBytes(bigIntToMinHex(gasPrice))),
      rlpEncodeBytes(hexToBytes(bigIntToMinHex(tx.gasLimit))),
      rlpEncodeBytes(hexToBytes(tx.to.slice(2))),
      rlpEncodeBytes(hexToBytes(bigIntToMinHex(tx.value))),
      rlpEncodeBytes(hexToBytes(tx.data.startsWith("0x") ? tx.data.slice(2) : tx.data)),
    ];
    const chainIdBig = BigInt(chainId);
    fields.push(rlpEncodeBytes(hexToBytes(bigIntToMinHex(chainIdBig))));
    fields.push(rlpEncodeBytes([]));
    fields.push(rlpEncodeBytes([]));
    const encodedTx = rlpEncodeList(fields);
    const txHash = keccak256(Buffer.from(encodedTx, "hex"));
    const sig = signMessage(this.privateKey, txHash);
    const sigHex = Buffer.from(sig, "hex");
    const r = sigHex.subarray(0, 32);
    const recId = sigHex[64] >= 27 ? sigHex[64] - 27 : sigHex[64];
    const v = chainId * 2 + 35 + recId;
    const s = sigHex.subarray(32, 64);
    const rawFields = [
      rlpEncodeBytes([nonce]),
      rlpEncodeBytes(hexToBytes(bigIntToMinHex(gasPrice))),
      rlpEncodeBytes(hexToBytes(bigIntToMinHex(tx.gasLimit))),
      rlpEncodeBytes(hexToBytes(tx.to.slice(2))),
      rlpEncodeBytes(hexToBytes(bigIntToMinHex(tx.value))),
      rlpEncodeBytes(hexToBytes(tx.data.startsWith("0x") ? tx.data.slice(2) : tx.data)),
      rlpEncodeBytes([v]), rlpEncodeBytes(Array.from(r)), rlpEncodeBytes(Array.from(s)),
    ];
    const rawTx = "0x" + rlpEncodeList(rawFields);
    return { raw: rawTx, hash: "0x" + txHash };
  }

  async getNonce(): Promise<number> {
    const hex = (await this.provider.call("eth_getTransactionCount", [this.address, "latest"])) as string;
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
