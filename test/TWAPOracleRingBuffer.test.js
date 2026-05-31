const { expect } = require("chai");
const { ethers, network } = require("hardhat");
const fs = require("fs");
const path = require("path");
const solc = require("solc");

function compileTWAPOracle() {
  const sourcePath = path.join(__dirname, "..", "contracts", "oracle", "TWAPOracle.sol");
  const source = fs.readFileSync(sourcePath, "utf8");
  const input = {
    language: "Solidity",
    sources: {
      "TWAPOracle.sol": { content: source },
    },
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: {
        "*": {
          "*": ["abi", "evm.bytecode.object"],
        },
      },
    },
  };
  const output = JSON.parse(solc.compile(JSON.stringify(input)));
  const errors = (output.errors || []).filter((error) => error.severity === "error");
  expect(errors.map((error) => error.formattedMessage)).to.deep.equal([]);
  const contract = output.contracts["TWAPOracle.sol"].TWAPOracle;
  return {
    abi: contract.abi,
    bytecode: `0x${contract.evm.bytecode.object}`,
  };
}

describe("TWAPOracle circular observation buffer", function () {
  async function deployOracle() {
    const compiled = compileTWAPOracle();
    const TWAPOracle = new ethers.ContractFactory(compiled.abi, compiled.bytecode, (await ethers.getSigners())[0]);
    const oracle = await TWAPOracle.deploy(ethers.ZeroAddress);
    await oracle.waitForDeployment();
    return oracle;
  }

  async function recordAt(oracle, timestamp, price) {
    await network.provider.send("evm_setNextBlockTimestamp", [timestamp]);
    await oracle.recordObservation(price);
  }

  it("caps observations at 480 and exposes them in chronological order after wrap", async function () {
    const oracle = await deployOracle();
    const max = await oracle.MAX_OBSERVATIONS();
    const start = (await ethers.provider.getBlock("latest")).timestamp + 10;

    for (let i = 0; i < Number(max) + 2; i++) {
      await recordAt(oracle, start + i, ethers.parseEther(String(100 + i)));
    }

    expect(await oracle.getObservationCount()).to.equal(max);
    expect(await oracle.observationHead()).to.equal(2n);

    const oldest = await oracle.getObservationAt(0);
    const newest = await oracle.getObservationAt(Number(max) - 1);

    expect(oldest.timestamp).to.equal(BigInt(start + 2));
    expect(oldest.spotPrice).to.equal(ethers.parseEther("102"));
    expect(newest.timestamp).to.equal(BigInt(start + Number(max) + 1));
    expect(newest.spotPrice).to.equal(ethers.parseEther("581"));
    expect(await oracle.getLatestPrice()).to.equal(ethers.parseEther("581"));
  });

  it("computes TWAP across a rotated buffer without scanning unbounded history", async function () {
    const oracle = await deployOracle();
    const max = Number(await oracle.MAX_OBSERVATIONS());
    const start = (await ethers.provider.getBlock("latest")).timestamp + 10;
    const price = ethers.parseEther("100");

    await oracle.setWindowSize(max - 1);

    for (let i = 0; i < max + 2; i++) {
      await recordAt(oracle, start + i, price);
    }

    expect(await oracle.getObservationCount()).to.equal(BigInt(max));
    expect(await oracle.getTWAP()).to.equal(price);
  });

  it("uses binary search over the logical ring order for partial windows", async function () {
    const oracle = await deployOracle();
    const max = Number(await oracle.MAX_OBSERVATIONS());
    const start = (await ethers.provider.getBlock("latest")).timestamp + 10;

    await oracle.setWindowSize(20);

    for (let i = 0; i < max + 2; i++) {
      const price = i < max - 19 ? ethers.parseEther("10") : ethers.parseEther("20");
      await recordAt(oracle, start + i, price);
    }

    expect(await oracle.getTWAP()).to.equal(ethers.parseEther("20"));
  });
});
