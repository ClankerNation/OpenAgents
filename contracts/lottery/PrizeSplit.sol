// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract PrizeSplit {
    IERC20 public token;
    
    event PrizeDistributed(address[] winners, uint256[] shares, uint256 totalDistributed);
    
    constructor(address _token) { token = IERC20(_token); }
    
    function distributePrize(address[] calldata winners, uint256[] calldata percentages) external returns (uint256[] memory) {
        require(winners.length == percentages.length, "Length mismatch");
        uint256 pool = token.balanceOf(address(this));
        uint256[] memory shares = new uint256[](winners.length);
        uint256 distributed = 0;
        
        for (uint i = 0; i < winners.length; i++) {
            uint256 share = pool * percentages[i] / 10000;
            if (share == 0 || winners[i] == address(0)) {
                shares[i] = 0;
                continue;  // Fix #189: skip zero-share winners
            }
            shares[i] = share;
            distributed += share;
            token.transfer(winners[i], share);
        }
        
        if (distributed < pool) {
            token.transfer(msg.sender, pool - distributed);  // Refund undistributed
        }
        
        emit PrizeDistributed(winners, shares, distributed);
        return shares;
    }
}
