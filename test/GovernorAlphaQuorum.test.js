const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");
const solc = require("solc");

const ROOT_DIR = path.resolve(__dirname, "..");

function readSource(sourcePath) {
  return fs.readFileSync(path.join(ROOT_DIR, sourcePath), "utf8");
}

function resolveImport(importPath) {
  const candidates = [
    path.join(ROOT_DIR, importPath),
    path.join(ROOT_DIR, "node_modules", importPath),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return { contents: fs.readFileSync(candidate, "utf8") };
    }
  }

  return { error: `Import not found: ${importPath}` };
}

function compileContracts() {
  const input = {
    language: "Solidity",
    sources: {
      "contracts/governance/GovernorAlpha.sol": {
        content: readSource("contracts/governance/GovernorAlpha.sol"),
      },
      "contracts/test/GovernanceTokenMock.sol": {
        content: readSource("contracts/test/GovernanceTokenMock.sol"),
      },
    },
    settings: {
      viaIR: true,
      optimizer: {
        enabled: true,
        runs: 200,
      },
      outputSelection: {
        "*": {
          "*": ["abi", "evm.bytecode.object"],
        },
      },
    },
  };

  const output = JSON.parse(solc.compile(JSON.stringify(input), { import: resolveImport }));
  const errors = (output.errors || []).filter((error) => error.severity === "error");
  if (errors.length > 0) {
    throw new Error(errors.map((error) => error.formattedMessage).join("\n"));
  }

  return {
    GovernorAlpha: output.contracts["contracts/governance/GovernorAlpha.sol"].GovernorAlpha,
    GovernanceTokenMock: output.contracts["contracts/test/GovernanceTokenMock.sol"].GovernanceTokenMock,
  };
}

describe("GovernorAlpha quorum", function () {
  let admin;
  let proposer;
  let voter;
  let recipient;
  let token;
  let governor;

  const defaultSupply = ethers.parseEther("1000000");
  const compiled = compileContracts();

  function getFactory(contractName, signer) {
    const artifact = compiled[contractName];
    return new ethers.ContractFactory(artifact.abi, artifact.evm.bytecode.object, signer);
  }

  beforeEach(async function () {
    [admin, proposer, voter, recipient] = await ethers.getSigners();

    const GovernanceToken = getFactory("GovernanceTokenMock", admin);
    token = await GovernanceToken.deploy();
    await token.waitForDeployment();

    await token.mint(proposer.address, defaultSupply);
    await token.mint(voter.address, defaultSupply);
    await token.connect(proposer).delegate(proposer.address);
    await token.connect(voter).delegate(voter.address);

    const GovernorAlpha = getFactory("GovernorAlpha", admin);
    governor = await GovernorAlpha.deploy(await token.getAddress());
    await governor.waitForDeployment();
  });

  async function mineBlocks(count) {
    for (let index = 0; index < count; index += 1) {
      await ethers.provider.send("evm_mine", []);
    }
  }

  async function createProposal() {
    const tx = await governor.connect(proposer).propose(
      [recipient.address],
      [0],
      ["0x"],
    );
    const receipt = await tx.wait();
    const event = receipt.logs
      .map((log) => {
        try {
          return governor.interface.parseLog(log);
        } catch {
          return null;
        }
      })
      .find((log) => log && log.name === "ProposalCreated");

    return event.args.id;
  }

  async function finishVoting(proposalId, signer) {
    await mineBlocks(2);
    await governor.connect(signer).vote(proposalId, true);
    await mineBlocks(Number(await governor.VOTING_PERIOD()) + 1);
  }

  it("initializes quorum to 4 percent of token supply", async function () {
    expect(await governor.quorumVotes()).to.equal(ethers.parseEther("80000"));
  });

  it("reverts execution when forVotes is below quorum", async function () {
    await governor.connect(admin).setQuorumVotes(ethers.parseEther("1500000"));
    const proposalId = await createProposal();

    await finishVoting(proposalId, proposer);

    await expect(governor.execute(proposalId))
      .to.be.revertedWith("Governor: quorum not reached");
  });

  it("executes when forVotes equals quorum and has majority", async function () {
    await governor.connect(admin).setQuorumVotes(defaultSupply);
    const proposalId = await createProposal();

    await finishVoting(proposalId, proposer);

    await expect(governor.execute(proposalId))
      .to.emit(governor, "ProposalExecuted")
      .withArgs(proposalId);
  });

  it("lets only admin update quorum", async function () {
    await expect(governor.connect(proposer).setQuorumVotes(1))
      .to.be.revertedWith("Governor: not admin");
    await expect(governor.connect(admin).setQuorumVotes(0))
      .to.be.revertedWith("Governor: quorum must be positive");

    await expect(governor.connect(admin).setQuorumVotes(ethers.parseEther("250000")))
      .to.emit(governor, "QuorumVotesUpdated")
      .withArgs(ethers.parseEther("80000"), ethers.parseEther("250000"));

    expect(await governor.quorumVotes()).to.equal(ethers.parseEther("250000"));
  });
});
