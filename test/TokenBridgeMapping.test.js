const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");
const solc = require("solc");

function findImport(importPath) {
  const candidates = [
    path.join(process.cwd(), importPath),
    path.join(process.cwd(), "node_modules", importPath),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return { contents: fs.readFileSync(candidate, "utf8") };
    }
  }

  return { error: `File not found: ${importPath}` };
}

function compileContracts() {
  const bridgePath = "contracts/bridge/TokenBridge.sol";
  const tokenPath = "contracts/test/MockBridgeToken.sol";
  const input = {
    language: "Solidity",
    sources: {
      [bridgePath]: { content: fs.readFileSync(bridgePath, "utf8") },
      [tokenPath]: {
        content: `
          // SPDX-License-Identifier: MIT
          pragma solidity ^0.8.20;
          import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

          contract MockBridgeToken is ERC20 {
              constructor() ERC20("Mock Bridge Token", "MBT") {}

              function mint(address account, uint256 amount) external {
                  _mint(account, amount);
              }
          }
        `,
      },
    },
    settings: {
      outputSelection: {
        "*": {
          "*": ["abi", "evm.bytecode.object"],
        },
      },
    },
  };

  const output = JSON.parse(solc.compile(JSON.stringify(input), { import: findImport }));
  const errors = (output.errors || []).filter((error) => error.severity === "error");
  if (errors.length) {
    throw new Error(errors.map((error) => error.formattedMessage).join("\n"));
  }

  return {
    bridge: output.contracts[bridgePath].TokenBridge,
    token: output.contracts[tokenPath].MockBridgeToken,
  };
}

async function deploy(artifact, signer, args = []) {
  const factory = new ethers.ContractFactory(
    artifact.abi,
    `0x${artifact.evm.bytecode.object}`,
    signer
  );
  const contract = await factory.deploy(...args);
  await contract.waitForDeployment();
  return contract;
}

describe("TokenBridge token mapping", function () {
  let compiled;
  let admin;
  let user;
  let recipient;
  let bridge;
  let token;
  let remoteToken;

  before(function () {
    compiled = compileContracts();
  });

  beforeEach(async function () {
    [admin, user, recipient, remoteToken] = await ethers.getSigners();
    bridge = await deploy(compiled.bridge, admin, [1]);
    token = await deploy(compiled.token, admin);

    await token.mint(user.address, ethers.parseEther("10"));
    await token.connect(user).approve(await bridge.getAddress(), ethers.parseEther("10"));
  });

  it("rejects locking an unmapped token", async function () {
    await expect(
      bridge.connect(user).lock(await token.getAddress(), recipient.address, ethers.parseEther("1"))
    ).to.be.revertedWith("Bridge: token not mapped");
  });

  it("lets the admin add and remove token mappings", async function () {
    const tokenAddress = await token.getAddress();

    await expect(bridge.addTokenMapping(tokenAddress, remoteToken.address))
      .to.emit(bridge, "TokenMappingAdded")
      .withArgs(tokenAddress, remoteToken.address);
    expect(await bridge.tokenMapping(tokenAddress)).to.equal(remoteToken.address);

    await expect(bridge.removeTokenMapping(tokenAddress))
      .to.emit(bridge, "TokenMappingRemoved")
      .withArgs(tokenAddress, remoteToken.address);
    expect(await bridge.tokenMapping(tokenAddress)).to.equal(ethers.ZeroAddress);
  });

  it("locks mapped tokens using a transfer id bound to the token pair", async function () {
    const tokenAddress = await token.getAddress();
    const bridgeAddress = await bridge.getAddress();
    const amount = ethers.parseEther("2");
    const chainId = (await ethers.provider.getNetwork()).chainId;

    await bridge.addTokenMapping(tokenAddress, remoteToken.address);

    const expectedTransferId = ethers.solidityPackedKeccak256(
      ["uint256", "address", "address", "address", "address", "uint256"],
      [chainId, tokenAddress, remoteToken.address, user.address, recipient.address, amount]
    );

    await expect(bridge.connect(user).lock(tokenAddress, recipient.address, amount))
      .to.emit(bridge, "TokensLocked")
      .withArgs(expectedTransferId, tokenAddress, user.address, recipient.address, amount);

    expect(await token.balanceOf(bridgeAddress)).to.equal(amount);
    const transfer = await bridge.transfers(expectedTransferId);
    expect(transfer.token).to.equal(tokenAddress);
    expect(transfer.sender).to.equal(user.address);
    expect(transfer.recipient).to.equal(recipient.address);
    expect(transfer.amount).to.equal(amount);
    expect(transfer.claimed).to.equal(false);
  });
});
