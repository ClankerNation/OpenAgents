const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");
const solc = require("solc");

function findImport(importPath) {
  const candidates = [
    path.join(process.cwd(), importPath),
    path.join(process.cwd(), "node_modules", importPath),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return { contents: fs.readFileSync(candidate, "utf8") };
    }
  }

  return { error: `File not found: ${importPath}` };
}

function compileContracts() {
  const escrowPath = "contracts/PaymentEscrow.sol";
  const tokenPath = "contracts/test/FeeOnTransferToken.sol";
  const input = {
    language: "Solidity",
    sources: {
      [escrowPath]: { content: fs.readFileSync(escrowPath, "utf8") },
      [tokenPath]: {
        content: `
          // SPDX-License-Identifier: MIT
          pragma solidity ^0.8.20;
          import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

          contract FeeOnTransferToken is ERC20 {
              uint256 public feeBps;

              constructor(uint256 _feeBps) ERC20("Fee Token", "FEE") {
                  feeBps = _feeBps;
              }

              function mint(address account, uint256 amount) external {
                  _mint(account, amount);
              }

              function _update(address from, address to, uint256 amount) internal override {
                  if (from != address(0) && to != address(0) && feeBps > 0) {
                      uint256 fee = amount * feeBps / 10000;
                      super._update(from, to, amount - fee);
                      super._update(from, address(0), fee);
                  } else {
                      super._update(from, to, amount);
                  }
              }
          }
        `,
      },
    },
    settings: {
      outputSelection: {
        "*": {
          "*": ["abi", "evm.bytecode.object"],
        },
      },
    },
  };

  const output = JSON.parse(solc.compile(JSON.stringify(input), { import: findImport }));
  const errors = (output.errors || []).filter((error) => error.severity === "error");
  if (errors.length) {
    throw new Error(errors.map((error) => error.formattedMessage).join("\n"));
  }

  return {
    escrow: output.contracts[escrowPath].PaymentEscrow,
    token: output.contracts[tokenPath].FeeOnTransferToken,
  };
}

async function deploy(artifact, signer, args = []) {
  const factory = new ethers.ContractFactory(
    artifact.abi,
    `0x${artifact.evm.bytecode.object}`,
    signer
  );
  const contract = await factory.deploy(...args);
  await contract.waitForDeployment();
  return contract;
}

describe("PaymentEscrow received amount accounting", function () {
  let compiled;
  let payer;
  let payee;
  let escrow;

  before(function () {
    compiled = compileContracts();
  });

  beforeEach(async function () {
    [payer, payee] = await ethers.getSigners();
    escrow = await deploy(compiled.escrow, payer);
  });

  async function deployToken(feeBps) {
    const token = await deploy(compiled.token, payer, [feeBps]);
    await token.mint(payer.address, ethers.parseEther("100"));
    await token.approve(await escrow.getAddress(), ethers.parseEther("100"));
    return token;
  }

  it("rejects zero amount escrows", async function () {
    const token = await deployToken(0);

    await expect(
      escrow.createEscrow(payee.address, await token.getAddress(), 0, 0)
    ).to.be.revertedWith("Amount must be > 0");
  });

  it("stores the full amount for standard ERC20 transfers", async function () {
    const token = await deployToken(0);
    const amount = ethers.parseEther("10");

    await expect(escrow.createEscrow(payee.address, await token.getAddress(), amount, 0))
      .to.emit(escrow, "EscrowCreated")
      .withArgs(0, payer.address, amount);

    const stored = await escrow.escrows(0);
    expect(stored.amount).to.equal(amount);
  });

  it("stores only the actual received amount for fee-on-transfer tokens", async function () {
    const token = await deployToken(1000);
    const amount = ethers.parseEther("10");
    const received = ethers.parseEther("9");

    await expect(escrow.createEscrow(payee.address, await token.getAddress(), amount, 0))
      .to.emit(escrow, "EscrowCreated")
      .withArgs(0, payer.address, received);

    const stored = await escrow.escrows(0);
    expect(stored.amount).to.equal(received);
    expect(await token.balanceOf(await escrow.getAddress())).to.equal(received);
  });

  it("releases the stored received amount", async function () {
    const token = await deployToken(1000);
    await escrow.createEscrow(payee.address, await token.getAddress(), ethers.parseEther("10"), 0);

    await escrow.releaseEscrow(0);

    expect(await token.balanceOf(payee.address)).to.equal(ethers.parseEther("8.1"));
  });
});
