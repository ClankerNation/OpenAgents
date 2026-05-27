const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("ChainlinkAdapter - Multi-hop Price", function () {
    let adapter;
    let owner;

    // Mock aggregator addresses (not actually deployed — we use ethers to create mock contracts)
    const DECIMALS_8 = 8;
    const DECIMALS_18 = 18;
    const TOKEN_USD_FEED_8 = "0x0000000000000000000000000000000000000001";
    const ETH_USD_FEED_8 = "0x0000000000000000000000000000000000000002";
    const TOKEN_ETH_FEED_18 = "0x0000000000000000000000000000000000000003";
    const BASE_TOKEN = "0x00000000000000000000000000000000000000a1";
    const QUOTE_TOKEN = "0x00000000000000000000000000000000000000a2";
    const BASE_TOKEN_18 = "0x00000000000000000000000000000000000000a3";
    const QUOTE_TOKEN_18 = "0x00000000000000000000000000000000000000a4";

    beforeEach(async function () {
        const ChainlinkAdapter = await ethers.getContractFactory("ChainlinkAdapter");
        adapter = await ChainlinkAdapter.deploy();
        await adapter.waitForDeployment();
        [owner] = await ethers.getSigners();
    });

    describe("Direct price (getPrice)", function () {
        it("should reject unregistered feeds", async function () {
            await expect(
                adapter.getPrice(BASE_TOKEN)
            ).to.be.revertedWith("Feed not active");
        });

        it("should reject deactivated feeds", async function () {
            await adapter.registerFeed(BASE_TOKEN, TOKEN_USD_FEED_8, 3600);
            await adapter.deactivateFeed(BASE_TOKEN);
            await expect(
                adapter.getPrice(BASE_TOKEN)
            ).to.be.revertedWith("Feed not active");
        });
    });

    describe("Derived price (derivedPrice)", function () {
        it("should reject when base feed is not registered", async function () {
            await adapter.registerFeed(QUOTE_TOKEN, ETH_USD_FEED_8, 3600);
            await expect(
                adapter.derivedPrice(BASE_TOKEN, QUOTE_TOKEN)
            ).to.be.revertedWith("Feed not active");
        });

        it("should reject when quote feed is not registered", async function () {
            await adapter.registerFeed(BASE_TOKEN, TOKEN_USD_FEED_8, 3600);
            await expect(
                adapter.derivedPrice(BASE_TOKEN, QUOTE_TOKEN)
            ).to.be.revertedWith("Feed not active");
        });

        it("should reject when both feeds are not registered", async function () {
            await expect(
                adapter.derivedPrice(BASE_TOKEN, QUOTE_TOKEN)
            ).to.be.revertedWith("Feed not active");
        });
    });

    describe("Feed validation", function () {
        it("should reject zero heartbeat on register", async function () {
            await expect(
                adapter.registerFeed(BASE_TOKEN, TOKEN_USD_FEED_8, 0)
            ).to.be.revertedWith("Invalid heartbeat");
        });

        it("should reject zero address feed on register", async function () {
            await expect(
                adapter.registerFeed(BASE_TOKEN, ethers.ZeroAddress, 3600)
            ).to.be.revertedWith("Invalid feed");
        });

        it("should only allow admin to register feeds", async function () {
            const [, other] = await ethers.getSigners();
            const adapterOther = adapter.connect(other);
            await expect(
                adapterOther.registerFeed(BASE_TOKEN, TOKEN_USD_FEED_8, 3600)
            ).to.be.revertedWith("Not admin");
        });

        it("should reject non-admin deactivation", async function () {
            await adapter.registerFeed(BASE_TOKEN, TOKEN_USD_FEED_8, 3600);
            const [, other] = await ethers.getSigners();
            await expect(
                adapter.connect(other).deactivateFeed(BASE_TOKEN)
            ).to.be.revertedWith("Not admin");
        });

        it("should return correct feed info", async function () {
            await adapter.registerFeed(BASE_TOKEN, TOKEN_USD_FEED_8, 3600);
            const info = await adapter.getFeedInfo(BASE_TOKEN);
            expect(info.feedAddress).to.equal(TOKEN_USD_FEED_8);
            expect(info.heartbeat).to.equal(3600);
            expect(info.active).to.be.true;
        });
    });
});
