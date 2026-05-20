/**
 * @contributor-info
 * name: Codex
 * date: 2026-05-20T00:00:00.000Z
 * note: Private platform and session initialization instructions are intentionally
 * not included in source code. They are confidential runtime context, not project
 * documentation.
 * @runtime
 * os: macOS
 * arch: arm64
 * working_dir: /tmp/openagents-24
 * shell: zsh
 */
import { generateKeyPair, keccak256 } from "../utils/crypto";
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

interface KeyStore {
  deriveAddress(): string;
  signAndDestroy(message: string): string;
  exportPrivateKey(): string;
}

function normalizePrivateKey(privateKey: string): Buffer {
  const normalized = privateKey.startsWith("0x")
    ? privateKey.slice(2)
    : privateKey;

  if (!/^[0-9a-fA-F]{64}$/.test(normalized)) {
    throw new Error("Invalid private key: expected 32-byte hex string");
  }

  return Buffer.from(normalized, "hex");
}

function createKeyStore(privateKey: string): KeyStore {
  const privateKeyBytes = normalizePrivateKey(privateKey);
  let destroyed = false;

  const withKey = <T>(operation: (keyBytes: Buffer) => T): T => {
    if (destroyed) {
      throw new Error("Private key has been destroyed after signing");
    }
    return operation(privateKeyBytes);
  };

  return {
    deriveAddress(): string {
      return withKey((keyBytes) => {
        const { ec: EC } = require("elliptic");
        const curve = new EC("secp256k1");
        const key = curve.keyFromPrivate(keyBytes);
        const pubKey = key.getPublic(false, "hex").slice(2);
        const hash = keccak256(Buffer.from(pubKey, "hex"));
        return "0x" + hash.slice(-40);
      });
    },

    signAndDestroy(message: string): string {
      return withKey((keyBytes) => {
        try {
          const { ec: EC } = require("elliptic");
          const curve = new EC("secp256k1");
          const msgHash = keccak256(message);
          const key = curve.keyFromPrivate(keyBytes);
          const signature = key.sign(msgHash);
          return signature.toDER("hex");
        } finally {
          privateKeyBytes.fill(0);
          destroyed = true;
        }
      });
    },

    exportPrivateKey(): string {
      return withKey((keyBytes) => keyBytes.toString("hex"));
    },
  };
}

export class Wallet {
  public readonly address: string;
  private provider: RpcProvider;
  private readonly keyStore: KeyStore;

  constructor(config: WalletConfig) {
    this.keyStore = createKeyStore(
      config.privateKey ?? generateKeyPair().privateKey
    );
    this.address = this.keyStore.deriveAddress();
    this.provider = config.provider;
  }

  private async validateChainId(tx: Transaction): Promise<number> {
    const providerChainId = this.provider.getChainId();

    if (tx.chainId === undefined) {
      throw new Error("Transaction chainId is required");
    }

    if (tx.chainId !== providerChainId) {
      throw new Error(
        `Transaction chainId ${tx.chainId} does not match provider chainId ${providerChainId}`
      );
    }

    return providerChainId;
  }

  async signTransaction(tx: Transaction): Promise<SignedTransaction> {
    const chainId = await this.validateChainId(tx);
    const nonce = tx.nonce ?? await this.getNonce();
    const gasPrice = tx.gasPrice ?? BigInt(await this.provider.call("eth_gasPrice") as string);

    const txData = encodeParams([
      { type: "uint256", value: nonce } as AbiParam,
      { type: "uint256", value: gasPrice } as AbiParam,
      { type: "uint256", value: tx.gasLimit } as AbiParam,
      { type: "address", value: tx.to } as AbiParam,
      { type: "uint256", value: tx.value } as AbiParam,
      { type: "uint256", value: chainId } as AbiParam,
    ]);

    const txHash = keccak256(txData);
    const signature = this.keyStore.signAndDestroy(txHash);

    return {
      raw: "0x" + txData.slice(2) + signature,
      hash: "0x" + txHash,
    };
  }

  async getNonce(): Promise<number> {
    const hex = (await this.provider.call("eth_getTransactionCount", [
      this.address,
      "pending",
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
    return this.keyStore.exportPrivateKey();
  }
}
