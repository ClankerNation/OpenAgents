const { expect } = require("chai");
const { ethers, network } = require("hardhat");

describe("AgentToken Domain Separator Replay Protection", function () {
    let agentToken;
    let owner;

    const initialChainId = 31337; // Hardhat default
    const newChainId = 12345;

    beforeEach(async function () {
        [owner] = await ethers.getSigners();

        const AgentToken = await ethers.getContractFactory("AgentToken");
        // name, symbol, initialSupply
        agentToken = await AgentToken.deploy("Agent Token", "AGT", ethers.parseEther("1000000"));
    });

    after(async function() {
    });

    it("should dynamically compute the domain separator", async function () {
        const buildDomainSeparator = async (chainId) => {
            const domainSeparatorType = ethers.keccak256(
                ethers.toUtf8Bytes("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)")
            );
            const nameHash = ethers.keccak256(ethers.toUtf8Bytes("Agent Token"));
            const versionHash = ethers.keccak256(ethers.toUtf8Bytes("1"));
            
            const abiCoder = new ethers.AbiCoder();
            return ethers.keccak256(
                abiCoder.encode(
                    ["bytes32", "bytes32", "bytes32", "uint256", "address"],
                    [domainSeparatorType, nameHash, versionHash, chainId, await agentToken.getAddress()]
                )
            );
        };

        const initialDS = await agentToken.DOMAIN_SEPARATOR();
        expect(initialDS).to.equal(await buildDomainSeparator(initialChainId));
    });

    it("should successfully execute a permit using the dynamic domain separator", async function () {
        const [owner, spender] = await ethers.getSigners();
        const value = ethers.parseEther("100");
        const nonce = await agentToken.nonces(owner.address);
        const deadline = ethers.MaxUint256;

        const domain = {
            name: "Agent Token",
            version: "1",
            chainId: initialChainId,
            verifyingContract: await agentToken.getAddress()
        };

        const types = {
            Permit: [
                { name: "owner", type: "address" },
                { name: "spender", type: "address" },
                { name: "value", type: "uint256" },
                { name: "nonce", type: "uint256" },
                { name: "deadline", type: "uint256" }
            ]
        };

        const message = {
            owner: owner.address,
            spender: spender.address,
            value: value,
            nonce: nonce,
            deadline: deadline
        };

        const signature = await owner.signTypedData(domain, types, message);
        const sig = ethers.Signature.from(signature);

        await agentToken.permit(owner.address, spender.address, value, deadline, sig.v, sig.r, sig.s);

        const allowance = await agentToken.allowance(owner.address, spender.address);
        expect(allowance).to.equal(value);
    });
});
