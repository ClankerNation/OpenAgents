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
  type?: number;
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

    if (tx.maxFeePerGas !== undefined) {
      return this._signEIP1559(tx, nonce);
    }

    const gasPrice = tx.gasPrice ?? BigInt(await this.provider.call("eth_gasPrice") as string);

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

  private async _signEIP1559(tx: Transaction, nonce: number): Promise<SignedTransaction> {
    const chainId = tx.chainId ?? parseInt(await this.provider.call("eth_chainId") as string, 16);
    const maxPriorityFeePerGas = tx.maxPriorityFeePerGas ?? 1_000_000_000n;
    const maxFeePerGas = tx.maxFeePerGas!;
    const gasLimit = tx.gasLimit;
    const to = tx.to;
    const value = tx.value;
    const data = tx.data;
    const accessList: Buffer[] = [];

    const rlpEncode = (items: Buffer[]): Buffer => {
      let encoded = Buffer.alloc(0);
      for (const item of items) {
        if (item.length === 1 && item[0] < 0x80) {
          encoded = Buffer.concat([encoded, item]);
        } else {
          const len = item.length;
          if (len < 56) {
            encoded = Buffer.concat([encoded, Buffer.from([0x80 + len]), item]);
          } else {
            const lenBuf = Buffer.from(len.toString(16), "hex");
            encoded = Buffer.concat([encoded, Buffer.from([0xb7 + lenBuf.length]), lenBuf, item]);
          }
        }
      }
      return encoded;
    };

    const toBuf = (v: bigint | number): Buffer => {
      if (v === 0n || v === 0) return Buffer.alloc(0);
      const hex = (typeof v === "bigint" ? v : BigInt(v)).toString(16);
      return hex.length % 2 === 0 ? Buffer.from(hex, "hex") : Buffer.from("0" + hex, "hex");
    };

    const addrBuf = (addr: string): Buffer => {
      if (!addr || addr === "0x" || addr === "0x0") return Buffer.alloc(0);
      return Buffer.from(addr.replace("0x", "").padStart(40, "0"), "hex");
    };

    const dataBuf = (d: string): Buffer => {
      if (!d || d === "0x") return Buffer.alloc(0);
      const hex = d.replace("0x", "");
      return hex.length % 2 === 0 ? Buffer.from(hex, "hex") : Buffer.from("0" + hex, "hex");
    };

    const fields: Buffer[] = [
      toBuf(chainId),
      toBuf(nonce),
      toBuf(maxPriorityFeePerGas),
      toBuf(maxFeePerGas),
      toBuf(gasLimit),
      addrBuf(to),
      toBuf(value),
      dataBuf(data),
      rlpEncode(accessList),
    ];

    const rlpTx = rlpEncode(fields);
    const payload = Buffer.concat([Buffer.from([0x02]), rlpTx]);
    const txHash = keccak256(payload);

    const sig = this.privateKey;
    const signature = signMessage(sig, txHash);

    const v = Buffer.from([chainId * 2 + 35]);
    const r = Buffer.alloc(32);
    const s = Buffer.alloc(32);

    const signedFields = [
      toBuf(chainId), toBuf(nonce), toBuf(maxPriorityFeePerGas),
      toBuf(maxFeePerGas), toBuf(gasLimit), addrBuf(to),
      toBuf(value), dataBuf(data), rlpEncode(accessList),
      v, r, s,
    ];

    const rawTx = Buffer.concat([Buffer.from([0x02]), rlpEncode(signedFields)]);
    return {
      raw: "0x" + rawTx.toString("hex"),
      hash: "0x" + txHash,
    };
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
