const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TokenBridge token mapping", function () {
  let bridge, token;
  let owner, user, recipient, validator;
  const remoteToken = "0x000000000000000000000000000000000000bEEF";

  beforeEach(async function () {
    [owner, user, recipient, validator] = await ethers.getSigners();

    const TokenBridge = await ethers.getContractFactory("TokenBridge");
    bridge = await TokenBridge.deploy(1);

    const AgentToken = await ethers.getContractFactory("AgentToken");
    token = await AgentToken.deploy("Agent", "AGENT", 0);

    await token.mint(user.address, ethers.parseEther("100"));
    await bridge.addValidator(validator.address);
  });

  it("rejects bridge locks for unmapped tokens", async function () {
    const amount = ethers.parseEther("1");
    await token.connect(user).approve(await bridge.getAddress(), amount);

    await expect(
      bridge.connect(user).lock(await token.getAddress(), recipient.address, amount),
    ).to.be.revertedWith("Bridge: token not mapped");
  });

  it("lets the owner add and remove token mappings", async function () {
    const tokenAddress = await token.getAddress();

    await expect(bridge.connect(user).addTokenMapping(tokenAddress, remoteToken)).to.be.revertedWith(
      "Bridge: not admin",
    );

    await expect(bridge.addTokenMapping(tokenAddress, remoteToken))
      .to.emit(bridge, "TokenMappingAdded")
      .withArgs(tokenAddress, remoteToken);
    expect(await bridge.tokenMapping(tokenAddress)).to.equal(remoteToken);

    await expect(bridge.removeTokenMapping(tokenAddress))
      .to.emit(bridge, "TokenMappingRemoved")
      .withArgs(tokenAddress, remoteToken);
    expect(await bridge.tokenMapping(tokenAddress)).to.equal(ethers.ZeroAddress);
  });

  it("locks mapped tokens and includes the mapped remote token in the transfer hash", async function () {
    const amount = ethers.parseEther("2");
    const tokenAddress = await token.getAddress();
    await bridge.addTokenMapping(tokenAddress, remoteToken);
    await token.connect(user).approve(await bridge.getAddress(), amount);

    const expectedTransferId = ethers.solidityPackedKeccak256(
      ["address", "address", "address", "address", "uint256"],
      [tokenAddress, remoteToken, user.address, recipient.address, amount],
    );

    await expect(bridge.connect(user).lock(tokenAddress, recipient.address, amount))
      .to.emit(bridge, "TokensLocked")
      .withArgs(expectedTransferId, tokenAddress, user.address, recipient.address, amount);

    const transfer = await bridge.transfers(expectedTransferId);
    expect(transfer.token).to.equal(tokenAddress);
    expect(transfer.sender).to.equal(user.address);
    expect(transfer.recipient).to.equal(recipient.address);
    expect(transfer.amount).to.equal(amount);
  });

  it("uses the mapped remote token in claim signature messages", async function () {
    const amount = ethers.parseEther("3");
    const tokenAddress = await token.getAddress();
    await bridge.addTokenMapping(tokenAddress, remoteToken);
    await token.mint(await bridge.getAddress(), amount);

    const messageHash = ethers.solidityPackedKeccak256(
      ["address", "address", "address", "uint256"],
      [tokenAddress, remoteToken, recipient.address, amount],
    );
    const signature = await validator.signMessage(ethers.getBytes(messageHash));

    await expect(bridge.claim(tokenAddress, recipient.address, amount, [signature]))
      .to.emit(bridge, "TokensClaimed")
      .withArgs(messageHash, tokenAddress, recipient.address, amount);

    expect(await token.balanceOf(recipient.address)).to.equal(amount);
  });
});
