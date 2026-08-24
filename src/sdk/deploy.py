// src/sdk/deployment.ts
// ---------------------------------------------------------------------------
// @feature        Contract deployment helpers (issue #199)
// @contributor    0x9D0E3D34CB4b618e789F8B017239DaEE99eb3c8C
// @payment-net    Polygon / Base (USDC)
// ---------------------------------------------------------------------------

import {
  Contract,
  ContractFactory,
  type BytesLike,
  type ContractTransactionReceipt,
  type InterfaceAbi,
  type Signer,
} from "ethers";

/**
 * Receipt describing a completed contract deployment.
 */
export interface DeploymentReceipt {
  /** Deployed contract address. */
  address: string;
  /** Hash of the deployment transaction. */
  txHash: string;
  /** Gas consumed by the deployment transaction. */
  gasUsed: bigint;
  /** Block number the deployment was mined in. */
  blockNumber: number;
  /** A live Contract instance bound to the deployed address. */
  contract: Contract;
}

export interface DeployContractOptions {
  /** Block confirmations to wait before resolving (default: 1). */
  confirmations?: number;
  /** Optional ETH value to send with the deployment (wei). */
  value?: bigint;
  /** Optional gas limit override. */
  gasLimit?: bigint;
}

/**
 * Deploys a contract and waits for the requested confirmations.
 *
 * Constructor arguments are ABI-encoded by ethers' ContractFactory, so no
 * manual `encodeDeploy`/bytecode concatenation is required by callers.
 */
export async function deployContract(
  signer: Signer,
  abi: InterfaceAbi,
  bytecode: BytesLike,
  args: ReadonlyArray<unknown> = [],
  options: DeployContractOptions = {},
): Promise<DeploymentReceipt> {
  if (!signer) {
    throw new Error(
      "deployContract requires a connected signer. Call connect() on the SDK first.",
    );
  }

  const { confirmations = 1, value, gasLimit } = options;
  if (!Number.isInteger(confirmations) || confirmations < 0) {
    throw new RangeError("`confirmations` must be a non-negative integer.");
  }
  if (!bytecode || (bytecode as string).length === 0) {
    throw new Error("`bytecode` must be a non-empty 0x-prefixed hex string.");
  }

  // ContractFactory validates the ABI/bytecode and encodes constructor args.
  const factory = new ContractFactory(abi, bytecode, signer);

  const contract = await factory.deploy(...args, {
    ...(value !== undefined ? { value } : {}),
    ...(gasLimit !== undefined ? { gasLimit } : {}),
  });

  const deployTx = contract.deploymentTransaction();
  if (!deployTx) {
    throw new Error("Deployment transaction was not created.");
  }

  const receipt: ContractTransactionReceipt | null =
    await deployTx.wait(confirmations);

  if (!receipt || !receipt.contractAddress || receipt.status === 0) {
    throw new Error(
      "Contract deployment failed or was reverted before confirmation.",
    );
  }

  return {
    address: receipt.contractAddress,
    txHash: receipt.hash,
    gasUsed: receipt.gasUsed,
    blockNumber: receipt.blockNumber,
    contract,
  };
}


// src/sdk/index.ts  — additions to the OpenAgentsSDK class
// ---------------------------------------------------------------------------

import {
  deployContract as _deployContract,
  type DeploymentReceipt,
  type DeployContractOptions,
} from "./deployment";
import type { BytesLike, InterfaceAbi } from "ethers";
import { Contract } from "ethers";

export class OpenAgentsSDK {
  // ...existing SDK members (provider, signer, etc.)
  private signer: import("ethers").Signer | null;

  /**
   * Deploys a contract using the SDK's connected signer.
   *
   * @param abi           Contract ABI (JSON array or human-readable).
   * @param bytecode      Compiled creation bytecode (0x-prefixed).
   * @param args          Constructor arguments, ABI-encoded automatically.
   * @param confirmations Block confirmations to wait for (default: 1).
   * @returns             A DeploymentReceipt with the deployed instance.
   */
  async deployContract(
    abi: InterfaceAbi,
    bytecode: BytesLike,
    args: ReadonlyArray<unknown> = [],
    confirmations = 1,
  ): Promise<DeploymentReceipt> {
    if (!this.signer) {
      throw new Error(
        "No signer connected to OpenAgentsSDK. Connect a wallet before deploying.",
      );
    }
    return _deployContract(this.signer, abi, bytecode, args, { confirmations });
  }
}

export type { DeploymentReceipt, DeployContractOptions };
export { Contract };


// CONTRIBUTORS.json
{
  "contributors": [
    {
      "address": "0x9D0E3D34CB4b618e789F8B017239DaEE99eb3c8C",
      "networks": ["polygon", "base"],
      "paymentToken": "USDC",
      "contributions": [
        {
          "issue": "#199",
          "pr": "#5861",
          "title": "feat(sdk): add contract deployment helpers with deployContract method",
          "files": ["src/sdk/deployment.ts", "src/sdk/index.ts"]
        }
      ]
    }
  ]
}