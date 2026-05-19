const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("BridgeValidator", function () {
  let BridgeValidator;
  let bridgeValidator;
  let owner;
  let val1;
  let val2;
  let val3;
  let val4;
  let val5;
  let nonOwner;

  beforeEach(async function () {
    [owner, val1, val2, val3, val4, val5, nonOwner] = await ethers.getSigners();
    BridgeValidator = await ethers.getContractFactory("BridgeValidator");
    // Deploy with threshold = 10
    bridgeValidator = await BridgeValidator.deploy(10);
  });

  describe("Deployment", function () {
    it("should set the correct owner and threshold", async function () {
      expect(await bridgeValidator.owner()).to.equal(owner.address);
      expect(await bridgeValidator.threshold()).to.equal(10);
      expect(await bridgeValidator.activeValidatorCount()).to.equal(0);
      expect(await bridgeValidator.totalWeight()).to.equal(0);
    });
  });

  describe("Bootstrap", function () {
    it("should allow owner to bootstrap the first validator", async function () {
      await expect(bridgeValidator.bootstrap(val1.address, 5))
        .to.emit(bridgeValidator, "ValidatorAdded")
        .withArgs(val1.address, 5);

      expect(await bridgeValidator.activeValidatorCount()).to.equal(1);
      expect(await bridgeValidator.totalWeight()).to.equal(5);

      const valInfo = await bridgeValidator.validators(val1.address);
      expect(valInfo.isActive).to.be.true;
      expect(valInfo.weight).to.equal(5);
    });

    it("should not allow non-owner to bootstrap", async function () {
      await expect(
        bridgeValidator.connect(nonOwner).bootstrap(val1.address, 5)
      ).to.be.revertedWith("BridgeValidator: not owner");
    });

    it("should not allow bootstrapping twice", async function () {
      await bridgeValidator.bootstrap(val1.address, 5);
      await expect(
        bridgeValidator.bootstrap(val2.address, 5)
      ).to.be.revertedWith("BridgeValidator: already bootstrapped");
    });
  });

  describe("Add Validator", function () {
    beforeEach(async function () {
      await bridgeValidator.bootstrap(val1.address, 5);
    });

    it("should allow owner to add validators", async function () {
      await expect(bridgeValidator.addValidator(val2.address, 3))
        .to.emit(bridgeValidator, "ValidatorAdded")
        .withArgs(val2.address, 3);

      expect(await bridgeValidator.activeValidatorCount()).to.equal(2);
      expect(await bridgeValidator.totalWeight()).to.equal(8);
    });

    it("should NOT allow validators to add other validators (the fix)", async function () {
      // Previously this was allowed due to onlyValidator. Now it should revert.
      await expect(
        bridgeValidator.connect(val1).addValidator(val2.address, 3)
      ).to.be.revertedWith("BridgeValidator: not owner");
    });

    it("should revert if validator is already active", async function () {
      await expect(
        bridgeValidator.addValidator(val1.address, 3)
      ).to.be.revertedWith("BridgeValidator: already active");
    });

    it("should revert on zero weight", async function () {
      await expect(
        bridgeValidator.addValidator(val2.address, 0)
      ).to.be.revertedWith("BridgeValidator: zero weight");
    });
  });

  describe("Remove Validator and Min Validator Constraint", function () {
    beforeEach(async function () {
      await bridgeValidator.bootstrap(val1.address, 5);
      await bridgeValidator.addValidator(val2.address, 5);
      await bridgeValidator.addValidator(val3.address, 5);
    });

    it("should not allow removing when active count <= 3", async function () {
      // Current active count is 3. Removing one would make it 2, which should fail.
      expect(await bridgeValidator.activeValidatorCount()).to.equal(3);
      await expect(
        bridgeValidator.removeValidator(val1.address)
      ).to.be.revertedWith("BridgeValidator: min 3 validators required");
    });

    it("should allow removing when active count > 3", async function () {
      // Add a 4th validator
      await bridgeValidator.addValidator(val4.address, 5);
      expect(await bridgeValidator.activeValidatorCount()).to.equal(4);

      // Now removal should succeed
      await expect(bridgeValidator.removeValidator(val1.address))
        .to.emit(bridgeValidator, "ValidatorRemoved")
        .withArgs(val1.address);

      expect(await bridgeValidator.activeValidatorCount()).to.equal(3);
      expect(await bridgeValidator.totalWeight()).to.equal(15);
    });

    it("should only allow owner to remove", async function () {
      await bridgeValidator.addValidator(val4.address, 5);
      await expect(
        bridgeValidator.connect(nonOwner).removeValidator(val1.address)
      ).to.be.revertedWith("BridgeValidator: not owner");
    });
  });

  describe("Update Weight and Bounding totalWeight", function () {
    beforeEach(async function () {
      await bridgeValidator.bootstrap(val1.address, 5);
    });

    it("should allow owner to update weight", async function () {
      await expect(bridgeValidator.updateWeight(val1.address, 10))
        .to.emit(bridgeValidator, "ValidatorWeightUpdated")
        .withArgs(val1.address, 5, 10);

      expect(await bridgeValidator.totalWeight()).to.equal(10);
      const valInfo = await bridgeValidator.validators(val1.address);
      expect(valInfo.weight).to.equal(10);
    });

    it("should revert if updating weight of inactive validator", async function () {
      await expect(
        bridgeValidator.updateWeight(val2.address, 10)
      ).to.be.revertedWith("BridgeValidator: not active");
    });

    it("should revert if update to zero weight", async function () {
      await expect(
        bridgeValidator.updateWeight(val1.address, 0)
      ).to.be.revertedWith("BridgeValidator: zero weight");
    });

    it("should respect MAX_TOTAL_WEIGHT bound", async function () {
      const maxWeight = await bridgeValidator.MAX_TOTAL_WEIGHT();
      // Try to add weight that exceeds maxWeight
      await expect(
        bridgeValidator.addValidator(val2.address, maxWeight)
      ).to.be.revertedWith("BridgeValidator: weight limit exceeded");
    });
  });
});
