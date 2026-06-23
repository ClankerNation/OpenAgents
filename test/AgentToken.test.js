const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentToken", function () {
  let token, owner, user1, user2;

  beforeEach(async function () {
    [owner, user1, user2] = await ethers.getSigners();

    const Token = await ethers.getContractFactory("AgentToken");
    token = await Token.deploy("Agent Token", "AGT", ethers.utils.parseEther("1000000"));
    await token.deployed();
  });

  describe("DOMAIN_SEPARATOR", function () {
    it("should return a valid domain separator", async function () {
      const sep = await token.DOMAIN_SEPARATOR();
      expect(sep).to.not.equal(ethers.constants.AddressZero);
    });

    it("should be a valid 32-byte hash", async function () {
      const sep = await token.DOMAIN_SEPARATOR();
      expect(sep).to.have.lengthOf(66); // 32 bytes as hex string
    });
  });

  describe("Permit with deadline", function () {
    it("should reject expired permits", async function () {
      const spender = user2.address;
      const value = ethers.utils.parseEther("100");
      const deadline = 1000;

      const chainId = (await ethers.provider.getNetwork()).chainId;
      const verifyingContract = token.address;

      const domain = {
        name: "Agent Token",
        version: "1",
        chainId: chainId,
        verifyingContract: verifyingContract,
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

      const message = {
        owner: user1.address,
        spender: spender,
        value: value,
        nonce: 0,
        deadline: deadline,
      };

      const signature = await user1.signTypedData(domain, types, message);
      const { v, r, s } = ethers.utils.splitSignature(signature);

      await expect(token.connect(user1).permit(
        user1.address, spender, value, deadline, v, r, s
      )).to.be.revertedWith("AgentToken: permit expired");
    });

    it("should accept valid permit", async function () {
      const spender = user2.address;
      const value = ethers.utils.parseEther("100");
      const deadline = ethers.utils.parseEther("10000000000").toNumber();

      const chainId = (await ethers.provider.getNetwork()).chainId;
      const verifyingContract = token.address;

      const domain = {
        name: "Agent Token",
        version: "1",
        chainId: chainId,
        verifyingContract: verifyingContract,
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

      const message = {
        owner: user1.address,
        spender: spender,
        value: value,
        nonce: 0,
        deadline: deadline,
      };

      const signature = await user1.signTypedData(domain, types, message);
      const { v, r, s } = ethers.utils.splitSignature(signature);

      await token.connect(user1).permit(
        user1.address, spender, value, deadline, v, r, s
      );

      const allowance = await token.allowance(user1.address, spender);
      expect(allowance).to.equal(value);
    });

    it("should increment nonce after permit", async function () {
      const spender = user2.address;
      const value = ethers.utils.parseEther("100");
      const deadline = ethers.utils.parseEther("10000000000").toNumber();

      const chainId = (await ethers.provider.getNetwork()).chainId;
      const verifyingContract = token.address;

      const domain = {
        name: "Agent Token",
        version: "1",
        chainId: chainId,
        verifyingContract: verifyingContract,
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

      const message = {
        owner: user1.address,
        spender: spender,
        value: value,
        nonce: 0,
        deadline: deadline,
      };

      const signature = await user1.signTypedData(domain, types, message);
      const { v, r, s } = ethers.utils.splitSignature(signature);

      await token.connect(user1).permit(
        user1.address, spender, value, deadline, v, r, s
      );

      expect(await token.nonces(user1.address)).to.equal(1);
    });
  });

  describe("Mint access control", function () {
    it("should restrict mint to owner only", async function () {
      await expect(token.connect(user1).mint(user1.address, ethers.utils.parseEther("100")))
        .to.be.revertedWith("AgentToken: not owner");
    });

    it("should allow owner to mint", async function () {
      await token.connect(owner).mint(user1.address, ethers.utils.parseEther("1000"));
      expect(await token.balanceOf(user1.address)).to.equal(ethers.utils.parseEther("1000"));
    });
  });
});
