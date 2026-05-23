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
    const chainId = tx.chainId ?? this.provider.getChainId();

    let txData: string;
    if (tx.maxFeePerGas !== undefined) {
      const maxFee = tx.maxFeePerGas;
      const maxPriority = tx.maxPriorityFeePerGas ?? 1n;
      const type2Fields = [
        { type: "uint256", value: chainId } as AbiParam,
        { type: "uint256", value: nonce } as AbiParam,
        { type: "uint256", value: maxPriority } as AbiParam,
        { type: "uint256", value: maxFee } as AbiParam,
        { type: "uint256", value: tx.gasLimit } as AbiParam,
        { type: "address", value: tx.to } as AbiParam,
        { type: "uint256", value: tx.value } as AbiParam,
      ];
      const inner = encodeParams(type2Fields).slice(2);
      txData = "0x02" + inner;
    } else {
      const gasPrice = tx.gasPrice ?? BigInt(await this.provider.call("eth_gasPrice") as string);
      const legacyFields = [
        { type: "uint256", value: nonce } as AbiParam,
        { type: "uint256", value: gasPrice } as AbiParam,
        { type: "uint256", value: tx.gasLimit } as AbiParam,
        { type: "address", value: tx.to } as AbiParam,
        { type: "uint256", value: tx.value } as AbiParam,
      ];
      txData = encodeParams(legacyFields);
    }

    const txHash = keccak256(txData);
    const signature = signMessage(this.privateKey, txHash);

    return {
      raw: txData + signature,
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
