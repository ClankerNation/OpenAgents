/**
 * @contributor-info rafaio1
 * @timestamp 2026-08-20T00:00:00Z
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
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
  type?: number; // 0 = legacy, 2 = EIP-1559
}

export interface SignedTransaction {
  raw: string;
  hash: string;
  type: number;
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
    const { ec as EC } = require("elliptic");
    const curve = new EC("secp256k1");
    const key = curve.keyFromPrivate(privateKey, "hex");
    const pubKey = key.getPublic(false, "hex").slice(2);
    const hash = keccak256(Buffer.from(pubKey, "hex"));
    return "0x" + hash.slice(-40);
  }

  async signTransaction(tx: Transaction): Promise<SignedTransaction> {
    const nonce = tx.nonce ?? (await this.getNonce());
    const chainId = tx.chainId ?? this.provider.getChainId();

    // Auto-detect transaction type: EIP-1559 if maxFeePerGas present, else legacy
    const isEip1559 =
      tx.maxFeePerGas !== undefined || tx.type === 2;

    if (isEip1559) {
      return this.signEip1559Transaction(tx, nonce, chainId);
    } else {
      return this.signLegacyTransaction(tx, nonce, chainId);
    }
  }

  private async signLegacyTransaction(
    tx: Transaction,
    nonce: number,
    chainId: number
  ): Promise<SignedTransaction> {
    const gasPrice =
      tx.gasPrice ??
      BigInt((await this.provider.call("eth_gasPrice")) as string);

    // RLP encode: [nonce, gasPrice, gasLimit, to, value, data, chainId, 0, 0]
    const fields: AbiParam[] = [
      { type: "uint256", value: nonce },
      { type: "uint256", value: gasPrice },
      { type: "uint256", value: tx.gasLimit },
      { type: "address", value: tx.to },
      { type: "uint256", value: tx.value },
      { type: "bytes", value: tx.data || "0x" },
      { type: "uint256", value: chainId },
      { type: "uint256", value: 0 },
      { type: "uint256", value: 0 },
    ];

    const encoded = encodeParams(fields);
    const txHash = keccak256(encoded);
    const signature = signMessage(this.privateKey, txHash);

    // Append signature to RLP for raw transaction
    const raw = "0x" + encoded.slice(2) + signature;

    return {
      raw,
      hash: "0x" + txHash,
      type: 0,
    };
  }

  private async signEip1559Transaction(
    tx: Transaction,
    nonce: number,
    chainId: number
  ): Promise<SignedTransaction> {
    const maxFeePerGas =
      tx.maxFeePerGas ??
      BigInt((await this.provider.call("eth_gasPrice")) as string);
    const maxPriorityFeePerGas =
      tx.maxPriorityFeePerGas ?? BigInt(1_500_000_000); // 1.5 gwei default

    // EIP-1559 unsigned tx payload (RLP without type prefix):
    // [chainId, nonce, maxPriorityFeePerGas, maxFeePerGas, gasLimit, to, value, data, accessList]
    const fields: AbiParam[] = [
      { type: "uint256", value: chainId },
      { type: "uint256", value: nonce },
      { type: "uint256", value: maxPriorityFeePerGas },
      { type: "uint256", value: maxFeePerGas },
      { type: "uint256", value: tx.gasLimit },
      { type: "address", value: tx.to },
      { type: "uint256", value: tx.value },
      { type: "bytes", value: tx.data || "0x" },
      { type: "bytes", value: "0x" }, // empty access list
    ];

    const encodedPayload = encodeParams(fields);

    // EIP-1559 signing hash: keccak256(0x02 || RLP(payload))
    const typePrefix = Buffer.from([0x02]);
    const payloadBuf = Buffer.from(encodedPayload.slice(2), "hex");
    const toSign = Buffer.concat([typePrefix, payloadBuf]);
    const txHash = keccak256(toSign);

    const signature = signMessage(this.privateKey, txHash);

    // Raw signed tx: 0x02 || RLP([...payload, v, r, s])
    // For simplicity, we concatenate type prefix + encoded payload + signature
    const raw =
      "0x02" + encodedPayload.slice(2) + signature;

    return {
      raw,
      hash: "0x" + txHash,
      type: 2,
    };
  }

  async getNonce(): Promise<number> {
    // Always fetch fresh nonce from chain to prevent stale nonce errors
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
    return (await this.provider.call("eth_sendRawTransaction", [
      signed.raw,
    ])) as string;
  }

  exportPrivateKey(): string {
    return this.privateKey;
  }
}
