const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("ChainlinkAdapter validation and fallback", function () {
  let token;
  let adapter;
  let primaryFeed;
  let fallbackFeed;

  const heartbeat = 3600;
  const primaryPrice = 2_000_00000000n;
  const fallbackPrice = 1_950_00000000n;

  beforeEach(async function () {
    [, token] = await ethers.getSigners();

    const ChainlinkAdapter = await ethers.getContractFactory("ChainlinkAdapter");
    adapter = await ChainlinkAdapter.deploy();

    const MockChainlinkFeed = await ethers.getContractFactory("MockChainlinkFeed");
    primaryFeed = await MockChainlinkFeed.deploy(8);
    fallbackFeed = await MockChainlinkFeed.deploy(8);

    await adapter.registerFeed(token.address, await primaryFeed.getAddress(), heartbeat);
    await adapter.registerFallbackFeed(token.address, await fallbackFeed.getAddress(), heartbeat);
  });

  async function setFeed(feed, answer, updatedAtOffset = 0, answeredInRound = 1, roundId = 1) {
    const updatedAt = (await time.latest()) - updatedAtOffset;
    await feed.setRoundData(roundId, answer, updatedAt, answeredInRound);
  }

  it("rejects incomplete rounds", async function () {
    await setFeed(primaryFeed, primaryPrice, 0, 1, 2);

    await expect(adapter.getPrice(token.address)).to.be.revertedWith("Incomplete round");
  });

  it("rejects zero and negative prices", async function () {
    await setFeed(primaryFeed, 0n);
    await expect(adapter.getPrice(token.address)).to.be.revertedWith("Invalid price");

    await setFeed(primaryFeed, -1n);
    await expect(adapter.getPrice(token.address)).to.be.revertedWith("Invalid price");
  });

  it("returns normalized primary prices when the feed is fresh", async function () {
    await setFeed(primaryFeed, primaryPrice);

    expect(await adapter.getPrice(token.address)).to.equal(primaryPrice * 10n ** 10n);
  });

  it("uses the fallback feed when the primary feed is stale", async function () {
    await setFeed(primaryFeed, primaryPrice, heartbeat + 1);
    await setFeed(fallbackFeed, fallbackPrice);

    expect(await adapter.getPrice(token.address)).to.equal(fallbackPrice * 10n ** 10n);
  });

  it("reverts stale prices when no active fallback is available", async function () {
    await adapter.deactivateFallbackFeed(token.address);
    await setFeed(primaryFeed, primaryPrice, heartbeat + 1);

    await expect(adapter.getPrice(token.address)).to.be.revertedWith("Stale price");
  });
});
