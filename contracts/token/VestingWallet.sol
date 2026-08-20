// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author rafaio1
// @date 2026-08-20
// @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
// @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/// @title VestingWallet
/// @notice Linear vesting wallet with a cliff period for token distribution.
/// @dev Tokens vest linearly from cliff end to vesting end. The contract owner
///      can revoke unvested tokens and redirect them to a specified address.
///      Supports token migration for upgraded tokens.
contract VestingWallet {
    using SafeERC20 for IERC20;

    address public beneficiary;
    address public owner;
    IERC20 public token;

    uint256 public start;
    uint256 public cliffDuration;
    uint256 public vestingDuration;
    uint256 public totalAllocation;
    uint256 public released;
    bool public revocable;
    bool public revoked;

    event TokensReleased(address indexed beneficiary, uint256 amount);
    event VestingRevoked(address indexed token, uint256 refund);
    event TokenMigrated(address indexed oldToken, address indexed newToken, uint256 balance);

    modifier onlyOwner() {
        require(msg.sender == owner, "Vesting: not owner");
        _;
    }

    constructor(
        address _beneficiary,
        address _token,
        uint256 _start,
        uint256 _cliffDuration,
        uint256 _vestingDuration,
        uint256 _totalAllocation,
        bool _revocable
    ) {
        require(_beneficiary != address(0), "Vesting: zero beneficiary");
        require(_token != address(0), "Vesting: zero token");
        require(_vestingDuration > _cliffDuration, "Vesting: cliff exceeds duration");
        require(_totalAllocation > 0, "Vesting: zero allocation");

        beneficiary = _beneficiary;
        owner = msg.sender;
        token = IERC20(_token);
        start = _start;
        cliffDuration = _cliffDuration;
        vestingDuration = _vestingDuration;
        totalAllocation = _totalAllocation;
        revocable = _revocable;
    }

    /// @notice Migrate to a new token address (e.g., after token upgrade).
    /// @param newToken Address of the new token contract.
    function migrateToken(address newToken) external onlyOwner {
        require(newToken != address(0), "Vesting: zero new token");
        require(newToken != address(token), "Vesting: same token");

        // Verify new token has sufficient balance to cover remaining vesting
        uint256 remaining = totalAllocation - released;
        uint256 newBalance = IERC20(newToken).balanceOf(address(this));
        require(newBalance >= remaining, "Vesting: insufficient new token balance");

        address oldToken = address(token);
        token = IERC20(newToken);

        emit TokenMigrated(oldToken, newToken, newBalance);
    }

    /// @notice Release vested tokens to the beneficiary.
    function release() external {
        require(msg.sender == beneficiary, "Vesting: not beneficiary");
        uint256 vested = vestedAmount();
        uint256 unreleased = vested - released;
        require(unreleased > 0, "Vesting: nothing to release");

        released += unreleased;
        token.safeTransfer(beneficiary, unreleased);
        emit TokensReleased(beneficiary, unreleased);
    }

    /// @notice Calculate the total vested amount at the current timestamp.
    /// @return The total amount of tokens that have vested.
    function vestedAmount() public view returns (uint256) {
        if (block.timestamp < start + cliffDuration) {
            return 0;
        }
        if (block.timestamp >= start + vestingDuration) {
            return totalAllocation;
        }
        uint256 elapsed = block.timestamp - start;
        // Use mulDiv pattern to avoid overflow: (a * b) / c -> a * (b / c) + (a % c) * b / c
        // For simplicity and since vestingDuration is typically large, direct division is safe
        // for reasonable allocations. For extreme values, consider OpenZeppelin Math.mulDiv.
        return (totalAllocation * elapsed) / vestingDuration;
    }

    /// @notice Revoke unvested tokens and return them to the owner.
    function revoke() external onlyOwner {
        require(revocable, "Vesting: not revocable");
        require(!revoked, "Vesting: already revoked");

        revoked = true;
        uint256 vested = vestedAmount();
        uint256 refund = totalAllocation - vested;
        
        // Cap refund to actual balance to prevent revert if contract doesn't hold full allocation
        uint256 balance = token.balanceOf(address(this));
        if (refund > balance) {
            refund = balance;
        }

        if (refund > 0) {
            token.safeTransfer(owner, refund);
        }
        emit VestingRevoked(address(token), refund);
    }

    /// @notice Get the releasable (vested but not yet released) token amount.
    function releasable() external view returns (uint256) {
        return vestedAmount() - released;
    }

    /// @notice Check if the cliff period has passed.
    function cliffReached() external view returns (bool) {
        return block.timestamp >= start + cliffDuration;
    }
}
