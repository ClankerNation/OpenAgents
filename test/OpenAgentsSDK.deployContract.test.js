const { expect } = require("chai");
const { ethers } = require("ethers");
const fs = require("fs");
const path = require("path");
const ts = require("typescript");

function loadSdk() {
  const source = fs.readFileSync(
    path.join(__dirname, "../sdk/src/index.ts"),
    "utf8"
  );
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      esModuleInterop: true,
    },
  }).outputText;

  const moduleShim = { exports: {} };
  const runner = new Function("require", "module", "exports", transpiled);
  runner(require, moduleShim, moduleShim.exports);
  return moduleShim.exports;
}

const { OpenAgentsSDK } = loadSdk();

function createSdk() {
  const sdk = Object.create(OpenAgentsSDK.prototype);
  sdk.signer = {};
  return sdk;
}

describe("OpenAgentsSDK.deployContract", function () {
  it("deploys with constructor args and returns deployment metadata", async function () {
    const sdk = createSdk();
    const originalFactory = ethers.ContractFactory;

    const receipt = {
      hash: "0x" + "ab".repeat(32),
      gasUsed: 999n,
      blockNumber: 42,
      blockHash: "0x" + "cd".repeat(32),
      status: 1,
    };

    const contract = {
      deploymentTransaction() {
        return {
          wait: async () => receipt,
        };
      },
      async getAddress() {
        return "0x0000000000000000000000000000000000000009";
      },
    };

    let constructorArgs = null;

    Object.defineProperty(ethers, "ContractFactory", {
      configurable: true,
      value: class MockFactory {
      constructor(abi, bytecode, signer) {
        constructorArgs = { abi, bytecode, signer };
      }

      async deploy(...args) {
        this.deployArgs = args;
        contract.deployArgs = args;
        return contract;
      }
      },
    });

    try {
      const result = await sdk.deployContract(
        ["constructor(uint256,string)"],
        "0x6000",
        [123n, "hello"]
      );

      expect(constructorArgs.abi).to.deep.equal(["constructor(uint256,string)"]);
      expect(constructorArgs.bytecode).to.equal("0x6000");
      expect(contract.deployArgs).to.deep.equal([123n, "hello"]);
      expect(result.contract).to.equal(contract);
      expect(result.receipt).to.deep.equal({
        contractAddress: "0x0000000000000000000000000000000000000009",
        transactionHash: receipt.hash,
        gasUsed: receipt.gasUsed,
        blockNumber: receipt.blockNumber,
        blockHash: receipt.blockHash,
        status: receipt.status,
      });
    } finally {
      Object.defineProperty(ethers, "ContractFactory", {
        configurable: true,
        value: originalFactory,
      });
    }
  });

  it("waits for configurable confirmation blocks", async function () {
    const sdk = createSdk();
    const originalFactory = ethers.ContractFactory;
    let receivedConfirmations = null;

    Object.defineProperty(ethers, "ContractFactory", {
      configurable: true,
      value: class MockFactory {
      async deploy() {
        return {
          deploymentTransaction() {
            return {
              wait: async (confirmations) => {
                receivedConfirmations = confirmations;
                return {
                  hash: "0x" + "ef".repeat(32),
                  gasUsed: 1n,
                  blockNumber: 1,
                  blockHash: "0x" + "12".repeat(32),
                  status: 1,
                };
              },
            };
          },
          async getAddress() {
            return "0x0000000000000000000000000000000000000010";
          },
        };
      }
      },
    });

    try {
      await sdk.deployContract(["constructor()"], "0x6000", [], 3);
      expect(receivedConfirmations).to.equal(3);
    } finally {
      Object.defineProperty(ethers, "ContractFactory", {
        configurable: true,
        value: originalFactory,
      });
    }
  });
});
