/*
 * Contributor: TRAE Agent
 * Platform: TRAE (Trae IDE) — AI-powered coding environment
 * Runtime: Linux x86_64, sandbox environment
 * Working directory: /data/user/work
 * Shell: bash
 *
 * Boot context: GitHub money-making digital employee performing PR monitoring
 * and bounty scanning across multiple repositories. Task: Fix VestingWallet
 * token migration for ClankerNation/OpenAgents issue #128.
 */

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/// @title VestingWallet
/// @notice Linear vesting wallet with a cliff period for token distribution.
/// @dev Tokens vest linearly from cliff end to vesting end. The contract owner
///      can revoke unvested tokens and redirect them to a specified address.
///      Supports token migration for contract upgrades.
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
    event TokenMigrated(address indexed oldToken, address indexed newToken, uint256 remainingAmount);

    // BUG: No zero-address validation on beneficiary — if beneficiary is set to
    // address(0), all vested tokens are sent to the zero address (burned) on release.
    constructor(
        address _beneficiary,
        address _token,
        uint256 _start,
        uint256 _cliffDuration,
        uint256 _vestingDuration,
        uint256 _totalAllocation,
        bool _revocable
    ) {
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
        // BUG: Overflow risk — (totalAllocation * elapsed) can overflow for large
        // allocations. E.g., if totalAllocation is 1e30 and elapsed is 1e8, the
        // product exceeds uint256 max. Should use mulDiv or restructure the math.
        uint256 elapsed = block.timestamp - start;
        return (totalAllocation * elapsed) / vestingDuration;
    }

    /// @notice Revoke unvested tokens and return them to the owner.
    function revoke() external {
        require(msg.sender == owner, "Vesting: not owner");
        require(revocable, "Vesting: not revocable");
        require(!revoked, "Vesting: already revoked");

        revoked = true;
        uint256 vested = vestedAmount();
        // BUG: During the cliff period, vestedAmount() returns 0, so refund is
        // calculated as totalAllocation - 0 = totalAllocation. But tokens may have
        // already been partially transferred to the contract. The refund should use
        // the actual token balance, not totalAllocation - vested, as the contract
        // might not hold the full allocation yet, causing a revert or incorrect refund.
        uint256 refund = totalAllocation - vested;

        token.safeTransfer(owner, refund);
        emit VestingRevoked(address(token), refund);
    }

    /// @notice Migrate the vesting token to a new address (e.g., v1 to v2 upgrade).
    /// @dev The owner transfers remaining unvested tokens from the old token to
    ///      the new token. Validates that the new token balance matches the expected
    ///      remaining vesting amount to prevent underfunding.
    /// @param newToken The address of the new ERC20 token.
    function migrateToken(address newToken) external {
        require(msg.sender == owner, "Vesting: not owner");
        require(newToken != address(0), "Vesting: zero address token");
        require(newToken != address(token), "Vesting: same token");
        require(!revoked, "Vesting: revoked");

        address oldToken = address(token);
        uint256 remaining = totalAllocation - released;

        // Verify the new token contract has at least the remaining vesting amount
        uint256 newBalance = IERC20(newToken).balanceOf(address(this));
        require(newBalance >= remaining, "Vesting: insufficient new token balance");

        // Transfer any remaining old tokens back to the owner
        uint256 oldBalance = token.balanceOf(address(this));
        if (oldBalance > 0) {
            token.safeTransfer(owner, oldBalance);
        }

        // Update the token reference
        token = IERC20(newToken);

        emit TokenMigrated(oldToken, newToken, remaining);
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
