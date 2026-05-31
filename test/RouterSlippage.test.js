// @contributor openai-codex-xyjk-20260531
// @platform-config Private pre-session instructions are not embedded in source; redacted execution metadata is recorded in CONTRIBUTORS.json.
// @env os=windows; arch=x64; home_dir=C:\Users\55093; working_dir=F:\jiedan\OpenAgents-bounty-run; shell=PowerShell
// @timestamp 2026-05-31T05:52:31.8443391-07:00
const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");
const solc = require("solc");

function compileContracts() {
  const routerPath = path.join(__dirname, "..", "contracts", "dex", "Router.sol");
  const input = {
    language: "Solidity",
    sources: {
      "contracts/dex/Router.sol": {
        content: fs.readFileSync(routerPath, "utf8"),
      },
      "test/RouterHarness.sol": {
        content: `
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MockERC20 {
    string public name;
    string public symbol;
    uint8 public decimals = 18;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    constructor(string memory name_, string memory symbol_) {
        name = name_;
        symbol = symbol_;
    }

    function mint(address to, uint256 amount) external {
        totalSupply += amount;
        balanceOf[to] += amount;
        emit Transfer(address(0), to, amount);
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        require(allowed >= amount, "ERC20: insufficient allowance");
        allowance[from][msg.sender] = allowed - amount;
        _transfer(from, to, amount);
        return true;
    }

    function _transfer(address from, address to, uint256 amount) internal {
        require(balanceOf[from] >= amount, "ERC20: transfer exceeds balance");
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
    }
}

contract MockAMMPool {
    MockERC20 public immutable token0;
    MockERC20 public immutable token1;
    uint256 public reserve0;
    uint256 public reserve1;
    uint256 public lastMinAmountOut;
    bool public forceZeroOutput;

    constructor(address token0_, address token1_, uint256 reserve0_, uint256 reserve1_) {
        token0 = MockERC20(token0_);
        token1 = MockERC20(token1_);
        reserve0 = reserve0_;
        reserve1 = reserve1_;
    }

    function tokenA() external view returns (address) {
        return address(token0);
    }

    function tokenB() external view returns (address) {
        return address(token1);
    }

    function getReserves() external view returns (uint256, uint256) {
        return (reserve0, reserve1);
    }

    function setForceZeroOutput(bool forceZeroOutput_) external {
        forceZeroOutput = forceZeroOutput_;
    }

    function swap(address tokenIn, uint256 amountIn, uint256 minAmountOut) external returns (uint256 amountOut) {
        require(amountIn > 0, "Pool: zero input");
        lastMinAmountOut = minAmountOut;

        bool zeroForOne = tokenIn == address(token0);
        require(zeroForOne || tokenIn == address(token1), "Pool: invalid token");

        (MockERC20 inToken, MockERC20 outToken, uint256 reserveIn, uint256 reserveOut) = zeroForOne
            ? (token0, token1, reserve0, reserve1)
            : (token1, token0, reserve1, reserve0);

        inToken.transferFrom(msg.sender, address(this), amountIn);

        if (forceZeroOutput) {
            return 0;
        }

        uint256 amountInWithFee = amountIn * 9970;
        amountOut = (amountInWithFee * reserveOut) / (reserveIn * 10000 + amountInWithFee);
        require(amountOut >= minAmountOut, "Pool: slippage");

        if (zeroForOne) {
            reserve0 += amountIn;
            reserve1 -= amountOut;
        } else {
            reserve1 += amountIn;
            reserve0 -= amountOut;
        }

        outToken.transfer(msg.sender, amountOut);
    }
}
`,
      },
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

function artifact(contracts, source, name) {
  const contract = contracts[source][name];
  return {
    abi: contract.abi,
    bytecode: `0x${contract.evm.bytecode.object}`,
  };
}

describe("Router multi-hop slippage protection", function () {
  let contracts;
  let user;
  let router;
  let tokenA;
  let tokenB;
  let tokenC;
  let poolAB;
  let poolBC;

  const initialLiquidity = ethers.parseEther("10000");
  const amountIn = ethers.parseEther("100");
  const minAmountOut = ethers.parseEther("90");

  before(function () {
    contracts = compileContracts();
  });

  async function deployFixture() {
    [, user] = await ethers.getSigners();

    const tokenArtifact = artifact(contracts, "test/RouterHarness.sol", "MockERC20");
    const tokenFactory = new ethers.ContractFactory(tokenArtifact.abi, tokenArtifact.bytecode, user);
    tokenA = await tokenFactory.deploy("Token A", "A");
    tokenB = await tokenFactory.deploy("Token B", "B");
    tokenC = await tokenFactory.deploy("Token C", "C");
    await Promise.all([tokenA.waitForDeployment(), tokenB.waitForDeployment(), tokenC.waitForDeployment()]);

    const poolArtifact = artifact(contracts, "test/RouterHarness.sol", "MockAMMPool");
    const poolFactory = new ethers.ContractFactory(poolArtifact.abi, poolArtifact.bytecode, user);
    poolAB = await poolFactory.deploy(await tokenA.getAddress(), await tokenB.getAddress(), initialLiquidity, initialLiquidity);
    poolBC = await poolFactory.deploy(await tokenB.getAddress(), await tokenC.getAddress(), initialLiquidity, initialLiquidity);
    await Promise.all([poolAB.waitForDeployment(), poolBC.waitForDeployment()]);

    await tokenB.mint(await poolAB.getAddress(), initialLiquidity);
    await tokenC.mint(await poolBC.getAddress(), initialLiquidity);

    const routerArtifact = artifact(contracts, "contracts/dex/Router.sol", "Router");
    const routerFactory = new ethers.ContractFactory(routerArtifact.abi, routerArtifact.bytecode, user);
    router = await routerFactory.deploy();
    await router.waitForDeployment();

    await router.registerPool(await tokenA.getAddress(), await tokenB.getAddress(), await poolAB.getAddress());
    await router.registerPool(await tokenB.getAddress(), await tokenC.getAddress(), await poolBC.getAddress());

    await tokenA.mint(user.address, amountIn);
    await tokenA.approve(await router.getAddress(), amountIn);
  }

  async function pathABC() {
    return Promise.all([tokenA.getAddress(), tokenB.getAddress(), tokenC.getAddress()]);
  }

  it("passes non-zero proportional minimums to every hop", async function () {
    await deployFixture();
    const deadline = (await ethers.provider.getBlock("latest")).timestamp + 60;

    const output = await router.getQuote(await pathABC(), amountIn);
    expect(output).to.be.greaterThan(minAmountOut);

    await expect(router.swapExactTokensForTokens(await pathABC(), amountIn, minAmountOut, deadline))
      .to.emit(router, "MultiHopSwap");

    expect(await poolAB.lastMinAmountOut()).to.be.greaterThan(0);
    expect(await poolBC.lastMinAmountOut()).to.equal(minAmountOut);
    expect(await tokenC.balanceOf(user.address)).to.be.greaterThanOrEqual(minAmountOut);
  });

  it("rejects circular paths", async function () {
    await deployFixture();
    const deadline = (await ethers.provider.getBlock("latest")).timestamp + 60;

    await expect(
      router.swapExactTokensForTokens(
        [await tokenA.getAddress(), await tokenB.getAddress(), await tokenA.getAddress()],
        amountIn,
        minAmountOut,
        deadline,
      ),
    ).to.be.revertedWith("Circular path");
  });

  it("rejects zero input amounts", async function () {
    await deployFixture();
    const deadline = (await ethers.provider.getBlock("latest")).timestamp + 60;

    await expect(router.swapExactTokensForTokens(await pathABC(), 0, minAmountOut, deadline)).to.be.revertedWith(
      "Zero amount",
    );
  });

  it("enforces the deadline", async function () {
    await deployFixture();
    const pastDeadline = (await ethers.provider.getBlock("latest")).timestamp - 1;

    await expect(
      router.swapExactTokensForTokens(await pathABC(), amountIn, minAmountOut, pastDeadline),
    ).to.be.revertedWith("Deadline expired");
  });

  it("rejects zero intermediate hop outputs", async function () {
    await deployFixture();
    const deadline = (await ethers.provider.getBlock("latest")).timestamp + 60;
    await poolAB.setForceZeroOutput(true);

    await expect(
      router.swapExactTokensForTokens(await pathABC(), amountIn, minAmountOut, deadline),
    ).to.be.revertedWith("Zero hop output");
  });
});
