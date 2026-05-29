const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const solc = require("solc");

const mockErc20Source = `
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MockERC20 {
    string public name;
    string public symbol;
    uint8 public decimals = 18;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    constructor(string memory _name, string memory _symbol) {
        name = _name;
        symbol = _symbol;
    }

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "balance");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        require(balanceOf[from] >= amount, "balance");
        require(allowance[from][msg.sender] >= amount, "allowance");
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}
`;

function compileContracts() {
  const input = {
    language: "Solidity",
    sources: {
      "AMMPool.sol": { content: fs.readFileSync("contracts/dex/AMMPool.sol", "utf8") },
      "MockERC20.sol": { content: mockErc20Source },
    },
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: { "*": { "*": ["abi", "evm.bytecode"] } },
    },
  };
  const output = JSON.parse(solc.compile(JSON.stringify(input)));
  const fatal = (output.errors || []).filter((error) => error.severity === "error");
  if (fatal.length > 0) {
    throw new Error(fatal.map((error) => error.formattedMessage).join("\n"));
  }
  return {
    pool: output.contracts["AMMPool.sol"].AMMPool,
    token: output.contracts["MockERC20.sol"].MockERC20,
  };
}

async function deployFactory(compiled, signer, ...args) {
  const factory = new ethers.ContractFactory(compiled.abi, compiled.evm.bytecode.object, signer);
  const contract = await factory.deploy(...args);
  await contract.waitForDeployment();
  return contract;
}

describe("AMMPool indexer events", function () {
  async function fixture() {
    const [user] = await ethers.getSigners();
    const compiled = compileContracts();
    const tokenA = await deployFactory(compiled.token, user, "Token A", "TKA");
    const tokenB = await deployFactory(compiled.token, user, "Token B", "TKB");
    const pool = await deployFactory(compiled.pool, user, await tokenA.getAddress(), await tokenB.getAddress());

    await tokenA.mint(user.address, 10_000n);
    await tokenB.mint(user.address, 10_000n);
    await tokenA.approve(await pool.getAddress(), 10_000n);
    await tokenB.approve(await pool.getAddress(), 10_000n);

    return { pool, tokenA, tokenB, user };
  }

  it("indexes Swap user and tokenIn fields", async function () {
    const { pool } = await fixture();
    const swap = pool.interface.getEvent("Swap");

    expect(swap.inputs[0].name).to.equal("user");
    expect(swap.inputs[0].indexed).to.equal(true);
    expect(swap.inputs[1].name).to.equal("tokenIn");
    expect(swap.inputs[1].indexed).to.equal(true);
  });

  it("emits Mint, Burn, Swap, and Sync with updated reserves", async function () {
    const { pool, tokenA, user } = await fixture();
    const tokenAAddress = await tokenA.getAddress();

    await expect(pool.addLiquidity(1_000n, 1_000n))
      .to.emit(pool, "Mint")
      .withArgs(user.address, 1_000n, 1_000n)
      .and.to.emit(pool, "Sync")
      .withArgs(1_000n, 1_000n);

    const swap = await pool.swap(tokenAAddress, 100n, 0);
    const receipt = await swap.wait();
    const swapLog = receipt.logs
      .map((log) => {
        try {
          return pool.interface.parseLog(log);
        } catch (_) {
          return null;
        }
      })
      .find((log) => log && log.name === "Swap");

    expect(swapLog.args.user).to.equal(user.address);
    expect(swapLog.args.tokenIn).to.equal(tokenAAddress);
    expect(swapLog.args.amountIn).to.equal(100n);
    expect(swapLog.args.amountOut).to.be.gt(0n);

    const [reserveA, reserveB] = await pool.getReserves();
    const burnAmountA = (reserveA * 100n) / 1_000n;
    const burnAmountB = (reserveB * 100n) / 1_000n;
    await expect(pool.removeLiquidity(100n))
      .to.emit(pool, "Burn")
      .withArgs(user.address, burnAmountA, burnAmountB, user.address)
      .and.to.emit(pool, "Sync")
      .withArgs(reserveA - burnAmountA, reserveB - burnAmountB);
  });
});
