const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("RandomLottery security hardening", function () {
  async function deployLottery(ticketPrice = 1n) {
    const [owner, player1, player2, player3] = await ethers.getSigners();
    const RandomLottery = await ethers.getContractFactory("RandomLottery");
    const lottery = await RandomLottery.deploy(ticketPrice);
    await lottery.waitForDeployment();
    return { lottery, owner, player1, player2, player3 };
  }

  async function startRound(lottery, duration = 100n) {
    await lottery.startRound(duration);
    return await lottery.roundEnd();
  }

  async function advanceTo(timestamp) {
    await ethers.provider.send("evm_setNextBlockTimestamp", [Number(timestamp)]);
    await ethers.provider.send("evm_mine");
  }

  function commitmentFor(secret) {
    return ethers.solidityPackedKeccak256(["bytes32"], [secret]);
  }

  it("uses commit-reveal randomness, requires three players, and enforces cooldown", async function () {
    const { lottery, owner, player1, player2, player3 } = await deployLottery();
    const roundEnd = await startRound(lottery);
    const secret = ethers.keccak256(ethers.toUtf8Bytes("issue-16-secret"));

    await lottery.connect(player1).buyTicket({ value: 1n });
    await lottery.connect(player2).buyTicket({ value: 1n });
    await lottery.connect(player3).buyTicket({ value: 1n });
    await lottery.connect(owner).commitRandomness(commitmentFor(secret));
    await advanceTo(roundEnd);

    await lottery.connect(owner).drawWinner(secret);
    expect(await lottery.roundWinners(1n)).to.not.equal(ethers.ZeroAddress);
    expect(await lottery.getPoolSize()).to.equal(3n);
    expect(await lottery.nextRoundAt()).to.be.gt(roundEnd);

    await expect(lottery.startRound(100n)).to.be.revertedWith("RandomLottery: draw cooldown");
    await advanceTo(await lottery.nextRoundAt());
    await lottery.startRound(100n);
  });

  it("rejects missing or invalid randomness and too few players", async function () {
    const { lottery, owner, player1, player2 } = await deployLottery();
    const roundEnd = await startRound(lottery);
    const secret = ethers.keccak256(ethers.toUtf8Bytes("issue-16-secret-2"));

    await lottery.connect(player1).buyTicket({ value: 1n });
    await lottery.connect(player2).buyTicket({ value: 1n });
    await lottery.connect(owner).commitRandomness(commitmentFor(secret));
    await advanceTo(roundEnd);

    await expect(lottery.connect(owner).drawWinner(secret)).to.be.revertedWith(
      "RandomLottery: need 3 players"
    );
  });

  it("keeps a rejecting winner's prize claimable and rescuable", async function () {
    const { lottery, owner, player1, player2 } = await deployLottery();
    const RejectingWinner = await ethers.getContractFactory("RejectingWinner");
    const rejectingWinner = await RejectingWinner.deploy();
    await rejectingWinner.waitForDeployment();
    const roundEnd = await startRound(lottery);

    await rejectingWinner.buyTicket(await lottery.getAddress(), { value: 1n });
    await lottery.connect(player1).buyTicket({ value: 1n });
    await lottery.connect(player2).buyTicket({ value: 1n });

    let secret;
    for (let i = 0; i < 100; i++) {
      const candidate = ethers.keccak256(ethers.toUtf8Bytes(`rejecting-winner-${i}`));
      const hash = ethers.solidityPackedKeccak256(["bytes32", "uint256"], [candidate, 1n]);
      if (BigInt(hash) % 3n === 0n) {
        secret = candidate;
        break;
      }
    }
    expect(secret).to.not.equal(undefined);

    await lottery.connect(owner).commitRandomness(commitmentFor(secret));
    await advanceTo(roundEnd);
    await lottery.connect(owner).drawWinner(secret);

    expect(await lottery.pendingPrizes(await rejectingWinner.getAddress())).to.equal(3n);
    const before = await ethers.provider.getBalance(player1.address);
    await lottery.connect(owner).rescuePrize(await rejectingWinner.getAddress(), player1.address);
    const after = await ethers.provider.getBalance(player1.address);
    expect(after - before).to.equal(3n);
    expect(await lottery.pendingPrizes(await rejectingWinner.getAddress())).to.equal(0n);
  });
});
