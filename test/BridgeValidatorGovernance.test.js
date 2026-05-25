const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("BridgeValidator governance", function () {
  let validator1;
  let validator2;
  let validator3;
  let validator4;
  let stranger;
  let bridgeValidator;

  beforeEach(async function () {
    [, validator1, validator2, validator3, validator4, stranger] = await ethers.getSigners();

    const BridgeValidator = await ethers.getContractFactory("BridgeValidator");
    bridgeValidator = await BridgeValidator.deploy(2);
    await bridgeValidator.bootstrap(validator1.address, 1);
  });

  it("only lets the owner add validators", async function () {
    await expect(
      bridgeValidator.connect(validator1).addValidator(validator2.address, 1),
    ).to.be.revertedWith("BridgeValidator: not owner");

    await expect(bridgeValidator.addValidator(validator2.address, 1))
      .to.emit(bridgeValidator, "ValidatorAdded")
      .withArgs(validator2.address, 1);

    expect(await bridgeValidator.activeValidatorCount()).to.equal(2);
  });

  it("only lets the owner remove validators and preserves a three-validator minimum", async function () {
    await bridgeValidator.addValidator(validator2.address, 1);
    await bridgeValidator.addValidator(validator3.address, 1);
    await bridgeValidator.addValidator(validator4.address, 1);

    await expect(
      bridgeValidator.connect(stranger).removeValidator(validator4.address),
    ).to.be.revertedWith("BridgeValidator: not owner");

    await expect(bridgeValidator.removeValidator(validator4.address))
      .to.emit(bridgeValidator, "ValidatorRemoved")
      .withArgs(validator4.address);

    expect(await bridgeValidator.activeValidatorCount()).to.equal(3);

    await expect(bridgeValidator.removeValidator(validator3.address)).to.be.revertedWith(
      "BridgeValidator: minimum validators",
    );
  });

  it("bounds total validator weight on add and update", async function () {
    const maxWeight = await bridgeValidator.MAX_TOTAL_WEIGHT();

    await expect(bridgeValidator.addValidator(validator2.address, maxWeight)).to.be.revertedWith(
      "BridgeValidator: total weight too high",
    );

    await bridgeValidator.addValidator(validator2.address, 1);

    await expect(bridgeValidator.updateWeight(validator2.address, maxWeight)).to.be.revertedWith(
      "BridgeValidator: total weight too high",
    );
  });
});
