export interface GasEstimationTransaction {
  from?: string;
  to: string;
  value?: bigint;
  data?: string;
}

export interface FeeData {
  gasPrice?: bigint;
  maxFeePerGas?: bigint;
  maxPriorityFeePerGas?: bigint;
}

export function toRpcQuantity(value: bigint): string {
  if (value < 0n) {
    throw new Error("RPC quantities cannot be negative");
  }

  return `0x${value.toString(16)}`;
}

export function parseRpcQuantity(value: unknown, field: string): bigint {
  if (typeof value !== "string" || !/^0x[0-9a-f]+$/i.test(value)) {
    throw new Error(`RPC field ${field} must be a hexadecimal quantity`);
  }

  return BigInt(value);
}

export function applyGasMargin(
  estimatedGas: bigint,
  blockGasLimit: bigint,
  marginPercent = 20
): bigint {
  if (estimatedGas < 0n) {
    throw new Error("Estimated gas cannot be negative");
  }
  if (blockGasLimit <= 0n) {
    throw new Error("Block gas limit must be positive");
  }
  if (!Number.isInteger(marginPercent) || marginPercent < 0) {
    throw new Error("Gas margin must be a non-negative integer");
  }

  const denominator = 100n;
  const numerator = denominator + BigInt(marginPercent);
  const padded = (estimatedGas * numerator + denominator - 1n) / denominator;
  return padded > blockGasLimit ? blockGasLimit : padded;
}

export function toRpcTransaction(
  transaction: GasEstimationTransaction
): Record<string, string> {
  const rpcTransaction: Record<string, string> = {
    to: transaction.to,
    data: transaction.data ?? "0x",
  };

  if (transaction.from !== undefined) {
    rpcTransaction.from = transaction.from;
  }
  if (transaction.value !== undefined) {
    rpcTransaction.value = toRpcQuantity(transaction.value);
  }

  return rpcTransaction;
}
