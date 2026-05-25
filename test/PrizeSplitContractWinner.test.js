const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("PrizeSplit pull claims", function () {
  let admin, winner, otherWinner, treasury;
  let prizeSplit, rejectEtherWinner;
  let prizeSplitAddress, rejectEtherWinnerAddress;

  const claimPeriod = 90 * 24 * 60 * 60;
  const prize = ethers.parseEther("9");

  beforeEach(async function () {
    [admin, winner, otherWinner, treasury] = await ethers.getSigners();

    const PrizeSplit = await ethers.getContractFactory("PrizeSplit");
    prizeSplit = await PrizeSplit.deploy();
    await prizeSplit.waitForDeployment();
    prizeSplitAddress = await prizeSplit.getAddress();

    const RejectEtherWinner = await ethers.getContractFactory("RejectEtherWinner");
    rejectEtherWinner = await RejectEtherWinner.deploy();
    await rejectEtherWinner.waitForDeployment();
    rejectEtherWinnerAddress = await rejectEtherWinner.getAddress();
  });

  async function fundAndFinalize(winners, value = prize) {
    await prizeSplit.fundRound({ value });
    await prizeSplit.finalizeRound(1, winners);
  }

  it("lets other winners claim even when a contract winner rejects ETH", async function () {
    await fundAndFinalize([rejectEtherWinnerAddress, winner.address]);

    const share = prize / 2n;

    await expect(rejectEtherWinner.claim(prizeSplitAddress, 1)).to.be.revertedWith("Transfer failed");
    expect(await prizeSplit.isClaimed(1, rejectEtherWinnerAddress)).to.equal(false);

    await expect(prizeSplit.connect(winner).claim(1))
      .to.emit(prizeSplit, "PrizeClaimed")
      .withArgs(winner.address, share, 1);

    expect(await prizeSplit.isClaimed(1, winner.address)).to.equal(true);
    expect(await prizeSplit.getRemainingPrize(1)).to.equal(share);
  });

  it("blocks claims after the 90-day deadline", async function () {
    await fundAndFinalize([winner.address]);

    await time.increase(claimPeriod + 1);

    await expect(prizeSplit.connect(winner).claim(1)).to.be.revertedWith("Claim period ended");
    expect(await prizeSplit.isClaimed(1, winner.address)).to.equal(false);
  });

  it("reclaims unclaimed prizes to treasury after the deadline", async function () {
    await prizeSplit.setTreasury(treasury.address);
    await fundAndFinalize([winner.address, otherWinner.address]);

    const share = prize / 2n;
    await prizeSplit.connect(winner).claimPrize(1);

    await time.increase(claimPeriod + 1);

    await expect(prizeSplit.reclaimUnclaimedPrizes(1)).to.changeEtherBalance(treasury, share);

    expect(await prizeSplit.getRemainingPrize(1)).to.equal(0);
    expect(await prizeSplit.totalPrize()).to.equal(0);
  });
});
