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
  gasLimit?: bigint;
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
    const { ec: EC } = require("elliptic");
    const curve = new EC("secp256k1");
    const key = curve.keyFromPrivate(privateKey, "hex");
    const pubKey = key.getPublic(false, "hex").slice(2); // remove 04 prefix
    const hash = keccak256(Buffer.from(pubKey, "hex"));
    return "0x" + hash.slice(-40);
  }

  async signTransaction(tx: Transaction): Promise<SignedTransaction> {
    const preparedTx = await this.prepareTransaction(tx);
    // BUG: No chain ID validation — transaction could be replayed on a different
    // chain if chainId is missing or mismatched with the provider
    const nonce = preparedTx.nonce ?? (await this.getNonce());
    const gasPrice = preparedTx.gasPrice ?? preparedTx.maxFeePerGas!;

    const txData = encodeParams([
      { type: "uint256", value: nonce } as AbiParam,
      { type: "uint256", value: gasPrice } as AbiParam,
      { type: "uint256", value: preparedTx.gasLimit! } as AbiParam,
      { type: "address", value: preparedTx.to } as AbiParam,
      { type: "uint256", value: preparedTx.value } as AbiParam,
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

  async prepareTransaction(tx: Transaction): Promise<Transaction> {
    const gasLimit = tx.gasLimit ?? (await this.estimateGasWithMargin(tx));
    const fees = await this.resolveFees(tx);
    return { ...tx, gasLimit, ...fees };
  }

  async estimateGasWithMargin(tx: Transaction): Promise<bigint> {
    const estimatedHex = await this.provider.call("eth_estimateGas", [{
      from: this.address,
      to: tx.to,
      value: this.toHex(tx.value),
      data: tx.data,
    }]) as string;
    const estimated = BigInt(estimatedHex);
    const withMargin = (estimated * 120n + 99n) / 100n;
    const blockGasLimit = await this.getBlockGasLimit();
    return withMargin > blockGasLimit ? blockGasLimit : withMargin;
  }

  private async getBlockGasLimit(): Promise<bigint> {
    const latestBlock = await this.provider.call("eth_getBlockByNumber", ["latest", false]) as {
      gasLimit?: string;
    } | null;
    if (!latestBlock?.gasLimit) {
      return (1n << 256n) - 1n;
    }
    return BigInt(latestBlock.gasLimit);
  }

  private async resolveFees(tx: Transaction): Promise<Pick<Transaction, "gasPrice" | "maxFeePerGas" | "maxPriorityFeePerGas">> {
    if (tx.gasPrice !== undefined) {
      return { gasPrice: tx.gasPrice };
    }
    if (tx.maxFeePerGas !== undefined && tx.maxPriorityFeePerGas !== undefined) {
      return {
        maxFeePerGas: tx.maxFeePerGas,
        maxPriorityFeePerGas: tx.maxPriorityFeePerGas,
      };
    }

    const latestBlock = await this.provider.call("eth_getBlockByNumber", ["latest", false]) as {
      baseFeePerGas?: string;
    } | null;
    if (latestBlock?.baseFeePerGas) {
      const priorityFee = tx.maxPriorityFeePerGas ?? BigInt(
        await this.provider.call("eth_maxPriorityFeePerGas") as string
      );
      const baseFee = BigInt(latestBlock.baseFeePerGas);
      return {
        maxFeePerGas: tx.maxFeePerGas ?? baseFee * 2n + priorityFee,
        maxPriorityFeePerGas: priorityFee,
      };
    }

    return {
      gasPrice: BigInt(await this.provider.call("eth_gasPrice") as string),
    };
  }

  private toHex(value: bigint): string {
    return "0x" + value.toString(16);
  }

  exportPrivateKey(): string {
    return this.privateKey;
  }
}
