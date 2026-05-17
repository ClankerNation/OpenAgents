const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("PrizeSplit", function () {
  let prizeSplit;
  let admin, winner1, winner2, winner3, treasury;

  beforeEach(async function () {
    [admin, winner1, winner2, winner3, treasury] = await ethers.getSigners();

    const PrizeSplit = await ethers.getContractFactory("PrizeSplit");
    prizeSplit = await PrizeSplit.deploy();
    await prizeSplit.waitForDeployment();

    // Set treasury to a separate address
    await prizeSplit.setTreasury(treasury.address);
  });

  describe("Deployment", function () {
    it("should set admin as deployer", async function () {
      expect(await prizeSplit.admin()).to.equal(admin.address);
    });

    it("should set treasury to deployer initially, then allow change", async function () {
      expect(await prizeSplit.treasury()).to.equal(treasury.address);
    });

    it("should reject zero-address treasury", async function () {
      await expect(
        prizeSplit.setTreasury(ethers.ZeroAddress)
      ).to.be.revertedWith("Zero address");
    });

    it("should reject non-admin setting treasury", async function () {
      await expect(
        prizeSplit.connect(winner1).setTreasury(winner1.address)
      ).to.be.revertedWith("Not admin");
    });
  });

  describe("Funding", function () {
    it("should allow admin to fund a round", async function () {
      const amount = ethers.parseEther("1");
      await prizeSplit.fundRound({ value: amount });

      expect(await prizeSplit.totalPrize()).to.equal(amount);
      expect(await prizeSplit.roundId()).to.equal(1);
    });

    it("should reject non-admin funding", async function () {
      await expect(
        prizeSplit.connect(winner1).fundRound({ value: ethers.parseEther("0.1") })
      ).to.be.revertedWith("Not admin");
    });
  });

  describe("Finalize Round", function () {
    beforeEach(async function () {
      await prizeSplit.fundRound({ value: ethers.parseEther("1") });
    });

    it("should finalize with winners and set deadline", async function () {
      await prizeSplit.finalizeRound(1, [winner1.address, winner2.address]);

      const share = ethers.parseEther("0.5");
      expect(await prizeSplit.getShare(1, winner1.address)).to.equal(share);
      expect(await prizeSplit.getShare(1, winner2.address)).to.equal(share);

      const deadline = await prizeSplit.getDeadline(1);
      expect(deadline).to.be.gt(0);
    });

    it("should reject zero winners", async function () {
      await expect(
        prizeSplit.finalizeRound(1, [])
      ).to.be.revertedWith("No winners");
    });

    it("should reject double finalization", async function () {
      await prizeSplit.finalizeRound(1, [winner1.address]);
      await expect(
        prizeSplit.finalizeRound(1, [winner2.address])
      ).to.be.revertedWith("Already finalized");
    });

    it("should send rounding dust to treasury", async function () {
      const balanceBefore = await ethers.provider.getBalance(treasury.address);

      await prizeSplit.finalizeRound(1, [winner1.address, winner2.address, winner3.address]);

      const balanceAfter = await ethers.provider.getBalance(treasury.address);
      expect(balanceAfter).to.be.gt(balanceBefore);
    });
  });

  describe("Claim Prize", function () {
    beforeEach(async function () {
      await prizeSplit.fundRound({ value: ethers.parseEther("1") });
      await prizeSplit.finalizeRound(1, [winner1.address, winner2.address]);
    });

    it("should allow winner to claim their share", async function () {
      const balanceBefore = await ethers.provider.getBalance(winner1.address);

      const tx = await prizeSplit.connect(winner1).claimPrize(1);
      const receipt = await tx.wait();
      const gasCost = receipt.gasUsed * receipt.gasPrice;

      const balanceAfter = await ethers.provider.getBalance(winner1.address);
      const netGain = balanceAfter - balanceBefore + gasCost;
      expect(netGain).to.equal(ethers.parseEther("0.5"));
    });

    it("should mark winner as claimed after successful claim", async function () {
      await prizeSplit.connect(winner1).claimPrize(1);
      expect(await prizeSplit.isClaimed(1, winner1.address)).to.be.true;
    });

    it("should reject double claim", async function () {
      await prizeSplit.connect(winner1).claimPrize(1);
      await expect(
        prizeSplit.connect(winner1).claimPrize(1)
      ).to.be.revertedWith("Already claimed");
    });

    it("should reject non-winner claiming", async function () {
      await expect(
        prizeSplit.connect(winner3).claimPrize(1)
      ).to.be.revertedWith("No share");
    });

    it("should reject claim for non-finalized round", async function () {
      await prizeSplit.fundRound({ value: ethers.parseEther("0.5") });
      await expect(
        prizeSplit.connect(winner1).claimPrize(2)
      ).to.be.revertedWith("Not finalized");
    });

    it("should allow one winner to claim without affecting the other", async function () {
      await prizeSplit.connect(winner1).claimPrize(1);
      expect(await prizeSplit.isClaimed(1, winner1.address)).to.be.true;
      expect(await prizeSplit.isClaimed(1, winner2.address)).to.be.false;

      await prizeSplit.connect(winner2).claimPrize(1);
      expect(await prizeSplit.isClaimed(1, winner2.address)).to.be.true;
    });
  });

  describe("Contract Winner (rejects ETH)", function () {
    let rejectingWinner;

    beforeEach(async function () {
      const RejectingWinner = await ethers.getContractFactory("RejectingWinner");
      rejectingWinner = await RejectingWinner.deploy();
      await rejectingWinner.waitForDeployment();

      await prizeSplit.fundRound({ value: ethers.parseEther("1") });
      await prizeSplit.finalizeRound(1, [rejectingWinner.target, winner2.address]);
    });

    it("should revert when a contract without receive() tries to claim", async function () {
      // The RejectingWinner contract tries to claim, but PrizeSplit's ETH
      // transfer to it reverts because it has no receive() or fallback().
      await expect(
        rejectingWinner.tryClaim(prizeSplit.target, 1)
      ).to.be.reverted;
    });

    it("should allow other winner to claim despite rejecting contract", async function () {
      // Winner2 (an EOA) can still claim normally
      await prizeSplit.connect(winner2).claimPrize(1);
      expect(await prizeSplit.isClaimed(1, winner2.address)).to.be.true;
    });

    it("should allow admin to reclaim the rejecting contract's share after deadline", async function () {
      // Winner2 claims normally
      await prizeSplit.connect(winner2).claimPrize(1);

      // Advance past deadline
      const deadline = await prizeSplit.getDeadline(1);
      await ethers.provider.send("evm_setNextBlockTimestamp", [Number(deadline) + 1]);
      await ethers.provider.send("evm_mine");

      const treasuryBefore = await ethers.provider.getBalance(treasury.address);
      await prizeSplit.reclaimUnclaimed(1);
      const treasuryAfter = await ethers.provider.getBalance(treasury.address);

      // The rejecting contract's 0.5 ETH share goes to treasury
      const reclaimed = treasuryAfter - treasuryBefore;
      expect(reclaimed).to.equal(ethers.parseEther("0.5"));
    });
  });

  describe("Claim Deadline", function () {
    beforeEach(async function () {
      await prizeSplit.fundRound({ value: ethers.parseEther("1") });
      await prizeSplit.finalizeRound(1, [winner1.address, winner2.address]);
    });

    it("should reject claim after deadline", async function () {
      const deadline = await prizeSplit.getDeadline(1);

      await ethers.provider.send("evm_setNextBlockTimestamp", [Number(deadline) + 1]);
      await ethers.provider.send("evm_mine");

      await expect(
        prizeSplit.connect(winner1).claimPrize(1)
      ).to.be.revertedWith("Claim deadline passed");
    });

    it("should allow claim before deadline", async function () {
      const deadline = await prizeSplit.getDeadline(1);

      await ethers.provider.send("evm_setNextBlockTimestamp", [Number(deadline) - 1]);
      await ethers.provider.send("evm_mine");

      await prizeSplit.connect(winner1).claimPrize(1);
      expect(await prizeSplit.isClaimed(1, winner1.address)).to.be.true;
    });
  });

  describe("Reclaim Unclaimed", function () {
    beforeEach(async function () {
      await prizeSplit.fundRound({ value: ethers.parseEther("1") });
      await prizeSplit.finalizeRound(1, [winner1.address, winner2.address]);
    });

    it("should allow admin to reclaim unclaimed prizes after deadline", async function () {
      await prizeSplit.connect(winner1).claimPrize(1);

      const deadline = await prizeSplit.getDeadline(1);
      await ethers.provider.send("evm_setNextBlockTimestamp", [Number(deadline) + 1]);
      await ethers.provider.send("evm_mine");

      const treasuryBalanceBefore = await ethers.provider.getBalance(treasury.address);

      await prizeSplit.reclaimUnclaimed(1);

      const treasuryBalanceAfter = await ethers.provider.getBalance(treasury.address);
      expect(treasuryBalanceAfter - treasuryBalanceBefore).to.equal(ethers.parseEther("0.5"));
    });

    it("should reject reclaim before deadline", async function () {
      await expect(
        prizeSplit.reclaimUnclaimed(1)
      ).to.be.revertedWith("Deadline not passed");
    });

    it("should reject reclaim with no unclaimed prizes", async function () {
      await prizeSplit.connect(winner1).claimPrize(1);
      await prizeSplit.connect(winner2).claimPrize(1);

      const deadline = await prizeSplit.getDeadline(1);
      await ethers.provider.send("evm_setNextBlockTimestamp", [Number(deadline) + 1]);
      await ethers.provider.send("evm_mine");

      await expect(
        prizeSplit.reclaimUnclaimed(1)
      ).to.be.revertedWith("No unclaimed prizes");
    });

    it("should reject non-admin reclaim", async function () {
      const deadline = await prizeSplit.getDeadline(1);
      await ethers.provider.send("evm_setNextBlockTimestamp", [Number(deadline) + 1]);
      await ethers.provider.send("evm_mine");

      await expect(
        prizeSplit.connect(winner1).reclaimUnclaimed(1)
      ).to.be.revertedWith("Not admin");
    });

    it("should not double-count unclaimed prizes", async function () {
      // Only winner1 claims
      await prizeSplit.connect(winner1).claimPrize(1);

      const deadline = await prizeSplit.getDeadline(1);
      await ethers.provider.send("evm_setNextBlockTimestamp", [Number(deadline) + 1]);
      await ethers.provider.send("evm_mine");

      // First reclaim — should succeed
      await prizeSplit.reclaimUnclaimed(1);

      // Second reclaim — should fail (all claimed now)
      await expect(
        prizeSplit.reclaimUnclaimed(1)
      ).to.be.revertedWith("No unclaimed prizes");
    });
  });
});
