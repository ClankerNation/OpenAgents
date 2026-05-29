const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");
const solc = require("solc");

function findImport(importPath) {
  const candidates = [
    path.join(process.cwd(), importPath),
    path.join(process.cwd(), "node_modules", importPath),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return { contents: fs.readFileSync(candidate, "utf8") };
    }
  }

  return { error: `File not found: ${importPath}` };
}

function compileAgentToken() {
  const sourcePath = "contracts/token/AgentToken.sol";
  const harnessPath = "contracts/test/AgentTokenDomainHarness.sol";
  const input = {
    language: "Solidity",
    sources: {
      [sourcePath]: { content: fs.readFileSync(sourcePath, "utf8") },
      [harnessPath]: {
        content: `
          // SPDX-License-Identifier: MIT
          pragma solidity ^0.8.20;
          import "../token/AgentToken.sol";

          contract AgentTokenDomainHarness is AgentToken {
              constructor() AgentToken("Agent Token", "AGENT", 1000) {}

              function domainSeparatorForChainId(uint256 chainId) external view returns (bytes32) {
                  return _buildDomainSeparator(chainId);
              }
          }
        `,
      },
    },
    settings: {
      outputSelection: {
        "*": {
          "*": ["abi", "evm.bytecode.object"],
        },
      },
    },
  };

  const output = JSON.parse(solc.compile(JSON.stringify(input), { import: findImport }));
  const errors = (output.errors || []).filter((error) => error.severity === "error");
  if (errors.length) {
    throw new Error(errors.map((error) => error.formattedMessage).join("\n"));
  }

  const contract = output.contracts[harnessPath].AgentTokenDomainHarness;
  return {
    abi: contract.abi,
    bytecode: `0x${contract.evm.bytecode.object}`,
  };
}

async function deployAgentToken() {
  const compiled = compileAgentToken();
  const [owner] = await ethers.getSigners();
  const factory = new ethers.ContractFactory(compiled.abi, compiled.bytecode, owner);
  return factory.deploy();
}

function expectedDomainSeparator(tokenAddress, chainId) {
  return ethers.TypedDataEncoder.hashDomain({
    name: "Agent Token",
    version: "1",
    chainId,
    verifyingContract: tokenAddress,
  });
}

describe("AgentToken DOMAIN_SEPARATOR", function () {
  it("returns the EIP-712 separator for the active chain ID", async function () {
    const token = await deployAgentToken();
    const chainId = (await ethers.provider.getNetwork()).chainId;

    expect(await token.DOMAIN_SEPARATOR()).to.equal(
      expectedDomainSeparator(await token.getAddress(), chainId)
    );
  });

  it("builds different separators for different fork chain IDs", async function () {
    const token = await deployAgentToken();
    const tokenAddress = await token.getAddress();
    const firstSeparator = await token.domainSeparatorForChainId(31337);
    const secondSeparator = await token.domainSeparatorForChainId(31338);

    expect(firstSeparator).to.not.equal(secondSeparator);
    expect(firstSeparator).to.equal(
      expectedDomainSeparator(tokenAddress, 31337n)
    );
    expect(secondSeparator).to.equal(
      expectedDomainSeparator(tokenAddress, 31338n)
    );
  });
});
