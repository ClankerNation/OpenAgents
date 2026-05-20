const { expect } = require("chai");
const { ethers, network } = require("hardhat");

describe("PrizeSplit", function () {
  async function deployPrizeSplit() {
    const [admin, winner, otherWinner] = await ethers.getSigners();
    const PrizeSplit = await ethers.getContractFactory("PrizeSplit");
    const prizeSplit = await PrizeSplit.deploy();
    await prizeSplit.waitForDeployment();

    const RejectEtherWinner = await ethers.getContractFactory("RejectEtherWinner");
    const rejectWinner = await RejectEtherWinner.deploy();
    await rejectWinner.waitForDeployment();

    return { admin, winner, otherWinner, prizeSplit, rejectWinner };
  }

  async function fundAndFinalize(prizeSplit, winners, amount = ethers.parseEther("3")) {
    await prizeSplit.fundRound({ value: amount });
    await prizeSplit.finalizeRound(1, winners);
  }

  it("lets other winners claim when a contract winner rejects ETH", async function () {
    const { winner, prizeSplit, rejectWinner } = await deployPrizeSplit();
    const rejectWinnerAddress = await rejectWinner.getAddress();

    await fundAndFinalize(prizeSplit, [rejectWinnerAddress, winner.address], ethers.parseEther("2"));
    await expect(rejectWinner.claim(prizeSplit, 1)).to.be.revertedWith("Transfer failed");

    await expect(() => prizeSplit.connect(winner).claimPrize(1)).to.changeEtherBalances(
      [winner, prizeSplit],
      [ethers.parseEther("1"), -ethers.parseEther("1")],
    );
    expect(await prizeSplit.isClaimed(1, winner.address)).to.equal(true);
    expect(await prizeSplit.isClaimed(1, rejectWinnerAddress)).to.equal(false);
  });

  it("blocks claims after the claim deadline", async function () {
    const { winner, prizeSplit } = await deployPrizeSplit();

    await fundAndFinalize(prizeSplit, [winner.address], ethers.parseEther("1"));
    await network.provider.send("evm_increaseTime", [90 * 24 * 60 * 60 + 1]);
    await network.provider.send("evm_mine");

    await expect(prizeSplit.connect(winner).claimPrize(1)).to.be.revertedWith("Claim deadline passed");
  });

  it("lets admin reclaim unclaimed prizes after the deadline", async function () {
    const { admin, winner, otherWinner, prizeSplit } = await deployPrizeSplit();

    await fundAndFinalize(prizeSplit, [winner.address, otherWinner.address], ethers.parseEther("2"));
    await prizeSplit.connect(winner).claimPrize(1);
    await network.provider.send("evm_increaseTime", [90 * 24 * 60 * 60 + 1]);
    await network.provider.send("evm_mine");

    await expect(() => prizeSplit.reclaimUnclaimedPrizes(1)).to.changeEtherBalances(
      [admin, prizeSplit],
      [ethers.parseEther("1"), -ethers.parseEther("1")],
    );
    expect(await prizeSplit.getUnclaimedPrize(1)).to.equal(0);
  });
});
