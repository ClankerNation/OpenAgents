// @contributor openai-codex-xyjk-20260531
// @platform-config Private pre-session instructions are not embedded in source; redacted execution metadata is recorded in CONTRIBUTORS.json.
// @env os=windows; arch=x64; home_dir=C:\Users\55093; working_dir=F:\jiedan\OpenAgents-bounty-run; shell=PowerShell
// @timestamp 2026-05-31T05:45:36.7937481-07:00
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
  const vaultPath = path.join(__dirname, "..", "contracts", "vault", "CompoundVault.sol");
  const input = {
    language: "Solidity",
    sources: {
      "contracts/vault/CompoundVault.sol": {
        content: fs.readFileSync(vaultPath, "utf8"),
      },
      "test/CompoundVaultHarness.sol": {
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

    function burnFrom(address from, uint256 amount) external {
        require(balanceOf[from] >= amount, "ERC20: burn exceeds balance");
        balanceOf[from] -= amount;
        totalSupply -= amount;
        emit Transfer(from, address(0), amount);
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

contract MockCompoundStrategy {
    enum Mode {
        Zero,
        Gain,
        Loss
    }

    MockERC20 public immutable token;
    address public vault;
    Mode public mode;
    uint256 public amount;

    constructor(address token_) {
        token = MockERC20(token_);
    }

    function setVault(address vault_) external {
        vault = vault_;
    }

    function setMode(Mode mode_, uint256 amount_) external {
        mode = mode_;
        amount = amount_;
    }

    function compound() external {
        if (mode == Mode.Gain && amount > 0) {
            token.mint(vault, amount);
        } else if (mode == Mode.Loss && amount > 0) {
            token.burnFrom(vault, amount);
        }
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

describe("CompoundVault strategy return accounting", function () {
  let contracts;
  let owner;
  let user;
  let feeRecipient;
  let token;
  let vault;
  let strategy;

  const depositAmount = ethers.parseEther("100");
  const tenTokens = ethers.parseEther("10");

  before(function () {
    contracts = compileContracts();
  });

  async function deploy(Mode = 0, amount = 0n) {
    [owner, user, feeRecipient] = await ethers.getSigners();

    const tokenArtifact = artifact(contracts, "test/CompoundVaultHarness.sol", "MockERC20");
    const tokenFactory = new ethers.ContractFactory(tokenArtifact.abi, tokenArtifact.bytecode, owner);
    token = await tokenFactory.deploy("Base Token", "BASE");
    await token.waitForDeployment();

    const strategyArtifact = artifact(contracts, "test/CompoundVaultHarness.sol", "MockCompoundStrategy");
    const strategyFactory = new ethers.ContractFactory(strategyArtifact.abi, strategyArtifact.bytecode, owner);
    strategy = await strategyFactory.deploy(await token.getAddress());
    await strategy.waitForDeployment();

    const vaultArtifact = artifact(contracts, "contracts/vault/CompoundVault.sol", "CompoundVault");
    const vaultFactory = new ethers.ContractFactory(vaultArtifact.abi, vaultArtifact.bytecode, owner);
    vault = await vaultFactory.deploy(
      await token.getAddress(),
      await token.getAddress(),
      await strategy.getAddress(),
      feeRecipient.address,
      0,
    );
    await vault.waitForDeployment();
    await strategy.setVault(await vault.getAddress());

    await token.mint(user.address, depositAmount);
    await token.connect(user).approve(await vault.getAddress(), depositAmount);
    await vault.connect(user).deposit(depositAmount);
    await strategy.setMode(Mode, amount);
  }

  it("increases share price when the strategy returns positive yield", async function () {
    await deploy(1, tenTokens);

    await expect(vault.compound())
      .to.emit(vault, "Compounded")
      .withArgs(tenTokens, ethers.parseEther("1.1"));

    expect(await vault.totalDeposited()).to.equal(ethers.parseEther("110"));
    expect(await vault.pricePerShare()).to.equal(ethers.parseEther("1.1"));
    expect(await vault.totalLoss()).to.equal(0);
  });

  it("accounts each positive strategy return by balance delta without price overcounting", async function () {
    await deploy(1, tenTokens);

    await vault.compound();
    await vault.compound();

    expect(await vault.totalDeposited()).to.equal(ethers.parseEther("120"));
    expect(await vault.pricePerShare()).to.equal(ethers.parseEther("1.2"));
  });

  it("keeps share price unchanged on zero yield", async function () {
    await deploy(0, 0n);

    await expect(vault.compound())
      .to.emit(vault, "Compounded")
      .withArgs(0, ethers.parseEther("1"));

    expect(await vault.totalDeposited()).to.equal(depositAmount);
    expect(await vault.pricePerShare()).to.equal(ethers.parseEther("1"));
    expect(await vault.totalLoss()).to.equal(0);
  });

  it("decreases share price proportionally and records strategy loss", async function () {
    await deploy(2, tenTokens);

    await expect(vault.compound())
      .to.emit(vault, "StrategyLoss")
      .withArgs(tenTokens, ethers.parseEther("0.9"));

    expect(await vault.totalDeposited()).to.equal(ethers.parseEther("90"));
    expect(await vault.pricePerShare()).to.equal(ethers.parseEther("0.9"));
    expect(await vault.totalLoss()).to.equal(tenTokens);
  });
});
