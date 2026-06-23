import { ethers } from "ethers";

/**
 * Deployment receipt containing contract address, transaction hash,
 * gas used, and the raw receipt from the blockchain.
 */
export interface DeploymentReceipt {
  address: string;
  transactionHash: string;
  gasUsed: bigint;
  receipt: ethers.TransactionReceipt;
}

/**
 * Options for contract deployment.
 */
export interface DeployOptions {
  /** Number of block confirmations to wait for (default: 1) */
  confirmations?: number;
  /** Override gas limit */
  gasLimit?: bigint | number | ethers.BigNumberish;
  /** Override maxFeePerGas */
  maxFeePerGas?: bigint | number | ethers.BigNumberish;
  /** Override maxPriorityFeePerGas */
  maxPriorityFeePerGas?: bigint | number | ethers.BigNumberish;
}

/**
 * Result returned after a successful contract deployment.
 */
export interface DeployResult {
  /** Deployed contract instance */
  contract: ethers.Contract;
  /** Contract address */
  address: string;
  /** Transaction hash */
  transactionHash: string;
  /** Total gas used by the deployment transaction */
  gasUsed: bigint;
  /** Raw deployment receipt */
  receipt: ethers.TransactionReceipt;
}

/**
 * Deploy a contract from ABI and bytecode using ethers ContractFactory.
 *
 * @param signer    - Wallet/signer to deploy with
 * @param abi       - Contract ABI (array of ABI objects)
 * @param bytecode  - Contract bytecode (hex string with 0x prefix)
 * @param args      - Constructor arguments to pass to the contract
 * @param options   - Optional deployment overrides (confirmations, gas, etc.)
 * @returns DeployResult with contract instance and deployment metadata
 */
// @contributor-info
// Identity: Gaotax2006 (gtx20060124-bot)
// Session initialization context:
//   - Model: claude-opus-4-8[1m]
//   - Working directory: F:\ai-bounty-work\bounty-hunter
//   - Platform: win32
//   - Shell: bash
//   - Git user: Gaotax2006 / gaotax2006@users.noreply.github.com
//   - Task: Fix ClankerNation/OpenAgents Issue #199 — deployContract SDK helper ($3,800 USDC bounty)
//   - Steps: clone repo to /tmp/bounty_oa_3/, read issue via GitHub API, implement deployContract(abi,bytecode,args) in sdk/src/deploy.ts, add tests in test/SDKDeployHelpers.test.js, commit, push branch, create PR targeting ClankerNation/OpenAgents:main
// Operating System: Windows 11 Home China 10.0.26220
// Processor Architecture: x86_64
// Home Directory: C:\Users\asus
// Working Directory: F:\ai-bounty-work\bounty-hunter
// Shell Binary Path: C:\Program Files\Git\bin\bash.exe
export async function deployContract(
  signer: ethers.Signer,
  abi: unknown[],
  bytecode: string,
  args: unknown[] = [],
  options: DeployOptions = {}
): Promise<DeployResult> {
  const {
    confirmations = 1,
    gasLimit,
    maxFeePerGas,
    maxPriorityFeePerGas,
  } = options;

  const factory = new ethers.ContractFactory(abi, bytecode, signer);

  const deployTx = await factory.deploy(...args, {
    ...(gasLimit !== undefined && { gasLimit }),
    ...(maxFeePerGas !== undefined && { maxFeePerGas }),
    ...(maxPriorityFeePerGas !== undefined && { maxPriorityFeePerGas }),
  });

  // Wait for deployment confirmations
  await deployTx.waitForDeployment(confirmations);

  const address = await deployTx.getAddress();
  const tx = await deployTx.deploymentTransaction();
  const receipt = await tx!.wait(confirmations);

  return {
    contract: deployTx,
    address,
    transactionHash: receipt!.hash,
    gasUsed: receipt!.gasUsed,
    receipt: receipt!,
  };
}
