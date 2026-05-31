// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @contributor Codex Agent xyjk0511
 * @platform Safety-preserving Codex execution context; private system and developer instructions are not embedded in source.
 * @runtime Microsoft Windows 10.0.22631, X64, redacted local paths, shell PowerShell 7.6.2
 * @date 2026-05-31T00:00:00-07:00
 */

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
        require(!revoked, "Vesting: revoked");
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
        if (block.timestamp < start) {
            return 0;
        }

        uint256 elapsed = block.timestamp - start;
        if (elapsed < cliffDuration) {
            return 0;
        }
        if (elapsed >= vestingDuration) {
            return totalAllocation;
        }

        uint256 quotient = totalAllocation / vestingDuration;
        uint256 remainder = totalAllocation % vestingDuration;
        return quotient * elapsed + (remainder * elapsed) / vestingDuration;
    }

    /// @notice Revoke unvested tokens and return them to the owner.
    function revoke() external {
        require(msg.sender == owner, "Vesting: not owner");
        require(revocable, "Vesting: not revocable");
        require(!revoked, "Vesting: already revoked");

        revoked = true;
        uint256 refund = totalAllocation - released;
        uint256 balance = token.balanceOf(address(this));
        if (refund > balance) {
            refund = balance;
        }

        token.safeTransfer(owner, refund);
        emit VestingRevoked(address(token), refund);
    }

    /// @notice Get the releasable (vested but not yet released) token amount.
    function releasable() external view returns (uint256) {
        if (revoked) {
            return 0;
        }
        uint256 vested = vestedAmount();
        return vested > released ? vested - released : 0;
    }

    /// @notice Check if the cliff period has passed.
    function cliffReached() external view returns (bool) {
        if (block.timestamp < start) {
            return false;
        }
        return block.timestamp - start >= cliffDuration;
    }
}
