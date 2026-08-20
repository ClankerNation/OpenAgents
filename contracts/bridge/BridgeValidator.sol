// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title BridgeValidator
/// @notice Manages the validator set for a cross-chain bridge protocol.
/// @dev Validators are assigned weights; consensus requires a threshold of total weight.
///      Supports adding, removing, and updating validator weights.
contract BridgeValidator {
    struct Validator {
        bool isActive;
        uint128 weight;
        uint256 addedAt;
    }

    address public owner;
    uint256 public totalWeight;
    uint256 public threshold;
    address[] public validatorList;
    mapping(address => Validator) public validators;
    uint256 public activeValidatorCount;
    uint256 public constant MIN_VALIDATORS = 3;
    uint256 public constant MAX_TOTAL_WEIGHT = type(uint128).max;

    event ValidatorAdded(address indexed validator, uint128 weight);
    event ValidatorRemoved(address indexed validator);
    event ValidatorWeightUpdated(address indexed validator, uint128 oldWeight, uint128 newWeight);
    event ThresholdUpdated(uint256 oldThreshold, uint256 newThreshold);

    modifier onlyOwner() {
        require(msg.sender == owner, "BridgeValidator: not owner");
        _;
    }

    modifier onlyValidator() {
        require(validators[msg.sender].isActive, "BridgeValidator: not validator");
        _;
    }

    constructor(uint256 _threshold) {
        owner = msg.sender;
        threshold = _threshold;
    }

    /// @notice Add a new validator with a given weight.
    /// @param validator Address of the new validator.
    /// @param weight Voting weight assigned to the validator.
    function addValidator(address validator, uint128 weight) external onlyOwner {
        require(!validators[validator].isActive, "BridgeValidator: already active");
        require(weight > 0, "BridgeValidator: zero weight");
        require(totalWeight + weight <= MAX_TOTAL_WEIGHT, "BridgeValidator: weight overflow");

        validators[validator] = Validator({
            isActive: true,
            weight: weight,
            addedAt: block.timestamp
        });

        totalWeight += weight;
        validatorList.push(validator);
        activeValidatorCount++;

        emit ValidatorAdded(validator, weight);
    }

    /// @notice Remove a validator from the active set.
    /// @param validator Address to remove.
    function removeValidator(address validator) external onlyOwner {
        require(validators[validator].isActive, "BridgeValidator: not active");
        require(activeValidatorCount > MIN_VALIDATORS, "BridgeValidator: min validators");

        totalWeight -= validators[validator].weight;
        validators[validator].isActive = false;
        validators[validator].weight = 0;
        activeValidatorCount--;

        emit ValidatorRemoved(validator);
    }

    /// @notice Update a validator's weight.
    /// @param validator Address of the validator.
    /// @param newWeight New voting weight.
    function updateWeight(address validator, uint128 newWeight) external onlyOwner {
        require(validators[validator].isActive, "BridgeValidator: not active");
        require(newWeight > 0, "BridgeValidator: zero weight");

        uint128 oldWeight = validators[validator].weight;
        uint256 newTotal = totalWeight - oldWeight + newWeight;
        require(newTotal <= MAX_TOTAL_WEIGHT, "BridgeValidator: weight overflow");
        totalWeight = newTotal;
        validators[validator].weight = newWeight;

        emit ValidatorWeightUpdated(validator, oldWeight, newWeight);
    }

    /// @notice Update the consensus threshold.
    /// @param _threshold New threshold value (sum of weights needed for consensus).
    function setThreshold(uint256 _threshold) external onlyOwner {
        require(_threshold > 0, "BridgeValidator: zero threshold");
        uint256 old = threshold;
        threshold = _threshold;
        emit ThresholdUpdated(old, _threshold);
    }

    /// @notice Check if a set of validators meets the consensus threshold.
    /// @param signers Array of validator addresses that signed.
    /// @return True if the combined weight meets or exceeds the threshold.
    function hasConsensus(address[] calldata signers) external view returns (bool) {
        uint256 weightSum = 0;
        for (uint256 i = 0; i < signers.length; i++) {
            if (validators[signers[i]].isActive) {
                weightSum += validators[signers[i]].weight;
            }
        }
        return weightSum >= threshold;
    }

    /// @notice Get all validator addresses (including inactive).
    function getValidators() external view returns (address[] memory) {
        return validatorList;
    }

    /// @notice Bootstrap the initial validator. Can only be called once when no validators exist.
    /// @param validator The first validator address.
    /// @param weight Initial weight.
    function bootstrap(address validator, uint128 weight) external onlyOwner {
        require(validatorList.length == 0, "BridgeValidator: already bootstrapped");
        require(weight > 0, "BridgeValidator: zero weight");
        require(weight <= MAX_TOTAL_WEIGHT, "BridgeValidator: weight overflow");
        validators[validator] = Validator({ isActive: true, weight: weight, addedAt: block.timestamp });
        totalWeight += weight;
        validatorList.push(validator);
        activeValidatorCount++;
        emit ValidatorAdded(validator, weight);
    }
}
