const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");
const solc = require("solc");

function compileAgentToken() {
  const sourcePath = path.join(__dirname, "..", "contracts", "token", "AgentToken.sol");
  const source = fs.readFileSync(sourcePath, "utf8");
  const input = {
    language: "Solidity",
    sources: {
      "contracts/token/AgentToken.sol": { content: source },
    },
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: {
        "*": {
          "*": ["abi", "evm.bytecode.object"],
        },
      },
    },
  };
  const output = JSON.parse(solc.compile(JSON.stringify(input), { import: importCallback }));
  const errors = (output.errors || []).filter((error) => error.severity === "error");
  expect(errors.map((error) => error.formattedMessage)).to.deep.equal([]);
  const contract = output.contracts["contracts/token/AgentToken.sol"].AgentToken;
  return {
    abi: contract.abi,
    bytecode: `0x${contract.evm.bytecode.object}`,
  };
}

function importCallback(importPath) {
  const fullPath = path.join(__dirname, "..", "node_modules", importPath);
  if (fs.existsSync(fullPath)) {
    return { contents: fs.readFileSync(fullPath, "utf8") };
  }
  return { error: `File not found: ${importPath}` };
}

function expectedDomainSeparator(name, chainId, verifyingContract) {
  return ethers.TypedDataEncoder.hashDomain({
    name,
    version: "1",
    chainId,
    verifyingContract,
  });
}

describe("AgentToken dynamic DOMAIN_SEPARATOR", function () {
  let compiled;

  before(function () {
    compiled = compileAgentToken();
  });

  async function deployToken(name = "Agent Token", symbol = "AGENT") {
    const signer = (await ethers.getSigners())[0];
    const factory = new ethers.ContractFactory(compiled.abi, compiled.bytecode, signer);
    const token = await factory.deploy(name, symbol, ethers.parseEther("1000"));
    await token.waitForDeployment();
    return token;
  }

  it("returns the EIP-712 separator for the current chain id", async function () {
    const token = await deployToken();
    const chainId = (await ethers.provider.getNetwork()).chainId;
    const expected = expectedDomainSeparator("Agent Token", chainId, await token.getAddress());

    expect(await token.DOMAIN_SEPARATOR()).to.equal(expected);
  });

  it("does not match the same deployment domain under a different chain id", async function () {
    const token = await deployToken();
    const chainId = (await ethers.provider.getNetwork()).chainId;
    const alternateChainId = chainId + 1n;
    const verifyingContract = await token.getAddress();

    expect(await token.DOMAIN_SEPARATOR()).to.not.equal(
      expectedDomainSeparator("Agent Token", alternateChainId, verifyingContract)
    );
  });

  it("validates permits only against the current chain domain", async function () {
    const [owner, spender] = await ethers.getSigners();
    const token = await deployToken();
    const chainId = (await ethers.provider.getNetwork()).chainId;
    const deadline = 2n ** 256n - 1n;
    const value = ethers.parseEther("5");
    const nonce = await token.nonces(owner.address);

    const signature = await owner.signTypedData(
      {
        name: "Agent Token",
        version: "1",
        chainId: chainId + 1n,
        verifyingContract: await token.getAddress(),
      },
      {
        Permit: [
          { name: "owner", type: "address" },
          { name: "spender", type: "address" },
          { name: "value", type: "uint256" },
          { name: "nonce", type: "uint256" },
          { name: "deadline", type: "uint256" },
        ],
      },
      {
        owner: owner.address,
        spender: spender.address,
        value,
        nonce,
        deadline,
      }
    );
    const { v, r, s } = ethers.Signature.from(signature);

    await expect(
      token.permit(owner.address, spender.address, value, deadline, v, r, s)
    ).to.be.revertedWith("AgentToken: invalid signature");
  });
});
