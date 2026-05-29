const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");
const solc = require("solc");

const votesTokenSource = `
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";

contract MockVotesToken is ERC20Votes {
    constructor() ERC20("Mock Votes", "MVOTE") EIP712("Mock Votes", "1") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
`;

function findImport(importPath) {
  const candidates = [
    path.join("node_modules", importPath),
    path.join(process.cwd(), importPath),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return { contents: fs.readFileSync(candidate, "utf8") };
    }
  }
  return { error: `File not found: ${importPath}` };
}

function compileContracts() {
  const input = {
    language: "Solidity",
    sources: {
      "GovernorAlpha.sol": { content: fs.readFileSync("contracts/governance/GovernorAlpha.sol", "utf8") },
      "MockVotesToken.sol": { content: votesTokenSource },
    },
    settings: {
      viaIR: true,
      optimizer: { enabled: true, runs: 200 },
      outputSelection: { "*": { "*": ["abi", "evm.bytecode"] } },
    },
  };
  const output = JSON.parse(solc.compile(JSON.stringify(input), { import: findImport }));
  const fatal = (output.errors || []).filter((error) => error.severity === "error");
  if (fatal.length > 0) {
    throw new Error(fatal.map((error) => error.formattedMessage).join("\n"));
  }
  return {
    governor: output.contracts["GovernorAlpha.sol"].GovernorAlpha,
    token: output.contracts["MockVotesToken.sol"].MockVotesToken,
  };
}

async function deployFactory(compiled, signer, ...args) {
  const factory = new ethers.ContractFactory(compiled.abi, compiled.evm.bytecode.object, signer);
  const contract = await factory.deploy(...args);
  await contract.waitForDeployment();
  return contract;
}

async function mineBlocks(count) {
  for (let i = 0; i < count; i++) {
    await ethers.provider.send("evm_mine", []);
  }
}

describe("GovernorAlpha proposal snapshots", function () {
  async function fixture() {
    const [proposer, lateBuyer, recipient] = await ethers.getSigners();
    const compiled = compileContracts();
    const token = await deployFactory(compiled.token, proposer);
    const governor = await deployFactory(compiled.governor, proposer, await token.getAddress());

    const threshold = await governor.PROPOSAL_THRESHOLD();
    await token.mint(proposer.address, threshold);
    await token.connect(proposer).delegate(proposer.address);
    await mineBlocks(1);

    return { governor, token, proposer, lateBuyer, recipient, threshold };
  }

  async function createProposal(governor, target) {
    const tx = await governor.propose([target], [0], ["0x"]);
    const receipt = await tx.wait();
    const event = receipt.logs
      .map((log) => {
        try {
          return governor.interface.parseLog(log);
        } catch (_) {
          return null;
        }
      })
      .find((log) => log && log.name === "ProposalCreated");
    return event.args.id;
  }

  it("stores the proposal creation block as snapshotBlock", async function () {
    const { governor, recipient } = await fixture();
    const proposalId = await createProposal(governor, recipient.address);
    const proposal = await governor.proposals(proposalId);

    expect(proposal.snapshotBlock).to.be.lt(proposal.startBlock);
  });

  it("ignores tokens acquired after proposal creation", async function () {
    const { governor, token, lateBuyer, recipient, threshold } = await fixture();
    const proposalId = await createProposal(governor, recipient.address);

    await token.mint(lateBuyer.address, threshold * 2n);
    await token.connect(lateBuyer).delegate(lateBuyer.address);
    await mineBlocks(2);

    expect(await governor.getVotingPower(lateBuyer.address, proposalId)).to.equal(0n);
  });

  it("keeps snapshot voting power even after later balance changes", async function () {
    const { governor, token, proposer, recipient, threshold } = await fixture();
    const proposalId = await createProposal(governor, recipient.address);

    await token.transfer(recipient.address, threshold / 2n);
    await mineBlocks(2);

    expect(await governor.getVotingPower(proposer.address, proposalId)).to.equal(threshold);
  });
});
