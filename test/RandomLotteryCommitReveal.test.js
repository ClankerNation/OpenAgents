const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("RandomLottery commit-reveal", function () {
  const ticketPrice = ethers.parseEther("1");
  const duration = 60;
  const cooldown = 60 * 60;
  const abiCoder = ethers.AbiCoder.defaultAbiCoder();

  let owner, player1, player2, player3, payoutRecipient;
  let lottery, lotteryAddress;

  function entropyFor(seed) {
    return ethers.zeroPadValue(ethers.toBeHex(seed), 32);
  }

  function commitmentFor(entropy) {
    return ethers.solidityPackedKeccak256(["bytes32"], [entropy]);
  }

  function winningIndex(entropy, round, contractAddress, playerCount) {
    const encoded = abiCoder.encode(
      ["bytes32", "uint256", "address", "uint256"],
      [entropy, round, contractAddress, playerCount],
    );
    return Number(BigInt(ethers.keccak256(encoded)) % BigInt(playerCount));
  }

  function findEntropyForWinner(targetIndex, round, contractAddress, playerCount) {
    for (let seed = 1; seed < 10000; seed++) {
      const entropy = entropyFor(seed);
      if (winningIndex(entropy, round, contractAddress, playerCount) === targetIndex) {
        return entropy;
      }
    }
    throw new Error("no entropy found");
  }

  async function deployLottery() {
    const RandomLottery = await ethers.getContractFactory("RandomLottery");
    lottery = await RandomLottery.deploy(ticketPrice);
    await lottery.waitForDeployment();
    lotteryAddress = await lottery.getAddress();
  }

  async function startRound(entropy) {
    await lottery.connect(owner).startRound(duration, commitmentFor(entropy));
  }

  async function endRoundAndCooldown() {
    await ethers.provider.send("evm_increaseTime", [duration + cooldown]);
    await ethers.provider.send("evm_mine");
  }

  beforeEach(async function () {
    [owner, player1, player2, player3, payoutRecipient] = await ethers.getSigners();
    await deployLottery();
  });

  it("draws from committed entropy and lets the winner claim with pull payments", async function () {
    const entropy = entropyFor(42);
    await startRound(entropy);

    const players = [player1, player2, player3];
    for (const player of players) {
      await lottery.connect(player).buyTicket({ value: ticketPrice });
    }

    await endRoundAndCooldown();

    const winner = players[winningIndex(entropy, 1, lotteryAddress, players.length)];
    const prize = ticketPrice * 3n;

    await expect(lottery.connect(owner).drawWinner(entropy))
      .to.emit(lottery, "WinnerSelected")
      .withArgs(winner.address, prize, 1);

    expect(await lottery.roundWinners(1)).to.equal(winner.address);
    expect(await lottery.pendingPrizes(winner.address)).to.equal(prize);
    expect(await lottery.getPoolSize()).to.equal(0);

    await expect(lottery.connect(winner).claimPrize())
      .to.emit(lottery, "PrizeClaimed")
      .withArgs(winner.address, winner.address, prize);
  });

  it("rejects bad reveals and enforces the draw cooldown", async function () {
    const entropy = entropyFor(10);
    await startRound(entropy);

    for (const player of [player1, player2, player3]) {
      await lottery.connect(player).buyTicket({ value: ticketPrice });
    }

    await ethers.provider.send("evm_increaseTime", [duration]);
    await ethers.provider.send("evm_mine");

    await expect(lottery.connect(owner).drawWinner(entropy)).to.be.revertedWith("Cooldown active");

    await ethers.provider.send("evm_increaseTime", [cooldown]);
    await ethers.provider.send("evm_mine");

    await expect(lottery.connect(owner).drawWinner(entropyFor(11))).to.be.revertedWith("Bad reveal");
  });

  it("enforces a minimum participant count and allows refunds for underfilled rounds", async function () {
    const entropy = entropyFor(20);
    await startRound(entropy);

    await lottery.connect(player1).buyTicket({ value: ticketPrice });
    await lottery.connect(player2).buyTicket({ value: ticketPrice });
    await endRoundAndCooldown();

    await expect(lottery.connect(owner).drawWinner(entropy)).to.be.revertedWith("Not enough players");

    await expect(lottery.connect(owner).cancelRound())
      .to.emit(lottery, "RoundCancelled")
      .withArgs(1, 2);

    expect(await lottery.pendingPrizes(player1.address)).to.equal(ticketPrice);
    expect(await lottery.pendingPrizes(player2.address)).to.equal(ticketPrice);
    expect(await lottery.getPoolSize()).to.equal(0);
  });

  it("does not revert the draw when the winning participant rejects ETH", async function () {
    const RejectEtherLotteryPlayer = await ethers.getContractFactory("RejectEtherLotteryPlayer");
    const rejectingPlayer = await RejectEtherLotteryPlayer.deploy();
    await rejectingPlayer.waitForDeployment();
    const rejectingPlayerAddress = await rejectingPlayer.getAddress();

    const entropy = findEntropyForWinner(0, 1, lotteryAddress, 3);
    await startRound(entropy);

    await rejectingPlayer.buyTicket(lotteryAddress, { value: ticketPrice });
    await lottery.connect(player2).buyTicket({ value: ticketPrice });
    await lottery.connect(player3).buyTicket({ value: ticketPrice });
    await endRoundAndCooldown();

    const prize = ticketPrice * 3n;

    await expect(lottery.connect(owner).drawWinner(entropy))
      .to.emit(lottery, "WinnerSelected")
      .withArgs(rejectingPlayerAddress, prize, 1);

    expect(await lottery.pendingPrizes(rejectingPlayerAddress)).to.equal(prize);

    await expect(rejectingPlayer.claimPrizeTo(lotteryAddress, payoutRecipient.address))
      .to.emit(lottery, "PrizeClaimed")
      .withArgs(rejectingPlayerAddress, payoutRecipient.address, prize);
  });
});
