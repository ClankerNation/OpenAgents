const { expect } = require("chai")
const { ethers } = require("hardhat")

const THRESHOLD = ethers.parseEther("100000")
const QUORUM = ethers.parseEther("40000000")

async function deploy() {
  const [admin, voter, other] = await ethers.getSigners()

  const Token = await ethers.getContractFactory("GovernanceToken")
  const token = await Token.deploy()

  const Governor = await ethers.getContractFactory("GovernorAlpha")
  const governor = await Governor.deploy(await token.getAddress())

  // Trivial payload that always succeeds: transfer 0 tokens to the admin.
  const targets = [await token.getAddress()]
  const values = [0]
  const calldatas = [token.interface.encodeFunctionData("transfer", [admin.address, 0])]

  await token.transfer(voter.address, ethers.parseEther("30000000"))
  await token.transfer(other.address, ethers.parseEther("30000000"))
  await token.connect(voter).delegate(voter.address)
  await token.connect(other).delegate(other.address)
  await token.connect(admin).delegate(admin.address)

  return { admin, voter, other, token, governor, targets, values, calldatas }
}

async function proposeAndVote(ctx, votes) {
  const { voter, token, governor, targets, values, calldatas } = ctx
  await governor.connect(voter).propose(targets, values, calldatas)
  const id = await governor.proposalCount()

  const start = (await governor.proposals(id)).startBlock
  await ethers.provider.send("hardhat_mine", ["0x2"])

  await governor.connect(voter).vote(id, true)
  const end = (await governor.proposals(id)).endBlock
  const head = await ethers.provider.getBlockNumber()
  await ethers.provider.send("hardhat_mine", ["0x" + (Number(end) - head + 1).toString(16)])
  return id
}

describe("GovernorAlpha quorum", function () {
  it("reverts execution when forVotes are below quorum", async function () {
    const ctx = await deploy()
    // voter holds 30M: above the 100k proposal threshold, below the 40M quorum
    const id = await proposeAndVote(ctx, 0)
    await expect(ctx.governor.execute(id)).to.be.revertedWith("Governor: quorum not reached")
  })

  it("executes at exactly quorum", async function () {
    const ctx = await deploy()
    await ctx.governor.connect(ctx.admin).setQuorum(ethers.parseEther("30000000"))
    const id = await proposeAndVote(ctx, 0)
    await expect(ctx.governor.execute(id)).to.emit(ctx.governor, "ProposalExecuted")
    expect((await ctx.governor.proposals(id)).executed).to.equal(true)
  })

  it("executes above quorum", async function () {
    const ctx = await deploy()
    await ctx.governor.connect(ctx.admin).setQuorum(ethers.parseEther("1000"))
    const id = await proposeAndVote(ctx, 0)
    await expect(ctx.governor.execute(id)).to.emit(ctx.governor, "ProposalExecuted")
  })

  it("lets the admin update quorum and emits it", async function () {
    const ctx = await deploy()
    await expect(ctx.governor.connect(ctx.admin).setQuorum(QUORUM / 4n))
      .to.emit(ctx.governor, "QuorumUpdated")
      .withArgs(QUORUM, QUORUM / 4n)
    expect(await ctx.governor.quorumVotes()).to.equal(QUORUM / 4n)
  })

  it("rejects a zero quorum", async function () {
    const ctx = await deploy()
    await expect(ctx.governor.connect(ctx.admin).setQuorum(0)).to.be.revertedWith("Governor: zero quorum")
  })

  it("rejects setQuorum from a non-admin", async function () {
    const ctx = await deploy()
    await expect(ctx.governor.connect(ctx.voter).setQuorum(1)).to.be.revertedWith("Governor: not admin")
  })

  it("lets the admin hand over the admin role", async function () {
    const ctx = await deploy()
    await expect(ctx.governor.connect(ctx.admin).setAdmin(ctx.voter.address))
      .to.emit(ctx.governor, "AdminUpdated").withArgs(ctx.admin.address, ctx.voter.address)
    expect(await ctx.governor.admin()).to.equal(ctx.voter.address)
    await expect(ctx.governor.connect(ctx.admin).setQuorum(1)).to.be.revertedWith("Governor: not admin")
  })

  it("rejects a zero admin", async function () {
    const ctx = await deploy()
    await expect(ctx.governor.connect(ctx.admin).setAdmin(ethers.ZeroAddress))
      .to.be.revertedWith("Governor: zero admin")
  })

  it("keeps the defeated-proposal check as a regression guard", async function () {
    const ctx = await deploy()
    await ctx.governor.connect(ctx.admin).setQuorum(1)
    await ctx.governor.connect(ctx.voter).propose(ctx.targets, ctx.values, ctx.calldatas)
    const id = await ctx.governor.proposalCount()
    await ethers.provider.send("hardhat_mine", ["0x2"])
    await ctx.governor.connect(ctx.voter).vote(id, false)
    const end = (await ctx.governor.proposals(id)).endBlock
    const head = await ethers.provider.getBlockNumber()
    await ethers.provider.send("hardhat_mine", ["0x" + (Number(end) - head + 1).toString(16)])
    await expect(ctx.governor.execute(id)).to.be.revertedWith("Governor: proposal defeated")
  })
})
