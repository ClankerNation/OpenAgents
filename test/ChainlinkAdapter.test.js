const { expect } = require("chai");
const { ethers } = require("hardhat");

const ZERO_ADDR = "0x0000000000000000000000000000000000000000";
const ADDR1 = "0x0000000000000000000000000000000000000001";
const ADDR2 = "0x0000000000000000000000000000000000000002";

describe("ChainlinkAdapter", function () {
  let adapter;
  let mockFeed1;
  let mockFeed2;
  let mockFeed3;

  beforeEach(async function () {
    const [owner] = await ethers.getSigners();

    const Adapter = await ethers.getContractFactory("ChainlinkAdapter");
    const adapterContract = await Adapter.deploy();
    adapter = await adapterContract.waitForDeployment();

    const MockFeed = await ethers.getContractFactory("MockAggregator");
    const mockFeed1Contract = await MockFeed.deploy(8);
    mockFeed1 = await mockFeed1Contract.waitForDeployment();

    const mockFeed2Contract = await MockFeed.deploy(8);
    mockFeed2 = await mockFeed2Contract.waitForDeployment();

    const mockFeed3Contract = await MockFeed.deploy(18);
    mockFeed3 = await mockFeed3Contract.waitForDeployment();

    const m1Addr = await mockFeed1.getAddress();
    const m2Addr = await mockFeed2.getAddress();
    const m3Addr = await mockFeed3.getAddress();

    const adapterAsOwner = adapter.connect(owner);
    await adapterAsOwner.registerFeed(ZERO_ADDR, m1Addr, 3600);
    await adapterAsOwner.registerFeed(m2Addr, m2Addr, 3600);
    await adapterAsOwner.registerFeed(m3Addr, m3Addr, 3600);
  });

  describe("getPrice", function () {
    it("should return normalized price for 8-decimal feed", async function () {
      await mockFeed1.setLatestRoundData(100000000, 250000000000, 0);
      const price = await adapter.getPrice(ZERO_ADDR);
      expect(price).to.equal(ethers.parseUnits("2500", 18));
    });

    it("should return normalized price for 18-decimal feed", async function () {
      await mockFeed3.setLatestRoundData(1, ethers.parseUnits("1.5", 18), 0);
      const price = await adapter.getPrice(await mockFeed3.getAddress());
      expect(price).to.equal(ethers.parseUnits("1.5", 18));
    });

    it("should revert when feed not active", async function () {
      await expect(adapter.getPrice(ADDR1))
        .to.be.revertedWith("Feed not active");
    });

    it("should revert when round incomplete", async function () {
      await mockFeed1.setLatestRoundData(100, 250000000000, 0, 0, 99);
      await expect(adapter.getPrice(ZERO_ADDR))
        .to.be.revertedWith("Round incomplete");
    });

    it("should revert when feed stale", async function () {
      const oldTimestamp = (await ethers.provider.getBlock())?.timestamp || 0;
      await mockFeed1.setLatestRoundData(100, 250000000000, 0, oldTimestamp - 4000, 100);
      await expect(adapter.getPrice(ZERO_ADDR))
        .to.be.revertedWith("Feed stale");
    });

    it("should revert on negative price", async function () {
      await mockFeed1.setLatestRoundData(100, -100, 0);
      await expect(adapter.getPrice(ZERO_ADDR))
        .to.be.revertedWith("Negative price");
    });
  });

  describe("derivedPrice", function () {
    it("should correctly derive cross-rate using registered feeds", async function () {
      // Register a second feed for testing derivedPrice
      const [owner] = await ethers.getSigners();
      const m2Addr = await mockFeed2.getAddress();

      // Register mockFeed2 at a custom token address
      const token2 = "0x0000000000000000000000000000000000000001";
      const adapterAsOwner = adapter.connect(owner);
      await adapterAsOwner.registerFeed(token2, m2Addr, 3600);

      await mockFeed1.setLatestRoundData(1, 250000000000, 0); // ETH/USD = $2500
      await mockFeed2.setLatestRoundData(1, 5000000000000, 0); // BTC/USD = $50000

      const price = await adapter.derivedPrice(token2, ZERO_ADDR);
      expect(price).to.equal(ethers.parseUnits("20", 18));
    });

    it("should handle decimal mismatch between feeds", async function () {
      const m3Addr = await mockFeed3.getAddress();
      await mockFeed1.setLatestRoundData(1, 250000000000, 0);
      await mockFeed3.setLatestRoundData(1, ethers.parseUnits("1.5", 18), 0);

      const price = await adapter.derivedPrice(m3Addr, ZERO_ADDR);
      expect(price).to.be.gt(0);
    });

    it("should revert when base feed is stale", async function () {
      const [owner] = await ethers.getSigners();
      const m2Addr = await mockFeed2.getAddress();
      const token2 = "0x0000000000000000000000000000000000000001";

      const adapterAsOwner = adapter.connect(owner);
      await adapterAsOwner.registerFeed(token2, m2Addr, 3600);

      await mockFeed1.setLatestRoundData(1, 250000000000, 0, 0, 1);
      await mockFeed2.setLatestRoundData(1, 5000000000000, 0);

      await expect(adapter.derivedPrice(ZERO_ADDR, token2))
        .to.be.revertedWith("Base feed stale");
    });

    it("should revert when quote feed is stale", async function () {
      const [owner] = await ethers.getSigners();
      const m2Addr = await mockFeed2.getAddress();
      const token2 = "0x0000000000000000000000000000000000000001";

      const adapterAsOwner = adapter.connect(owner);
      // Register a new token at token2 using mockFeed1
      await adapterAsOwner.registerFeed(token2, await mockFeed1.getAddress(), 3600);

      const currentTime = (await ethers.provider.getBlock('latest')).timestamp;
      // Set ZERO_ADDR feed (mockFeed1) to current time (valid)
      await mockFeed1.setLatestRoundData(1, 250000000000, currentTime, currentTime, 1);
      // Set token2 feed (mockFeed2) to old time (stale) - register it to mockFeed2
      await adapterAsOwner.registerFeed(token2, m2Addr, 3600);
      await mockFeed2.setLatestRoundData(1, 5000000000000, currentTime, currentTime - 4000, 1);

      await expect(adapter.derivedPrice(ZERO_ADDR, token2))
        .to.be.revertedWith("Quote feed stale");
    });

    it("should revert when base round incomplete", async function () {
      const [owner] = await ethers.getSigners();
      const m2Addr = await mockFeed2.getAddress();
      const token2 = "0x0000000000000000000000000000000000000001";

      const adapterAsOwner = adapter.connect(owner);
      await adapterAsOwner.registerFeed(token2, m2Addr, 3600);

      await mockFeed1.setLatestRoundData(100, 250000000000, 0, 0, 99);
      await mockFeed2.setLatestRoundData(1, 5000000000000, 0);

      await expect(adapter.derivedPrice(ZERO_ADDR, token2))
        .to.be.revertedWith("Base round incomplete");
    });

    it("should revert when same token provided", async function () {
      await expect(adapter.derivedPrice(ZERO_ADDR, ZERO_ADDR))
        .to.be.revertedWith("Same token");
    });

    it("should revert when base feed not active", async function () {
      await expect(adapter.derivedPrice(ADDR1, ZERO_ADDR))
        .to.be.revertedWith("Feed not active");
    });

    it("should revert when quote feed not active", async function () {
      await expect(adapter.derivedPrice(ZERO_ADDR, ADDR1))
        .to.be.revertedWith("Feed not active");
    });
  });
});