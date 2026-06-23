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
  nonce?: number;
  chainId?: number;
}

export interface Eip712Domain {
  name?: string;
  version?: string;
  chainId?: number;
  verifyingContract?: string;
  salt?: string;
}

export interface Eip712Type {
  name: string;
  type: string;
}

export interface TypedData {
  types: {
    EIP712Domain: Eip712Type[];
    [typeName: string]: Eip712Type[];
  };
  primaryType: string;
  domain: Eip712Domain;
  message: Record<string, unknown>;
}

export interface SignedTransaction {
  raw: string;
  hash: string;
}

const TYPE_HASH_SEPARATOR = "\x19\x01";

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

  private encodeType(primaryType: string, types: Record<string, Eip712Type[]>): string {
    const visited = new Set<string>();
    const order: string[] = [];

    const traverse = (name: string) => {
      if (visited.has(name)) return;
      visited.add(name);
      order.push(name);
      const deps = types[name];
      if (deps) {
        deps.forEach((dep) => traverse(dep.type));
      }
    };

    traverse(primaryType);

    return order
      .map((name) => {
        const deps = types[name];
        if (!deps) return "";
        const encoded = deps.map((d) => `${d.type} ${d.name}`).join(", ");
        return `${name}(${encoded})`;
      })
      .filter(Boolean)
      .join("");
  }

  private hashType(primaryType: string, types: Record<string, Eip712Type[]>): string {
    const encoded = this.encodeType(primaryType, types);
    return keccak256(Buffer.from(encoded, "utf-8"));
  }

  private encodeValue(type: string, value: unknown): string {
    if (type === "bytes32") {
      const hex = typeof value === "string" ? value : String(value);
      const cleaned = hex.startsWith("0x") ? hex.slice(2) : hex;
      return "0x" + cleaned.padEnd(64, "0");
    }
    if (type === "uint256" || type === "uint") {
      return "0x" + BigInt(value as number | bigint).toString(16).padStart(64, "0");
    }
    if (type === "address") {
      const cleaned = String(value).startsWith("0x") ? String(value).slice(2) : String(value);
      return "0x" + cleaned.toLowerCase().padStart(64, "0");
    }
    if (type === "bool") {
      return "0x" + (value ? "1" : "0").padStart(64, "0");
    }
    if (type === "string") {
      const hex = Buffer.from(String(value)).toString("hex");
      return "0x" + hex.padEnd(64, "0");
    }
    if (type.startsWith("[")) {
      const arrType = type.slice(0, type.indexOf("["));
      const arr = value as unknown[];
      return arr.map((v) => this.encodeValue(arrType, v)).join("");
    }
    return "0x" + String(value).padStart(64, "0");
  }

  private hashStruct(primaryType: string, data: Record<string, unknown>, types: Record<string, Eip712Type[]>): string {
    const typeHash = this.hashType(primaryType, types);
    const typeFields = types[primaryType];

    let encoded = typeHash;
    for (const field of typeFields) {
      const val = data[field.name];
      if (field.type === "EIP712Domain") {
        encoded += this.hashStruct("EIP712Domain", val as Record<string, unknown>, types);
      } else if ((val as unknown[])?.isArray) {
        const items = val as unknown[];
        encoded += items.map((item) => this.hashStruct(field.type, item as Record<string, unknown>, types)).join("");
      } else {
        encoded += this.encodeValue(field.type, val);
      }
    }

    return keccak256(Buffer.from(encoded.slice(2), "hex"));
  }

  private buildTypedDataHash(typedData: TypedData): string {
    const hashDomain = this.hashStruct("EIP712Domain", typedData.domain, typedData.types);
    const hashMessage = this.hashStruct(typedData.primaryType, typedData.message, typedData.types);
    const preimage = TYPE_HASH_SEPARATOR + hashDomain + hashMessage;
    return keccak256(Buffer.from(preimage.slice(2), "hex"));
  }

  async signTransaction(tx: Transaction | TypedData): Promise<SignedTransaction> {
    if ("types" in tx && "primaryType" in tx && "domain" in tx && "message" in tx) {
      const typedData = tx as TypedData;
      const dataHash = this.buildTypedDataHash(typedData);
      const signature = signMessage(this.privateKey, dataHash);
      return {
        raw: dataHash,
        hash: "0x" + dataHash,
      };
    }

    const nonce = tx.nonce ?? await this.getNonce();
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
