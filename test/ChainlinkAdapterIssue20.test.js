const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("ChainlinkAdapter validation", function () {
  async function deploy() {
    const [admin] = await ethers.getSigners();
    const Adapter = await ethers.getContractFactory("ChainlinkAdapter");
    const adapter = await Adapter.deploy();
    await adapter.waitForDeployment();
    const Feed = await ethers.getContractFactory("MockChainlinkFeed");
    const primary = await Feed.deploy(8);
    const fallbackFeed = await Feed.deploy(18);
    await primary.waitForDeployment();
    await fallbackFeed.waitForDeployment();
    return { admin, adapter, primary, fallbackFeed };
  }

  async function setData(feed, answer, updatedAt, answeredInRound = 1n) {
    await feed.setRoundData(1n, answer, updatedAt, updatedAt, answeredInRound, false);
  }

  it("normalizes a complete, fresh primary round", async function () {
    const { adapter, primary, fallbackFeed, admin } = await deploy();
    const token = admin.address;
    const latest = await ethers.provider.getBlock("latest");
    await setData(primary, 123_00000000n, BigInt(latest.timestamp));
    await setData(fallbackFeed, 77n * 10n ** 18n, BigInt(latest.timestamp));
    await adapter.registerFeed(token, await primary.getAddress(), 3_600n);
    await adapter.setFallbackFeed(token, await fallbackFeed.getAddress(), 3_600n);

    expect(await adapter.getPrice(token)).to.equal(123n * 10n ** 18n);
  });

  it("uses the fallback for incomplete, negative, or stale primary data", async function () {
    const { adapter, primary, fallbackFeed, admin } = await deploy();
    const token = admin.address;
    const latest = await ethers.provider.getBlock("latest");
    const now = BigInt(latest.timestamp);
    await adapter.registerFeed(token, await primary.getAddress(), 3_600n);
    await adapter.setFallbackFeed(token, await fallbackFeed.getAddress(), 3_600n);
    await setData(fallbackFeed, 77n * 10n ** 18n, now);

    await primary.setRoundData(2n, 123_00000000n, now, now, 1n, false);
    expect(await adapter.getPrice(token)).to.equal(77n * 10n ** 18n);

    await primary.setRoundData(3n, -1n, now, now, 3n, false);
    expect(await adapter.getPrice(token)).to.equal(77n * 10n ** 18n);

    await primary.setRoundData(4n, 123_00000000n, now - 7_200n, now - 7_200n, 4n, false);
    expect(await adapter.getPrice(token)).to.equal(77n * 10n ** 18n);
  });

  it("reverts when neither primary nor fallback data is valid", async function () {
    const { adapter, primary, fallbackFeed, admin } = await deploy();
    const token = admin.address;
    const latest = await ethers.provider.getBlock("latest");
    const stale = BigInt(latest.timestamp) - 7_200n;
    await adapter.registerFeed(token, await primary.getAddress(), 3_600n);
    await adapter.setFallbackFeed(token, await fallbackFeed.getAddress(), 3_600n);
    await setData(primary, 1n, stale);
    await setData(fallbackFeed, 1n, stale);

    await expect(adapter.getPrice(token)).to.be.revertedWith("No valid feed");
  });
});
