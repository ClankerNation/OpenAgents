const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("PrizeSplit", function () {
  let PrizeSplit;
  let prizeSplit;
  let admin;
  let winner1;
  let winner2;
  let winner3;
  let treasury;

  const PRIZE_AMOUNT = ethers.parseEther("1.0");

  beforeEach(async function () {
    [admin, winner1, winner2, winner3, treasury] = await ethers.getSigners();

    PrizeSplit = await ethers.getContractFactory("PrizeSplit");
    prizeSplit = await PrizeSplit.deploy();
    await prizeSplit.waitForDeployment();
  });

  describe("Deployment", function () {
    it("should set the admin", async function () {
      expect(await prizeSplit.admin()).to.equal(admin.address);
    });

    it("should initialize roundId to 0", async function () {
      expect(await prizeSplit.roundId()).to.equal(0n);
    });
  });

  describe("fundRound", function () {
    it("should fund a new round", async function () {
      await expect(prizeSplit.fundRound({ value: PRIZE_AMOUNT }))
        .to.emit(prizeSplit, "RoundFunded")
        .withArgs(1n, PRIZE_AMOUNT);

      expect(await prizeSplit.roundId()).to.equal(1n);
    });

    it("should reject non-admin funding", async function () {
      await expect(
        prizeSplit.connect(winner1).fundRound({ value: PRIZE_AMOUNT })
      ).to.be.revertedWith("Not admin");
    });
  });

  describe("finalizeRound", function () {
    beforeEach(async function () {
      await prizeSplit.fundRound({ value: PRIZE_AMOUNT });
    });

    it("should finalize a round with winners", async function () {
      await expect(
        prizeSplit.finalizeRound(1, [winner1.address, winner2.address])
      )
        .to.emit(prizeSplit, "RoundFinalized")
        .withArgs(1n, 2);

      const share1 = await prizeSplit.getShare(1, winner1.address);
      const share2 = await prizeSplit.getShare(2, winner2.address);
      expect(share1).to.equal(PRIZE_AMOUNT / 2n);
    });

    it("should reject empty winners array", async function () {
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

    it("should reject non-admin finalization", async function () {
      await expect(
        prizeSplit.connect(winner1).finalizeRound(1, [winner1.address])
      ).to.be.revertedWith("Not admin");
    });
  });

  describe("claimPrize", function () {
    beforeEach(async function () {
      await prizeSplit.fundRound({ value: PRIZE_AMOUNT });
      await prizeSplit.finalizeRound(1, [winner1.address, winner2.address]);
    });

    it("should allow a winner to claim their prize", async function () {
      const share = PRIZE_AMOUNT / 2n;
      const balanceBefore = await ethers.provider.getBalance(winner1.address);

      const tx = await prizeSplit.connect(winner1).claimPrize(1);
      const receipt = await tx.wait();

      // Calculate gas cost
      const gasUsed = receipt.gasUsed * receipt.gasPrice;

      await expect(tx)
        .to.emit(prizeSplit, "PrizeClaimed")
        .withArgs(winner1.address, share, 1n);

      const balanceAfter = await ethers.provider.getBalance(winner1.address);
      expect(balanceAfter - balanceBefore + gasUsed).to.equal(share);
    });

    it("should mark a winner as claimed", async function () {
      await prizeSplit.connect(winner1).claimPrize(1);
      expect(await prizeSplit.isClaimed(1, winner1.address)).to.be.true;
    });

    it("should reject double claiming", async function () {
      await prizeSplit.connect(winner1).claimPrize(1);
      await expect(
        prizeSplit.connect(winner1).claimPrize(1)
      ).to.be.revertedWith("Already claimed");
    });

    it("should reject non-winner claim", async function () {
      await expect(
        prizeSplit.connect(winner3).claimPrize(1)
      ).to.be.revertedWith("No share");
    });

    it("should reject claim before finalization", async function () {
      await prizeSplit.fundRound({ value: PRIZE_AMOUNT });
      await expect(
        prizeSplit.connect(winner1).claimPrize(2)
      ).to.be.revertedWith("Not finalized");
    });
  });

  describe("Contract winner without receive()", function () {
    let noReceiveContract;

    beforeEach(async function () {
      // Deploy a contract that has no receive/fallback
      const NoReceive = await ethers.getContractFactory("NoReceiveContract");
      noReceiveContract = await NoReceive.deploy();

      await prizeSplit.fundRound({ value: PRIZE_AMOUNT });
      await prizeSplit.finalizeRound(1, [noReceiveContract.target, winner2.address]);
    });

    it("should not block other winners when a contract without receive fails", async function () {
      // Contract without receive should fail to claim
      await expect(
        prizeSplit.connect(noReceiveContract).claimPrize(1) // This would be called from EOA not contract
      ).to.be.reverted; // The contract can't claim since call{value} fails

      // But other winners should still be able to claim
      const share = PRIZE_AMOUNT / 2n;
      await expect(
        prizeSplit.connect(winner2).claimPrize(1)
      ).to.emit(prizeSplit, "PrizeClaimed");

      expect(await prizeSplit.isClaimed(1, winner2.address)).to.be.true;
    });

    it("should allow a contract without receive to be skipped via reclaim", async function () {
      // Claim what we can
      await prizeSplit.connect(winner2).claimPrize(1);

      // Fast forward past the 90-day deadline
      await time.increase(90 * 24 * 60 * 60);

      // Reclaim unclaimed to treasury
      await expect(
        prizeSplit.reclaimUnclaimed(1, treasury.address)
      ).to.emit(prizeSplit, "UnclaimedReclaimed");

      expect(await prizeSplit.isClaimed(1, noReceiveContract.target)).to.be.true;
    });
  });

  describe("reclaimUnclaimed", function () {
    beforeEach(async function () {
      await prizeSplit.fundRound({ value: PRIZE_AMOUNT });
      await prizeSplit.finalizeRound(1, [winner1.address, winner2.address]);
    });

    it("should reclaim unclaimed prizes after 90-day deadline", async function () {
      // Only winner1 claims
      await prizeSplit.connect(winner1).claimPrize(1);

      // Fast forward 90 days
      await time.increase(90 * 24 * 60 * 60);

      // Reclaim unclaimed prize (winner2's share) to treasury
      const share2 = PRIZE_AMOUNT / 2n;
      await expect(
        prizeSplit.reclaimUnclaimed(1, treasury.address)
      ).to.emit(prizeSplit, "UnclaimedReclaimed")
        .withArgs(1n, treasury.address, share2);
    });

    it("should reject reclaim before 90-day deadline", async function () {
      await expect(
        prizeSplit.reclaimUnclaimed(1, treasury.address)
      ).to.be.revertedWith("Claim period not expired");
    });

    it("should reject reclaim for unfinalized round", async function () {
      await prizeSplit.fundRound({ value: PRIZE_AMOUNT });
      await expect(
        prizeSplit.reclaimUnclaimed(2, treasury.address)
      ).to.be.revertedWith("Not finalized");
    });

    it("should reject reclaim with zero treasury address", async function () {
      await time.increase(90 * 24 * 60 * 60);
      await expect(
        prizeSplit.reclaimUnclaimed(1, ethers.ZeroAddress)
      ).to.be.revertedWith("Zero address");
    });

    it("should reject reclaim when all prizes claimed", async function () {
      await prizeSplit.connect(winner1).claimPrize(1);
      await prizeSplit.connect(winner2).claimPrize(1);

      await time.increase(90 * 24 * 60 * 60);
      await expect(
        prizeSplit.reclaimUnclaimed(1, treasury.address)
      ).to.be.revertedWith("No unclaimed prizes");
    });

    it("should reject non-admin reclaim", async function () {
      await time.increase(90 * 24 * 60 * 60);
      await expect(
        prizeSplit.connect(winner1).reclaimUnclaimed(1, treasury.address)
      ).to.be.revertedWith("Not admin");
    });
  });

  describe("Reentrancy protection", function () {
    it("should prevent reentrancy by setting claimed before transfer", async function () {
      // Deploy a malicious contract that tries to re-enter
      const Malicious = await ethers.getContractFactory("MaliciousClaimer");
      const malicious = await Malicious.deploy(prizeSplit.target);

      // Fund and finalize with malicious contract as winner
      const fundAmount = ethers.parseEther("2.0");
      await prizeSplit.fundRound({ value: fundAmount });
      await prizeSplit.finalizeRound(1, [malicious.target]);

      // The malicious contract tries to re-enter claimPrize
      // but claimed is set before the call, so re-entry reverts with "Already claimed"
      await expect(malicious.attack(1)).to.not.be.reverted;
      // Should have claimed exactly once
      expect(await prizeSplit.isClaimed(1, malicious.target)).to.be.true;
    });
  });
});
