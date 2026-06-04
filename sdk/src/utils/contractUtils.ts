import { ethers } from '@ethersproject/contracts';
import { HDWalletProvider } from '@truffle/hdwallet-provider';

/**
 * Deploys a contract and waits for confirmation.
 *
 * @param abi - The ABI of the contract to deploy.
 * @param bytecode - The bytecode of the contract to deploy.
 * @param args - The constructor arguments for the contract.
 * @returns A promise that resolves with the deployed contract instance.
 */
export async function deployContract(abi: any[], bytecode: string, args: any[]): Promise<ethers.Contract> {
    // Replace 'YOUR_PRIVATE_KEY' and 'YOUR_INFURA_PROJECT_ID' with your actual private key and Infura project ID
    const provider = new HDWalletProvider('YOUR_PRIVATE_KEY', `https://mainnet.infura.io/v3/YOUR_INFURA_PROJECT_ID`);
    const signer = provider.getSigner();

    // Encode constructor arguments
    const encodedArgs = ethers.utils.defaultAbiCoder.encode(abi.filter((param) => param.type !== 'constructor').map((param) => param.type), args);

    // Deploy contract
    const factory = new ethers.ContractFactory(bytecode, abi, signer);
    const contract = await factory.deploy(...args);

    // Wait for deployment to be confirmed
    await contract.deployed();

    return contract;
}

/**
 * 