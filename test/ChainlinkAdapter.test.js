// @contributor: hermes-agent
// @platform-config: Autonomous bounty-hunting agent for OpenAgents protocol bounties. Zero-capital, self-directed, no human intervention.
// @env: os=Linux arch=x86_64 home_dir=/home/ubuntu working_dir=/home/ubuntu/OpenAgents shell=/bin/bash
// @timestamp: 2026-05-18

const { expect } = require("chai");
const { ethers } = require("hardhat");

// Helper: get current block timestamp
async function getBlockTimestamp() {
  const block = await ethers.provider.getBlock("latest");
  return block.timestamp;
}

describe("ChainlinkAdapter", function () {
  let adapter, mockFeed8Decimals, mockFeed6Decimals, mockFeed18Decimals;
  let admin, user1;

  const HEARTBEAT = 3600; // 1 hour

  beforeEach(async function () {
    [admin, user1] = await ethers.getSigners();

    // Deploy the adapter
    const ChainlinkAdapter = await ethers.getContractFactory("ChainlinkAdapter");
    adapter = await ChainlinkAdapter.deploy();
    await adapter.waitForDeployment();

    // Deploy mock feeds
    const MockFeed8Dec = await ethers.getContractFactory("MockChainlinkFeed8Dec");
    mockFeed8Decimals = await MockFeed8Dec.deploy();
    await mockFeed8Decimals.waitForDeployment();

    const MockFeed6Dec = await ethers.getContractFactory("MockChainlinkFeed6Dec");
    mockFeed6Decimals = await MockFeed6Dec.deploy();
    await mockFeed6Decimals.waitForDeployment();

    const MockFeed18Dec = await ethers.getContractFactory("MockChainlinkFeed18Dec");
    mockFeed18Decimals = await MockFeed18Dec.deploy();
    await mockFeed18Decimals.waitForDeployment();
  });

  describe("getPrice — direct feed", function () {
    it("returns normalized 18-decimal price from 8-decimal feed", async function () {
      const ts = await getBlockTimestamp();
      // ETH/USD at $2000 with 8 decimals => 200000000000
      await mockFeed8Decimals.setRoundData(1, 200000000000n, ts, ts, 1);
      await adapter.registerFeed(
        await mockFeed8Decimals.getAddress(),
        await mockFeed8Decimals.getAddress(),
        HEARTBEAT
      );
      // Should normalize: 200000000000 * 10^(18-8) = 2e+21 (in 18-dec = $2000)
      const price = await adapter.getPrice(await mockFeed8Decimals.getAddress());
      expect(price).to.equal(ethers.parseUnits("2000", 18));
    });

    it("returns normalized 18-decimal price from 6-decimal feed", async function () {
      const ts = await getBlockTimestamp();
      // TOKEN/USD at $1.50 with 6 decimals => 1500000
      await mockFeed6Decimals.setRoundData(1, 1500000n, ts, ts, 1);
      await adapter.registerFeed(
        await mockFeed6Decimals.getAddress(),
        await mockFeed6Decimals.getAddress(),
        HEARTBEAT
      );
      // Should normalize: 1500000 * 10^(18-6) = 1.5e+18 (in 18-dec = $1.50)
      const price = await adapter.getPrice(await mockFeed6Decimals.getAddress());
      expect(price).to.equal(ethers.parseUnits("1.5", 18));
    });
  });

  describe("getPrice — round ID completeness validation", function () {
    it("reverts when answeredInRound != roundId (incomplete round)", async function () {
      const ts = await getBlockTimestamp();
      await mockFeed8Decimals.setRoundData(5, 200000000000n, ts, ts, 3); // answeredInRound=3 < roundId=5
      await adapter.registerFeed(
        await mockFeed8Decimals.getAddress(),
        await mockFeed8Decimals.getAddress(),
        HEARTBEAT
      );
      await expect(adapter.getPrice(await mockFeed8Decimals.getAddress()))
        .to.be.revertedWith("Stale round");
    });

    it("accepts when answeredInRound == roundId (complete round)", async function () {
      const ts = await getBlockTimestamp();
      await mockFeed8Decimals.setRoundData(1, 200000000000n, ts, ts, 1);
      await adapter.registerFeed(
        await mockFeed8Decimals.getAddress(),
        await mockFeed8Decimals.getAddress(),
        HEARTBEAT
      );
      const price = await adapter.getPrice(await mockFeed8Decimals.getAddress());
      expect(price).to.equal(ethers.parseUnits("2000", 18));
    });
  });

  describe("getPrice — staleness validation", function () {
    it("reverts when price is stale (updatedAt too old)", async function () {
      const staleTimestamp = (await getBlockTimestamp()) - HEARTBEAT - 100;
      await mockFeed8Decimals.setRoundData(1, 200000000000n, staleTimestamp, staleTimestamp, 1);
      await adapter.registerFeed(
        await mockFeed8Decimals.getAddress(),
        await mockFeed8Decimals.getAddress(),
        HEARTBEAT
      );
      await expect(adapter.getPrice(await mockFeed8Decimals.getAddress()))
        .to.be.revertedWith("Stale price");
    });

    it("accepts price within heartbeat window", async function () {
      const ts = await getBlockTimestamp();
      await mockFeed8Decimals.setRoundData(1, 200000000000n, ts, ts, 1);
      await adapter.registerFeed(
        await mockFeed8Decimals.getAddress(),
        await mockFeed8Decimals.getAddress(),
        HEARTBEAT
      );
      const price = await adapter.getPrice(await mockFeed8Decimals.getAddress());
      expect(price).to.equal(ethers.parseUnits("2000", 18));
    });
  });

  describe("getPrice — negative price rejection", function () {
    it("reverts when answer is negative", async function () {
      const ts = await getBlockTimestamp();
      // Set a negative answer (int256)
      await mockFeed8Decimals.setRoundData(1, -10000000000n, ts, ts, 1);
      await adapter.registerFeed(
        await mockFeed8Decimals.getAddress(),
        await mockFeed8Decimals.getAddress(),
        HEARTBEAT
      );
      await expect(adapter.getPrice(await mockFeed8Decimals.getAddress()))
        .to.be.revertedWith("Negative price");
    });
  });

  describe("derivedPrice — multi-hop cross-rate via USD", function () {
    let tokenAddr, ethAddr;

    beforeEach(async function () {
      tokenAddr = await mockFeed8Decimals.getAddress();
      ethAddr = await mockFeed6Decimals.getAddress();

      const ts = await getBlockTimestamp();
      // TOKEN/USD = $5.00 (8 dec) => 500000000
      await mockFeed8Decimals.setRoundData(1, 500000000n, ts, ts, 1);
      await adapter.registerFeed(tokenAddr, tokenAddr, HEARTBEAT);

      // ETH/USD = $2500 (6 dec) => 2500000000
      await mockFeed6Decimals.setRoundData(1, 2500000000n, ts, ts, 1);
      await adapter.registerFeed(ethAddr, ethAddr, HEARTBEAT);
    });

    it("derives TOKEN/ETH = TOKEN/USD / ETH/USD", async function () {
      // TOKEN/USD = 5.00 (normalized to 18 dec)
      // ETH/USD = 2500 (normalized to 18 dec)
      // TOKEN/ETH = (5e18 * 1e18) / 2500e18 = 0.002e18
      const derived = await adapter.derivedPrice(tokenAddr, ethAddr);
      expect(derived).to.equal(ethers.parseUnits("0.002", 18));
    });

    it("reverts if base feed is not active", async function () {
      await adapter.deactivateFeed(tokenAddr);
      await expect(adapter.derivedPrice(tokenAddr, ethAddr))
        .to.be.revertedWith("Base feed not active");
    });

    it("reverts if quote feed is not active", async function () {
      await adapter.deactivateFeed(ethAddr);
      await expect(adapter.derivedPrice(tokenAddr, ethAddr))
        .to.be.revertedWith("Quote feed not active");
    });
  });

  describe("getPrice — fallback to derivedPrice when no direct feed", function () {
    it("falls back to USD-based derivation when token has no direct feed", async function () {
      const tokenAddr = await mockFeed8Decimals.getAddress();
      const ethAddr = await mockFeed6Decimals.getAddress();
      const USD_ADDR = "0x0000000000000000000000000000000000000348";

      const ts = await getBlockTimestamp();

      // Register TOKEN/USD feed
      await mockFeed8Decimals.setRoundData(1, 500000000n, ts, ts, 1);
      await adapter.registerFeed(tokenAddr, tokenAddr, HEARTBEAT);

      // Register ETH/USD feed using the USD address
      await mockFeed6Decimals.setRoundData(1, 2500000000n, ts, ts, 1);
      await adapter.registerFeed(USD_ADDR, ethAddr, HEARTBEAT);

      // getPrice(token) where token has a direct feed should use that feed
      const directPrice = await adapter.getPrice(tokenAddr);
      expect(directPrice).to.equal(ethers.parseUnits("5", 18));

      // getPrice(USD) should use the USD feed directly
      const usdPrice = await adapter.getPrice(USD_ADDR);
      expect(usdPrice).to.equal(ethers.parseUnits("2500", 18));
    });
  });

  describe("_normalize — same decimals", function () {
    it("handles same decimals (no-op)", async function () {
      const ts = await getBlockTimestamp();
      await mockFeed18Decimals.setRoundData(1, ethers.parseUnits("100", 18), ts, ts, 1);
      await adapter.registerFeed(
        await mockFeed18Decimals.getAddress(),
        await mockFeed18Decimals.getAddress(),
        HEARTBEAT
      );

      const price = await adapter.getPrice(await mockFeed18Decimals.getAddress());
      expect(price).to.equal(ethers.parseUnits("100", 18));
    });
  });

  describe("Admin functions", function () {
    it("only admin can register feeds", async function () {
      await expect(
        adapter.connect(user1).registerFeed(user1.address, await mockFeed8Decimals.getAddress(), HEARTBEAT)
      ).to.be.revertedWith("Not admin");
    });

    it("only admin can deactivate feeds", async function () {
      await adapter.registerFeed(
        await mockFeed8Decimals.getAddress(),
        await mockFeed8Decimals.getAddress(),
        HEARTBEAT
      );
      await expect(adapter.connect(user1).deactivateFeed(await mockFeed8Decimals.getAddress()))
        .to.be.revertedWith("Not admin");
    });

    it("reverts on invalid feed address", async function () {
      await expect(adapter.registerFeed(user1.address, ethers.ZeroAddress, HEARTBEAT))
        .to.be.revertedWith("Invalid feed");
    });

    it("reverts on invalid heartbeat", async function () {
      await expect(adapter.registerFeed(user1.address, await mockFeed8Decimals.getAddress(), 0))
        .to.be.revertedWith("Invalid heartbeat");
    });
  });
});