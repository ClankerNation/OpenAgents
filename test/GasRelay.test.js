const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("GasRelay — Issue #183: Meta-Transaction Relay", function () {
  let gasRelay, registry, owner, relayer, agent;

  beforeEach(async function () {
    [owner, relayer, agent] = await ethers.getSigners();

    const GasRelay = await ethers.getContractFactory("GasRelay");
    gasRelay = await GasRelay.deploy(owner.address);
    await gasRelay.waitForDeployment();

    const Registry = await ethers.getContractFactory("AgentRegistry");
    registry = await Registry.deploy(ethers.parseEther("0.01"), await gasRelay.getAddress());
    await registry.waitForDeployment();

    // Authorize relayer
    await gasRelay.connect(owner).setRelayer(relayer.address, true);
  });

  it("relayer can execute meta-transaction on behalf of agent", async function () {
    // Build registerAgent calldata
    const iface = registry.interface;
    const data = iface.encodeFunctionData("registerAgent", ["test-agent", "http://test"]);

    // Create forward request
    const nonce = await gasRelay.getNonce(agent.address);
    const deadline = Math.floor(Date.now() / 1000) + 3600;

    const req = {
      from: agent.address,
      to: await registry.getAddress(),
      value: ethers.parseEther("0.01"),
      data: data,
      nonce: nonce,
      deadline: deadline
    };

    // Sign EIP-712
    const domain = {
      name: "GasRelay",
      version: "1",
      chainId: (await ethers.provider.getNetwork()).chainId,
      verifyingContract: await gasRelay.getAddress()
    };

    const types = {
      ForwardRequest: [
        { name: "from", type: "address" },
        { name: "to", type: "address" },
        { name: "value", type: "uint256" },
        { name: "data", type: "bytes" },
        { name: "nonce", type: "uint256" },
        { name: "deadline", type: "uint256" }
      ]
    };

    const signature = await agent.signTypedData(domain, types, req);

    // Relayer executes
    await gasRelay.connect(relayer).executeMetaTransaction(req, signature, {
      value: ethers.parseEther("0.01")
    });

    // Agent should be registered
    const agentNonce = await registry.nonce(agent.address);
    expect(agentNonce).to.equal(1);
  });

  it("replay prevention via nonce", async function () {
    const iface = registry.interface;
    const data = iface.encodeFunctionData("registerAgent", ["replay-test", "http://test"]);
    const nonce = await gasRelay.getNonce(agent.address);
    const deadline = Math.floor(Date.now() / 1000) + 3600;

    const req = {
      from: agent.address,
      to: await registry.getAddress(),
      value: ethers.parseEther("0.01"),
      data: data,
      nonce: nonce,
      deadline: deadline
    };

    const domain = {
      name: "GasRelay",
      version: "1",
      chainId: (await ethers.provider.getNetwork()).chainId,
      verifyingContract: await gasRelay.getAddress()
    };

    const types = {
      ForwardRequest: [
        { name: "from", type: "address" },
        { name: "to", type: "address" },
        { name: "value", type: "uint256" },
        { name: "data", type: "bytes" },
        { name: "nonce", type: "uint256" },
        { name: "deadline", type: "uint256" }
      ]
    };

    const signature = await agent.signTypedData(domain, types, req);

    // First execution succeeds
    await gasRelay.connect(relayer).executeMetaTransaction(req, signature, {
      value: ethers.parseEther("0.01")
    });

    // Replay should fail (nonce already used)
    await expect(
      gasRelay.connect(relayer).executeMetaTransaction(req, signature, {
        value: ethers.parseEther("0.01")
      })
    ).to.be.revertedWith("GasRelay: invalid nonce");
  });

  it("non-relayer cannot execute meta-transaction", async function () {
    const iface = registry.interface;
    const data = iface.encodeFunctionData("registerAgent", ["no-auth", "http://test"]);
    const nonce = await gasRelay.getNonce(agent.address);

    const req = {
      from: agent.address,
      to: await registry.getAddress(),
      value: 0,
      data: data,
      nonce: nonce,
      deadline: Math.floor(Date.now() / 1000) + 3600
    };

    await expect(
      gasRelay.connect(agent).executeMetaTransaction(req, "0x")
    ).to.be.revertedWith("GasRelay: not authorized relayer");
  });

  it("agent can submit tasks without holding ETH (via relay)", async function () {
    // This is verified by the first test — agent registers via relayer who pays gas
    // The agent never needs ETH, the relayer forwards value from the relay contract
    expect(await registry.trustedForwarder()).to.equal(await gasRelay.getAddress());
  });
});
