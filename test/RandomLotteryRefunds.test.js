const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const solc = require("solc");

function compileLottery() {
  const sourcePath = "contracts/lottery/RandomLottery.sol";
  const input = {
    language: "Solidity",
    sources: {
      [sourcePath]: { content: fs.readFileSync(sourcePath, "utf8") },
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

  return output.contracts[sourcePath].RandomLottery;
}

async function deployLottery(ticketPrice) {
  const [owner] = await ethers.getSigners();
  const artifact = compileLottery();
  const factory = new ethers.ContractFactory(
    artifact.abi,
    `0x${artifact.evm.bytecode.object}`,
    owner
  );
  const contract = await factory.deploy(ticketPrice);
  await contract.waitForDeployment();
  return contract;
}

async function increaseTime(seconds) {
  await ethers.provider.send("evm_increaseTime", [seconds]);
  await ethers.provider.send("evm_mine");
}

describe("RandomLottery refunds", function () {
  let owner;
  let player;
  let other;
  let lottery;
  const ticketPrice = ethers.parseEther("1");

  beforeEach(async function () {
    [owner, player, other] = await ethers.getSigners();
    lottery = await deployLottery(ticketPrice);
    await lottery.startRound(60);
  });

  it("cancels after the deadline when minimum participants are not met", async function () {
    await lottery.connect(player).buyTicket({ value: ticketPrice });
    await increaseTime(61);

    await expect(lottery.cancelLottery())
      .to.emit(lottery, "LotteryCancelled")
      .withArgs(1);

    expect(await lottery.cancelled()).to.equal(true);
  });

  it("refunds each participant exactly once after cancellation", async function () {
    await lottery.connect(player).buyTicket({ value: ticketPrice });
    await increaseTime(61);
    await lottery.cancelLottery();

    await expect(lottery.connect(player).refund(1))
      .to.emit(lottery, "TicketRefunded")
      .withArgs(player.address, 1, ticketPrice);
    await expect(lottery.connect(player).refund(1))
      .to.be.revertedWith("Already refunded");
    expect(await ethers.provider.getBalance(await lottery.getAddress())).to.equal(0);
  });

  it("does not allow refunds while the round is active or completed", async function () {
    await lottery.connect(player).buyTicket({ value: ticketPrice });
    await expect(lottery.connect(player).refund(1))
      .to.be.revertedWith("Lottery not cancelled");

    await lottery.connect(other).buyTicket({ value: ticketPrice });
    await increaseTime(61);
    await lottery.drawWinner();

    await expect(lottery.connect(player).refund(1))
      .to.be.revertedWith("Lottery not cancelled");
  });
});
