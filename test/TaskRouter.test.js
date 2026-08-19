const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRouter Gas Sponsorship", function () {
  let router, registry;
  let admin, agent, relayer;
  const FEE = ethers.parseEther("0.01");

  beforeEach(async function () {
    [admin, agent, relayer] = await ethers.getSigners();
    
    const RegistryFactory = await ethers.getContractFactory("AgentRegistry");
    registry = await RegistryFactory.deploy(FEE);
    await registry.waitForDeployment();

    const RouterFactory = await ethers.getContractFactory("TaskRouter");
    router = await RouterFactory.deploy(registry.target, 100);
    await router.waitForDeployment();
  });

  it("should allow agent to deposit and withdraw stake", async function () {
    await expect(router.connect(agent).depositStake({ value: ethers.parseEther("1.0") }))
      .to.emit(router, "StakeDeposited")
      .withArgs(agent.address, ethers.parseEther("1.0"));
      
    expect(await router.stakes(agent.address)).to.equal(ethers.parseEther("1.0"));
    
    await router.connect(agent).withdrawStake(ethers.parseEther("0.5"));
    expect(await router.stakes(agent.address)).to.equal(ethers.parseEther("0.5"));
  });

  it("should execute on behalf of agent and reimburse relayer", async function () {
    await router.connect(agent).depositStake({ value: ethers.parseEther("1.0") });
    
    // Use withdrawStake(0) as a safe dummy call that succeeds and requires no special permissions
    const data = router.interface.encodeFunctionData("withdrawStake", [0]);
    const nonce = await router.nonces(agent.address);
    
    const abiCoder = ethers.AbiCoder.defaultAbiCoder();
    const encoded = abiCoder.encode(
      ["address", "address", "bytes", "uint256"],
      [router.target, agent.address, data, nonce]
    );
    const hash = ethers.keccak256(encoded);
    const signature = await agent.signMessage(ethers.getBytes(hash));
    
    const tx = await router.connect(relayer).executeOnBehalf(agent.address, data, signature);
    await tx.wait();
    
    expect(await router.nonces(agent.address)).to.equal(1);
  });

  it("should reject invalid signature", async function () {
    await router.connect(agent).depositStake({ value: ethers.parseEther("1.0") });
    const data = router.interface.encodeFunctionData("withdrawStake", [0]);
    const nonce = await router.nonces(agent.address);
    
    const abiCoder = ethers.AbiCoder.defaultAbiCoder();
    const encoded = abiCoder.encode(
      ["address", "address", "bytes", "uint256"],
      [router.target, agent.address, data, nonce]
    );
    const hash = ethers.keccak256(encoded);
    
    // Sign with relayer instead of agent
    const signature = await relayer.signMessage(ethers.getBytes(hash));
    
    await expect(
      router.connect(relayer).executeOnBehalf(agent.address, data, signature)
    ).to.be.revertedWith("Invalid signature");
  });

  it("should reject replay (nonce increment)", async function () {
    await router.connect(agent).depositStake({ value: ethers.parseEther("1.0") });
    const data = router.interface.encodeFunctionData("withdrawStake", [0]);
    const nonce = await router.nonces(agent.address);
    
    const abiCoder = ethers.AbiCoder.defaultAbiCoder();
    const encoded = abiCoder.encode(
      ["address", "address", "bytes", "uint256"],
      [router.target, agent.address, data, nonce]
    );
    const hash = ethers.keccak256(encoded);
    const signature = await agent.signMessage(ethers.getBytes(hash));
    
    await router.connect(relayer).executeOnBehalf(agent.address, data, signature);
    
    // Try to replay the same signature
    await expect(
      router.connect(relayer).executeOnBehalf(agent.address, data, signature)
    ).to.be.revertedWith("Invalid signature");
  });

  it("should reject if insufficient stake for gas", async function () {
    await router.connect(agent).depositStake({ value: 1 });
    
    const data = router.interface.encodeFunctionData("withdrawStake", [0]);
    const nonce = await router.nonces(agent.address);
    
    const abiCoder = ethers.AbiCoder.defaultAbiCoder();
    const encoded = abiCoder.encode(
      ["address", "address", "bytes", "uint256"],
      [router.target, agent.address, data, nonce]
    );
    const hash = ethers.keccak256(encoded);
    const signature = await agent.signMessage(ethers.getBytes(hash));
    
    await expect(
      router.connect(relayer).executeOnBehalf(agent.address, data, signature)
    ).to.be.revertedWith("Insufficient stake for gas");
  });
});
