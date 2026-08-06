const assert = require("assert");
const { execFileSync } = require("child_process");
const fs = require("fs");
const hre = require("hardhat");
const Module = require("module");
const os = require("os");
const path = require("path");
const solc = require("solc");

function loadSdk() {
  const outputDir = fs.mkdtempSync(
    path.join(os.tmpdir(), "openagents-sdk-deploy-integration-"),
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
  process.env.NODE_PATH = path.join(__dirname, "..", "node_modules");
  Module._initPaths();
  return require(path.join(outputDir, "index.js"));
}

function compileFixture() {
  const input = {
    language: "Solidity",
    sources: {
      "ConstructorStore.sol": {
        content: `pragma solidity ^0.8.20;
contract ConstructorStore {
  uint256 public stored;
  constructor(uint256 initial) payable { stored = initial; }
}`,
      },
    },
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: { "*": { "*": ["abi", "evm.bytecode.object"] } },
    },
  };
  const output = JSON.parse(solc.compile(JSON.stringify(input)));
  const errors = (output.errors || []).filter((error) => error.severity === "error");
  assert.deepStrictEqual(errors, []);
  const artifact = output.contracts["ConstructorStore.sol"].ConstructorStore;
  return { abi: artifact.abi, bytecode: `0x${artifact.evm.bytecode.object}` };
}

describe("OpenAgentsSDK.deployContract integration", function () {
  this.timeout(30_000);

  it("deploys a constructor-bearing contract and returns receipt metadata", async function () {
    const { OpenAgentsSDK } = loadSdk();
    const { abi, bytecode } = compileFixture();
    const [signer] = await hre.ethers.getSigners();
    const sdk = new OpenAgentsSDK({
      name: "integration-agent",
      endpoint: "https://agent.example",
      privateKey: "0x" + "11".repeat(32),
      rpcUrl: "http://127.0.0.1:8545",
      registryAddress: "0x" + "22".repeat(20),
      routerAddress: "0x" + "33".repeat(20),
    });
    sdk.signer = signer;
    sdk.provider = hre.ethers.provider;

    const value = hre.ethers.parseEther("0.01");
    await hre.network.provider.send("evm_setAutomine", [false]);
    const mining = setInterval(() => {
      void hre.network.provider.send("evm_mine");
    }, 10);

    let result;
    try {
      result = await sdk.deployContract(abi, bytecode, [42n], {
        confirmations: 2,
        overrides: { value },
      });
    } finally {
      clearInterval(mining);
      await hre.network.provider.send("evm_setAutomine", [true]);
    }

    const deployed = new hre.ethers.Contract(result.address, abi, signer);
    assert.strictEqual(await deployed.stored(), 42n);
    assert.strictEqual(await hre.ethers.provider.getCode(result.address) !== "0x", true);
    assert.strictEqual(await hre.ethers.provider.getBalance(result.address), value);
    assert.strictEqual(result.receipt.contractAddress, result.address);
    assert.strictEqual(result.receipt.hash, result.transactionHash);
    assert.strictEqual(result.metadata.contractAddress, result.address);
    assert.strictEqual(result.metadata.status, 1);
    assert.strictEqual(result.metadata.requestedConfirmations, 2);
    assert.ok(result.metadata.confirmations >= 2);
    assert.ok(result.gasUsed > 0n);
  });
});
