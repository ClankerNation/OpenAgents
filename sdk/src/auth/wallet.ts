/**
 * @generated-by rafaio1
 * @timestamp 2026-08-20T14:25:00Z
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents
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
  type?: number; // 0 = legacy, 2 = EIP-1559
  nonce?: number;
  chainId?: number;
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
    const pubKey = key.getPublic(false, "hex").slice(2); // remove 04 prefix
    const hash = keccak256(Buffer.from(pubKey, "hex"));
    return "0x" + hash.slice(-40);
  }

  async signTransaction(tx: Transaction): Promise<SignedTransaction> {
    const nonce = tx.nonce ?? await this.getNonce();
    const chainId = tx.chainId ?? this.provider.getChainId();

    // Determine transaction type: EIP-1559 (type 2) if maxFeePerGas present, else legacy (type 0)
    const isEip1559 = tx.maxFeePerGas !== undefined || tx.type === 2;

    let txData: string;
    let txHash: string;

    if (isEip1559) {
      // EIP-1559 Transaction (Type 2)
      const maxFeePerGas = tx.maxFeePerGas ?? BigInt(await this.provider.call("eth_gasPrice") as string);
      const maxPriorityFeePerGas = tx.maxPriorityFeePerGas ?? BigInt(1_500_000_000); // Default 1.5 gwei

      // RLP encode: [chainId, nonce, maxPriorityFeePerGas, maxFeePerGas, gasLimit, to, value, data, accessList]
      // Simplified RLP encoding for EIP-1559 without access list
      const rlpPayload = this._rlpEncodeEip1559(
        chainId,
        nonce,
        maxPriorityFeePerGas,
        maxFeePerGas,
        tx.gasLimit,
        tx.to,
        tx.value,
        tx.data
      );

      // EIP-1559 transactions are prefixed with 0x02 before hashing
      txHash = keccak256(Buffer.concat([Buffer.from([0x02]), Buffer.from(rlpPayload.slice(2), "hex")]));
      const signature = signMessage(this.privateKey, txHash);

      // Signed tx = 0x02 || RLP([chainId, nonce, maxPriorityFee, maxFee, gasLimit, to, value, data, accessList, v, r, s])
      const signedRlp = this._rlpEncodeSignedEip1559(
        chainId,
        nonce,
        maxPriorityFeePerGas,
        maxFeePerGas,
        tx.gasLimit,
        tx.to,
        tx.value,
        tx.data,
        signature
      );

      txData = "0x02" + signedRlp.slice(2);
    } else {
      // Legacy Transaction (Type 0)
      const gasPrice = tx.gasPrice ?? BigInt(await this.provider.call("eth_gasPrice") as string);

      // RLP encode: [nonce, gasPrice, gasLimit, to, value, data, chainId, 0, 0] (EIP-155)
      const rlpPayload = this._rlpEncodeLegacy(
        nonce,
        gasPrice,
        tx.gasLimit,
        tx.to,
        tx.value,
        tx.data,
        chainId
      );

      txHash = keccak256(Buffer.from(rlpPayload.slice(2), "hex"));
      const signature = signMessage(this.privateKey, txHash);

      // Signed legacy tx includes chainId in v (EIP-155)
      const signedRlp = this._rlpEncodeSignedLegacy(
        nonce,
        gasPrice,
        tx.gasLimit,
        tx.to,
        tx.value,
        tx.data,
        chainId,
        signature
      );

      txData = signedRlp;
    }

    return {
      raw: txData,
      hash: "0x" + txHash,
    };
  }

  /**
   * Minimal RLP encoder for unsigned EIP-1559 transaction fields.
   */
  private _rlpEncodeEip1559(
    chainId: number,
    nonce: number,
    maxPriorityFeePerGas: bigint,
    maxFeePerGas: bigint,
    gasLimit: bigint,
    to: string,
    value: bigint,
    data: string
  ): string {
    const fields = [
      this._encodeUint(chainId),
      this._encodeUint(nonce),
      this._encodeBigint(maxPriorityFeePerGas),
      this._encodeBigint(maxFeePerGas),
      this._encodeBigint(gasLimit),
      this._encodeAddress(to),
      this._encodeBigint(value),
      this._encodeBytes(data),
      this._encodeEmptyList(), // accessList placeholder
    ];
    return this._rlpEncodeList(fields);
  }

  /**
   * Minimal RLP encoder for signed EIP-1559 transaction fields.
   */
  private _rlpEncodeSignedEip1559(
    chainId: number,
    nonce: number,
    maxPriorityFeePerGas: bigint,
    maxFeePerGas: bigint,
    gasLimit: bigint,
    to: string,
    value: bigint,
    data: string,
    signature: string
  ): string {
    const sig = signature.startsWith("0x") ? signature.slice(2) : signature;
    const r = sig.slice(0, 64);
    const s = sig.slice(64, 128);
    const v = parseInt(sig.slice(128, 130), 16);
    // EIP-1559 uses yParity (0 or 1) instead of v (27/28)
    const yParity = v >= 27 ? v - 27 : v;

    const fields = [
      this._encodeUint(chainId),
      this._encodeUint(nonce),
      this._encodeBigint(maxPriorityFeePerGas),
      this._encodeBigint(maxFeePerGas),
      this._encodeBigint(gasLimit),
      this._encodeAddress(to),
      this._encodeBigint(value),
      this._encodeBytes(data),
      this._encodeEmptyList(), // accessList
      this._encodeUint(yParity),
      this._encodeHex(r),
      this._encodeHex(s),
    ];
    return this._rlpEncodeList(fields);
  }

  /**
   * Minimal RLP encoder for unsigned legacy transaction fields (EIP-155).
   */
  private _rlpEncodeLegacy(
    nonce: number,
    gasPrice: bigint,
    gasLimit: bigint,
    to: string,
    value: bigint,
    data: string,
    chainId: number
  ): string {
    const fields = [
      this._encodeUint(nonce),
      this._encodeBigint(gasPrice),
      this._encodeBigint(gasLimit),
      this._encodeAddress(to),
      this._encodeBigint(value),
      this._encodeBytes(data),
      this._encodeUint(chainId),
      this._encodeUint(0),
      this._encodeUint(0),
    ];
    return this._rlpEncodeList(fields);
  }

  /**
   * Minimal RLP encoder for signed legacy transaction fields (EIP-155).
   */
  private _rlpEncodeSignedLegacy(
    nonce: number,
    gasPrice: bigint,
    gasLimit: bigint,
    to: string,
    value: bigint,
    data: string,
    chainId: number,
    signature: string
  ): string {
    const sig = signature.startsWith("0x") ? signature.slice(2) : signature;
    const r = sig.slice(0, 64);
    const s = sig.slice(64, 128);
    const vRaw = parseInt(sig.slice(128, 130), 16);
    // EIP-155: v = chainId * 2 + 35 + recovery_id
    const v = chainId * 2 + 35 + (vRaw >= 27 ? vRaw - 27 : vRaw);

    const fields = [
      this._encodeUint(nonce),
      this._encodeBigint(gasPrice),
      this._encodeBigint(gasLimit),
      this._encodeAddress(to),
      this._encodeBigint(value),
      this._encodeBytes(data),
      this._encodeUint(v),
      this._encodeHex(r),
      this._encodeHex(s),
    ];
    return this._rlpEncodeList(fields);
  }

  // --- Minimal RLP helpers ---

  private _encodeUint(value: number): string {
    if (value === 0) return "80"; // empty byte string
    const hex = value.toString(16);
    const padded = hex.length % 2 ? "0" + hex : hex;
    const len = padded.length / 2;
    if (len === 1 && value < 128) return padded;
    return (128 + len).toString(16) + padded;
  }

  private _encodeBigint(value: bigint): string {
    if (value === 0n) return "80";
    let hex = value.toString(16);
    if (hex.length % 2) hex = "0" + hex;
    const len = hex.length / 2;
    if (len === 1 && value < 128n) return hex;
    return (128 + len).toString(16) + hex;
  }

  private _encodeAddress(addr: string): string {
    const clean = addr.startsWith("0x") ? addr.slice(2) : addr;
    return "94" + clean.toLowerCase().padStart(40, "0"); // 0x94 = 128 + 20
  }

  private _encodeBytes(data: string): string {
    const clean = data.startsWith("0x") ? data.slice(2) : data;
    if (clean.length === 0) return "80";
    const len = clean.length / 2;
    if (len <= 55) return (128 + len).toString(16) + clean;
    const lenHex = len.toString(16);
    const lenPadded = lenHex.length % 2 ? "0" + lenHex : lenHex;
    return (183 + lenPadded.length / 2).toString(16) + lenPadded + clean;
  }

  private _encodeHex(hex: string): string {
    const clean = hex.startsWith("0x") ? hex.slice(2) : hex;
    const len = clean.length / 2;
    if (len <= 55) return (128 + len).toString(16) + clean;
    const lenHex = len.toString(16);
    const lenPadded = lenHex.length % 2 ? "0" + lenHex : lenHex;
    return (183 + lenPadded.length / 2).toString(16) + lenPadded + clean;
  }

  private _encodeEmptyList(): string {
    return "c0"; // empty list
  }

  private _rlpEncodeList(items: string[]): string {
    const payload = items.join("");
    const len = payload.length / 2;
    if (len <= 55) return (192 + len).toString(16) + payload;
    const lenHex = len.toString(16);
    const lenPadded = lenHex.length % 2 ? "0" + lenHex : lenHex;
    return (247 + lenPadded.length / 2).toString(16) + lenPadded + payload;
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
