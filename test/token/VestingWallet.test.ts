// test/token/VestingWallet.test.ts

import { expect } from "chai";
import { ethers, ContractFactory, Signer } from "hardhat";

describe("VestingWallet", function () {
  let VestingWallet: ContractFactory;
  let vestingWallet: any;
  let owner: Signer;
  let newOwner: Signer;
  let user: Signer;
  let token: any;
  let newToken: any;

  beforeEach(async function () {
    [owner, newOwner, user] = await ethers.getSigners();
    VestingWallet = await ethers.getContractFactory("VestingWallet");
    token = await (await ethers.getContractFactory("MockERC20")).deploy();
    newToken = await (await ethers.getContractFactory("MockERC20")).deploy();

    vestingWallet = await VestingWallet.deploy(token.address);
    await vestingWallet.deployed();
  });

  it("should migrate to new token address", async function () {
    const initialBalance = await token.balanceOf(owner.address);
    await vestingWallet.connect(owner).migrateToken(newToken.address);

    expect(await vestingWallet.token()).to.equal(newToken.address);
    expect(await newToken.balanceOf(vestingWallet.address)).to.equal(initialBalance);
  });

  it("should revert migration with insufficient new token balance", async function () {
    const initialBalance = await token.balanceOf(owner.address);
    await expect(vestingWallet.connect(owner).migrateToken(token.address))
      .to.be.revertedWith("Insufficient new token balance");
  });

  it("should use new token after migration", async function () {
    const initialBalance = await token.balanceOf(user.address);
    await vestingWallet.connect(owner).migrateToken(newToken.address);

    await newToken.transfer(vestingWallet.address, initialBalance);
    await vestingWallet.connect(user).claim();

    expect(await newToken.balanceOf(user.address)).to.equal(initialBalance);
  });

  it("should emit TokenMigrated event", async function () {
    const tx = await vestingWallet.connect(owner).migrateToken(newToken.address);
    const receipt = await tx.wait();
    const event = receipt.events.find((e) => e.event === "TokenMigrated");
    expect(event).to.exist;
  });
});