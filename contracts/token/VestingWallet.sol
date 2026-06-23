// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/**
 * @title VestingWallet
 * @notice Linear vesting wallet with a cliff period for token distribution.
 * @dev Tokens vest linearly from cliff end to vesting end. Supports token migration.
 * @contributor Gaotax2006
 * @platform claude-code/opus-4.8
 * @runtime node-v24.15.0 / win32 / amd64
 * @date 2026-06-24
 * @fixes #170 — Added migrateToken for token upgrades, overflow-safe vestedAmount,
 *              zero-address beneficiary validation, balance-aware revoke
 */

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
    event TokenMigrated(IERC20 indexed oldToken, IERC20 indexed newToken, uint256 migratedAmount);

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

    function release() external {
        require(msg.sender == beneficiary, "Vesting: not beneficiary");
        uint256 vested = vestedAmount();
        uint256 unreleased = vested - released;
        require(unreleased > 0, "Vesting: nothing to release");

        released += unreleased;
        token.safeTransfer(beneficiary, unreleased);
        emit TokensReleased(beneficiary, unreleased);
    }

    function vestedAmount() public view returns (uint256) {
        if (block.timestamp < start + cliffDuration) {
            return 0;
        }
        if (block.timestamp >= start + vestingDuration) {
            return totalAllocation;
        }
        // Safe math: divide first to avoid overflow
        uint256 elapsed = block.timestamp - start;
        return (totalAllocation / vestingDuration) * elapsed + (totalAllocation % vestingDuration * elapsed) / vestingDuration;
    }

    function revoke() external {
        require(msg.sender == owner, "Vesting: not owner");
        require(revocable, "Vesting: not revocable");
        require(!revoked, "Vesting: already revoked");

        revoked = true;
        uint256 vested = vestedAmount();
        uint256 refund = totalAllocation - vested;
        // Cap refund at actual contract balance to prevent revert
        uint256 actualBalance = token.balanceOf(address(this));
        if (refund > actualBalance) {
            refund = actualBalance;
        }

        token.safeTransfer(owner, refund);
        emit VestingRevoked(address(token), refund);
    }

    /**
     * @notice Migrate to a new token address (e.g., v1 to v2 upgrade).
     *         Verifies new token balance matches expected remaining vesting amount.
     */
    function migrateToken(IERC20 newToken) external {
        require(msg.sender == owner, "Vesting: not owner");
        require(address(newToken) != address(0), "Vesting: zero token address");
        require(address(newToken) != address(token), "Vesting: same token");

        uint256 remaining = totalAllocation - released;

        // Verify new token has at least the expected balance
        uint256 newBalance = newToken.balanceOf(address(this));
        require(newBalance >= remaining, "Vesting: insufficient new token balance");

        // Transfer remaining tokens to new contract
        token.safeTransfer(address(this), token.balanceOf(address(this)));
        newToken.safeTransferFrom(msg.sender, address(this), newBalance);

        emit TokenMigrated(token, newToken, remaining);

        // Update state
        token = newToken;
    }

    function releasable() external view returns (uint256) {
        return vestedAmount() - released;
    }

    function cliffReached() external view returns (bool) {
        return block.timestamp >= start + cliffDuration;
    }
}
