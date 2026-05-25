const { expect } = require("chai");
const { ethers } = require("hardhat");

const abiCoder = ethers.AbiCoder.defaultAbiCoder();

function transferHash(localToken, remoteToken, sender, recipient, amount, nonce) {
  return ethers.keccak256(
    abiCoder.encode(
      ["address", "address", "address", "address", "uint256", "uint256"],
      [localToken, remoteToken, sender, recipient, amount, nonce]
    )
  );
}

function claimHash(localToken, remoteToken, recipient, amount) {
  return ethers.keccak256(
    abiCoder.encode(
      ["address", "address", "address", "uint256"],
      [localToken, remoteToken, recipient, amount]
    )
  );
}

function findEvent(receipt, contract, eventName) {
  for (const log of receipt.logs) {
    try {
      const parsed = contract.interface.parseLog(log);
      if (parsed.name === eventName) {
        return parsed;
      }
    } catch (_err) {
      // Ignore logs emitted by other contracts in the transaction.
    }
  }
  throw new Error(`Event ${eventName} not found`);
}

describe("TokenBridge token mapping", function () {
  let admin;
  let user;
  let recipient;
  let validator;
  let nonAdmin;
  let remoteToken;
  let bridge;
  let localToken;
  let unmappedToken;

  const bridgeAmount = ethers.parseEther("10");
  const initialSupply = ethers.parseEther("1000000");

  beforeEach(async function () {
    [admin, user, recipient, validator, nonAdmin, remoteToken] = await ethers.getSigners();

    const TokenBridge = await ethers.getContractFactory("TokenBridge");
    bridge = await TokenBridge.deploy(1);
    await bridge.waitForDeployment();

    const AgentToken = await ethers.getContractFactory("AgentToken");
    localToken = await AgentToken.deploy("Local Token", "LOCAL", initialSupply);
    await localToken.waitForDeployment();

    unmappedToken = await AgentToken.deploy("Unmapped Token", "UNMAPPED", initialSupply);
    await unmappedToken.waitForDeployment();

    await bridge.addValidator(validator.address);
    await localToken.mint(user.address, bridgeAmount);
    await localToken.connect(user).approve(await bridge.getAddress(), bridgeAmount);
  });

  it("rejects unmapped tokens before tokens can be locked or claimed", async function () {
    const localTokenAddress = await localToken.getAddress();

    await expect(
      bridge.connect(user).lock(localTokenAddress, recipient.address, bridgeAmount)
    ).to.be.revertedWith("Bridge: token not mapped");

    await expect(
      bridge.claim(localTokenAddress, recipient.address, bridgeAmount, [])
    ).to.be.revertedWith("Bridge: token not mapped");
  });

  it("lets only the admin add and remove token mappings", async function () {
    const localTokenAddress = await localToken.getAddress();

    await expect(
      bridge.connect(nonAdmin).addTokenMapping(localTokenAddress, remoteToken.address)
    ).to.be.revertedWith("Bridge: not admin");

    await expect(bridge.addTokenMapping(localTokenAddress, remoteToken.address))
      .to.emit(bridge, "TokenMappingAdded")
      .withArgs(localTokenAddress, remoteToken.address);

    expect(await bridge.tokenMapping(localTokenAddress)).to.equal(remoteToken.address);

    await expect(
      bridge.connect(nonAdmin).removeTokenMapping(localTokenAddress)
    ).to.be.revertedWith("Bridge: not admin");

    await expect(bridge.removeTokenMapping(localTokenAddress))
      .to.emit(bridge, "TokenMappingRemoved")
      .withArgs(localTokenAddress, remoteToken.address);

    expect(await bridge.tokenMapping(localTokenAddress)).to.equal(ethers.ZeroAddress);
  });

  it("locks mapped tokens and binds the remote token into the transfer hash", async function () {
    const localTokenAddress = await localToken.getAddress();
    await bridge.addTokenMapping(localTokenAddress, remoteToken.address);

    const tx = await bridge.connect(user).lock(localTokenAddress, recipient.address, bridgeAmount);
    const receipt = await tx.wait();
    const locked = findEvent(receipt, bridge, "TokensLocked");
    const expectedTransferId = transferHash(
      localTokenAddress,
      remoteToken.address,
      user.address,
      recipient.address,
      bridgeAmount,
      1n
    );

    expect(locked.args.transferId).to.equal(expectedTransferId);
    expect(locked.args.token).to.equal(localTokenAddress);
    expect(locked.args.sender).to.equal(user.address);
    expect(locked.args.recipient).to.equal(recipient.address);
    expect(locked.args.amount).to.equal(bridgeAmount);

    const transfer = await bridge.transfers(expectedTransferId);
    expect(transfer.token).to.equal(localTokenAddress);
    expect(transfer.remoteToken).to.equal(remoteToken.address);
    expect(transfer.sender).to.equal(user.address);
    expect(transfer.recipient).to.equal(recipient.address);
    expect(transfer.amount).to.equal(bridgeAmount);
    expect(transfer.nonce).to.equal(1n);
    expect(transfer.claimed).to.equal(false);
  });

  it("claims mapped tokens only with a signature bound to the mapped remote token", async function () {
    const localTokenAddress = await localToken.getAddress();
    const bridgeAddress = await bridge.getAddress();
    await bridge.addTokenMapping(localTokenAddress, remoteToken.address);
    await localToken.mint(bridgeAddress, bridgeAmount);

    const oldHash = ethers.solidityPackedKeccak256(
      ["address", "address", "uint256"],
      [localTokenAddress, recipient.address, bridgeAmount]
    );
    const oldSignature = await validator.signMessage(ethers.getBytes(oldHash));

    await expect(
      bridge.claim(localTokenAddress, recipient.address, bridgeAmount, [oldSignature])
    ).to.be.reverted;

    const messageHash = claimHash(localTokenAddress, remoteToken.address, recipient.address, bridgeAmount);
    const signature = await validator.signMessage(ethers.getBytes(messageHash));

    await expect(bridge.claim(localTokenAddress, recipient.address, bridgeAmount, [signature]))
      .to.emit(bridge, "TokensClaimed")
      .withArgs(messageHash, localTokenAddress, recipient.address, bridgeAmount);

    expect(await bridge.processedHashes(messageHash)).to.equal(true);
    expect(await localToken.balanceOf(recipient.address)).to.equal(bridgeAmount);
  });
});
