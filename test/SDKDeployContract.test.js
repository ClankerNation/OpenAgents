process.env.TS_NODE_IGNORE_DIAGNOSTICS = "5102";
process.env.TS_NODE_COMPILER_OPTIONS = JSON.stringify({
  module: "commonjs",
  target: "es2020",
});

require("ts-node/register/transpile-only");

const { expect } = require("chai");
const { OpenAgentsSDK } = require("../sdk/src/index.ts");

const sdkConfig = {
  name: "agent",
  endpoint: "https://agent.example",
  privateKey: "0x".padEnd(66, "1"),
  rpcUrl: "http://127.0.0.1:8545",
  registryAddress: "0x0000000000000000000000000000000000000001",
  routerAddress: "0x0000000000000000000000000000000000000002",
};

describe("OpenAgentsSDK.deployContract", function () {
  it("deploys with constructor args and returns deployment metadata", async function () {
    const deployedAddress = "0x00000000000000000000000000000000000000aa";
    const receipt = { gasUsed: 123456n };
    const calls = { args: null, confirmations: null, waited: false };

    class TestSDK extends OpenAgentsSDK {
      createContractFactory(abi, bytecode) {
        calls.abi = abi;
        calls.bytecode = bytecode;
        return {
          deploy: async (...args) => {
            calls.args = args;
            return {
              waitForDeployment: async () => {
                calls.waited = true;
              },
              deploymentTransaction: () => ({
                hash: "0xabc123",
                wait: async (confirmations) => {
                  calls.confirmations = confirmations;
                  return receipt;
                },
              }),
              getAddress: async () => deployedAddress,
            };
          },
        };
      }
    }

    const abi = ["constructor(uint256,string)"];
    const bytecode = "0x60006000";
    const sdk = new TestSDK(sdkConfig);

    const result = await sdk.deployContract(abi, bytecode, [42n, "hello"], { confirmations: 3 });

    expect(calls.abi).to.equal(abi);
    expect(calls.bytecode).to.equal(bytecode);
    expect(calls.args).to.deep.equal([42n, "hello"]);
    expect(calls.waited).to.equal(true);
    expect(calls.confirmations).to.equal(3);
    expect(result.address).to.equal(deployedAddress);
    expect(result.txHash).to.equal("0xabc123");
    expect(result.gasUsed).to.equal(123456n);
    expect(result.receipt).to.equal(receipt);
  });

  it("waits for one confirmation by default", async function () {
    let confirmations;

    class TestSDK extends OpenAgentsSDK {
      createContractFactory() {
        return {
          deploy: async () => ({
            waitForDeployment: async () => {},
            deploymentTransaction: () => ({
              hash: "0xdef456",
              wait: async (count) => {
                confirmations = count;
                return { gasUsed: 1n };
              },
            }),
            getAddress: async () => "0x00000000000000000000000000000000000000bb",
          }),
        };
      }
    }

    const sdk = new TestSDK(sdkConfig);
    await sdk.deployContract([], "0x6000");

    expect(confirmations).to.equal(1);
  });
});
