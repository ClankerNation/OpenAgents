const { expect } = require("chai");
const { ethers, network } = require("hardhat");

describe("PrizeSplit issue #189", function () {
  const NINETY_DAYS = 90 * 24 * 60 * 60;
  const ROUND_ID = 1;

  let admin;
  let eoaWinner;
  let altRecipient;
  let otherWinner;
  let prizeSplit;
  let nonPayableWinner;

  beforeEach(async function () {
    [admin, eoaWinner, altRecipient, otherWinner] = await ethers.getSigners();

    const PrizeSplit = await ethers.getContractFactory("PrizeSplit");
    prizeSplit = await PrizeSplit.deploy();
    await prizeSplit.waitForDeployment();

    const NonPayableWinner = await ethers.getContractFactory("NonPayableWinner");
    nonPayableWinner = await NonPayableWinner.deploy();
    await nonPayableWinner.waitForDeployment();
  });

  async function setupRoundWithTwoWinners() {
    const prizePool = ethers.parseEther("1");
    const nonPayableWinnerAddress = await nonPayableWinner.getAddress();
    await prizeSplit.fundRound({ value: prizePool });
    await prizeSplit.finalizeRound(ROUND_ID, [nonPayableWinnerAddress, eoaWinner.address]);
    return { prizePool, share: prizePool / 2n };
  }

  it("allows a non-payable contract winner to claim to an alternate recipient", async function () {
    const { share } = await setupRoundWithTwoWinners();

    await prizeSplit.connect(eoaWinner).claimPrize(ROUND_ID);
    expect(await prizeSplit.isClaimed(ROUND_ID, eoaWinner.address)).to.equal(true);

    const before = await ethers.provider.getBalance(altRecipient.address);
    await nonPayableWinner.claimTo(await prizeSplit.getAddress(), ROUND_ID, altRecipient.address);
    const after = await ethers.provider.getBalance(altRecipient.address);

    expect(after - before).to.equal(share);
    expect(await prizeSplit.isClaimed(ROUND_ID, await nonPayableWinner.getAddress())).to.equal(true);
  });

  it("enforces a 90-day claim deadline", async function () {
    await setupRoundWithTwoWinners();

    await network.provider.send("evm_increaseTime", [NINETY_DAYS + 1]);
    await network.provider.send("evm_mine");

    await expect(prizeSplit.connect(eoaWinner).claimPrize(ROUND_ID)).to.be.revertedWith(
      "Claim period over"
    );
  });

  it("allows treasury reclaim of unclaimed prizes after the deadline", async function () {
    const prizePool = ethers.parseEther("3");
    await prizeSplit.fundRound({ value: prizePool });
    await prizeSplit.finalizeRound(ROUND_ID, [eoaWinner.address, otherWinner.address]);

    const share = prizePool / 2n;
    await prizeSplit.connect(eoaWinner).claimPrize(ROUND_ID);

    await network.provider.send("evm_increaseTime", [NINETY_DAYS + 1]);
    await network.provider.send("evm_mine");

    const before = await ethers.provider.getBalance(admin.address);
    const tx = await prizeSplit.reclaimUnclaimed(ROUND_ID);
    const receipt = await tx.wait();
    const gas = receipt.gasUsed * receipt.gasPrice;
    const after = await ethers.provider.getBalance(admin.address);

    expect(after + gas - before).to.equal(share);
    expect(await ethers.provider.getBalance(await prizeSplit.getAddress())).to.equal(0);
  });
});
