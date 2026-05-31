// @contributor openai-codex-xyjk-20260531
// @platform-config Private pre-session instructions are not embedded in source; redacted execution metadata is recorded in CONTRIBUTORS.json.
// @env os=windows; arch=x64; home_dir=C:\Users\55093; working_dir=F:\jiedan\OpenAgents-bounty-run; shell=PowerShell
// @timestamp 2026-05-31T06:06:02.9251807-07:00
const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");
const solc = require("solc");

function importCallback(importPath) {
  const fullPath = path.join(__dirname, "..", "node_modules", importPath);
  if (fs.existsSync(fullPath)) {
    return { contents: fs.readFileSync(fullPath, "utf8") };
  }
  return { error: `File not found: ${importPath}` };
}

function compileContracts() {
  const aggregatorPath = path.join(__dirname, "..", "contracts", "vault", "YieldAggregator.sol");
  const input = {
    language: "Solidity",
    sources: {
      "contracts/vault/YieldAggregator.sol": {
        content: fs.readFileSync(aggregatorPath, "utf8"),
      },
      "test/YieldAggregatorHarness.sol": {
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

  const output = JSON.parse(solc.compile(JSON.stringify(input), { import: importCallback }));
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

describe("YieldAggregator allocation caps", function () {
  let contracts;
  let owner;
  let user;
  let strategyA;
  let strategyB;
  let asset;
  let aggregator;

  const depositAmount = ethers.parseEther("100");

  before(function () {
    contracts = compileContracts();
  });

  async function deployFixture() {
    [owner, user, strategyA, strategyB] = await ethers.getSigners();

    const tokenArtifact = artifact(contracts, "test/YieldAggregatorHarness.sol", "MockERC20");
    const tokenFactory = new ethers.ContractFactory(tokenArtifact.abi, tokenArtifact.bytecode, owner);
    asset = await tokenFactory.deploy("Asset", "AST");
    await asset.waitForDeployment();

    const aggregatorArtifact = artifact(
      contracts,
      "contracts/vault/YieldAggregator.sol",
      "YieldAggregator",
    );
    const aggregatorFactory = new ethers.ContractFactory(
      aggregatorArtifact.abi,
      aggregatorArtifact.bytecode,
      owner,
    );
    aggregator = await aggregatorFactory.deploy(await asset.getAddress());
    await aggregator.waitForDeployment();

    await asset.mint(user.address, depositAmount);
    await asset.connect(user).approve(await aggregator.getAddress(), depositAmount);
  }

  it("splits deposits across strategies according to allocation caps", async function () {
    await deployFixture();
    await aggregator["addStrategy(address,uint256)"](strategyA.address, 6000);
    await aggregator["addStrategy(address,uint256)"](strategyB.address, 4000);

    await aggregator.connect(user).deposit(depositAmount);

    expect(await aggregator.currentAllocation(0)).to.equal(ethers.parseEther("60"));
    expect(await aggregator.currentAllocation(1)).to.equal(ethers.parseEther("40"));
    expect(await asset.balanceOf(strategyA.address)).to.equal(ethers.parseEther("60"));
    expect(await asset.balanceOf(strategyB.address)).to.equal(ethers.parseEther("40"));
    expect(await asset.balanceOf(await aggregator.getAddress())).to.equal(0);
  });

  it("prevents owner allocation above a strategy cap", async function () {
    await deployFixture();
    await aggregator["addStrategy(address,uint256)"](strategyA.address, 5000);

    await aggregator.connect(user).deposit(depositAmount);

    expect(await aggregator.currentAllocation(0)).to.equal(ethers.parseEther("50"));
    await expect(aggregator.allocate(0, 1)).to.be.revertedWith("Vault: allocation cap exceeded");
  });

  it("rebalances idle funds into a newly added strategy without exceeding caps", async function () {
    await deployFixture();
    await aggregator["addStrategy(address,uint256)"](strategyA.address, 5000);

    await aggregator.connect(user).deposit(depositAmount);
    expect(await asset.balanceOf(await aggregator.getAddress())).to.equal(ethers.parseEther("50"));

    await aggregator["addStrategy(address,uint256)"](strategyB.address, 5000);
    await aggregator.rebalance();

    expect(await aggregator.currentAllocation(0)).to.equal(ethers.parseEther("50"));
    expect(await aggregator.currentAllocation(1)).to.equal(ethers.parseEther("50"));
    expect(await asset.balanceOf(strategyB.address)).to.equal(ethers.parseEther("50"));
    expect(await asset.balanceOf(await aggregator.getAddress())).to.equal(0);
  });

  it("keeps excess deposits idle when total caps are below 100%", async function () {
    await deployFixture();
    await aggregator["addStrategy(address,uint256)"](strategyA.address, 2500);
    await aggregator["addStrategy(address,uint256)"](strategyB.address, 2500);

    await aggregator.connect(user).deposit(depositAmount);

    expect(await aggregator.currentAllocation(0)).to.equal(ethers.parseEther("25"));
    expect(await aggregator.currentAllocation(1)).to.equal(ethers.parseEther("25"));
    expect(await asset.balanceOf(await aggregator.getAddress())).to.equal(ethers.parseEther("50"));
  });
});

