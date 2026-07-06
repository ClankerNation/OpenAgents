const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TokenBridge", function () {
  let bridge, token;
  let admin, user, validator1, validator2, validator3;
  let chainId;

  const AMOUNT = ethers.parseEther("100");

  // Sign EIP-712 typed data for the bridge's claim
  async function signClaim(signer, bridgeAddr, tokenAddr, senderAddr, recipientAddr, amount, nonce) {
    const domain = {
      name: "TokenBridge",
      version: "1",
      chainId: chainId,
      verifyingContract: bridgeAddr,
    };
    const types = {
      Transfer: [
        { name: "token", type: "address" },
        { name: "sender", type: "address" },
        { name: "recipient", type: "address" },
        { name: "amount", type: "uint256" },
        { name: "nonce", type: "uint256" },
      ],
    };
    const value = {
      token: tokenAddr,
      sender: senderAddr,
      recipient: recipientAddr,
      amount: amount,
      nonce: nonce,
    };
    return await signer.signTypedData(domain, types, value);
  }

  beforeEach(async function () {
    [admin, user, validator1, validator2, validator3] = await ethers.getSigners();
    chainId = (await ethers.provider.getNetwork()).chainId;

    const MockToken = await ethers.getContractFactory("MockToken");
    token = await MockToken.deploy("Test Token", "TST");
    await token.waitForDeployment();

    const Bridge = await ethers.getContractFactory("TokenBridge");
    bridge = await Bridge.deploy(2); // require 2 signatures
    await bridge.waitForDeployment();

    // Add validators
    await bridge.addValidator(validator1.address);
    await bridge.addValidator(validator2.address);
    await bridge.addValidator(validator3.address);

    // Mint tokens to user
    await token.mint(user.address, ethers.parseEther("10000"));
    await token.mint(admin.address, ethers.parseEther("10000"));
    // Mint tokens to bridge so it can pay claims
    await token.mint(bridge.target, ethers.parseEther("10000"));
  });

  // ── lock() tests ──────────────────────────────────────────

  it("should lock tokens and emit event with nonce", async function () {
    await token.connect(user).approve(bridge.target, AMOUNT);

    const nonce = await bridge.nonces(user.address);
    const tx = await bridge.connect(user).lock(token.target, user.address, AMOUNT);
    const receipt = await tx.wait();

    const iface = bridge.interface;
    const events = [];
    for (const log of receipt.logs) {
      try {
        const parsed = iface.parseLog({ topics: [...log.topics], data: log.data });
        if (parsed && parsed.name === "TokensLocked") {
          events.push(parsed.args);
        }
      } catch(e) {}
    }

    expect(events.length).to.equal(1);
    expect(events[0].token).to.equal(token.target);
    expect(events[0].sender).to.equal(user.address);
    expect(events[0].recipient).to.equal(user.address);
    expect(events[0].amount).to.equal(AMOUNT);
    expect(events[0].nonce).to.equal(nonce);
  });

  it("should increment nonce after each lock", async function () {
    await token.connect(user).approve(bridge.target, AMOUNT * 2n);

    const nonce0 = await bridge.nonces(user.address);
    await bridge.connect(user).lock(token.target, user.address, AMOUNT);
    const nonce1 = await bridge.nonces(user.address);
    expect(nonce1 - nonce0).to.equal(1n);

    await bridge.connect(user).lock(token.target, user.address, AMOUNT);
    const nonce2 = await bridge.nonces(user.address);
    expect(nonce2 - nonce1).to.equal(1n);
  });

  it("should produce different transferIds for same params", async function () {
    await token.connect(user).approve(bridge.target, AMOUNT * 2n);

    // Need to capture event args to get transferId
    const iface = bridge.interface;
    const ids = [];
    for (let i = 0; i < 2; i++) {
      const tx = await bridge.connect(user).lock(token.target, user.address, AMOUNT);
      const receipt = await tx.wait();
      for (const log of receipt.logs) {
        try {
          const parsed = iface.parseLog({ topics: [...log.topics], data: log.data });
          if (parsed && parsed.name === "TokensLocked") {
            ids.push(parsed.args.transferId);
          }
        } catch(e) {}
      }
    }
    expect(ids[0]).to.not.equal(ids[1]);
  });

  it("should revert on zero amount lock", async function () {
    await expect(
      bridge.connect(user).lock(token.target, user.address, 0)
    ).to.be.revertedWith("Bridge: zero amount");
  });

  // ── claim() tests ─────────────────────────────────────────

  it("should claim tokens with 2 valid signatures", async function () {
    await token.connect(user).approve(bridge.target, AMOUNT);
    await bridge.connect(user).lock(token.target, user.address, AMOUNT);

    const nonce = await bridge.nonces(user.address);
    // nonce was incremented, so use the previous nonce
    const lockNonce = nonce - 1n;

    const sig1 = await signClaim(validator1, bridge.target, token.target, user.address, user.address, AMOUNT, lockNonce);
    const sig2 = await signClaim(validator2, bridge.target, token.target, user.address, user.address, AMOUNT, lockNonce);

    await expect(
      bridge.connect(user).claim(token.target, user.address, user.address, AMOUNT, lockNonce, [sig1, sig2])
    ).to.not.be.reverted;
  });

  it("should revert with insufficient signatures", async function () {
    await token.connect(user).approve(bridge.target, AMOUNT);
    await bridge.connect(user).lock(token.target, user.address, AMOUNT);

    const nonce = await bridge.nonces(user.address);
    const lockNonce = nonce - 1n;
    const sig1 = await signClaim(validator1, bridge.target, token.target, user.address, user.address, AMOUNT, lockNonce);

    await expect(
      bridge.connect(user).claim(token.target, user.address, user.address, AMOUNT, lockNonce, [sig1])
    ).to.be.revertedWith("Bridge: insufficient sigs");
  });

  it("should revert with invalid signature (ecrecover zero)", async function () {
    await token.connect(user).approve(bridge.target, AMOUNT);
    await bridge.connect(user).lock(token.target, user.address, AMOUNT);

    const nonce = await bridge.nonces(user.address);
    const lockNonce = nonce - 1n;

    // Create a fake 65-byte signature that recovers to address(0)
    const fakeSig = "0x" + "00".repeat(65);

    await expect(
      bridge.connect(user).claim(
        token.target, user.address, user.address, AMOUNT, lockNonce,
        [fakeSig, fakeSig]
      )
    ).to.be.revertedWith("Bridge: invalid signature");
  });

  it("should revert on double claim (replay protection)", async function () {
    await token.connect(user).approve(bridge.target, AMOUNT);
    await bridge.connect(user).lock(token.target, user.address, AMOUNT);

    const nonce = await bridge.nonces(user.address);
    const lockNonce = nonce - 1n;
    const sig1 = await signClaim(validator1, bridge.target, token.target, user.address, user.address, AMOUNT, lockNonce);
    const sig2 = await signClaim(validator2, bridge.target, token.target, user.address, user.address, AMOUNT, lockNonce);

    // First claim
    await bridge.connect(user).claim(token.target, user.address, user.address, AMOUNT, lockNonce, [sig1, sig2]);

    // Second claim should fail
    await expect(
      bridge.connect(user).claim(token.target, user.address, user.address, AMOUNT, lockNonce, [sig1, sig2])
    ).to.be.revertedWith("Bridge: already processed");
  });

  // ── cross-chain replay protection tests ───────────────────

  it("should produce different digests for different chain IDs", async function () {
    // Simulate a different chain by creating a bridge with same address
    // but different chainId in the EIP-712 domain
    // We test this conceptually: signatures from chain A shouldn't work on chain B
    await token.connect(user).approve(bridge.target, AMOUNT);
    await bridge.connect(user).lock(token.target, user.address, AMOUNT);

    const nonce = await bridge.nonces(user.address);
    const lockNonce = nonce - 1n;

    // Sign with a DIFFERENT chainId (simulating cross-chain)
    const fakeDomain = {
      name: "TokenBridge",
      version: "1",
      chainId: 99999, // different chain!
      verifyingContract: bridge.target,
    };
    const types = {
      Transfer: [
        { name: "token", type: "address" },
        { name: "sender", type: "address" },
        { name: "recipient", type: "address" },
        { name: "amount", type: "uint256" },
        { name: "nonce", type: "uint256" },
      ],
    };
    const value = {
      token: token.target,
      sender: user.address,
      recipient: user.address,
      amount: AMOUNT,
      nonce: lockNonce,
    };
    const crossChainSig = await validator1.signTypedData(fakeDomain, types, value);
    const validSig = await signClaim(validator2, bridge.target, token.target, user.address, user.address, AMOUNT, lockNonce);

    // Cross-chain signature should be rejected
    await expect(
      bridge.connect(user).claim(token.target, user.address, user.address, AMOUNT, lockNonce, [crossChainSig, validSig])
    ).to.be.revertedWith("Bridge: not enough valid sigs");
  });

  // ── EIP-712 domain separator test ─────────────────────────

  it("should have correct domain separator", async function () {
    const sep = await bridge.DOMAIN_SEPARATOR();
    expect(sep).to.not.equal(ethers.ZeroHash);
  });

  // ── duplicate/out-of-order signatures ─────────────────────

  it("should revert on duplicate signatures", async function () {
    await token.connect(user).approve(bridge.target, AMOUNT);
    await bridge.connect(user).lock(token.target, user.address, AMOUNT);

    const nonce = await bridge.nonces(user.address);
    const lockNonce = nonce - 1n;
    const sig1 = await signClaim(validator1, bridge.target, token.target, user.address, user.address, AMOUNT, lockNonce);

    await expect(
      bridge.connect(user).claim(token.target, user.address, user.address, AMOUNT, lockNonce, [sig1, sig1])
    ).to.be.revertedWith("Bridge: duplicate or unordered sig");
  });

  it("should revert on unordered signatures", async function () {
    await token.connect(user).approve(bridge.target, AMOUNT);
    await bridge.connect(user).lock(token.target, user.address, AMOUNT);

    const nonce = await bridge.nonces(user.address);
    const lockNonce = nonce - 1n;
    const sig2 = await signClaim(validator2, bridge.target, token.target, user.address, user.address, AMOUNT, lockNonce);
    const sig1 = await signClaim(validator1, bridge.target, token.target, user.address, user.address, AMOUNT, lockNonce);

    // validator2 > validator1, so [sig2, sig1] fails because sig2's signer > sig1's signer
    await expect(
      bridge.connect(user).claim(token.target, user.address, user.address, AMOUNT, lockNonce, [sig2, sig1])
    ).to.be.revertedWith("Bridge: duplicate or unordered sig");
  });

  // ── validator management ──────────────────────────────────

  it("should add and remove validators", async function () {
    const newVal = ethers.Wallet.createRandom().address;
    await bridge.addValidator(newVal);
    expect(await bridge.isValidator(newVal)).to.be.true;

    await bridge.removeValidator(newVal);
    expect(await bridge.isValidator(newVal)).to.be.false;
  });

  it("should revert when non-admin adds validator", async function () {
    await expect(
      bridge.connect(user).addValidator(user.address)
    ).to.be.revertedWith("Bridge: not admin");
  });
});
