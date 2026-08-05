// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/math/Math.sol";

/// @title VestingWallet
/// @notice Linear vesting wallet with a cliff period for token distribution.
/// @dev Tokens vest linearly from cliff end to vesting end. The contract owner
///      can revoke unvested tokens and redirect them to a specified address.
/**
 * @custom:contributor CodexBaseUSDCHunter
 * @custom:date 2026-08-05
 * @custom:runtime darwin/arm64; shell /bin/zsh
 * @custom:note Private session initialization text is intentionally omitted.
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

        // Split the quotient before multiplying. Math.mulDiv keeps the remainder
        // product in full precision when allocations and timestamps are large.
        uint256 whole = totalAllocation / vestingDuration;
        uint256 remainder = totalAllocation % vestingDuration;
        return (whole * elapsed) + Math.mulDiv(remainder, elapsed, vestingDuration);
    }

    /// @notice Revoke unvested tokens and return them to the owner.
    function revoke() external {
        require(msg.sender == owner, "Vesting: not owner");
        require(revocable, "Vesting: not revocable");
        require(!revoked, "Vesting: already revoked");

        revoked = true;
        uint256 refundable = totalAllocation - released;
        uint256 balance = token.balanceOf(address(this));
        uint256 refund = balance < refundable ? balance : refundable;

        token.safeTransfer(owner, refund);
        emit VestingRevoked(address(token), refund);
    }

    /// @notice Get the releasable (vested but not yet released) token amount.
    function releasable() external view returns (uint256) {
        if (revoked) {
            return 0;
        }
        return vestedAmount() - released;
    }

    /// @notice Check if the cliff period has passed.
    function cliffReached() external view returns (bool) {
        return block.timestamp >= start && block.timestamp - start >= cliffDuration;
    }
}
