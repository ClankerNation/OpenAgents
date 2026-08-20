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
  maxFeePerGas?: bigint;
  maxPriorityFeePerGas?: bigint;
  nonce?: number;
  chainId?: number;
  type?: number; // 0 = legacy, 2 = EIP-1559
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
    const { ec as EC } = require("elliptic");
    const curve = new EC("secp256k1");
    const key = curve.keyFromPrivate(privateKey, "hex");
    const pubKey = key.getPublic(false, "hex").slice(2);
    const hash = keccak256(Buffer.from(pubKey, "hex"));
    return "0x" + hash.slice(-40);
  }

  async signTransaction(tx: Transaction): Promise<SignedTransaction> {
    const nonce = tx.nonce ?? (await this.getNonce());
    const chainId = tx.chainId ?? 1;

    // Auto-detect transaction type: use EIP-1559 if maxFeePerGas is present
    const isEip1559 = tx.maxFeePerGas !== undefined || tx.type === 2;

    let txData: string;
    let txHash: string;

    if (isEip1559) {
      // EIP-1559 Type 2 transaction encoding
      const maxFeePerGas = tx.maxFeePerGas ?? BigInt(await this.provider.call("eth_gasPrice") as string);
      const maxPriorityFeePerGas = tx.maxPriorityFeePerGas ?? BigInt(1_500_000_000); // 1.5 gwei default

      // RLP encode: [chainId, nonce, maxPriorityFeePerGas, maxFeePerGas, gasLimit, to, value, data, accessList]
      const fields = [
        this.encodeUint(chainId),
        this.encodeUint(nonce),
        this.encodeUint(maxPriorityFeePerGas),
        this.encodeUint(maxFeePerGas),
        this.encodeUint(tx.gasLimit),
        this.encodeAddress(tx.to),
        this.encodeUint(tx.value),
        this.encodeBytes(tx.data),
        "0xc0", // empty access list RLP
      ];
      const rlpPayload = this.rlpEncode(fields);
      // Type 2 prefix: 0x02 || RLP(payload)
      const typedPayload = "0x02" + rlpPayload.slice(2);
      txHash = keccak256(Buffer.from(typedPayload.slice(2), "hex"));
      const signature = signMessage(this.privateKey, txHash);
      // Append v, r, s to RLP for signed tx
      const v = "0x"; // EIP-1559 uses yParity (0 or 1), simplified here
      const signedRlp = this.rlpEncode([
        ...fields,
        v,
        "0x" + signature.slice(2, 66),   // r
        "0x" + signature.slice(66, 130),  // s
      ]);
      txData = "0x02" + signedRlp.slice(2);
    } else {
      // Legacy transaction encoding
      const gasPrice = tx.gasPrice ?? BigInt(await this.provider.call("eth_gasPrice") as string);

      const fields = [
        this.encodeUint(nonce),
        this.encodeUint(gasPrice),
        this.encodeUint(tx.gasLimit),
        this.encodeAddress(tx.to),
        this.encodeUint(tx.value),
        this.encodeBytes(tx.data),
      ];
      const rlpPayload = this.rlpEncode(fields);
      // For signing: RLP([...fields, chainId, 0, 0]) per EIP-155
      const unsignedRlp = this.rlpEncode([
        ...fields,
        this.encodeUint(chainId),
        "0x",
        "0x",
      ]);
      txHash = keccak256(Buffer.from(unsignedRlp.slice(2), "hex"));
      const signature = signMessage(this.privateKey, txHash);
      const v = parseInt(signature.slice(130, 132), 16) + chainId * 2 + 35;
      const signedRlp = this.rlpEncode([
        ...fields,
        this.encodeUint(v),
        "0x" + signature.slice(2, 66),
        "0x" + signature.slice(66, 130),
      ]);
      txData = signedRlp;
    }

    return {
      raw: txData,
      hash: "0x" + txHash,
    };
  }

  private encodeUint(value: number | bigint): string {
    const n = BigInt(value);
    if (n === 0n) return "0x";
    return "0x" + n.toString(16);
  }

  private encodeAddress(addr: string): string {
    return addr.toLowerCase();
  }

  private encodeBytes(data: string): string {
    if (!data || data === "0x") return "0x";
    return data;
  }

  private rlpEncode(items: string[]): string {
    // Simplified RLP encoding for transaction fields
    const encoded = items.map((item) => {
      const hex = item.startsWith("0x") ? item.slice(2) : item;
      const len = hex.length / 2;
      if (len === 0) return "80";
      if (len === 1 && parseInt(hex, 16) < 128) return hex;
      if (len < 56) return (128 + len).toString(16).padStart(2, "0") + hex;
      const lenBytes = len.toString(16);
      return (183 + lenBytes.length / 2).toString(16).padStart(2, "0") + lenBytes + hex;
    });
    const payload = encoded.join("");
    const payloadLen = payload.length / 2;
    let prefix: string;
    if (payloadLen < 56) {
      prefix = (192 + payloadLen).toString(16).padStart(2, "0");
    } else {
      const lenHex = payloadLen.toString(16);
      prefix = (247 + lenHex.length / 2).toString(16).padStart(2, "0") + lenHex;
    }
    return "0x" + prefix + payload;
  }

  async getNonce(): Promise<number> {
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
