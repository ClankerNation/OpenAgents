const { expect } = require("chai");
const { ethers } = require("ethers");

process.env.TS_NODE_TRANSPILE_ONLY = "true";
process.env.TS_NODE_COMPILER_OPTIONS = JSON.stringify({
  module: "commonjs",
  moduleResolution: "node",
  target: "es2020",
  esModuleInterop: true,
  ignoreDeprecations: "6.0",
});
require("ts-node/register/transpile-only");

const { OpenAgentsSDK } = require("../sdk/src/index.ts");

describe("OpenAgentsSDK.deployContract", function () {
  it("deploys with constructor args, waits for confirmations, and returns receipt metadata", async function () {
    const sdk = new OpenAgentsSDK({
      name: "test-agent",
      endpoint: "http://localhost",
      privateKey:
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
      rpcUrl: "http://127.0.0.1:8545",
      registryAddress: ethers.ZeroAddress,
      routerAddress: ethers.ZeroAddress,
    });

    sdk.signer = { __mockSigner: true };

    const originalFactory = ethers.ContractFactory;
    const observed = {
      abi: null,
      bytecode: null,
      signer: null,
      deployArgs: null,
      waitConfirmations: null,
    };

    const mockContract = {
      deploymentTransaction: () => ({
        wait: async (confirmations) => {
          observed.waitConfirmations = confirmations;
          return {
            hash: "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            gasUsed: 21000n,
            blockNumber: 123,
            status: 1,
          };
        },
      }),
      getAddress: async () => "0x1111111111111111111111111111111111111111",
    };

    class MockContractFactory {
      constructor(abi, bytecode, signer) {
        observed.abi = abi;
        observed.bytecode = bytecode;
        observed.signer = signer;
      }

      async deploy(...args) {
        observed.deployArgs = args;
        return mockContract;
      }
    }

    Object.defineProperty(ethers, "ContractFactory", {
      value: MockContractFactory,
      configurable: true,
    });

    try {
      const result = await sdk.deployContract(
        ["constructor(uint256,string)"],
        "0x60006000",
        [123n, "hello"],
        { confirmationBlocks: 2 }
      );

      expect(observed.abi).to.deep.equal(["constructor(uint256,string)"]);
      expect(observed.bytecode).to.equal("0x60006000");
      expect(observed.signer).to.equal(sdk.signer);
      expect(observed.deployArgs).to.deep.equal([123n, "hello"]);
      expect(observed.waitConfirmations).to.equal(2);

      expect(result.contract).to.equal(mockContract);
      expect(result.receipt).to.deep.equal({
        address: "0x1111111111111111111111111111111111111111",
        txHash: "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        gasUsed: 21000n,
        blockNumber: 123,
        status: 1,
      });
    } finally {
      Object.defineProperty(ethers, "ContractFactory", {
        value: originalFactory,
        configurable: true,
      });
    }
  });
});
