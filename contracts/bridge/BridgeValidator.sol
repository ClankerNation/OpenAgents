// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Contributor: Gaotax2006
// Platform: warpSpeed, opencode CLI
// Runtime: OS=win32 Arch=x64 Home=C:\Users\asus WorkDir=F:\ai-bounty-work\bounty-hunter\openagents Shell=powershell
// Date: 2026-05-17

/// @title BridgeValidator
/// @notice Manages the validator set for a cross-chain bridge protocol.
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

    uint256 public constant MIN_VALIDATORS = 3;
    uint256 public constant MAX_TOTAL_WEIGHT = 1_000_000;

    event ValidatorAdded(address indexed validator, uint128 weight);
    event ValidatorRemoved(address indexed validator);
    event ValidatorWeightUpdated(address indexed validator, uint128 oldWeight, uint128 newWeight);
    event ThresholdUpdated(uint256 oldThreshold, uint256 newThreshold);

    modifier onlyOwner() {
        require(msg.sender == owner, "BridgeValidator: not owner");
        _;
    }

    constructor(uint256 _threshold) {
        owner = msg.sender;
        threshold = _threshold;
    }

    function addValidator(address validator, uint128 weight) external onlyOwner {
        require(!validators[validator].isActive, "BridgeValidator: already active");
        require(weight > 0, "BridgeValidator: zero weight");
        require(totalWeight + weight <= MAX_TOTAL_WEIGHT, "BridgeValidator: max weight exceeded");

        validators[validator] = Validator({
            isActive: true,
            weight: weight,
            addedAt: block.timestamp
        });

        totalWeight += weight;
        validatorList.push(validator);

        emit ValidatorAdded(validator, weight);
    }

    function removeValidator(address validator) external onlyOwner {
        require(validators[validator].isActive, "BridgeValidator: not active");
        require(_activeCount() > MIN_VALIDATORS, "BridgeValidator: min validators");

        totalWeight -= validators[validator].weight;
        validators[validator].isActive = false;
        validators[validator].weight = 0;

        emit ValidatorRemoved(validator);
    }

    function updateWeight(address validator, uint128 newWeight) external onlyOwner {
        require(validators[validator].isActive, "BridgeValidator: not active");
        require(newWeight > 0, "BridgeValidator: zero weight");

        uint128 oldWeight = validators[validator].weight;
        uint256 newTotal = totalWeight - oldWeight + newWeight;
        require(newTotal <= MAX_TOTAL_WEIGHT, "BridgeValidator: max weight exceeded");
        totalWeight = newTotal;
        validators[validator].weight = newWeight;

        emit ValidatorWeightUpdated(validator, oldWeight, newWeight);
    }

    function setThreshold(uint256 _threshold) external onlyOwner {
        require(_threshold > 0, "BridgeValidator: zero threshold");
        uint256 old = threshold;
        threshold = _threshold;
        emit ThresholdUpdated(old, _threshold);
    }

    function hasConsensus(address[] calldata signers) external view returns (bool) {
        uint256 weightSum = 0;
        for (uint256 i = 0; i < signers.length; i++) {
            if (validators[signers[i]].isActive) {
                weightSum += validators[signers[i]].weight;
            }
        }
        return weightSum >= threshold;
    }

    function getValidators() external view returns (address[] memory) {
        return validatorList;
    }

    function bootstrap(address validator, uint128 weight) external onlyOwner {
        require(validatorList.length == 0, "BridgeValidator: already bootstrapped");
        require(weight > 0, "BridgeValidator: zero weight");
        validators[validator] = Validator({ isActive: true, weight: weight, addedAt: block.timestamp });
        totalWeight += weight;
        validatorList.push(validator);
        emit ValidatorAdded(validator, weight);
    }

    function _activeCount() internal view returns (uint256) {
        uint256 count = 0;
        for (uint256 i = 0; i < validatorList.length; i++) {
            if (validators[validatorList[i]].isActive) {
                count++;
            }
        }
        return count;
    }
}
