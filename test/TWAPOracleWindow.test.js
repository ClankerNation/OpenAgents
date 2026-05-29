const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const solc = require("solc");

function compileTWAPOracle() {
  const source = fs.readFileSync("contracts/oracle/TWAPOracle.sol", "utf8");
  const input = {
    language: "Solidity",
    sources: { "TWAPOracle.sol": { content: source } },
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: { "*": { "*": ["abi", "evm.bytecode"] } },
    },
  };
  const output = JSON.parse(solc.compile(JSON.stringify(input)));
  const errors = output.errors || [];
  const fatal = errors.filter((error) => error.severity === "error");
  if (fatal.length > 0) {
    throw new Error(fatal.map((error) => error.formattedMessage).join("\n"));
  }
  return output.contracts["TWAPOracle.sol"].TWAPOracle;
}

async function deployTWAPOracle() {
  const [owner] = await ethers.getSigners();
  const compiled = compileTWAPOracle();
  const factory = new ethers.ContractFactory(compiled.abi, compiled.evm.bytecode.object, owner);
  const oracle = await factory.deploy(owner.address);
  await oracle.waitForDeployment();
  return oracle;
}

describe("TWAPOracle window hardening", function () {
  it("enforces a 30 minute minimum window", async function () {
    const oracle = await deployTWAPOracle();

    await expect(oracle.setWindowSize(60)).to.be.revertedWith("Window too short");
    await oracle.setWindowSize(30 * 60);

    expect(await oracle.windowSize()).to.equal(30n * 60n);
    expect(await oracle.MIN_WINDOW_SIZE()).to.equal(30n * 60n);
  });

  it("rejects multiple observations mined in the same block", async function () {
    const oracle = await deployTWAPOracle();

    try {
      await ethers.provider.send("evm_setAutomine", [false]);
      const first = await oracle.recordObservation(100);
      const second = await oracle.recordObservation(200);
      await ethers.provider.send("evm_mine", []);

      await first.wait();
      await second.wait().then(
        () => {
          throw new Error("second same-block observation did not revert");
        },
        (error) => {
          expect(error.message).to.include("transaction execution reverted");
        },
      );
    } finally {
      await ethers.provider.send("evm_setAutomine", [true]);
    }
    expect(await oracle.getObservationCount()).to.equal(1n);
  });

  it("computes TWAP from cumulative prices after the full window", async function () {
    const oracle = await deployTWAPOracle();

    await oracle.recordObservation(100);
    await ethers.provider.send("evm_increaseTime", [30 * 60]);
    await oracle.recordObservation(200);

    expect(await oracle.getTWAP()).to.equal(100n);
  });

  it("reverts when the latest observation is stale", async function () {
    const oracle = await deployTWAPOracle();

    await oracle.recordObservation(100);
    await ethers.provider.send("evm_increaseTime", [30 * 60]);
    await oracle.recordObservation(200);
    await ethers.provider.send("evm_increaseTime", [2 * 60 * 60 + 1]);
    await ethers.provider.send("evm_mine", []);

    await expect(oracle.getTWAP()).to.be.revertedWith("Stale price");
  });

  it("requires observations to cover the configured window", async function () {
    const oracle = await deployTWAPOracle();

    await oracle.recordObservation(100);
    await ethers.provider.send("evm_increaseTime", [10 * 60]);
    await oracle.recordObservation(200);

    await expect(oracle.getTWAP()).to.be.revertedWith("Insufficient window");
  });
});
