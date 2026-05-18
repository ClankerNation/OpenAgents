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
    const gasPrice = tx.gasPrice ?? BigInt(await this.provider.call("eth_gasPrice") as string);

    let v: bigint, r: bigint, s: bigint;
    let chainIdForSig: bigint;
    let txType: number;

    if (tx.maxFeePerGas !== undefined && tx.maxPriorityFeePerGas !== undefined) {
      // EIP-1559 transaction
      txType = 2;
      chainIdForSig = BigInt(tx.chainId ?? this.provider.getChainId());

      const baseFee = await this.provider.call("eth_gasPrice") as string;
      const priorityFee = tx.maxPriorityFeePerGas;
      const maxFee = tx.maxFeePerGas;

      const txFields = [
        chainIdForSig,
        nonce,
        priorityFee,
        tx.gasLimit,
        tx.to,
        tx.value,
        tx.data || "0x",
        baseFee,
        maxFee,
      ];

      const txHash = keccak256(encodeParams(txFields.map((f) => ({
        type: "uint256",
        value: f,
      }))));

      const signature = signMessage(this.privateKey, txHash);
      const { r: sr, s: ss, v: sv } = this.parseSignature(signature);
      r = sr;
      s = ss;
      v = sv + chainIdForSig * 2n + 35n;
    } else {
      // Legacy transaction
      txType = 0;
      chainIdForSig = BigInt(tx.chainId ?? this.provider.getChainId());

      const txData = encodeParams([
        { type: "uint256", value: nonce } as AbiParam,
        { type: "uint256", value: gasPrice } as AbiParam,
        { type: "uint256", value: tx.gasLimit } as AbiParam,
        { type: "address", value: tx.to } as AbiParam,
        { type: "uint256", value: tx.value } as AbiParam,
      ]);

      const txHash = keccak256(txData);
      const signature = signMessage(this.privateKey, txHash);
      const { r: sr, s: ss, v: sv } = this.parseSignature(signature);
      r = sr;
      s = ss;
      v = sv + chainIdForSig * 2n + 35n;
    }

    const encodedTx = this.encodeSignedTransaction(tx, v, r, s, txType);

    return {
      raw: encodedTx,
      hash: "0x" + keccak256(Buffer.from(encodedTx.slice(2), "hex")),
    };
  }

  private parseSignature(sig: string): { r: bigint; s: bigint; v: number } {
    const hash = Buffer.from(sig.slice(2), "hex");
    const { ec as EC } = require("elliptic");
    const curve = new EC("secp256k1");
    const key = curve.recoverPubKeyFromRecoveryParam(hash.slice(0, 32), hash[32], hash[33]);
    const pubKey = key.encode("hex").slice(2);
    const pubHash = keccak256(Buffer.from(pubKey, "hex"));
    const v = pubHash.slice(0, 2) === "0x" ? parseInt(pubHash.slice(2, 4), 16) : parseInt(pubHash.slice(0, 2), 16);
    const r = BigInt("0x" + hash.slice(0, 32).toString("hex"));
    const s = BigInt("0x" + hash.slice(32, 64).toString("hex"));
    return { r, s, v: v % 2 === 0 ? 27 : 28 };
  }

  private encodeSignedTransaction(tx: Transaction, v: bigint, r: bigint, s: bigint, txType: number): string {
    if (txType === 2 && tx.maxFeePerGas !== undefined && tx.maxPriorityFeePerGas !== undefined) {
      // EIP-1559 rlp encoding
      const chainId = tx.chainId ?? this.provider.getChainId();
      const items = [
        chainId,
        tx.nonce ?? 0,
        tx.maxPriorityFeePerGas,
        tx.maxFeePerGas,
        tx.gasLimit,
        tx.to,
        tx.value,
        tx.data || "0x",
      ];
      const listItems: AbiParam[] = items.map((v) => ({ type: "uint256", value: v as any }));
      const encoded = encodeParams(listItems).slice(2);
      return "0x02" + encoded;
    }
    // Legacy encoding fallback
    return "0x" + encodeParams([
      { type: "uint256", value: v } as AbiParam,
      { type: "uint256", value: r } as AbiParam,
      { type: "uint256", value: s } as AbiParam,
    ]);
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
