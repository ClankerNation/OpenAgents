require("ts-node/register");
const { expect } = require("chai");
const { ethers } = require("hardhat");
const { OpenAgentsSDK } = require("../sdk/src/index");

describe("OpenAgentsSDK - deployContract", function () {
  let sdk;
  let signer;
  let TestDeployFactory;

  before(async function () {
    const signers = await ethers.getSigners();
    signer = signers[0];
    
    // We can instantiate the SDK. But we need a running network and private key.
    // However, the SDK expects AgentConfig which includes privateKey and rpcUrl.
    // Hardhat provides a local network.
    
    // To properly test the SDK class which creates its own provider and signer,
    // we would need a hardhat network URL and a known private key.
    // Since we are inside hardhat environment, we can just test the method directly
    // by mocking or creating a specialized instance.
    
    // Actually, Hardhat Network default URL is http://127.0.0.1:8545 when run as a node.
    // If we just run tests, there's no HTTP endpoint by default unless we start one.
    // Let's create an SDK instance and override the signer and provider for testing.
    
    sdk = new OpenAgentsSDK({
      name: "TestAgent",
      endpoint: "http://localhost",
      privateKey: "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80", // Hardhat Account #0
      rpcUrl: "http://127.0.0.1:8545",
      registryAddress: ethers.ZeroAddress,
      routerAddress: ethers.ZeroAddress,
    });
    
    // Override the internal signer to use the hardhat signer to bypass network issues during normal 'npx hardhat test'
    sdk.signer = signer;
    sdk.provider = signer.provider;
    
    TestDeployFactory = await ethers.getContractFactory("TestDeploy");
  });

  it("should deploy a contract with constructor arguments and wait for confirmation", async function () {
    const valueArg = 42n;
    const nameArg = "AgentContract";

    const { contract, receipt } = await sdk.deployContract(
      TestDeployFactory.interface.fragments,
      TestDeployFactory.bytecode,
      [valueArg, nameArg],
      { confirmations: 1 }
    );

    expect(contract).to.not.be.undefined;
    expect(await contract.getAddress()).to.be.properAddress;
    expect(receipt).to.not.be.undefined;
    expect(receipt.contractAddress).to.equal(await contract.getAddress());
    expect(receipt.transactionHash).to.exist;
    expect(receipt.gasUsed).to.be.greaterThan(0n);
    expect(receipt.blockNumber).to.be.greaterThan(0);

    // Verify constructor args were set correctly
    const value = await contract.value();
    const name = await contract.name();
    expect(value).to.equal(valueArg);
    expect(name).to.equal(nameArg);
  });
});
