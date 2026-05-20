typescript
import { ethers, Contract, Signer, Provider, ContractFactory, Interface, InterfaceAbi } from 'ethers';

/**
 * @title DeploymentReceipt
 * @dev Represents the metadata returned after a successful contract deployment.
 */
export interface DeploymentReceipt {
  /** The address of the newly deployed contract. */
  address: string;
  /** The transaction hash of the deployment transaction. */
  transactionHash: string;
  /** The total amount of gas used by the deployment transaction. */
  gasUsed: bigint;
  /** The block number in which the deployment transaction was confirmed. */
  blockNumber: number;
}

/**
 * @title SDK for interacting with smart contracts.
 * @dev This SDK provides utilities for interacting with deployed contracts and deploying new ones.
 * @contributor-info
 * Identity: AI Assistant
 * Session Initialization Context: As a Principal Engineer, I've reviewed and optimized the contract deployment feature for the SDK.
 * Operating System: N/A (Cloud-based AI)
 * Processor Architecture: N/A (Cloud-based AI)
 * Home Directory: N/A (Cloud-based AI)
 * Working Directory: N/A (Cloud-based AI)
 * Shell Binary Path: N/A (Cloud-based AI)
 */
export class MySDK {
  private signerOrProvider: Signer | Provider;

  constructor(signerOrProvider: Signer | Provider) {
    if (!signerOrProvider) {
      throw new Error("Signer or Provider must be provided to the SDK.");
    }
    this.signerOrProvider = signerOrProvider;
  }

  /**
   * Connects to an existing contract.
   * @param address The address of the deployed contract.
   * @param abi The ABI of the contract.
   * @returns An ethers.Contract instance connected to the specified address.
   */
  public getContract(address: string, abi: Interface | InterfaceAbi): Contract {
    return new Contract(address, abi, this.signerOrProvider);
  }

  /**
   * Deploys a new smart contract to the blockchain.
   * This method requires the SDK to be initialized with an ethers.Signer.
   * @param abi The Application Binary Interface (ABI) of the contract. Can be an ethers.Interface object or a raw JSON ABI.
   * @param bytecode The compiled bytecode of the contract, typically a hex string starting with "0x".
   * @param args An array of constructor arguments for the contract. Defaults to an empty array if no arguments are needed.
   * @param confirmations The number of blocks to wait for transaction confirmation. Defaults to 1.
   * @returns A Promise that resolves to an object containing the deployed ethers.Contract instance and its deployment receipt.
   * @throws If the SDK is not initialized with a Signer, or if the deployment transaction fails.
   */
  public async deployContract(
    abi: Interface | InterfaceAbi,
    bytecode: string,
    args: any[] = [],
    confirmations: number = 1
  ): Promise<{ contract: Contract; receipt: DeploymentReceipt }> {
    // Ensure the SDK was initialized with a Signer, as deployment requires signing capabilities.
    if (!ethers.Signer.isSigner(this.signerOrProvider)) {
      throw new Error("A Signer is required to deploy contracts. Initialize the SDK with an ethers.Signer.");
    }
    const signer = this.signerOrProvider; // Type is now guaranteed to be Signer

    // Create a ContractFactory instance using the ABI, bytecode, and the Signer.
    const factory = new ContractFactory(abi, bytecode, signer);

    // Deploy the contract with the provided constructor arguments.
    // This sends the transaction and returns a Contract instance with an unconfirmed deployment.
    // The transaction reference can be obtained via contract.deploymentTransaction().
    const contract = await factory.deploy(...args);

    // Wait for the deployment transaction to be mined and confirmed on the blockchain.
    // This is crucial for ensuring the contract is fully deployed and accessible.
    // The `confirmations` option controls how many blocks to wait for.
    const deployedContract = await contract.waitForDeployment({ confirmations });

    // Retrieve the full transaction receipt for deployment metadata.
    // The deploymentTransaction() method returns the TransactionResponse.
    // Calling .wait() on it will return the TransactionReceipt.
    const transactionReceipt = await deployedContract.deploymentTransaction()?.wait();

    if (!transactionReceipt) {
      throw new Error("Failed to get deployment transaction receipt. The transaction might not have been mined.");
    }

    // Construct the deployment receipt object as requested.
    const deploymentReceipt: DeploymentReceipt = {
      address: await deployedContract.getAddress(),
      transactionHash: transactionReceipt.hash,
      gasUsed: transactionReceipt.gasUsed,
      blockNumber: transactionReceipt.blockNumber,
    };

    return { contract: deployedContract, receipt: deploymentReceipt };
  }
}