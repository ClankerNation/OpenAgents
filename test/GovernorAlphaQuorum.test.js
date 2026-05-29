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

function compileContracts() {
  const governorPath = "contracts/governance/GovernorAlpha.sol";
  const votesTokenPath = "contracts/test/GovernorVotesToken.sol";
  const targetPath = "contracts/test/GovernorTarget.sol";
  const input = {
    language: "Solidity",
    sources: {
      [governorPath]: { content: fs.readFileSync(governorPath, "utf8") },
      [votesTokenPath]: {
        content: `
          // SPDX-License-Identifier: MIT
          pragma solidity ^0.8.24;
          import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
          import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";

          contract GovernorVotesToken is ERC20Votes {
              constructor() ERC20("Governor Votes", "GOV") EIP712("Governor Votes", "1") {}

              function mint(address account, uint256 amount) external {
                  _mint(account, amount);
              }
          }
        `,
      },
      [targetPath]: {
        content: `
          // SPDX-License-Identifier: MIT
          pragma solidity ^0.8.20;

          contract GovernorTarget {
              uint256 public value;

              function setValue(uint256 newValue) external {
                  value = newValue;
              }
          }
        `,
      },
    },
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
      viaIR: true,
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

  return {
    governor: output.contracts[governorPath].GovernorAlpha,
    token: output.contracts[votesTokenPath].GovernorVotesToken,
    target: output.contracts[targetPath].GovernorTarget,
  };
}

async function deploy(artifact, signer, args = []) {
  const factory = new ethers.ContractFactory(
    artifact.abi,
    `0x${artifact.evm.bytecode.object}`,
    signer
  );
  const contract = await factory.deploy(...args);
  await contract.waitForDeployment();
  return contract;
}

async function mineVotingPeriod() {
  await ethers.provider.send("hardhat_mine", ["0x4382"]);
}

describe("GovernorAlpha quorum", function () {
  let compiled;
  let admin;
  let proposer;
  let outsider;
  let token;
  let governor;
  let target;

  before(function () {
    compiled = compileContracts();
  });

  beforeEach(async function () {
    [admin, proposer, outsider] = await ethers.getSigners();
    token = await deploy(compiled.token, admin);
    governor = await deploy(compiled.governor, admin, [await token.getAddress()]);
    target = await deploy(compiled.target, admin);

    await token.mint(proposer.address, ethers.parseEther("100000"));
    await token.connect(proposer).delegate(proposer.address);
    await ethers.provider.send("evm_mine");
  });

  async function createAndPassProposal() {
    const calldata = target.interface.encodeFunctionData("setValue", [7]);
    await governor.connect(proposer).propose(
      [await target.getAddress()],
      [0],
      [calldata]
    );

    await ethers.provider.send("evm_mine");
    await governor.connect(proposer).vote(1, true);
    await mineVotingPeriod();
  }

  it("reverts execution when forVotes is below quorum", async function () {
    await createAndPassProposal();
    await governor.setQuorumVotes(ethers.parseEther("100001"));

    await expect(governor.execute(1)).to.be.revertedWith("Governor: quorum not reached");
    expect(await target.value()).to.equal(0);
  });

  it("executes proposals that reach quorum and majority", async function () {
    await createAndPassProposal();
    await governor.setQuorumVotes(ethers.parseEther("100000"));

    await expect(governor.execute(1))
      .to.emit(governor, "ProposalExecuted")
      .withArgs(1);
    expect(await target.value()).to.equal(7);
  });

  it("lets only admin update quorum", async function () {
    await expect(governor.connect(outsider).setQuorumVotes(1))
      .to.be.revertedWith("Governor: not admin");

    await expect(governor.setQuorumVotes(ethers.parseEther("42")))
      .to.emit(governor, "QuorumVotesUpdated");
    expect(await governor.quorumVotes()).to.equal(ethers.parseEther("42"));
  });
});
