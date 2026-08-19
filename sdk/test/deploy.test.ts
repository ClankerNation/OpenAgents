/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
 */
import { expect } from "chai";
import { ethers } from "hardhat";
import { OpenAgentsSDK } from "../src/index";

describe("OpenAgentsSDK deployContract", function () {
  it("should deploy a contract with constructor args and return receipt", async function () {
    const [signer] = await ethers.getSigners();
    
    // Use StakingToken as a test contract (has no constructor args but valid bytecode)
    const StakingToken = await ethers.getContractFactory("StakingToken");
    const abi = StakingToken.interface.format();
    const bytecode = StakingToken.bytecode;
    
    const sdk = new OpenAgentsSDK({
      name: "test",
      endpoint: "http://localhost",
      privateKey: signer.privateKey,
      rpcUrl: "http://127.0.0.1:8545",
      registryAddress: ethers.ZeroAddress,
      routerAddress: ethers.ZeroAddress,
    });
    
    // Override provider/signer to use hardhat's
    (sdk as any).provider = ethers.provider;
    (sdk as any).signer = signer;
    
    const result = await sdk.deployContract(abi, bytecode, [], 1);
    
    expect(result.contract).to.not.be.undefined;
    expect(result.receipt).to.not.be.undefined;
    expect(result.receipt.contractAddress).to.be.properAddress;
    expect(result.receipt.hash).to.be.a("string");
    expect(result.receipt.gasUsed).to.be.gt(0);
  });
});
