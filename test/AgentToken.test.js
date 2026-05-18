const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentToken — #162 Permit Replay Across Forks", function () {
  let agentToken;
  let owner, spender, holder;
  const NAME = "AgentToken";
  const SYMBOL = "AGENT";
  const INITIAL_SUPPLY = ethers.parseEther("1000000");

  beforeEach(async function () {
    [owner, spender, holder] = await ethers.getSigners();
    const AgentToken = await ethers.getContractFactory("AgentToken");
    agentToken = await AgentToken.deploy(NAME, SYMBOL, INITIAL_SUPPLY);
    await agentToken.waitForDeployment();
  });

  describe("DOMAIN_SEPARATOR()", function () {
    it("should return a non-zero bytes32", async function () {
      const separator = await agentToken.DOMAIN_SEPARATOR();
      expect(separator).to.not.equal(ethers.ZeroHash);
    });

    it("should return consistent values within the same chain ID", async function () {
      const sep1 = await agentToken.DOMAIN_SEPARATOR();
      const sep2 = await agentToken.DOMAIN_SEPARATOR();
      expect(sep1).to.equal(sep2);
    });

    it("should change when chain ID changes (fork simulation)", async function () {
      const oldSeparator = await agentToken.DOMAIN_SEPARATOR();

      // Simulate a chain fork by changing the chain ID
      await ethers.provider.send("hardhat_setChainId", [8453]); // Base chain ID as example fork

      const newSeparator = await agentToken.DOMAIN_SEPARATOR();
      expect(newSeparator).to.not.equal(oldSeparator);
      expect(newSeparator).to.not.equal(ethers.ZeroHash);

      // After returning to original chain ID, separator should be original again
      await ethers.provider.send("hardhat_setChainId", [31337]);
      const restoredSeparator = await agentToken.DOMAIN_SEPARATOR();
      expect(restoredSeparator).to.equal(oldSeparator);
    });

    it("should include chain ID in domain separator computation", async function () {
      // Verify the separator encodes the domain correctly by checking
      // that different chain IDs produce different separators
      const sep31337 = await agentToken.DOMAIN_SEPARATOR();

      await ethers.provider.send("hardhat_setChainId", [1]);
      const sep1 = await agentToken.DOMAIN_SEPARATOR();
      expect(sep1).to.not.equal(sep31337);

      await ethers.provider.send("hardhat_setChainId", [137]);
      const sep137 = await agentToken.DOMAIN_SEPARATOR();
      expect(sep137).to.not.equal(sep31337);
      expect(sep137).to.not.equal(sep1);

      // Restore
      await ethers.provider.send("hardhat_setChainId", [31337]);
    });
  });

  describe("permit() with domain separator", function () {
    it("should accept a valid permit on the current chain", async function () {
      const value = ethers.parseEther("100");
      const deadline = Math.floor(Date.now() / 1000) + 3600; // 1 hour from now

      // Build the EIP-712 domain
      const domain = {
        name: NAME,
        version: "1",
        chainId: 31337,
        verifyingContract: await agentToken.getAddress(),
      };

      // Build the Permit type
      const types = {
        Permit: [
          { name: "owner", type: "address" },
          { name: "spender", type: "address" },
          { name: "value", type: "uint256" },
          { name: "nonce", type: "uint256" },
          { name: "deadline", type: "uint256" },
        ],
      };

      const nonce = await agentToken.nonces(holder.address);
      const message = {
        owner: holder.address,
        spender: spender.address,
        value: value,
        nonce: nonce,
        deadline: deadline,
      };

      // Sign the typed data
      const signature = await holder.signTypedData(domain, types, message);
      const sig = ethers.Signature.from(signature);

      await agentToken.permit(
        holder.address,
        spender.address,
        value,
        deadline,
        sig.v,
        sig.r,
        sig.s
      );

      const allowance = await agentToken.allowance(holder.address, spender.address);
      expect(allowance).to.equal(value);
    });

    it("should reject a permit signed on a different chain ID (fork)", async function () {
      const value = ethers.parseEther("100");
      const deadline = Math.floor(Date.now() / 1000) + 3600;

      // Sign the permit on chain 31337
      const domain31337 = {
        name: NAME,
        version: "1",
        chainId: 31337,
        verifyingContract: await agentToken.getAddress(),
      };

      const types = {
        Permit: [
          { name: "owner", type: "address" },
          { name: "spender", type: "address" },
          { name: "value", type: "uint256" },
          { name: "nonce", type: "uint256" },
          { name: "deadline", type: "uint256" },
        ],
      };

      const nonce = await agentToken.nonces(holder.address);
      const message = {
        owner: holder.address,
        spender: spender.address,
        value: value,
        nonce: nonce,
        deadline: deadline,
      };

      const signature = await holder.signTypedData(domain31337, types, message);
      const sig = ethers.Signature.from(signature);

      // Now simulate a fork — change chain ID
      await ethers.provider.send("hardhat_setChainId", [8453]);

      // The DOMAIN_SEPARATOR should now be different
      const newSeparator = await agentToken.DOMAIN_SEPARATOR();

      // The old signature should be REJECTED because the domain separator
      // no longer matches
      await expect(
        agentToken.permit(
          holder.address,
          spender.address,
          value,
          deadline,
          sig.v,
          sig.r,
          sig.s
        )
      ).to.be.revertedWith("AgentToken: invalid signature");

      // Restore chain ID
      await ethers.provider.send("hardhat_setChainId", [31337]);
    });
  });
});
