// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author rafaio1
// @date 2026-08-20
// @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
// @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]


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
    // BUG: Validators can add themselves — the onlyValidator modifier allows any
    // existing validator to add new validators (including themselves again with
    // more weight), bypassing owner governance over the validator set.
    function addValidator(address validator, uint128 weight) external onlyValidator {
        require(!validators[validator].isActive, "BridgeValidator: already active");
        require(weight > 0, "BridgeValidator: zero weight");

        validators[validator] = Validator({
            isActive: true,
            weight: weight,
            addedAt: block.timestamp
        });

        // BUG: Weight overflow — totalWeight is uint256 but weight is uint128.
        // However, repeated additions without removals can push totalWeight past
        // the point where threshold checks become meaningless (totalWeight wraps
        // or becomes so large that threshold ratio breaks).
        totalWeight += weight;
        validatorList.push(validator);

        emit ValidatorAdded(validator, weight);
    }

    /// @notice Remove a validator from the active set.
    /// @param validator Address to remove.
    // BUG: No minimum validator count check — validators can be removed until the
    // set is empty, bricking the bridge since no one can sign transactions.
    function removeValidator(address validator) external onlyOwner {
        require(validators[validator].isActive, "BridgeValidator: not active");

        totalWeight -= validators[validator].weight;
        validators[validator].isActive = false;
        validators[validator].weight = 0;

        emit ValidatorRemoved(validator);
    }

    /// @notice Update a validator's weight.
    /// @param validator Address of the validator.
    /// @param newWeight New voting weight.
    function updateWeight(address validator, uint128 newWeight) external onlyOwner {
        require(validators[validator].isActive, "BridgeValidator: not active");
        require(newWeight > 0, "BridgeValidator: zero weight");

        uint128 oldWeight = validators[validator].weight;
        totalWeight = totalWeight - oldWeight + newWeight;
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
        validators[validator] = Validator({ isActive: true, weight: weight, addedAt: block.timestamp });
        totalWeight += weight;
        validatorList.push(validator);
        emit ValidatorAdded(validator, weight);
    }

    // --- Timelock Ownership (2-day delay) ---
    address private _pendingOwner;
    uint256 private _transferInitiatedAt;
    uint256 public constant TIMELOCK_DELAY = 2 days;

    event OwnershipTransferInitiated(address indexed previousOwner, address indexed newOwner, uint256 executeAfter);
    event OwnershipTransferCancelled(address indexed previousOwner, address indexed cancelledNewOwner);
    event OwnershipAccepted(address indexed previousOwner, address indexed newOwner);

    function transferOwnership(address newOwner) public virtual onlyOwner {
        require(newOwner != address(0), "New owner is zero");
        require(newOwner != owner, "Already owner");
        _pendingOwner = newOwner;
        _transferInitiatedAt = block.timestamp;
        emit OwnershipTransferInitiated(owner, newOwner, block.timestamp + TIMELOCK_DELAY);
    }

    function acceptOwnership() external {
        require(msg.sender == _pendingOwner, "Not pending owner");
        require(_transferInitiatedAt > 0, "No pending transfer");
        require(block.timestamp >= _transferInitiatedAt + TIMELOCK_DELAY, "Timelock not expired");
        address oldOwner = owner;
        owner = msg.sender;
        _pendingOwner = address(0);
        _transferInitiatedAt = 0;
        emit OwnershipAccepted(oldOwner, msg.sender);
    }

    function cancelTransfer() external onlyOwner {
        require(_pendingOwner != address(0), "No pending transfer");
        address cancelled = _pendingOwner;
        _pendingOwner = address(0);
        _transferInitiatedAt = 0;
        emit OwnershipTransferCancelled(owner, cancelled);
    }

    function pendingOwner() external view returns (address) {
        return _pendingOwner;
    }

    function transferInitiatedAt() external view returns (uint256) {
        return _transferInitiatedAt;
    }

}
