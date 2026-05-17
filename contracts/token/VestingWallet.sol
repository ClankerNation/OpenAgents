// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Contributor: Gaotax2006
// Platform: warpSpeed bounty agent, opencode CLI
// Runtime: OS=win32 Arch=x64 Home=C:\Users\asus WorkDir=F:\ai-bounty-work\bounty-hunter\openagents Shell=powershell
// Date: 2026-05-17

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

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
    event TokenMigrated(address indexed oldToken, address indexed newToken);

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
        uint256 unreleased = releasable();
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
        uint256 elapsed = block.timestamp - start;
        uint256 perSecond = totalAllocation / vestingDuration;
        uint256 remainder = totalAllocation % vestingDuration;
        return perSecond * elapsed + (remainder * elapsed) / vestingDuration;
    }

    function revoke() external {
        require(msg.sender == owner, "Vesting: not owner");
        require(revocable, "Vesting: not revocable");
        require(!revoked, "Vesting: already revoked");

        revoked = true;
        uint256 refund = token.balanceOf(address(this));
        if (refund > 0) {
            token.safeTransfer(owner, refund);
        }
        emit VestingRevoked(address(token), refund);
    }

    function releasable() public view returns (uint256) {
        return vestedAmount() - released;
    }

    function migrateToken(address newToken) external {
        require(msg.sender == owner, "Vesting: not owner");
        require(newToken != address(0), "Vesting: zero address");
        emit TokenMigrated(address(token), newToken);
        token = IERC20(newToken);
    }

    function cliffReached() external view returns (bool) {
        return block.timestamp >= start + cliffDuration;
    }
}
