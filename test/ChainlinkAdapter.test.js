const { expect } = require("chai");
const { ethers } = require("hardhat");

// Mock Aggregator for testing
const MOCK_ABI = [
  "function latestRoundData() external view returns (uint80, int256, uint256, uint256, uint80)",
  "function decimals() external view returns (uint8)"
];

describe("ChainlinkAdapter", function () {
  let adapter;
  let mockFeed1; // base/USD feed (e.g., ETH)
  let mockFeed2; // quote/USD feed (e.g., BTC)
  let mockFeed3; // feed with different decimals

  beforeEach(async function () {
    const Adapter = await ethers.getContractFactory("ChainlinkAdapter");
    adapter = await Adapter.deploy();
    await adapter.deployed();

    // Deploy mock feeds
    const MockFeed = await ethers.getContractFactory("MockAggregator");
    mockFeed1 = await MockFeed.deploy(8); // ETH/USD with 8 decimals
    await mockFeed1.deployed();

    mockFeed2 = await MockFeed.deploy(8); // BTC/USD with 8 decimals
    await mockFeed2.deployed();

    mockFeed3 = await MockFeed.deploy(18); // Some token with 18 decimals
    await mockFeed3.deployed();

    // Register feeds
    await adapter.registerFeed(ethers.constants.AddressZero, mockFeed1.address, 3600);
    await adapter.registerFeed("0x0000000000000000000000000000000000000001", mockFeed2.address, 3600);
    await adapter.registerFeed("0x0000000000000000000000000000000000000002", mockFeed3.address, 3600);
  });

  describe("getPrice", function () {
    it("should return normalized price for 8-decimal feed", async function () {
      await mockFeed1.setLatestRoundData(100000000, 250000000000, 0); // $2500 with 8 decimals
      const price = await adapter.getPrice(ethers.constants.AddressZero);
      expect(price).to.equal(ethers.utils.parseUnits("2500", 18));
    });

    it("should return normalized price for 18-decimal feed", async function () {
      await mockFeed3.setLatestRoundData(1, ethers.utils.parseUnits("1.5", 18), 0);
      const price = await adapter.getPrice("0x0000000000000000000000000000000000000002");
      expect(price).to.equal(ethers.utils.parseUnits("1.5", 18));
    });

    it("should revert when feed not active", async function () {
      await expect(adapter.getPrice("0x0000000000000000000000000000000000000999"))
        .to.be.revertedWith("Feed not active");
    });

    it("should revert when round incomplete", async function () {
      await mockFeed1.setLatestRoundData(100, 250000000000, 0, 0, 99); // answeredInRound != roundId
      await expect(adapter.getPrice(ethers.constants.AddressZero))
        .to.be.revertedWith("Round incomplete");
    });

    it("should revert when feed stale", async function () {
      const oldTimestamp = (await ethers.provider.getBlock()).timestamp - 4000;
      await mockFeed1.setLatestRoundData(100, 250000000000, 0, oldTimestamp, 100);
      await expect(adapter.getPrice(ethers.constants.AddressZero))
        .to.be.revertedWith("Feed stale");
    });

    it("should revert on negative price", async function () {
      await mockFeed1.setLatestRoundData(100, -100, 0, (await ethers.provider.getBlock()).timestamp, 100);
      await expect(adapter.getPrice(ethers.constants.AddressZero))
        .to.be.revertedWith("Negative price");
    });
  });

  describe("derivedPrice", function () {
    it("should correctly derive TOKEN/ETH using cross-rates", async function () {
      // ETH/USD = $2500 (8 decimals)
      await mockFeed1.setLatestRoundData(1, 250000000000, 0, (await ethers.provider.getBlock()).timestamp, 1);
      // BTC/USD = $50000 (8 decimals)
      await mockFeed2.setLatestRoundData(1, 5000000000000, 0, (await ethers.provider.getBlock()).timestamp, 1);

      const btcEthPrice = await adapter.derivedPrice(
        "0x0000000000000000000000000000000000000001", // BTC
        ethers.constants.AddressZero // ETH
      );

      // BTC/ETH = (BTC/USD) / (ETH/USD) = 50000 / 2500 = 20
      expect(btcEthPrice).to.equal(ethers.utils.parseUnits("20", 18));
    });

    it("should handle decimal mismatch between feeds", async function () {
      // Set up feeds with different decimals
      await mockFeed1.setLatestRoundData(1, 250000000000, 0, (await ethers.provider.getBlock()).timestamp, 1);
      await mockFeed3.setLatestRoundData(1, ethers.utils.parseUnits("1.5", 18), 0, (await ethers.provider.getBlock()).timestamp, 1);

      const price = await adapter.derivedPrice(
        "0x0000000000000000000000000000000000000002", // 18-decimal token
        ethers.constants.AddressZero // 8-decimal feed (ETH)
      );

      // Price should be normalized to 18 decimals
      expect(price).to.be.gt(0);
    });

    it("should revert when base feed is stale", async function () {
      const oldTimestamp = (await ethers.provider.getBlock()).timestamp - 4000;
      await mockFeed1.setLatestRoundData(1, 250000000000, 0, oldTimestamp, 1);
      await mockFeed2.setLatestRoundData(1, 5000000000000, 0, (await ethers.provider.getBlock()).timestamp, 1);

      await expect(adapter.derivedPrice(
        ethers.constants.AddressZero,
        "0x0000000000000000000000000000000000000001"
      )).to.be.revertedWith("Base feed stale");
    });

    it("should revert when quote feed is stale", async function () {
      const oldTimestamp = (await ethers.provider.getBlock()).timestamp - 4000;
      await mockFeed1.setLatestRoundData(1, 250000000000, 0, (await ethers.provider.getBlock()).timestamp, 1);
      await mockFeed2.setLatestRoundData(1, 5000000000000, 0, oldTimestamp, 1);

      await expect(adapter.derivedPrice(
        "0x0000000000000000000000000000000000000001",
        ethers.constants.AddressZero
      )).to.be.revertedWith("Quote feed stale");
    });

    it("should revert when base round incomplete", async function () {
      await mockFeed1.setLatestRoundData(100, 250000000000, 0, (await ethers.provider.getBlock()).timestamp, 99);
      await mockFeed2.setLatestRoundData(1, 5000000000000, 0, (await ethers.provider.getBlock()).timestamp, 1);

      await expect(adapter.derivedPrice(
        ethers.constants.AddressZero,
        "0x0000000000000000000000000000000000000001"
      )).to.be.revertedWith("Base round incomplete");
    });

    it("should revert when same token provided", async function () {
      await expect(adapter.derivedPrice(ethers.constants.AddressZero, ethers.constants.AddressZero))
        .to.be.revertedWith("Same token");
    });

    it("should revert when base feed not active", async function () {
      await expect(adapter.derivedPrice(
        "0x0000000000000000000000000000000000000999",
        ethers.constants.AddressZero
      )).to.be.revertedWith("Feed not active");
    });

    it("should revert when quote feed not active", async function () {
      await expect(adapter.derivedPrice(
        ethers.constants.AddressZero,
        "0x0000000000000000000000000000000000000999"
      )).to.be.revertedWith("Feed not active");
    });
  });
});