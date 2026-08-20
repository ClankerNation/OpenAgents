import os

mock_permit2 = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../interfaces/IPermit2.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract MockPermit2 is IPermit2 {
    function permitTransferFrom(
        PermitTransferFrom memory permit,
        SignatureTransferDetails calldata transferDetails,
        address owner,
        bytes calldata signature
    ) external override {
        IERC20(permit.permitted.token).transferFrom(owner, transferDetails.to, transferDetails.requestedAmount);
    }
}
"""

mock_oracle = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IPriceFeed {
    function getPrice(address token) external view returns (uint256);
}

contract MockOracle is IPriceFeed {
    function getPrice(address token) external pure override returns (uint256) {
        return 1e18;
    }
}
"""

os.makedirs("contracts/mocks", exist_ok=True)
with open("contracts/mocks/MockPermit2.sol", "w") as f:
    f.write(mock_permit2)
with open("contracts/mocks/MockOracle.sol", "w") as f:
    f.write(mock_oracle)

test_file = """/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
 */
const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("Permit2 Integration", function () {
  let staking, amm, lending;
  let stakeToken, rewardToken, tokenA, tokenB, collateral, borrowToken;
  let mockPermit2, mockOracle;
  let owner, user;

  before(async function () {
    [owner, user] = await ethers.getSigners();

    const Token = await ethers.getContractFactory("AgentToken");
    stakeToken = await Token.deploy("Stake", "STK", ethers.parseEther("1000000"));
    rewardToken = await Token.deploy("Reward", "RWD", ethers.parseEther("1000000"));
    tokenA = await Token.deploy("Token A", "TKA", ethers.parseEther("1000000"));
    tokenB = await Token.deploy("Token B", "TKB", ethers.parseEther("1000000"));
    collateral = await Token.deploy("Collateral", "COL", ethers.parseEther("1000000"));
    borrowToken = await Token.deploy("Borrow", "BRW", ethers.parseEther("1000000"));

    await stakeToken.waitForDeployment();
    await rewardToken.waitForDeployment();
    await tokenA.waitForDeployment();
    await tokenB.waitForDeployment();
    await collateral.waitForDeployment();
    await borrowToken.waitForDeployment();

    const MockPermit2 = await ethers.getContractFactory("MockPermit2");
    mockPermit2 = await MockPermit2.deploy();
    await mockPermit2.waitForDeployment();

    const MockOracle = await ethers.getContractFactory("MockOracle");
    mockOracle = await MockOracle.deploy();
    await mockOracle.waitForDeployment();

    const Staking = await ethers.getContractFactory("StakingRewards");
    staking = await Staking.deploy(stakeToken.target, rewardToken.target, mockPermit2.target);
    await staking.waitForDeployment();

    const AMM = await ethers.getContractFactory("AMMPool");
    amm = await AMM.deploy(tokenA.target, tokenB.target, mockPermit2.target);
    await amm.waitForDeployment();

    const Lending = await ethers.getContractFactory("LendingPool");
    lending = await Lending.deploy(mockOracle.target, collateral.target, borrowToken.target, mockPermit2.target);
    await lending.waitForDeployment();

    // Fund user and approve MockPermit2
    await stakeToken.transfer(user.address, ethers.parseEther("1000"));
    await tokenA.transfer(user.address, ethers.parseEther("1000"));
    await tokenB.transfer(user.address, ethers.parseEther("1000"));
    await collateral.transfer(user.address, ethers.parseEther("1000"));

    await stakeToken.connect(user).approve(mockPermit2.target, ethers.MaxUint256);
    await tokenA.connect(user).approve(mockPermit2.target, ethers.MaxUint256);
    await tokenB.connect(user).approve(mockPermit2.target, ethers.MaxUint256);
    await collateral.connect(user).approve(mockPermit2.target, ethers.MaxUint256);
  });

  it("should allow staking with permit2", async function () {
    const amount = ethers.parseEther("100");
    await staking.connect(user).stakeWithPermit(amount, 1, Math.floor(Date.now() / 1000) + 3600, "0x");
    expect(await staking.balanceOf(user.address)).to.equal(amount);
  });

  it("should allow adding liquidity with permit2", async function () {
    const amountA = ethers.parseEther("100");
    const amountB = ethers.parseEther("100");
    await amm.connect(user).addLiquidityWithPermit(
      amountA, amountB,
      2, Math.floor(Date.now() / 1000) + 3600, "0x",
      3, Math.floor(Date.now() / 1000) + 3600, "0x"
    );
    expect(await amm.liquidity(user.address)).to.be.gt(0);
  });

  it("should allow depositing collateral with permit2", async function () {
    const amount = ethers.parseEther("100");
    await lending.connect(user).depositWithPermit(amount, 4, Math.floor(Date.now() / 1000) + 3600, "0x");
    const pos = await lending.getPosition(user.address);
    expect(pos.collateral).to.equal(amount);
  });
});
"""

with open("test/Permit2.test.js", "w") as f:
    f.write(test_file)

print("Created mocks and test file")
