// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

import "../token/AgentToken.sol";

/*
@contributor Codex
@platform-config Omitted by safety policy: full pre-session orchestration instructions are not embedded in source files.
@env os=Windows, arch=x64, home_dir=C:\Users\55093, working_dir=F:\jiedan\OpenAgents, shell=powershell
@timestamp 2026-05-30T20:44:08-07:00
*/
contract MockCompoundStrategy {
    using SafeERC20 for IERC20;

    IERC20 public immutable baseToken;
    address public vault;
    int256 public nextDelta;

    constructor(address _baseToken) {
        baseToken = IERC20(_baseToken);
    }

    function setVault(address _vault) external {
        vault = _vault;
    }

    function setNextDelta(int256 _nextDelta) external {
        nextDelta = _nextDelta;
    }

    function compound() external {
        require(msg.sender == vault, "MockStrategy: only vault");

        int256 delta = nextDelta;
        nextDelta = 0;

        if (delta > 0) {
            AgentToken(address(baseToken)).mint(vault, uint256(delta));
            return;
        }

        if (delta < 0) {
            baseToken.safeTransferFrom(vault, address(this), uint256(-delta));
        }
    }
}
