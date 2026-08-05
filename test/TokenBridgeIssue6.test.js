const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TokenBridge issue #6", function () {
  let bridge;
  let token;
  let admin;
  let sender;
  let recipient;
  let validator1;
  let validator2;

  const AMOUNT = ethers.parseEther("100");
  const TYPES = {
    BridgeTransfer: [
      { name: "token", type: "address" },
      { name: "sender", type: "address" },
      { name: "recipient", type: "address" },
      { name: "amount", type: "uint256" },
      { name: "nonce", type: "uint256" },
    ],
  };

  beforeEach(async function () {
    [admin, sender, recipient, validator1, validator2] = await ethers.getSigners();

    const TestToken = await ethers.getContractFactory("TokenBridgeTestToken");
    token = await TestToken.deploy("Bridge Token", "BRG");
    await token.waitForDeployment();

    const TokenBridge = await ethers.getContractFactory("TokenBridge");
    bridge = await TokenBridge.deploy(2);
    await bridge.waitForDeployment();

    await bridge.addValidator(validator1.address);
    await bridge.addValidator(validator2.address);
    await token.mint(sender.address, AMOUNT * 2n);
    await token.mint(await bridge.getAddress(), AMOUNT * 4n);
  });

  async function domain(overrides = {}) {
    const network = await ethers.provider.getNetwork();
    return {
      name: "TokenBridge",
      version: "1",
      chainId: network.chainId,
      verifyingContract: await bridge.getAddress(),
      ...overrides,
    };
  }

  async function transferValue(nonce = 0n) {
    return {
      token: await token.getAddress(),
      sender: sender.address,
      recipient: recipient.address,
      amount: AMOUNT,
      nonce,
    };
  }

  async function sortedSignatures(value, domainOverrides = {}) {
    const typedDomain = await domain(domainOverrides);
    const signatures = [];
    for (const signer of [validator1, validator2]) {
      const signature = await signer.signTypedData(typedDomain, TYPES, value);
      const recovered = ethers.verifyTypedData(typedDomain, TYPES, value, signature);
      signatures.push({ recovered, signature });
    }
    return signatures
      .sort((left, right) => BigInt(left.recovered) < BigInt(right.recovered) ? -1 : 1)
      .map((entry) => entry.signature);
  }

  it("uses an EIP-712 domain separator with chain and verifying contract", async function () {
    const expectedDomainSeparator = ethers.TypedDataEncoder.hashDomain(await domain());

    expect(await bridge.DOMAIN_SEPARATOR()).to.equal(expectedDomainSeparator);
  });

  it("includes chain, contract, and nonce in the transfer digest", async function () {
    const value0 = await transferValue(0n);
    const value1 = await transferValue(1n);
    const expectedDigest0 = ethers.TypedDataEncoder.hash(await domain(), TYPES, value0);
    const expectedDigest1 = ethers.TypedDataEncoder.hash(await domain(), TYPES, value1);

    expect(await bridge.getTransferDigest(
      value0.token,
      value0.sender,
      value0.recipient,
      value0.amount,
      value0.nonce
    )).to.equal(expectedDigest0);
    expect(expectedDigest0).to.not.equal(expectedDigest1);
  });

  it("prevents same-chain replay by processing each digest once", async function () {
    const value = await transferValue(0n);
    const signatures = await sortedSignatures(value);

    await bridge.claim(value.token, value.sender, value.recipient, value.amount, value.nonce, signatures);

    await expect(
      bridge.claim(value.token, value.sender, value.recipient, value.amount, value.nonce, signatures)
    ).to.be.revertedWith("Bridge: already processed");
  });

  it("rejects signatures from another EIP-712 chain domain", async function () {
    const value = await transferValue(0n);
    const signatures = await sortedSignatures(value, { chainId: 99999n });

    await expect(
      bridge.claim(value.token, value.sender, value.recipient, value.amount, value.nonce, signatures)
    ).to.be.revertedWith("Bridge: not enough valid sigs");
  });

  it("rejects zero-address signature recovery", async function () {
    const value = await transferValue(0n);
    const zeroSignature = `0x${"00".repeat(65)}`;

    await expect(
      bridge.claim(value.token, value.sender, value.recipient, value.amount, value.nonce, [zeroSignature, zeroSignature])
    ).to.be.revertedWith("Bridge: invalid signature");
  });

  it("uses per-sender nonces for repeated locks", async function () {
    await token.connect(sender).approve(await bridge.getAddress(), AMOUNT * 2n);

    await expect(bridge.connect(sender).lock(await token.getAddress(), recipient.address, AMOUNT))
      .to.emit(bridge, "TokensLocked")
      .withArgs(await bridge.getTransferDigest(await token.getAddress(), sender.address, recipient.address, AMOUNT, 0n), await token.getAddress(), sender.address, recipient.address, AMOUNT, 0n);

    await expect(bridge.connect(sender).lock(await token.getAddress(), recipient.address, AMOUNT))
      .to.emit(bridge, "TokensLocked")
      .withArgs(await bridge.getTransferDigest(await token.getAddress(), sender.address, recipient.address, AMOUNT, 1n), await token.getAddress(), sender.address, recipient.address, AMOUNT, 1n);

    expect(await bridge.nonces(sender.address)).to.equal(2n);
  });
});
