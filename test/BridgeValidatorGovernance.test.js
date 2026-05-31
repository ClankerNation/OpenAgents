const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("BridgeValidator governance hardening", function () {
  async function deployBridgeValidator() {
    const [owner, validator1, validator2, validator3, validator4, attacker] = await ethers.getSigners();
    const BridgeValidator = await ethers.getContractFactory("BridgeValidator");
    const bridgeValidator = await BridgeValidator.deploy(3);
    await bridgeValidator.waitForDeployment();
    return { bridgeValidator, owner, validator1, validator2, validator3, validator4, attacker };
  }

  async function bootstrapFour(bridgeValidator, validators) {
    await bridgeValidator.bootstrap(validators[0].address, 1);
    await bridgeValidator.addValidator(validators[1].address, 1);
    await bridgeValidator.addValidator(validators[2].address, 1);
    await bridgeValidator.addValidator(validators[3].address, 1);
  }

  it("allows only the owner to add validators", async function () {
    const { bridgeValidator, validator1, validator2, attacker } = await deployBridgeValidator();

    await bridgeValidator.bootstrap(validator1.address, 1);
    await expect(
      bridgeValidator.connect(validator1).addValidator(validator2.address, 1)
    ).to.be.revertedWith("BridgeValidator: not owner");
    await expect(
      bridgeValidator.connect(attacker).addValidator(attacker.address, 1)
    ).to.be.revertedWith("BridgeValidator: not owner");

    await bridgeValidator.addValidator(validator2.address, 1);
    expect((await bridgeValidator.validators(validator2.address)).isActive).to.equal(true);
  });

  it("allows only the owner to remove validators", async function () {
    const { bridgeValidator, validator1, validator2, validator3, validator4, attacker } =
      await deployBridgeValidator();
    await bootstrapFour(bridgeValidator, [validator1, validator2, validator3, validator4]);

    await expect(
      bridgeValidator.connect(attacker).removeValidator(validator4.address)
    ).to.be.revertedWith("BridgeValidator: not owner");

    await bridgeValidator.removeValidator(validator4.address);
    expect((await bridgeValidator.validators(validator4.address)).isActive).to.equal(false);
  });

  it("prevents removing validators below the minimum active set", async function () {
    const { bridgeValidator, validator1, validator2, validator3, validator4 } =
      await deployBridgeValidator();
    await bootstrapFour(bridgeValidator, [validator1, validator2, validator3, validator4]);

    await bridgeValidator.removeValidator(validator4.address);
    expect(await bridgeValidator.activeValidatorCount()).to.equal(3n);
    await expect(
      bridgeValidator.removeValidator(validator3.address)
    ).to.be.revertedWith("BridgeValidator: minimum validators");
  });

  it("bounds total validator weight on add and update", async function () {
    const { bridgeValidator, validator1, validator2 } = await deployBridgeValidator();
    const maxTotalWeight = await bridgeValidator.MAX_TOTAL_WEIGHT();

    await bridgeValidator.bootstrap(validator1.address, maxTotalWeight);
    await expect(
      bridgeValidator.addValidator(validator2.address, 1)
    ).to.be.revertedWith("BridgeValidator: total weight overflow");

    const { bridgeValidator: updateValidator, validator1: updateSigner } = await deployBridgeValidator();
    await updateValidator.bootstrap(updateSigner.address, 1);
    await ethers.provider.send("hardhat_setStorageAt", [
      await updateValidator.getAddress(),
      "0x01",
      ethers.toBeHex(maxTotalWeight, 32),
    ]);
    await expect(
      updateValidator.updateWeight(updateSigner.address, 2)
    ).to.be.revertedWith("BridgeValidator: total weight overflow");
  });

  it("rejects zero validator address", async function () {
    const { bridgeValidator } = await deployBridgeValidator();

    await expect(
      bridgeValidator.bootstrap(ethers.ZeroAddress, 1)
    ).to.be.revertedWith("BridgeValidator: zero validator");
  });
});
