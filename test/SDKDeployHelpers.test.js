const assert = require("assert");
const { ethers } = require("ethers");
const { OpenAgentsSDK } = require("../.tmp-sdk/index.js");

async function testDeployWithArgsAndConfirmations() {
  const originalFactory = ethers.ContractFactory;
  const captured = {
    constructorAbi: null,
    constructorBytecode: null,
    constructorSigner: null,
    deployArgs: null,
    waitConfirmations: null,
  };

  const mockReceipt = {
    gasUsed: 21000n,
    blockNumber: 123,
    status: 1,
  };

  const mockDeploymentTx = {
    hash: "0xdeploytx",
    wait: async (confirmations) => {
      captured.waitConfirmations = confirmations;
      return mockReceipt;
    },
  };

  const mockContract = {
    waitForDeployment: async () => {},
    deploymentTransaction: () => mockDeploymentTx,
    getAddress: async () => "0x000000000000000000000000000000000000dEaD",
  };

  class MockFactory {
    constructor(abi, bytecode, signer) {
      captured.constructorAbi = abi;
      captured.constructorBytecode = bytecode;
      captured.constructorSigner = signer;
    }

    async deploy(...deployArgs) {
      captured.deployArgs = deployArgs;
      return mockContract;
    }
  }

  Object.defineProperty(ethers, "ContractFactory", {
    value: MockFactory,
    configurable: true,
    enumerable: true,
    writable: true,
  });

  try {
    const sdk = new OpenAgentsSDK({
      name: "agent",
      endpoint: "http://localhost:3000",
      privateKey: "0x59c6995e998f97a5a0044966f094538e54f6d4a8351e6c4d9969f40d5f5f4f7d",
      rpcUrl: "http://127.0.0.1:8545",
      registryAddress: "0x0000000000000000000000000000000000000001",
      routerAddress: "0x0000000000000000000000000000000000000002",
    });

    const abi = ["constructor(uint256,string)"];
    const bytecode = "0x60006000";
    const args = [42n, "hello"];
    const overrides = { gasLimit: 500000n };

    const result = await sdk.deployContract(abi, bytecode, args, {
      confirmations: 3,
      overrides,
    });

    assert.deepStrictEqual(captured.constructorAbi, abi);
    assert.strictEqual(captured.constructorBytecode, bytecode);
    assert.ok(captured.constructorSigner);
    assert.deepStrictEqual(captured.deployArgs, [42n, "hello", overrides]);
    assert.strictEqual(captured.waitConfirmations, 3);

    assert.strictEqual(result.address, "0x000000000000000000000000000000000000dEaD");
    assert.strictEqual(result.txHash, "0xdeploytx");
    assert.strictEqual(result.gasUsed, 21000n);
    assert.strictEqual(result.receipt, mockReceipt);
    assert.deepStrictEqual(result.metadata, {
      blockNumber: 123,
      status: 1,
      confirmations: 3,
    });
  } finally {
    Object.defineProperty(ethers, "ContractFactory", {
      value: originalFactory,
      configurable: true,
      enumerable: true,
      writable: true,
    });
  }
}

async function testDefaultConfirmations() {
  const originalFactory = ethers.ContractFactory;
  let observedConfirmations = null;

  const mockContract = {
    waitForDeployment: async () => {},
    deploymentTransaction: () => ({
      hash: "0xabc",
      wait: async (confirmations) => {
        observedConfirmations = confirmations;
        return {
          gasUsed: 1n,
          blockNumber: 1,
          status: 1,
        };
      },
    }),
    getAddress: async () => "0x0000000000000000000000000000000000000003",
  };

  class MockFactory {
    async deploy() {
      return mockContract;
    }
  }

  Object.defineProperty(ethers, "ContractFactory", {
    value: MockFactory,
    configurable: true,
    enumerable: true,
    writable: true,
  });

  try {
    const sdk = new OpenAgentsSDK({
      name: "agent",
      endpoint: "http://localhost:3000",
      privateKey: "0x59c6995e998f97a5a0044966f094538e54f6d4a8351e6c4d9969f40d5f5f4f7d",
      rpcUrl: "http://127.0.0.1:8545",
      registryAddress: "0x0000000000000000000000000000000000000001",
      routerAddress: "0x0000000000000000000000000000000000000002",
    });

    await sdk.deployContract([], "0x6000");
    assert.strictEqual(observedConfirmations, 1);
  } finally {
    Object.defineProperty(ethers, "ContractFactory", {
      value: originalFactory,
      configurable: true,
      enumerable: true,
      writable: true,
    });
  }
}

(async () => {
  await testDeployWithArgsAndConfirmations();
  await testDefaultConfirmations();
  console.log("SDK deploy helper tests passed");
})();
