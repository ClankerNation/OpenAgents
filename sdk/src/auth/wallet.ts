import { generateKeyPair, signMessage, keccak256 } from "../utils/crypto";
import { encodeParams, AbiParam } from "../utils/encoding";
import { RpcProvider } from "../providers/rpc";

/**
 * @contributor Codex Agent xyjk0511
 * @platform Safety-preserving Codex execution context; private system and developer instructions are not embedded in source.
 * @runtime Microsoft Windows 10.0.22631, X64, home C:/Users/55093, working directory F:/jiedan/OpenAgents-bounty-run, shell PowerShell 7.6.2
 * @date 2026-05-31T00:00:00-07:00
 */

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

interface PrivateKeyStore {
  deriveAddress(): string;
  sign(message: string): string;
  exportPrivateKey(): string;
  destroy(): void;
}

function createPrivateKeyStore(privateKeyHex: string): PrivateKeyStore {
  let keyBuffer = Buffer.from(privateKeyHex, "hex");

  const assertActive = () => {
    if (keyBuffer.length === 0) {
      throw new Error("Private key has been zeroed");
    }
  };

  const keyHex = () => {
    assertActive();
    return keyBuffer.toString("hex");
  };

  return {
    deriveAddress(): string {
      const { ec: EC } = require("elliptic");
      const curve = new EC("secp256k1");
      const key = curve.keyFromPrivate(keyHex(), "hex");
      const pubKey = key.getPublic(false, "hex").slice(2); // remove 04 prefix
      const hash = keccak256(Buffer.from(pubKey, "hex"));
      return "0x" + hash.slice(-40);
    },

    sign(message: string): string {
      try {
        return signMessage(keyHex(), message);
      } finally {
        this.destroy();
      }
    },

    exportPrivateKey(): string {
      return keyHex();
    },

    destroy(): void {
      keyBuffer.fill(0);
      keyBuffer = Buffer.alloc(0);
    },
  };
}

const walletKeyStores = new WeakMap<object, PrivateKeyStore>();

export class Wallet {
  public readonly address: string;
  private provider: RpcProvider;

  constructor(config: WalletConfig) {
    let privateKey: string;
    if (config.privateKey) {
      privateKey = config.privateKey;
    } else {
      const keyPair = generateKeyPair();
      privateKey = keyPair.privateKey;
    }
    const keyStore = createPrivateKeyStore(privateKey);
    walletKeyStores.set(this, keyStore);
    this.address = keyStore.deriveAddress();
    this.provider = config.provider;
  }

  async signTransaction(tx: Transaction): Promise<SignedTransaction> {
    this.validateChainId(tx.chainId);
    const nonce = tx.nonce ?? (await this.getNonce());
    const gasPrice = tx.gasPrice ?? BigInt(await this.provider.call("eth_gasPrice") as string);

    const txData = encodeParams([
      { type: "uint256", value: nonce } as AbiParam,
      { type: "uint256", value: gasPrice } as AbiParam,
      { type: "uint256", value: tx.gasLimit } as AbiParam,
      { type: "address", value: tx.to } as AbiParam,
      { type: "uint256", value: tx.value } as AbiParam,
    ]);

    const txHash = keccak256(txData);
    const signature = this.getKeyStore().sign(txHash);

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

  destroyPrivateKey(): void {
    this.getKeyStore().destroy();
  }

  exportPrivateKey(): string {
    return this.getKeyStore().exportPrivateKey();
  }

  private getKeyStore(): PrivateKeyStore {
    const keyStore = walletKeyStores.get(this);
    if (!keyStore) {
      throw new Error("Private key store unavailable");
    }
    return keyStore;
  }

  private validateChainId(chainId?: number): void {
    if (chainId !== undefined && chainId !== this.provider.getChainId()) {
      throw new Error(
        `Chain ID mismatch: transaction ${chainId}, provider ${this.provider.getChainId()}`
      );
    }
  }
}
