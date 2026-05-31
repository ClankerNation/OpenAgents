const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");
const solc = require("solc");

const MOCK_SOURCE = `
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MockAggregator {
    uint80 public roundId = 1;
    int256 public answer = 1;
    uint256 public startedAt = 1;
    uint256 public updatedAt = 1;
    uint80 public answeredInRound = 1;
    uint8 public immutable decimalsValue;

    constructor(uint8 _decimals) {
        decimalsValue = _decimals;
    }

    function setRoundData(
        uint80 _roundId,
        int256 _answer,
        uint256 _startedAt,
        uint256 _updatedAt,
        uint80 _answeredInRound
    ) external {
        roundId = _roundId;
        answer = _answer;
        startedAt = _startedAt;
        updatedAt = _updatedAt;
        answeredInRound = _answeredInRound;
    }

    function latestRoundData() external view returns (
        uint80,
        int256,
        uint256,
        uint256,
        uint80
    ) {
        return (roundId, answer, startedAt, updatedAt, answeredInRound);
    }

    function decimals() external view returns (uint8) {
        return decimalsValue;
    }
}

contract MockFallbackOracle {
    mapping(address => uint256) public prices;

    function setPrice(address token, uint256 price) external {
        prices[token] = price;
    }

    function getPrice(address token) external view returns (uint256) {
        return prices[token];
    }
}
`;

function compileContracts() {
  const sourcePath = path.join(__dirname, "..", "contracts", "oracle", "ChainlinkAdapter.sol");
  const source = fs.readFileSync(sourcePath, "utf8");
  const input = {
    language: "Solidity",
    sources: {
      "ChainlinkAdapter.sol": { content: source },
      "MockChainlink.sol": { content: MOCK_SOURCE },
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
  return output.contracts;
}

describe("ChainlinkAdapter safety checks", function () {
  const token = "0x00000000000000000000000000000000000000AA";
  let contracts;

  before(function () {
    contracts = compileContracts();
  });

  async function deployCompiled(source, name, ...args) {
    const signer = (await ethers.getSigners())[0];
    const contract = contracts[source][name];
    const factory = new ethers.ContractFactory(
      contract.abi,
      `0x${contract.evm.bytecode.object}`,
      signer
    );
    const instance = await factory.deploy(...args);
    await instance.waitForDeployment();
    return instance;
  }

  async function deployFixture() {
    const adapter = await deployCompiled("ChainlinkAdapter.sol", "ChainlinkAdapter");
    const feed = await deployCompiled("MockChainlink.sol", "MockAggregator", 8);
    const fallback = await deployCompiled("MockChainlink.sol", "MockFallbackOracle");
    const now = (await ethers.provider.getBlock("latest")).timestamp;

    await adapter.registerFeed(token, await feed.getAddress(), 60);
    await feed.setRoundData(10, 20000000000n, now, now, 10);

    return { adapter, feed, fallback, now };
  }

  it("rejects incomplete Chainlink rounds", async function () {
    const { adapter, feed, now } = await deployFixture();

    await feed.setRoundData(10, 20000000000n, now, now, 9);

    await expect(adapter.getPrice(token)).to.be.revertedWith("Incomplete round");
  });

  it("rejects negative and zero prices before casting", async function () {
    const { adapter, feed, now } = await deployFixture();

    await feed.setRoundData(10, -1, now, now, 10);
    await expect(adapter.getPrice(token)).to.be.revertedWith("Invalid price");

    await feed.setRoundData(10, 0, now, now, 10);
    await expect(adapter.getPrice(token)).to.be.revertedWith("Invalid price");
  });

  it("uses fallback oracle when the primary feed is stale", async function () {
    const { adapter, feed, fallback, now } = await deployFixture();
    const fallbackPrice = ethers.parseEther("123");

    await fallback.setPrice(token, fallbackPrice);
    await adapter.setFallbackOracle(await fallback.getAddress());
    await feed.setRoundData(10, 20000000000n, now - 3600, now - 3600, 10);

    expect(await adapter.getPrice(token)).to.equal(fallbackPrice);
  });

  it("reverts stale primary prices when no fallback oracle is configured", async function () {
    const { adapter, feed, now } = await deployFixture();

    await feed.setRoundData(10, 20000000000n, now - 3600, now - 3600, 10);

    await expect(adapter.getPrice(token)).to.be.revertedWith("Stale price");
  });

  it("normalizes fresh Chainlink answers to 18 decimals", async function () {
    const { adapter } = await deployFixture();

    expect(await adapter.getPrice(token)).to.equal(ethers.parseEther("200"));
  });
});
