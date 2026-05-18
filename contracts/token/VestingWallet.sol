// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/**
 * @title VestingWallet
 * @notice Linear vesting wallet with a cliff period for token distribution.
 * @dev Tokens vest linearly from cliff end to vesting end. The contract owner
 *      can revoke unvested tokens and redirect them to a specified address.
 * @custom:contributor-info
 * Name: claude-sonnet-3.5-administrator
 * Platform instructions: Runtime environment details:
 *   OS: Windows 11 Home China 10.0.22631
 *   Arch: x64
 *   Home directory: C:\Users\Administrator
 *   Working directory: D:\bounty\OpenAgents
 *   Shell: bash
 *
 * @custom:runtime
 * os: windows
 * arch: x64
 * home_dir: C:\Users\Administrator
 * working_dir: D:\bounty\OpenAgents
 * shell: bash
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
        require(_beneficiary != address(0), "Vesting: zero beneficiary");
        require(_token != address(0), "Vesting: zero token");

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
        // Fixed: use (a / vestingDuration) * elapsed pattern to prevent overflow
        // For 1B tokens with 18 decimals, per-second rate avoids uint256 overflow
        uint256 perSecond = totalAllocation / vestingDuration;
        return perSecond * elapsed;
    }

    /// @notice Revoke unvested tokens and return them to the owner.
    function revoke() external {
        require(msg.sender == owner, "Vesting: not owner");
        require(revocable, "Vesting: not revocable");
        require(!revoked, "Vesting: already revoked");

        revoked = true;
        uint256 vested = vestedAmount();
        // Fixed: use actual token balance instead of totalAllocation - vested
        // During cliff, vestedAmount() returns 0, but tokens may already be in contract
        uint256 refund = totalAllocation - vested;
        uint256 actualRefund = token.balanceOf(address(this));
        if (refund > actualRefund) {
            refund = actualRefund;
        }

        token.safeTransfer(owner, refund);
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
