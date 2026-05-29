const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const solc = require("solc");

function compileContracts() {
  const prizeSplitPath = "contracts/lottery/PrizeSplit.sol";
  const rejectWinnerPath = "contracts/test/RejectEthWinner.sol";
  const input = {
    language: "Solidity",
    sources: {
      [prizeSplitPath]: { content: fs.readFileSync(prizeSplitPath, "utf8") },
      [rejectWinnerPath]: {
        content: `
          // SPDX-License-Identifier: MIT
          pragma solidity ^0.8.20;

          contract RejectEthWinner {
              function claim(address prizeSplit, uint256 roundId) external {
                  (bool ok, ) = prizeSplit.call(
                      abi.encodeWithSignature("claimPrize(uint256)", roundId)
                  );
                  require(ok, "claim failed");
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

  const output = JSON.parse(solc.compile(JSON.stringify(input)));
  const errors = (output.errors || []).filter((error) => error.severity === "error");
  if (errors.length) {
    throw new Error(errors.map((error) => error.formattedMessage).join("\n"));
  }

  return {
    prizeSplit: output.contracts[prizeSplitPath].PrizeSplit,
    rejectWinner: output.contracts[rejectWinnerPath].RejectEthWinner,
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

async function increaseTime(seconds) {
  await ethers.provider.send("evm_increaseTime", [seconds]);
  await ethers.provider.send("evm_mine");
}

describe("PrizeSplit pull claims", function () {
  let compiled;
  let admin;
  let winner;
  let other;
  let prizeSplit;
  let rejectWinner;

  before(function () {
    compiled = compileContracts();
  });

  beforeEach(async function () {
    [admin, winner, other] = await ethers.getSigners();
    prizeSplit = await deploy(compiled.prizeSplit, admin);
    rejectWinner = await deploy(compiled.rejectWinner, admin);
  });

  async function fundAndFinalize(winners, value = ethers.parseEther("2")) {
    await prizeSplit.fundRound({ value });
    await prizeSplit.finalizeRound(1, winners);
  }

  it("lets other winners claim even when a contract winner rejects ETH", async function () {
    await fundAndFinalize([await rejectWinner.getAddress(), winner.address]);

    await expect(
      rejectWinner.claim(await prizeSplit.getAddress(), 1)
    ).to.be.revertedWith("claim failed");

    await expect(prizeSplit.connect(winner).claimPrize(1))
      .to.emit(prizeSplit, "PrizeClaimed")
      .withArgs(winner.address, ethers.parseEther("1"), 1);
    expect(await prizeSplit.isClaimed(1, winner.address)).to.equal(true);
    expect(await prizeSplit.isClaimed(1, await rejectWinner.getAddress())).to.equal(false);
  });

  it("prevents treasury reclaim before the claim deadline", async function () {
    await fundAndFinalize([winner.address, other.address]);

    await expect(prizeSplit.reclaimUnclaimed(1))
      .to.be.revertedWith("Claim period active");
  });

  it("reclaims unclaimed prizes after 90 days", async function () {
    await fundAndFinalize([winner.address, other.address]);
    await prizeSplit.connect(winner).claimPrize(1);

    await increaseTime(90 * 24 * 60 * 60);

    await expect(prizeSplit.reclaimUnclaimed(1))
      .to.emit(prizeSplit, "UnclaimedPrizesReclaimed")
      .withArgs(1, ethers.parseEther("1"));
    expect(await prizeSplit.isClaimed(1, other.address)).to.equal(true);
  });
});
