const { expect } = require("chai");
const { ethers } = require("hardhat");
const fs = require("fs");
const solc = require("solc");

function compileInterestRateModel() {
  const sourcePath = "contracts/lending/InterestRateModel.sol";
  const input = {
    language: "Solidity",
    sources: {
      [sourcePath]: { content: fs.readFileSync(sourcePath, "utf8") },
    },
    settings: {
      outputSelection: {
        "*": {
          "*": ["abi", "evm.bytecode.object"],
        },
      },
    },
  };

  const output = JSON.parse(solc.compile(JSON.stringify(input)));
  const errors = (output.errors || []).filter((error) => error.severity === "error");
  if (errors.length) {
    throw new Error(errors.map((error) => error.formattedMessage).join("\n"));
  }

  return output.contracts[sourcePath].InterestRateModel;
}

async function deployModel(args) {
  const [admin] = await ethers.getSigners();
  const artifact = compileInterestRateModel();
  const factory = new ethers.ContractFactory(
    artifact.abi,
    `0x${artifact.evm.bytecode.object}`,
    admin
  );
  const contract = await factory.deploy(...args);
  await contract.waitForDeployment();
  return contract;
}

describe("InterestRateModel parameters", function () {
  it("returns all current parameters", async function () {
    const model = await deployModel([1, 2, 3, 4]);

    const params = await model.getParameters();

    expect(params.baseRate).to.equal(1);
    expect(params.multiplier).to.equal(2);
    expect(params.jumpMultiplier).to.equal(3);
    expect(params.kink).to.equal(4);
  });

  it("emits old and new parameters on update", async function () {
    const model = await deployModel([10, 20, 30, 40]);

    await expect(model.updateParams(11, 21, 31, 41))
      .to.emit(model, "RateParametersUpdated")
      .withArgs([10, 20, 30, 40], [11, 21, 31, 41]);

    const params = await model.getParameters();
    expect(params.baseRate).to.equal(11);
    expect(params.multiplier).to.equal(21);
    expect(params.jumpMultiplier).to.equal(31);
    expect(params.kink).to.equal(41);
  });
});
