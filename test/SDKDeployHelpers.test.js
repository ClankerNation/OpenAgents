const assert = require("node:assert/strict");
const { ethers } = require("ethers");

const { OpenAgentsSDK } = require("./tmp-sdk/index.js");

const ORIGINAL_CONTRACT_FACTORY_DESCRIPTOR = Object.getOwnPropertyDescriptor(
  ethers,
  "ContractFactory"
);

function createSdkWithSigner(signer) {
  const sdk = Object.create(OpenAgentsSDK.prototype);
  sdk.signer = signer;
  return sdk;
}

async function run() {
  const deployCalls = [];
  const waitCalls = [];
  const deploymentReceipts = [
    {
      hash: "0xaaa",
      gasUsed: 21000n,
      blockNumber: 111,
      contractAddress: "0x00000000000000000000000000000000000000a1",
    },
    {
      hash: "0xbbb",
      gasUsed: 43000n,
      blockNumber: 112,
      contractAddress: "0x00000000000000000000000000000000000000b2",
    },
  ];

  const deployments = [
    {
      address: "0x00000000000000000000000000000000000000a1",
      receipt: deploymentReceipts[0],
    },
    {
      address: "0x00000000000000000000000000000000000000b2",
      receipt: deploymentReceipts[1],
    },
  ];
  let deploymentIndex = 0;

  class MockContractFactory {
    constructor(abi, bytecode, signer) {
      this.abi = abi;
      this.bytecode = bytecode;
      this.signer = signer;
    }

    async deploy(...params) {
      const current = deployments[deploymentIndex];
      deploymentIndex += 1;
      deployCalls.push(params);

      return {
        waitForDeployment: async () => {},
        deploymentTransaction: () => ({
          wait: async (confirmations) => {
            waitCalls.push(confirmations);
            return current.receipt;
          },
        }),
        getAddress: async () => current.address,
      };
    }
  }

  Object.defineProperty(ethers, "ContractFactory", {
    value: MockContractFactory,
    configurable: true,
    enumerable: true,
    writable: true,
  });

  try {
    const abi = ["constructor(uint256 value, string name)"];
    const bytecode = "0x6000600055";
    const signer = { name: "mock-signer" };
    const sdk = createSdkWithSigner(signer);

    const firstResult = await sdk.deployContract(abi, bytecode, [7, "alpha"]);
    assert.equal(firstResult.address, deployments[0].address);
    assert.equal(firstResult.txHash, deploymentReceipts[0].hash);
    assert.equal(firstResult.gasUsed, deploymentReceipts[0].gasUsed);
    assert.equal(firstResult.receipt.blockNumber, deploymentReceipts[0].blockNumber);
    assert.deepEqual(deployCalls[0], [7, "alpha"]);
    assert.equal(waitCalls[0], 1);

    const overrides = { gasLimit: 500000n, value: 100n };
    const secondResult = await sdk.deployContract(abi, bytecode, [9, "beta"], {
      confirmations: 3,
      overrides,
    });
    assert.equal(secondResult.address, deployments[1].address);
    assert.equal(secondResult.txHash, deploymentReceipts[1].hash);
    assert.equal(secondResult.gasUsed, deploymentReceipts[1].gasUsed);
    assert.deepEqual(deployCalls[1], [9, "beta", overrides]);
    assert.equal(waitCalls[1], 3);

    console.log("SDK deploy helper tests passed");
  } finally {
    Object.defineProperty(ethers, "ContractFactory", ORIGINAL_CONTRACT_FACTORY_DESCRIPTOR);
  }
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
