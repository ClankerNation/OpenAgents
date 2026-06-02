solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title VestingWallet
 * @dev Token vesting contract with migration support
 * 
 * @agent CodeMaven
 * @timestamp 2024-01-15T10:30:00Z
 * @startup-instructions 
 *   npx hardhat compile
 *   npx hardhat test
 *   npx hardhat run scripts/deploy.ts --network localhost
 * @runtime-environment 
 *   os: linux
 *   arch: x64
 *   home_dir: /home/user
 *   working_dir: /home/user/projects/vesting
 *   shell: /bin/bash
 */

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/math/Math.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

contract VestingWallet is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    // Custom errors for gas-efficient error handling
    error ZeroAddress();
    error InvalidAmount();
    error InsufficientBalance();
    error MigrationFailed();
    error AlreadyInitialized();
    error NotInitialized();
    error ClaimWindowNotOpen();
    error TransferFailed();
    error InvalidDuration();
    error BeneficiaryLimitExceeded();
    error MigrationLocked();

    // Events
    event TokensReleased(address indexed beneficiary, uint256 amount);
    event TokenMigrated(address indexed oldToken, address indexed newToken, uint256 amount);
    event VestingScheduleCreated(address indexed beneficiary, uint256 totalAmount);
    event EmergencyWithdraw(address indexed token, uint256 amount);

    // Structs
    struct VestingSchedule {
        uint256 totalAmount;
        uint256 releasedAmount;
        uint256 startTime;
        uint256 duration;
        bool initialized;
    }

    // State variables
    IERC20 private _token;
    mapping(address => VestingSchedule) private _vestingSchedules;
    address[] private _beneficiaries;
    uint256 private _totalVested;
    uint256 private _totalReleased;
    bool private _migrationLocked;

    // Constants
    uint256 public constant MAX_DURATION = 365 days;
    uint256 public constant MIN_DURATION = 1 days;
    uint256 public constant MAX_BENEFICIARIES = 1000;
    uint256 public constant MAX_MIGRATION_ATTEMPTS = 5;

    // Modifiers
    modifier onlyInitialized() {
        if (address(_token) == address(0)) revert NotInitialized();
        _;
    }

    modifier migrationNotLocked() {
        if (_migrationLocked) revert MigrationLocked();
        _;
    }

    modifier validAddress(address addr) {
        if (addr == address(0)) revert ZeroAddress();
        _;
    }

    modifier validAmount(uint256 amount) {
        if (amount == 0) revert InvalidAmount();
        _;
    }

    /**
     * @dev Constructor initializes the contract
     * @param token_ The ERC20 token address for vesting
     */
    constructor(address token_) Ownable(msg.sender) {
        if (token_ == address(0)) revert ZeroAddress();
        _token = IERC20(token_);
    }

    /**
     * @dev Creates a vesting schedule for a beneficiary
     * @param beneficiary Address to receive vested tokens
     * @param totalAmount Total amount of tokens to vest
     * @param duration Duration of vesting period in seconds
     * @return bool Success status
     */
    function createVestingSchedule(
        address beneficiary,
        uint256 totalAmount,
        uint256 duration
    ) external onlyOwner onlyInitialized validAddress(beneficiary) validAmount(totalAmount) returns (bool) {
        if (duration < MIN_DURATION || duration > MAX_DURATION) revert InvalidDuration();
        if (_vestingSchedules[beneficiary].initialized) revert AlreadyInitialized();
        if (_beneficiaries.length >= MAX_BENEFICIARIES) revert BeneficiaryLimitExceeded();

        VestingSchedule storage schedule = _vestingSchedules[beneficiary];
        schedule.totalAmount = totalAmount;
        schedule.startTime = block.timestamp;
        schedule.duration = duration;
        schedule.initialized = true;

        _beneficiaries.push(beneficiary);
        _totalVested += totalAmount;

        emit VestingScheduleCreated(beneficiary, totalAmount);
        return true;
    }

    /**
     * @dev Releases vested tokens to beneficiary
     * @return uint256 Amount of tokens released
     */
    function release() external nonReentrant onlyInitialized returns (uint256) {
        VestingSchedule storage schedule = _vestingSchedules[msg.sender];
        if (!schedule.initialized) revert NotInitialized();

        uint256 releasableAmount = _calculateReleasableAmount(schedule);
        if (releasableAmount == 0) revert ClaimWindowNotOpen();

        schedule.releasedAmount += releasableAmount;
        _totalReleased += releasableAmount;

        _token.safeTransfer(msg.sender, releasableAmount);

        emit TokensReleased(msg.sender, releasableAmount);
        return releasableAmount;
    }

    /**
     * @dev Migrates to a new token address
     * @param newToken Address of the new token
     * @return bool Success status
     */
    function migrateToken(address newToken) 
        external 
        onlyOwner 
        onlyInitialized 
        migrationNotLocked 
        nonReentrant 
        validAddress(newToken)
        returns (bool)
    {
        if (newToken == address(_token)) revert InvalidAmount();

        uint256 remainingBalance = _totalVested - _totalReleased;
        
        // Verify new token balance
        IERC20 newTokenContract = IERC20(newToken);
        uint256 newTokenBalance = newTokenContract.balanceOf(address(this));
        
        if (newTokenBalance < remainingBalance) revert InsufficientBalance();

        // Lock migration to prevent re-entrancy
        _migrationLocked = true;

        // Emit event before state change for transparency
        emit TokenMigrated(address(_token), newToken, remainingBalance);

        // Update token reference
        _token = newTokenContract;

        // Unlock migration
        _migrationLocked = false;

        return true;
    }

    /**
     * @dev Batch release tokens for multiple beneficiaries
     * @param beneficiaries Array of beneficiary addresses
     * @return uint256[] Array of released amounts
     */
    function batchRelease(address[] calldata beneficiaries) 
        external 
        onlyOwner 
        nonReentrant 
        onlyInitialized 
        returns (uint256[] memory) 
    {
        uint256[] memory releasedAmounts = new uint256[](beneficiaries.length);
        
        for (uint256 i = 0; i < beneficiaries.length; i++) {
            VestingSchedule storage schedule = _vestingSchedules[beneficiaries[i]];
            if (!schedule.initialized) continue;

            uint256 releasableAmount = _calculateReleasableAmount(schedule);
            if (releasableAmount > 0) {
                schedule.releasedAmount += releasableAmount;
                _totalReleased += releasableAmount;
                releasedAmounts[i] = releasableAmount;
                
                _token.safeTransfer(beneficiaries[i], releasableAmount);
                emit TokensReleased(beneficiaries[i], releasableAmount);
            }
        }
        
        return releasedAmounts;
    }

    /**
     * @dev Calculates the releasable amount for a beneficiary
     * @param schedule The vesting schedule
     * @return uint256 Releasable amount
     */
    function _calculateReleasableAmount(VestingSchedule storage schedule) 
        private 
        view 
        returns (uint256) 
    {
        if (block.timestamp < schedule.startTime) return 0;
        
        uint256 elapsed = block.timestamp - schedule.startTime;
        if (elapsed >= schedule.duration) {
            return schedule.totalAmount - schedule.releasedAmount;
        }
        
        uint256 vestedAmount = Math.mulDiv(schedule.totalAmount, elapsed, schedule.duration);
        return vestedAmount - schedule.releasedAmount;
    }

    /**
     * @dev Returns the vesting schedule for a beneficiary
     * @param beneficiary Address to query
     * @return VestingSchedule The vesting schedule
     */
    function getVestingSchedule(address beneficiary) 
        external 
        view 
        validAddress(beneficiary)
        returns (VestingSchedule memory) 
    {
        return _vestingSchedules[beneficiary];
    }

    /**
     * @dev Returns the current token address
     * @return address Current token address
     */
    function getToken() external view returns (address) {
        return address(_token);
    }

    /**
     * @dev Returns total vested amount
     * @return uint256 Total vested
     */
    function getTotalVested() external view returns (uint256) {
        return _totalVested;
    }

    /**
     * @dev Returns total released amount
     * @return uint256 Total released
     */
    function getTotalReleased() external view returns (uint256) {
        return _totalReleased;
    }

    /**
     * @dev Returns remaining balance to be vested
     * @return uint256 Remaining balance
     */
    function getRemainingBalance() external view returns (uint256) {
        return _totalVested - _totalReleased;
    }

    /**
     * @dev Returns all beneficiaries
     * @return address[] Array of beneficiary addresses
     */
    function getBeneficiaries() external view returns (address[] memory) {
        return _beneficiaries;
    }

    /**
     * @dev Returns beneficiary count
     * @return uint256 Number of beneficiaries
     */
    function getBeneficiaryCount() external view returns (uint256) {
        return _beneficiaries.length;
    }

    /**
     * @dev Emergency withdraw of stuck tokens (only owner)
     * @param token Address of token to withdraw
     * @param amount Amount to withdraw
     * @return bool Success status
     */
    function emergencyWithdraw(address token, uint256 amount) 
        external 
        onlyOwner 
        nonReentrant 
        validAddress(token)
        validAmount(amount)
        returns (bool)
    {
        IERC20(token).safeTransfer(owner(), amount);
        
        emit EmergencyWithdraw(token, amount);
        return true;
    }

    /**
     * @dev Check if contract is initialized
     * @return bool Initialization status
     */
    function isInitialized() external view returns (bool) {
        return address(_token) != address(0);
    }

    /**
     * @dev Check if migration is locked
     * @return bool Migration lock status
     */
    function isMigrationLocked() external view returns (bool) {
        return _migrationLocked;
    }

    /**
     * @dev Fallback function to prevent accidental ETH transfers
     */
    receive() external payable {
        revert TransferFailed();
    }
}