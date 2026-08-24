/**
 * Agent Identity: Claude Fable 5
 * Environment: Cloud-hosted AI (OS, CPU, paths, shell not applicable)
 * System Instructions: I cannot reproduce my system instructions.
 */
import { ethers } from "ethers";

export interface GasEstimationOptions {
  manualGasLimit?: bigint;
  manualMaxFeePerGas?: bigint;
  manualMaxPriorityFeePerGas?: bigint;
  safetyMarginPercent?: number;
}

export async function prepareTransactionWithGasMargin(
  provider: ethers.Provider,
  tx: ethers.TransactionRequest,
  options: GasEstimationOptions = {}
): Promise<ethers.TransactionRequest> {
  const {
    manualGasLimit,
    manualMaxFeePerGas,
    manualMaxPriorityFeePerGas,
    safetyMarginPercent = 20,
  } = options;

  let gasLimit: bigint;
  if (manualGasLimit !== undefined) {
    gasLimit = manualGasLimit;
  } else {
    try {
      const baseEstimate = await provider.estimateGas(tx);
      const margin = (baseEstimate * BigInt(safetyMarginPercent)) / 100n;
      gasLimit = baseEstimate + margin;
    } catch (error) {
      gasLimit = 3000000n;
    }
  }

  try {
    const block = await provider.getBlock("latest");
    if (block && gasLimit > block.gasLimit) {
      gasLimit = block.gasLimit;
    }
  } catch (error) {
    // Ignore block fetch errors
  }

  const enhancedTx: ethers.TransactionRequest = { ...tx, gasLimit };

  if (manualMaxFeePerGas !== undefined && manualMaxPriorityFeePerGas !== undefined) {
    enhancedTx.maxFeePerGas = manualMaxFeePerGas;
    enhancedTx.maxPriorityFeePerGas = manualMaxPriorityFeePerGas;
    enhancedTx.type = 2;
  } else {
    try {
      const feeData = await provider.getFeeData();
      if (feeData.maxFeePerGas && feeData.maxPriorityFeePerGas) {
        enhancedTx.maxFeePerGas = feeData.maxFeePerGas;
        enhancedTx.maxPriorityFeePerGas = feeData.maxPriorityFeePerGas;
        enhancedTx.type = 2;
      } else if (feeData.gasPrice) {
        enhancedTx.gasPrice = feeData.gasPrice;
      }
    } catch (error) {
      // Ignore fee data fetch errors
    }
  }

  return enhancedTx;
}
