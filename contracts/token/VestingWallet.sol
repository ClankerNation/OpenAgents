// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract VestingWallet is Ownable {
    IERC20 public token;
    mapping(address => uint256) public vestedAmounts;
    mapping(address => uint256) public releasedAmounts;
    uint256 public startTime;
    uint256 public duration = 365 days;
    
    event TokenChanged(address indexed oldToken, address indexed newToken);  // Fix #170
    event Released(address indexed beneficiary, uint256 amount);
    
    constructor(address _token) Ownable(msg.sender) { token = IERC20(_token); startTime = block.timestamp; }
    
    function changeToken(address newToken) external onlyOwner {  // Fix #170
        address old = address(token);
        token = IERC20(newToken);
        emit TokenChanged(old, newToken);
    }
    
    function release(address beneficiary) external {
        uint256 vested = vestedAmounts[beneficiary];
        uint256 released = releasedAmounts[beneficiary];
        uint256 releasable = vested * (block.timestamp - startTime) / duration - released;
        require(releasable > 0, "Nothing to release");
        releasedAmounts[beneficiary] += releasable;
        token.transfer(beneficiary, releasable);
        emit Released(beneficiary, releasable);
    }
}
