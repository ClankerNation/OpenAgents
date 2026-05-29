const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");
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

function findImport(importPath) {
  const candidates = [
    path.join("node_modules", importPath),
    path.join(process.cwd(), importPath),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return { contents: fs.readFileSync(candidate, "utf8") };
    }
  }
  return { error: `File not found: ${importPath}` };
}

function compileContracts() {
  const input = {
    language: "Solidity",
    sources: {
      "StakingRewards.sol": { content: fs.readFileSync("contracts/staking/StakingRewards.sol", "utf8") },
      "MockERC20.sol": { content: mockErc20Source },
    },
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: { "*": { "*": ["abi", "evm.bytecode"] } },
    },
  };
  const output = JSON.parse(solc.compile(JSON.stringify(input), { import: findImport }));
  const fatal = (output.errors || []).filter((error) => error.severity === "error");
  if (fatal.length > 0) {
    throw new Error(fatal.map((error) => error.formattedMessage).join("\n"));
  }
  return {
    staking: output.contracts["StakingRewards.sol"].StakingRewards,
    token: output.contracts["MockERC20.sol"].MockERC20,
  };
}

async function deployFactory(compiled, signer, ...args) {
  const factory = new ethers.ContractFactory(compiled.abi, compiled.evm.bytecode.object, signer);
  const contract = await factory.deploy(...args);
  await contract.waitForDeployment();
  return contract;
}

async function fixture() {
  const [owner, alice, bob] = await ethers.getSigners();
  const compiled = compileContracts();
  const stakingToken = await deployFactory(compiled.token, owner, "Stake", "STK");
  const rewardsToken = await deployFactory(compiled.token, owner, "Reward", "RWD");
  const rewards = await deployFactory(
    compiled.staking,
    owner,
    await stakingToken.getAddress(),
    await rewardsToken.getAddress(),
  );

  for (const user of [alice, bob]) {
    await stakingToken.mint(user.address, 1_000n);
    await stakingToken.connect(user).approve(await rewards.getAddress(), 1_000n);
  }
  await rewardsToken.mint(await rewards.getAddress(), 1_000_000n);
  return { rewards, stakingToken, rewardsToken, owner, alice, bob };
}

describe("StakingRewards time accounting", function () {
  it("does not accrue rewards past periodFinish", async function () {
    const { rewards, alice } = await fixture();
    await rewards.connect(alice).stake(100n);
    await rewards.notifyRewardAmount(604_800n);

    await ethers.provider.send("evm_increaseTime", [7 * 24 * 60 * 60]);
    await ethers.provider.send("evm_mine", []);
    const atFinish = await rewards.earned(alice.address);

    await ethers.provider.send("evm_increaseTime", [7 * 24 * 60 * 60]);
    await ethers.provider.send("evm_mine", []);
    const afterFinish = await rewards.earned(alice.address);

    expect(afterFinish).to.equal(atFinish);
  });

  it("keeps earlier accrual when reward rate changes mid-stake", async function () {
    const { rewards, alice } = await fixture();
    await rewards.connect(alice).stake(100n);
    await rewards.notifyRewardAmount(604_800n);

    await ethers.provider.send("evm_increaseTime", [100]);
    await ethers.provider.send("evm_mine", []);
    const beforeChange = await rewards.earned(alice.address);

    await rewards.notifyRewardAmount(1_209_600n);
    expect(await rewards.earned(alice.address)).to.be.gte(beforeChange);
  });

  it("allocates rewards proportionally for staggered stakers", async function () {
    const { rewards, alice, bob } = await fixture();
    await rewards.notifyRewardAmount(604_800n);
    await rewards.connect(alice).stake(100n);
    await ethers.provider.send("evm_increaseTime", [100]);
    await ethers.provider.send("evm_mine", []);
    await rewards.connect(bob).stake(100n);
    await ethers.provider.send("evm_increaseTime", [100]);
    await ethers.provider.send("evm_mine", []);

    expect(await rewards.earned(alice.address)).to.be.gt(await rewards.earned(bob.address));
  });
});
