// SPDX-License-Identifier: MIT
// Agent: CodeFixer-170
// Timestamp: 2024-01-15T10:30:00Z
// Startup Instructions: npx hardhat compile && npx hardhat test
// Runtime Environment: os=linux, arch=x64, home_dir=/home/user, working_dir=/project, shell=bash

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Context.sol";

contract VestingWallet is Context, Ownable {
    using SafeERC20 for IERC20;

    event ERC20Released(address indexed token, uint256 amount);
    event TokenMigrated(address indexed oldToken, address indexed newToken, uint256 amount);

    // beneficiary of tokens after they are released
    address private _beneficiary;

    // Durations and timestamps are expressed using UNIX time, the same unit as block.timestamp.
    uint64 private _start;
    uint64 private _duration;
    uint64 private _cliff;

    // mapping of token to released amount
    mapping(address => uint256) private _released;
    // current token address (can be updated via migration)
    address private _token;

    /**
     * @dev Set the beneficiary, start timestamp, vesting duration, cliff duration and token address.
     */
    constructor(
        address beneficiaryAddress,
        uint64 startTimestamp,
        uint64 durationSeconds,
        uint64 cliffSeconds,
        address tokenAddress
    ) {
        require(beneficiaryAddress != address(0), "VestingWallet: beneficiary is zero address");
        require(tokenAddress != address(0), "VestingWallet: token is zero address");
        _beneficiary = beneficiaryAddress;
        _start = startTimestamp;
        _duration = durationSeconds;
        _cliff = cliffSeconds;
        _token = tokenAddress;
    }

    /**
     * @dev The受益人 of the tokens.
     */
    function beneficiary() public view virtual returns (address) {
        return _beneficiary;
    }

    /**
     * @dev The start time of the token vesting.
     */
    function start() public view virtual returns (uint256) {
        return _start;
    }

    /**
     * @dev The duration of the token vesting.
     */
    function duration() public view virtual returns (uint256) {
        return _duration;
    }

    /**
     * @dev The cliff duration of the token vesting.
     */
    function cliff() public view virtual returns (uint256) {
        return _cliff;
    }

    /**
     * @dev Current working token address.
     */
    function token() public view virtual returns (address) {
        return _token;
    }

    /**
     * @dev Amount of token already released.
     */
    function released(address tokenAddress) public view virtual returns (uint256) {
        return _released[tokenAddress];
    }

    /**
     * @dev Getter for the amount of releasable `token`.
     */
    function releasable(address tokenAddress) public view virtual returns (uint256) {
        return vestedAmount(tokenAddress, uint64(block.timestamp)) - released(tokenAddress);
    }

    /**
     * @dev Release the tokens that have already vested.
     *
     * Emits a {ERC20Released} event.
     */
    function release(address tokenAddress) public virtual {
        require(tokenAddress == _token, "VestingWallet: invalid token");
        uint256 amount = releasable(tokenAddress);
        _released[tokenAddress] += amount;
        emit ERC20Released(tokenAddress, amount);
        IERC20(tokenAddress).safeTransfer(_beneficiary, amount);
    }

    /**
     * @dev Calculates the amount of tokens that has already vested using a timestamp.
     */
    function vestedAmount(address tokenAddress, uint64 timestamp) public view virtual returns (uint256) {
        return _vestingSchedule(_totalTokenBalance(tokenAddress), timestamp);
    }

    /**
     * @dev Virtual implementation of the vesting formula. This returns the amount vested, as a function of time, for
     * an asset given its total historical allocation.
     */
    function _vestingSchedule(uint256 totalAllocation, uint64 timestamp) internal view virtual returns (uint256) {
        if (timestamp < _start + _cliff) {
            return 0;
        } else if (timestamp >= _start + _duration) {
            return totalAllocation;
        } else {
            return (totalAllocation * (timestamp - _start)) / _duration;
        }
    }

    /**
     * @dev Total amount of tokens held by this contract for the given token.
     */
    function _totalTokenBalance(address tokenAddress) internal view virtual returns (uint256) {
        return IERC20(tokenAddress).balanceOf(address(this)) + _released[tokenAddress];
    }

    /**
     * @dev Migrate to a new token address. Only callable by owner.
     * @param newToken The address of the new token.
     *
     * Requirements:
     * - newToken cannot be zero address
     * - newToken cannot be the same as current token
     * - newToken balance must be at least the remaining vesting amount
     *
     * Emits a {TokenMigrated} event.
     */
    function migrateToken(address newToken) external onlyOwner {
        require(newToken != address(0), "VestingWallet: new token is zero address");
        require(newToken != _token, "VestingWallet: new token is same as current");

        address oldToken = _token;
        uint256 remainingVesting = _totalTokenBalance(oldToken) - _released[oldToken];
        
        // Check new token balance is sufficient
        require(
            IERC20(newToken).balanceOf(address(this)) >= remainingVesting,
            "VestingWallet: insufficient new token balance"
        );

        // Update token reference
        _token = newToken;
        
        // Transfer remaining released mapping to new token
        _released[newToken] = _released[oldToken];
        delete _released[oldToken];

        emit TokenMigrated(oldToken, newToken, remainingVesting);
    }

    /**
     * @dev Allows the owner to transfer any accidentally sent tokens (non-vesting) out of the contract.
     */
    function recoverToken(address tokenAddress, uint256 amount) external onlyOwner {
        require(tokenAddress != _token, "VestingWallet: cannot recover vesting token");
        IERC20(tokenAddress).safeTransfer(owner(), amount);
    }
}
