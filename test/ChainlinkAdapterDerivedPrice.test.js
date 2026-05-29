const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("ChainlinkAdapter derived prices", function () {
  const BASE = ethers.getAddress("0x00000000000000000000000000000000000000ba");
  const QUOTE = ethers.getAddress("0x00000000000000000000000000000000000000cd");
  const HEARTBEAT = 3600;

  async function deployAdapter() {
    const ChainlinkAdapter = await ethers.getContractFactory("ChainlinkAdapter");
    const adapter = await ChainlinkAdapter.deploy();
    await adapter.waitForDeployment();
    return adapter;
  }

  async function deployFeed(decimals, answer) {
    const MockAggregatorV3 = await ethers.getContractFactory("MockAggregatorV3");
    const feed = await MockAggregatorV3.deploy(decimals, answer);
    await feed.waitForDeployment();
    return feed;
  }

  async function registerFeed(adapter, token, feed, heartbeat = HEARTBEAT) {
    await adapter.registerFeed(token, await feed.getAddress(), heartbeat);
  }

  it("derives a base/quote price from two USD feeds", async function () {
    const adapter = await deployAdapter();
    const baseFeed = await deployFeed(8, ethers.parseUnits("2000", 8));
    const quoteFeed = await deployFeed(8, ethers.parseUnits("1", 8));

    await registerFeed(adapter, BASE, baseFeed);
    await registerFeed(adapter, QUOTE, quoteFeed);

    expect(await adapter.derivedPrice(BASE, QUOTE)).to.equal(ethers.parseUnits("2000", 18));
  });

  it("normalizes different feed decimals before deriving", async function () {
    const adapter = await deployAdapter();
    const baseFeed = await deployFeed(18, ethers.parseUnits("2", 18));
    const quoteFeed = await deployFeed(8, ethers.parseUnits("0.5", 8));

    await registerFeed(adapter, BASE, baseFeed);
    await registerFeed(adapter, QUOTE, quoteFeed);

    expect(await adapter.derivedPrice(BASE, QUOTE)).to.equal(ethers.parseUnits("4", 18));
  });

  it("rejects stale component feeds", async function () {
    const adapter = await deployAdapter();
    const baseFeed = await deployFeed(8, ethers.parseUnits("2000", 8));
    const quoteFeed = await deployFeed(8, ethers.parseUnits("1", 8));
    const latestBlock = await ethers.provider.getBlock("latest");

    await baseFeed.setRoundData(1, ethers.parseUnits("2000", 8), latestBlock.timestamp - 7200, 1);
    await registerFeed(adapter, BASE, baseFeed);
    await registerFeed(adapter, QUOTE, quoteFeed);

    await expect(adapter.derivedPrice(BASE, QUOTE)).to.be.revertedWith("Stale price");
  });

  it("uses a legacy direct feed when no quote feed is registered", async function () {
    const adapter = await deployAdapter();
    const directFeed = await deployFeed(8, ethers.parseUnits("1999", 8));

    await registerFeed(adapter, BASE, directFeed);

    expect(await adapter.derivedPrice(BASE, QUOTE)).to.equal(ethers.parseUnits("1999", 18));
  });

  it("prefers an explicit direct pair feed when one is registered", async function () {
    const adapter = await deployAdapter();
    const baseFeed = await deployFeed(8, ethers.parseUnits("2000", 8));
    const quoteFeed = await deployFeed(8, ethers.parseUnits("1", 8));
    const directFeed = await deployFeed(8, ethers.parseUnits("1999", 8));
    const directKey = await adapter.pairKey(BASE, QUOTE);

    await registerFeed(adapter, BASE, baseFeed);
    await registerFeed(adapter, QUOTE, quoteFeed);
    await registerFeed(adapter, directKey, directFeed);

    expect(await adapter.derivedPrice(BASE, QUOTE)).to.equal(ethers.parseUnits("1999", 18));
  });
});
