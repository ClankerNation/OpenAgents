const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("PrizeSplit pull claims", function () {
  let admin;
  let alice;
  let bob;
  let treasury;
  let prizeSplit;
  let rejectingWinner;

  const prizePool = ethers.parseEther("9");
  const roundId = 1;

  beforeEach(async function () {
    [admin, alice, bob, treasury] = await ethers.getSigners();

    const PrizeSplit = await ethers.getContractFactory("PrizeSplit");
    prizeSplit = await PrizeSplit.deploy();
    await prizeSplit.setTreasury(treasury.address);

    const RejectEthWinner = await ethers.getContractFactory("RejectEthWinner");
    rejectingWinner = await RejectEthWinner.deploy();
  });

  async function fundAndFinalize(winners) {
    await prizeSplit.fundRound({ value: prizePool });
    await prizeSplit.finalizeRound(roundId, winners);
    return prizePool / BigInt(winners.length);
  }

  it("lets other winners claim when a contract winner rejects ETH", async function () {
    const rejectingAddress = await rejectingWinner.getAddress();
    const share = await fundAndFinalize([rejectingAddress, alice.address, bob.address]);

    await expect(rejectingWinner.claimPrize(prizeSplit, roundId)).to.be.revertedWith(
      "Transfer failed",
    );

    await expect(prizeSplit.connect(alice).claim(roundId))
      .to.emit(prizeSplit, "PrizeClaimed")
      .withArgs(alice.address, share, roundId);

    await expect(prizeSplit.connect(bob).claimPrize(roundId)).to.changeEtherBalances(
      [bob, prizeSplit],
      [share, -share],
    );

    expect(await prizeSplit.isClaimed(roundId, alice.address)).to.equal(true);
    expect(await prizeSplit.isClaimed(roundId, bob.address)).to.equal(true);
    expect(await prizeSplit.getUnclaimedPrize(roundId)).to.equal(share);
  });

  it("blocks claims after the deadline and lets treasury reclaim unclaimed prizes", async function () {
    const rejectingAddress = await rejectingWinner.getAddress();
    const share = await fundAndFinalize([rejectingAddress, alice.address, bob.address]);

    await prizeSplit.connect(alice).claim(roundId);

    const deadline = await prizeSplit.getClaimDeadline(roundId);
    await time.increaseTo(deadline + 1n);

    await expect(prizeSplit.connect(bob).claim(roundId)).to.be.revertedWith("Claim expired");

    await expect(prizeSplit.reclaimExpiredPrizes(roundId))
      .to.emit(prizeSplit, "ExpiredPrizesReclaimed")
      .withArgs(roundId, treasury.address, share * 2n);

    expect(await prizeSplit.getUnclaimedPrize(roundId)).to.equal(0);
    expect(await prizeSplit.totalPrize()).to.equal(0);
    expect(await ethers.provider.getBalance(await prizeSplit.getAddress())).to.equal(0);
  });

  it("rejects empty winner batches and duplicate winners", async function () {
    await prizeSplit.fundRound({ value: prizePool });
    await expect(prizeSplit.finalizeRound(roundId, [])).to.be.revertedWith("No winners");

    await expect(
      prizeSplit.finalizeRound(roundId, [alice.address, alice.address]),
    ).to.be.revertedWith("Duplicate winner");
  });
});
