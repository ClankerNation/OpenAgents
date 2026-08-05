const { expect } = require('chai');
const { ethers } = require('hardhat');

describe('GovernorAlpha Quorum Tests', function () {
    let governorAlpha, token, accounts;

    beforeEach(async function () {
        accounts = await ethers.getSigners();
        const Token = await ethers.getContractFactory('TestToken');
        token = await Token.deploy();
        await token.mint(accounts[0].address, ethers.utils.parseEther('1000'));

        const GovernorAlpha = await ethers.getContractFactory('GovernorAlpha');
        governorAlpha = await GovernorAlpha.deploy(token.address);

        // Transfer tokens to other accounts for voting
        await token.transfer(accounts[1].address, ethers.utils.parseEther('100'));
        await token.transfer(accounts[2].address, ethers.utils.parseEther('100'));
        await token.transfer(accounts[3].address, ethers.utils.parseEther('100'));
        await token.transfer(accounts[4].address, ethers.utils.parseEther('100'));
    });

    it('should revert if forVotes is less than quorum', async function () {
        await token.delegate(accounts[0].address);
        await token.connect(accounts[1]).delegate(accounts[0].address);
        await token.connect(accounts[2]).delegate(accounts[0].address);

        const targets = [accounts[5].address];
        const values = ['0'];
        const signatures = ['getBalance(address)'];
        const calldatas = [ethers.utils.defaultAbiCoder.encode(['address'], [accounts[5].address])];
        const description = 'Test Proposal';

        await governorAlpha.propose(targets, values, signatures, calldatas, description);
        await ethers.provider.send('evm_increaseTime', [3601]); // Increase time by 1 hour
        await ethers.provider.send('evm_mine');

        await governorAlpha.castVote(1, true); // Only 1 vote, less than quorum
        await ethers.provider.send('evm_increaseTime', [86401]); // Increase time by 1 day
        await ethers.provider.send('evm_mine');

        await expect(governorAlpha.execute(1)).to.be.revertedWith('GovernorAlpha::execute: proposal did not meet quorum');
    });

    it('should pass if forVotes meets quorum', async function () {
        await token.delegate(accounts[0].address);
        await token.connect(accounts[1]).delegate(accounts[0].address);
        await token.connect(accounts[2]).delegate(accounts[0].address);
        await token.connect(accounts[3]).delegate(accounts[0].address);

        const targets = [accounts[5].address];
        const values = ['0'];
        const signatures = ['getBalance(address)'];
        const calldatas = [ethers.utils.defaultAbiCoder.encode(['address'], [accounts[5].address])];
        const description = 'Test Proposal';

        await governorAlpha.propose(targets, values, signatures, calldatas, description);
        await ethers.provider.send('evm_increaseTime', [3601]); // Increase time by 1 hour
        await ethers.provider.send('evm_mine');

        await governorAlpha.castVote(1, true); // 4 votes, meets quorum
        await ethers.provider.send('evm_increaseTime', [86401]); // Increase time by 1 day
        await ethers.provider.send('evm_mine');

        await expect(governorAlpha.execute(1)).to.not.be.reverted;
    });

    it('should allow admin to update QUORUM_VOTES', async function () {
        const newQuorumVotes = ethers.utils.parseEther('10');
        await governorAlpha.setQuorumVotes(newQuorumVotes);

        expect(await governorAlpha.quorumVotes()).to.equal(newQuorumVotes);
    });
});
