const { expect } = require("chai")
const { ethers } = require("hardhat")

const DAY = 24 * 60 * 60
const WINDOW = 90 * DAY

async function setup() {
  const [admin, w1, w2, treasury] = await ethers.getSigners()
  const Split = await ethers.getContractFactory("PrizeSplit")
  const split = await Split.deploy()
  await split.connect(admin).setTreasury(treasury.address)
  await split.connect(admin).fundRound({ value: ethers.parseEther("10") })
  return { admin, w1, w2, treasury, split }
}

async function advance(seconds) {
  await ethers.provider.send("evm_increaseTime", [seconds])
  await ethers.provider.send("evm_mine", [])
}

describe("PrizeSplit pull pattern", function () {
  it("lets each winner claim independently and marks them claimed", async function () {
    const { admin, w1, w2, split } = await setup()
    await split.connect(admin).finalizeRound(1, [w1.address, w2.address])

    await expect(split.connect(w1).claimPrize(1)).to.emit(split, "PrizeClaimed")
    expect(await split.isClaimed(1, w1.address)).to.equal(true)
    expect(await split.isClaimed(1, w2.address)).to.equal(false)

    await split.connect(w2).claimPrize(1)
    expect(await split.isClaimed(1, w2.address)).to.equal(true)
  })

  it("does not block other winners when a contract winner rejects ETH", async function () {
    const { admin, w1, split } = await setup()
    const R = await ethers.getContractFactory("RejectingWinner")
    const rejecter = await R.deploy(await split.getAddress())
    const rejecterAddr = await rejecter.getAddress()

    await split.connect(admin).finalizeRound(1, [rejecterAddr, w1.address])

    // the contract cannot receive, so its own claim fails
    await expect(rejecter.claim(1)).to.be.revertedWith("Transfer failed")
    expect(await split.isClaimed(1, rejecterAddr)).to.equal(false)

    // the other winner is unaffected
    await expect(split.connect(w1).claimPrize(1)).to.emit(split, "PrizeClaimed")
  })

  it("gives the division remainder to the last winner so nothing is stranded", async function () {
    const { admin, w1, w2, split } = await setup()
    // 11 wei across 2 winners: 5 + 5 truncates one wei, which must land on the last winner
    await split.connect(admin).fundRound({ value: 11n })
    await split.connect(admin).finalizeRound(2, [w1.address, w2.address])

    const s1 = await split.getShare(2, w1.address)
    const s2 = await split.getShare(2, w2.address)
    expect(s1 + s2).to.equal(11n)
    expect(s1).to.equal(5n)
    expect(s2).to.equal(6n)
  })

  it("rejects finalizing with no winners", async function () {
    const { admin, split } = await setup()
    await expect(split.connect(admin).finalizeRound(1, [])).to.be.revertedWith("No winners")
  })

  it("closes claiming after the 90 day window", async function () {
    const { admin, w1, split } = await setup()
    await split.connect(admin).finalizeRound(1, [w1.address])
    await advance(WINDOW + 1)
    await expect(split.connect(w1).claimPrize(1)).to.be.revertedWith("Claim window closed")
  })

  it("lets the admin sweep unclaimed prizes to treasury after the deadline", async function () {
    const { admin, w1, treasury, split } = await setup()
    await split.connect(admin).finalizeRound(1, [w1.address])
    await advance(WINDOW + 1)

    const before = await ethers.provider.getBalance(treasury.address)
    await expect(split.connect(admin).sweepUnclaimed(1)).to.emit(split, "UnclaimedSwept")
    const after = await ethers.provider.getBalance(treasury.address)

    expect(after - before).to.equal(ethers.parseEther("10"))
  })

  it("sweeps only what is left after partial claims", async function () {
    const { admin, w1, w2, treasury, split } = await setup()
    await split.connect(admin).finalizeRound(1, [w1.address, w2.address])
    await split.connect(w1).claimPrize(1)

    await advance(WINDOW + 1)
    const before = await ethers.provider.getBalance(treasury.address)
    await split.connect(admin).sweepUnclaimed(1)
    const after = await ethers.provider.getBalance(treasury.address)

    expect(after - before).to.equal(await split.getShare(1, w2.address))
  })

  it("rejects sweeping before the deadline and from a non-admin", async function () {
    const { admin, w1, split } = await setup()
    await split.connect(admin).finalizeRound(1, [w1.address])

    await expect(split.connect(admin).sweepUnclaimed(1)).to.be.revertedWith("Claim window open")
    await advance(WINDOW + 1)
    await expect(split.connect(w1).sweepUnclaimed(1)).to.be.revertedWith("Not admin")
  })

  it("cannot sweep the same round twice", async function () {
    const { admin, w1, split } = await setup()
    await split.connect(admin).finalizeRound(1, [w1.address])
    await advance(WINDOW + 1)
    await split.connect(admin).sweepUnclaimed(1)
    await expect(split.connect(admin).sweepUnclaimed(1)).to.be.revertedWith("Already swept")
  })

  it("records the claim before transferring, so a reentrant winner cannot double claim", async function () {
    const { admin, split } = await setup()
    const R = await ethers.getContractFactory("ReentrantWinner")
    const reenter = await R.deploy(await split.getAddress())

    await split.connect(admin).finalizeRound(1, [await reenter.getAddress()])
    await reenter.claim(1)

    expect(await split.isClaimed(1, await reenter.getAddress())).to.equal(true)
    // contract received its share exactly once
    expect(await ethers.provider.getBalance(await reenter.getAddress())).to.equal(ethers.parseEther("10"))
  })
})
