const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("ChainlinkAdapter - derivedPrice", function () {
  let adapter;
  let mockBaseFeed, mockQuoteFeed;
  let baseToken, quoteToken;
  let owner;
  const TARGET_DECIMALS = 10n ** 18n;
  const HEARTBEAT = 86400n;
  const NOW = Math.floor(Date.now() / 1000);

  before(async function () {
    [owner] = await ethers.getSigners();

    const MockAggregator = await ethers.getContractFactory("MockAggregator");
    mockBaseFeed = await MockAggregator.deploy();
    mockQuoteFeed = await MockAggregator.deploy();

    const ChainlinkAdapter = await ethers.getContractFactory("ChainlinkAdapter");
    adapter = await ChainlinkAdapter.deploy();

    baseToken = ethers.Wallet.createRandom().address;
    quoteToken = ethers.Wallet.createRandom().address;

    await adapter.registerFeed(baseToken, mockBaseFeed.target, HEARTBEAT);
    await adapter.registerFeed(quoteToken, mockQuoteFeed.target, HEARTBEAT);
  });

  describe("derived price", function () {
    it("computes cross-rate from two 8-decimal feeds", async function () {
      await mockBaseFeed.setDecimals(8);
      await mockQuoteFeed.setDecimals(8);
      // ETH/USD: $3000  => 3000 * 10^8
      // BTC/USD: $60000 => 60000 * 10^8
      // ETH/BTC = 3000/60000 = 0.05 => 5e16
      await mockBaseFeed.setRoundData(1, 3000_00000000, NOW, 1);
      await mockQuoteFeed.setRoundData(1, 60000_00000000, NOW, 1);

      const result = await adapter.derivedPrice(baseToken, quoteToken);
      expect(result).to.equal(50000000000000000n);
    });

    it("computes cross-rate when base price > quote price", async function () {
      await mockBaseFeed.setDecimals(8);
      await mockQuoteFeed.setDecimals(8);
      // BTC/USD: $60000
      // ETH/USD: $3000
      // BTC/ETH = 60000/3000 = 20 => 20e18
      await mockBaseFeed.setRoundData(2, 60000_00000000, NOW, 2);
      await mockQuoteFeed.setRoundData(2, 3000_00000000, NOW, 2);

      const result = await adapter.derivedPrice(baseToken, quoteToken);
      expect(result).to.equal(20000000000000000000n);
    });
  });

  describe("decimal mismatch", function () {
    it("normalizes base 8 dec, quote 18 dec", async function () {
      await mockBaseFeed.setDecimals(8);
      await mockQuoteFeed.setDecimals(18);
      await mockBaseFeed.setRoundData(3, 3000_00000000, NOW, 3);
      await mockQuoteFeed.setRoundData(3, 60000n * TARGET_DECIMALS, NOW, 3);

      const result = await adapter.derivedPrice(baseToken, quoteToken);
      expect(result).to.equal(50000000000000000n);
    });

    it("normalizes base 18 dec, quote 8 dec", async function () {
      await mockBaseFeed.setDecimals(18);
      await mockQuoteFeed.setDecimals(8);
      await mockBaseFeed.setRoundData(4, 3000n * TARGET_DECIMALS, NOW, 4);
      await mockQuoteFeed.setRoundData(4, 60000_00000000, NOW, 4);

      const result = await adapter.derivedPrice(baseToken, quoteToken);
      expect(result).to.equal(50000000000000000n);
    });

    it("handles both feeds at 18 decimals", async function () {
      await mockBaseFeed.setDecimals(18);
      await mockQuoteFeed.setDecimals(18);
      await mockBaseFeed.setRoundData(5, 3000n * TARGET_DECIMALS, NOW, 5);
      await mockQuoteFeed.setRoundData(5, 60000n * TARGET_DECIMALS, NOW, 5);

      const result = await adapter.derivedPrice(baseToken, quoteToken);
      expect(result).to.equal(50000000000000000n);
    });
  });

  describe("direct feed fallback", function () {
    it("returns 1e18 when base == quote", async function () {
      const result = await adapter.derivedPrice(baseToken, baseToken);
      expect(result).to.equal(TARGET_DECIMALS);
    });

    it("returns 1e18 for quote paired with itself", async function () {
      const result = await adapter.derivedPrice(quoteToken, quoteToken);
      expect(result).to.equal(TARGET_DECIMALS);
    });

    it("works for unregistered tokens (identity pair)", async function () {
      const randomAddr = ethers.Wallet.createRandom().address;
      const result = await adapter.derivedPrice(randomAddr, randomAddr);
      expect(result).to.equal(TARGET_DECIMALS);
    });
  });

  describe("component stale", function () {
    it("reverts when base roundId != answeredInRound", async function () {
      await mockBaseFeed.setDecimals(8);
      await mockQuoteFeed.setDecimals(8);
      await mockBaseFeed.setRoundData(6, 3000_00000000, NOW, 5); // mismatch
      await mockQuoteFeed.setRoundData(6, 60000_00000000, NOW, 6);

      await expect(
        adapter.derivedPrice(baseToken, quoteToken)
      ).to.be.revertedWith("Base round stale");
    });

    it("reverts when quote roundId != answeredInRound", async function () {
      await mockBaseFeed.setRoundData(7, 3000_00000000, NOW, 7);
      await mockQuoteFeed.setRoundData(8, 60000_00000000, NOW, 7); // mismatch

      await expect(
        adapter.derivedPrice(baseToken, quoteToken)
      ).to.be.revertedWith("Quote round stale");
    });

    it("reverts when base has negative price", async function () {
      await mockBaseFeed.setRoundData(8, -1, NOW, 8);
      await mockQuoteFeed.setRoundData(8, 60000_00000000, NOW, 8);

      await expect(
        adapter.derivedPrice(baseToken, quoteToken)
      ).to.be.revertedWith("Invalid base price");
    });

    it("reverts when quote has negative price", async function () {
      await mockBaseFeed.setRoundData(9, 3000_00000000, NOW, 9);
      await mockQuoteFeed.setRoundData(9, -1, NOW, 9);

      await expect(
        adapter.derivedPrice(baseToken, quoteToken)
      ).to.be.revertedWith("Invalid quote price");
    });

    it("reverts when base updatedAt exceeds heartbeat", async function () {
      const staleTimestamp = NOW - Number(HEARTBEAT) - 1;
      await mockBaseFeed.setRoundData(10, 3000_00000000, staleTimestamp, 10);
      await mockQuoteFeed.setRoundData(10, 60000_00000000, NOW, 10);

      await expect(
        adapter.derivedPrice(baseToken, quoteToken)
      ).to.be.revertedWith("Base price stale");
    });

    it("reverts when quote updatedAt exceeds heartbeat", async function () {
      const staleTimestamp = NOW - Number(HEARTBEAT) - 1;
      await mockBaseFeed.setRoundData(11, 3000_00000000, NOW, 11);
      await mockQuoteFeed.setRoundData(11, 60000_00000000, staleTimestamp, 11);

      await expect(
        adapter.derivedPrice(baseToken, quoteToken)
      ).to.be.revertedWith("Quote price stale");
    });
  });

  describe("feed deactivation", function () {
    let deactAdapter;
    let deactMockBase, deactMockQuote;
    let deactBase, deactQuote;

    before(async function () {
      const MockAggregator = await ethers.getContractFactory("MockAggregator");
      deactMockBase = await MockAggregator.deploy();
      deactMockQuote = await MockAggregator.deploy();

      const ChainlinkAdapter = await ethers.getContractFactory("ChainlinkAdapter");
      deactAdapter = await ChainlinkAdapter.deploy();

      deactBase = ethers.Wallet.createRandom().address;
      deactQuote = ethers.Wallet.createRandom().address;

      await deactAdapter.registerFeed(deactBase, deactMockBase.target, HEARTBEAT);
      await deactAdapter.registerFeed(deactQuote, deactMockQuote.target, HEARTBEAT);
    });

    it("reverts when base feed is deactivated", async function () {
      await deactAdapter.deactivateFeed(deactBase);

      await expect(
        deactAdapter.derivedPrice(deactBase, deactQuote)
      ).to.be.revertedWith("Base feed not active");
    });

    it("reverts when quote feed is deactivated", async function () {
      // base is already deactivated; use a fresh adapter scenario
      await deactAdapter.deactivateFeed(deactQuote);

      // Both feeds now inactive, but base is checked first
      await expect(
        deactAdapter.derivedPrice(deactBase, deactQuote)
      ).to.be.revertedWith("Base feed not active");
    });
  });
});
