const assert = require("assert");
const { execFileSync } = require("child_process");
const fs = require("fs");
const Module = require("module");
const os = require("os");
const path = require("path");

function loadSdk(fakeEthers) {
  const outputDir = fs.mkdtempSync(
    path.join(os.tmpdir(), "openagents-sdk-deploy-"),
  );
  execFileSync(
    process.platform === "win32" ? "npx.cmd" : "npx",
    [
      "tsc",
      "--target",
      "ES2022",
      "--module",
      "Node16",
      "--moduleResolution",
      "Node16",
      "--skipLibCheck",
      "--types",
      "node",
      "--outDir",
      outputDir,
      "sdk/src/index.ts",
    ],
    { cwd: path.join(__dirname, ".."), stdio: "ignore" },
  );

  const originalLoad = Module._load;
  Module._load = function load(request, parent, isMain) {
    if (request === "ethers") return { ethers: fakeEthers };
    return originalLoad.call(this, request, parent, isMain);
  };
  try {
    return require(path.join(outputDir, "index.js"));
  } finally {
    Module._load = originalLoad;
  }
}

function createSdk(fakeEthers) {
  const { OpenAgentsSDK } = loadSdk(fakeEthers);
  return new OpenAgentsSDK({
    name: "agent",
    endpoint: "https://agent.example",
    privateKey: "0x" + "11".repeat(32),
    rpcUrl: "http://127.0.0.1:8545",
    registryAddress: "0x" + "22".repeat(20),
    routerAddress: "0x" + "33".repeat(20),
  });
}

function createFakeEthers(state, deployment) {
  class FakeContractFactory {
    constructor(abi, bytecode, signer) {
      state.abi = abi;
      state.bytecode = bytecode;
      state.signer = signer;
    }

    async deploy(...args) {
      state.deployArgs = args;
      return deployment;
    }
  }

  return {
    JsonRpcProvider: class FakeProvider {},
    Wallet: class FakeWallet {},
    Contract: class FakeContract {},
    ContractFactory: FakeContractFactory,
  };
}

async function testDeploysWithConstructorArgsOverridesAndMetadata() {
  const state = {};
  const receipt = {
    hash: "0xdeploy",
    contractAddress: "0x000000000000000000000000000000000000dEaD",
    gasUsed: 12345n,
    blockNumber: 77,
    blockHash: "0xblock",
    status: 1,
    confirmations: async () => 4,
  };
  const transaction = {
    hash: "0xdeploy",
    async wait(confirmations) {
      state.confirmations = confirmations;
      return receipt;
    },
  };
  const contract = {
    deploymentTransaction: () => transaction,
    getAddress: async () => "0x000000000000000000000000000000000000dEaD",
  };
  const sdk = createSdk(createFakeEthers(state, contract));
  const args = [42n, "hello"];
  const overrides = { value: 10n };

  const result = await sdk.deployContract(
    ["constructor(uint256,string)"],
    "0x60006000",
    args,
    { confirmations: 3, overrides },
  );

  assert.deepStrictEqual(state.abi, ["constructor(uint256,string)"]);
  assert.strictEqual(state.bytecode, "0x60006000");
  assert.deepStrictEqual(state.deployArgs, [42n, "hello", overrides]);
  assert.deepStrictEqual(args, [42n, "hello"]);
  assert.strictEqual(state.confirmations, 3);
  assert.strictEqual(result.contract, contract);
  assert.strictEqual(result.address, "0x000000000000000000000000000000000000dEaD");
  assert.strictEqual(result.transactionHash, "0xdeploy");
  assert.strictEqual(result.gasUsed, 12345n);
  assert.strictEqual(result.receipt, receipt);
  assert.deepStrictEqual(result.metadata, {
    address: result.address,
    contractAddress: result.address,
    transactionHash: "0xdeploy",
    gasUsed: 12345n,
    blockNumber: 77,
    blockHash: "0xblock",
    status: 1,
    confirmations: 4,
    requestedConfirmations: 3,
  });
}

async function testDefaultConfirmationsAndInvalidValues() {
  const state = {};
  const contract = {
    deploymentTransaction: () => ({
      hash: "0xdeploy",
      async wait(confirmations) {
        state.confirmations = confirmations;
        return { gasUsed: 1n, blockNumber: 1 };
      },
    }),
    getAddress: async () => "0x0000000000000000000000000000000000000001",
  };
  const sdk = createSdk(createFakeEthers(state, contract));
  await sdk.deployContract([], "0x6000");
  assert.strictEqual(state.confirmations, 1);

  await assert.rejects(
    () => sdk.deployContract([], "0x6000", [], { confirmations: -1 }),
    /confirmations must be a positive integer/,
  );
  await assert.rejects(
    () => sdk.deployContract([], "0x6000", [], { confirmations: 1.5 }),
    /confirmations must be a positive integer/,
  );
}

async function testMissingDeploymentDataFailsClearly() {
  const noTransaction = createSdk(
    createFakeEthers({}, { deploymentTransaction: () => null }),
  );
  await assert.rejects(
    () => noTransaction.deployContract([], "0x6000"),
    /Deployment transaction is unavailable/,
  );

  const noReceipt = createSdk(
    createFakeEthers({}, {
      deploymentTransaction: () => ({
        hash: "0xdeploy",
        async wait() {
          return null;
        },
      }),
    }),
  );
  await assert.rejects(
    () => noReceipt.deployContract([], "0x6000"),
    /Deployment receipt is unavailable/,
  );
}

async function testConstructorArgumentsAreEncodedByEthers() {
  const { ethers } = require("ethers");
  const abi = ["constructor(uint256,string)"];
  const bytecode = "0x60006000";
  const factory = new ethers.ContractFactory(abi, bytecode);
  const transaction = await factory.getDeployTransaction(42n, "hello");
  const iface = new ethers.Interface(abi);
  const encodedArgs = iface.encodeDeploy([42n, "hello"]).slice(2);
  assert.strictEqual(transaction.data, bytecode + encodedArgs);
}

Promise.all([
  testDeploysWithConstructorArgsOverridesAndMetadata(),
  testDefaultConfirmationsAndInvalidValues(),
  testMissingDeploymentDataFailsClearly(),
  testConstructorArgumentsAreEncodedByEthers(),
])
  .then(() => console.log("SDK deploy helper tests passed"))
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
