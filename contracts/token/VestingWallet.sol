// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/// @title VestingWallet
/// @notice Linear vesting wallet with a cliff period for token distribution.
/// @dev Tokens vest linearly from cliff end to vesting end. The contract owner
///      can revoke unvested tokens and redirect them to a specified address.
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

    /// @notice Get the releasable (vested but not yet released) token amount.
    function releasable() external view returns (uint256) {
        return vestedAmount() - released;
    }

    /// @notice Migrate vesting to a new token address (e.g., after token upgrade).
    /// @param newToken Address of the new token contract.
    /// @dev Transfers entire remaining balance of old token to owner and updates token reference.
    ///      Owner must ensure new token is pre-funded with equivalent remaining vesting amount.
    function migrateToken(address newToken) external {
        require(msg.sender == owner, "Vesting: not owner");
        require(newToken != address(0), "Vesting: zero address");
        require(newToken != address(token), "Vesting: same token");
        require(!revoked, "Vesting: already revoked");

        // Transfer any remaining old tokens back to owner
        uint256 oldBalance = token.balanceOf(address(this));
        if (oldBalance > 0) {
            token.safeTransfer(owner, oldBalance);
        }

        address oldTokenAddr = address(token);
        token = IERC20(newToken);

        emit TokenMigrated(oldTokenAddr, newToken, oldBalance);
    }

    /// @notice Check if the cliff period has passed.
    function cliffReached() external view returns (bool) {
        return block.timestamp >= start + cliffDuration;
    }
}
