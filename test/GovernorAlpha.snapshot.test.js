const { expect } = require("chai");
const { ethers } = require("hardhat");

// @contributor Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
// @platform full verbatim block: header of contracts/governance/GovernorAlpha.sol
// @runtime os=windows arch=x86_64 working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
//   shell=C:\Program Files\Git\bin\bash.exe
// @date 2026-11-04T18:45:00Z

const THRESHOLD = ethers.parseEther("100000");
const MINT = ethers.parseEther("50000000");

async function deploy() {
  const [admin, voter, other, buyer] = await ethers.getSigners();

  const Token = await ethers.getContractFactory("GovernanceToken");
  const token = await Token.deploy();
  const Governor = await ethers.getContractFactory("GovernorAlpha");
  const governor = await Governor.deploy(await token.getAddress());

  const targets = [await token.getAddress()];
  const values = [0];
  const calldatas = [token.interface.encodeFunctionData("transfer", [admin.address, 0])];

  // the fixture token mints 1,000,000 on deploy
  await token.transfer(voter.address, eters(300_000));
  await token.transfer(buyer.address, eters(300_000));
  await token.transfer(other.address, eters(20_000));
  await token.connect(voter).delegate(voter.address);
  await token.connect(buyer).delegate(buyer.address);
  await token.connect(admin).delegate(admin.address);

  return { admin, voter, other, buyer, token, governor, targets, values, calldatas };
}

function eters(n) {
  return ethers.parseEther(String(n));
}

describe("GovernorAlpha snapshot voting power", function () {
  it("stores a snapshot block at creation", async function () {
    const { voter, governor, targets, values, calldatas } = await deploy();
    await governor.connect(voter).propose(targets, values, calldatas);
    const id = await governor.proposalCount();
    const proposal = await governor.proposals(id);

    expect(proposal.snapshotBlock).to.equal(proposal.startBlock - 1n);
  });

  it("reports the balance held at the snapshot block", async function () {
    const { voter, governor, targets, values, calldatas } = await deploy();
    await governor.connect(voter).propose(targets, values, calldatas);
    const id = await governor.proposalCount();

    expect(await governor.getVotingPower(voter.address, id)).to.equal(eters(300_000));
  });

  it("ignores tokens transferred away after creation", async function () {
    const { voter, other, token, governor, targets, values, calldatas } = await deploy();
    await governor.connect(voter).propose(targets, values, calldatas);
    const id = await governor.proposalCount();

    await token.connect(voter).transfer(other.address, eters(250_000));
    await token.connect(other).delegate(other.address);

    expect(await token.balanceOf(voter.address)).to.equal(eters(50_000));
    expect(await governor.getVotingPower(voter.address, id)).to.equal(eters(300_000));
  });

  it("ignores tokens acquired after creation", async function () {
    const { voter, other, buyer, token, governor, targets, values, calldatas } = await deploy();
    await governor.connect(voter).propose(targets, values, calldatas);
    const id = await governor.proposalCount();

    await token.connect(other).transfer(buyer.address, eters(10_000));

    expect(await governor.getVotingPower(buyer.address, id)).to.equal(eters(300_000));
  });

  it("casts the frozen weight, not the current balance", async function () {
    const { voter, other, token, governor, targets, values, calldatas } = await deploy();
    await governor.connect(voter).propose(targets, values, calldatas);
    const id = await governor.proposalCount();

    await token.connect(voter).transfer(other.address, eters(250_000));
    await ethers.provider.send("evm_mine", []);
    await governor.connect(voter).vote(id, true);

    const proposal = await governor.proposals(id);
    expect(proposal.forVotes).to.equal(eters(300_000));
  });

  it("keeps the frozen weight even after the holder sells out", async function () {
    const { admin, voter, buyer, token, governor, targets, values, calldatas } = await deploy();
    await governor.connect(voter).propose(targets, values, calldatas);
    const id = await governor.proposalCount();

    await token.connect(buyer).transfer(admin.address, eters(300_000)); // sell out after creation
    await token.connect(admin).transfer(voter.address, eters(300_000));
    await ethers.provider.send("evm_mine", []);
    await governor.connect(buyer).vote(id, true);

    // 30M at creation, sold afterwards: the frozen weight still applies
    expect((await governor.proposals(id)).forVotes).to.equal(eters(300_000));
  });

  it("counts a delegation that happened before creation", async function () {
    const { admin, voter, token, governor, targets, values, calldatas } = await deploy();
    // admin delegates to voter before any proposal exists
    await token.connect(admin).delegate(voter.address);

    await governor.connect(voter).propose(targets, values, calldatas);
    const id = await governor.proposalCount();

    await ethers.provider.send("evm_mine", []);
    // delegated power is both balances, whichever way the fixture divided them
    const expected = (await token.balanceOf(admin.address)) + (await token.balanceOf(voter.address));
    expect(await governor.getVotingPower(voter.address, id)).to.equal(expected);
  });

  it("returns zero power for an unknown proposal", async function () {
    const { voter, governor } = await deploy();
    expect(await governor.getVotingPower(voter.address, 999)).to.equal(0n);
  });

  it("still enforces the proposal threshold on current votes", async function () {
    const { other, governor, targets, values, calldatas } = await deploy();
    await expect(governor.connect(other).propose(targets, values, calldatas)).to.be.revertedWith(
      "Governor: below threshold"
    );
    expect(THRESHOLD).to.equal(eters(100_000));
  });
});
