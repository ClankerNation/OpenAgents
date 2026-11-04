const { expect } = require("chai")
const { ethers } = require("hardhat")
const fs = require("fs")
const path = require("path")

const PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
const PERMIT2_CODE = fs.readFileSync(
  path.join(__dirname, "fixtures", "permit2.bytecode.hex"),
  "utf8",
).trim()

const TYPES = {
  PermitTransferFrom: [
    { name: "permitted", type: "TokenPermissions" },
    { name: "spender", type: "address" },
    { name: "nonce", type: "uint256" },
    { name: "deadline", type: "uint256" },
  ],
  TokenPermissions: [
    { name: "token", type: "address" },
    { name: "amount", type: "uint256" },
  ],
}

async function installPermit2() {
  // The canonical Permit2 deployment is immutable; drop its runtime code at the
  // canonical address so the contracts under test talk to the real implementation.
  await ethers.provider.send("hardhat_setCode", [PERMIT2, PERMIT2_CODE])
}

async function signPermit2(signer, token, amount, spender, nonce, deadline) {
  const { chainId } = await ethers.provider.getNetwork()
  return signer.signTypedData(
    { name: "Permit2", chainId, verifyingContract: PERMIT2 },
    TYPES,
    { permitted: { token, amount }, spender, nonce, deadline },
  )
}

describe("Permit2 flows", function () {
  let token, other, staking, pool, lending, owner, user

  beforeEach(async function () {
    [owner, user] = await ethers.getSigners()
    await installPermit2()

    const Token = await ethers.getContractFactory("StakingToken")
    token = await Token.deploy()
    const Other = await ethers.getContractFactory("RewardToken")
    other = await Other.deploy()

    const Staking = await ethers.getContractFactory("StakingRewards")
    staking = await Staking.deploy(await token.getAddress(), await other.getAddress())

    const AMM = await ethers.getContractFactory("AMMPool")
    pool = await AMM.deploy(await token.getAddress(), await other.getAddress())
    await token.approve(await pool.getAddress(), ethers.parseEther("1000"))
    await other.approve(await pool.getAddress(), ethers.parseEther("1000"))
    await pool.addLiquidity(ethers.parseEther("500"), ethers.parseEther("500"))

    const Lending = await ethers.getContractFactory("LendingPool")
    lending = await Lending.deploy(
      await other.getAddress(),
      await token.getAddress(),
      await other.getAddress(),
    )

    await token.transfer(user.address, ethers.parseEther("1000"))
    // Permit2 itself pulls the tokens, so the owner approves Permit2 once (never the contract)
    await token.connect(user).approve(PERMIT2, ethers.MaxUint256)
  })

  it("stakes with a permit2 signature and no prior approve", async function () {
    const amount = ethers.parseEther("10")
    const deadline = Math.floor(Date.now() / 1000) + 3600
    const nonce = 0
    const sig = await signPermit2(
      user, await token.getAddress(), amount, await staking.getAddress(), nonce, deadline,
    )

    await expect(
      staking.connect(user).stakeWithPermit2(amount, nonce, deadline, sig),
    ).to.emit(staking, "Staked").withArgs(user.address, amount)

    expect(await staking.balanceOf(user.address)).to.equal(amount)
    expect(await token.balanceOf(await staking.getAddress())).to.equal(amount)
    expect(await token.allowance(user.address, await staking.getAddress())).to.equal(0)
  })

  it("swaps with a permit2 signature", async function () {
    const amount = ethers.parseEther("5")
    const deadline = Math.floor(Date.now() / 1000) + 3600
    const sig = await signPermit2(
      user, await token.getAddress(), amount, await pool.getAddress(), 1, deadline,
    )

    await expect(pool.connect(user).swapWithPermit2(await token.getAddress(), amount, 0, 1, deadline, sig))
      .to.emit(pool, "Swap")
  })

  it("deposits collateral with a permit2 signature", async function () {
    const amount = ethers.parseEther("2")
    const deadline = Math.floor(Date.now() / 1000) + 3600
    const sig = await signPermit2(
      user, await token.getAddress(), amount, await lending.getAddress(), 2, deadline,
    )

    await expect(lending.connect(user).depositWithPermit2(amount, 2, deadline, sig))
      .to.emit(lending, "Deposited").withArgs(user.address, amount)
  })

  it("rejects a replayed nonce", async function () {
    const amount = ethers.parseEther("1")
    const deadline = Math.floor(Date.now() / 1000) + 3600
    const sig = await signPermit2(
      user, await token.getAddress(), amount, await staking.getAddress(), 7, deadline,
    )
    await staking.connect(user).stakeWithPermit2(amount, 7, deadline, sig)
    await expect(staking.connect(user).stakeWithPermit2(amount, 7, deadline, sig)).to.be.reverted
  })

  it("still works through the approve fallback", async function () {
    const amount = ethers.parseEther("3")
    await token.connect(user).approve(await staking.getAddress(), amount)
    await expect(staking.connect(user).stake(amount))
      .to.emit(staking, "Staked").withArgs(user.address, amount)
    expect(await staking.balanceOf(user.address)).to.equal(amount)
  })
})
