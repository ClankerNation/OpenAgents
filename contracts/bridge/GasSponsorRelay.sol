// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/metatx/ERC2771Context.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract GasSponsorRelay is ERC2771Context, ReentrancyGuard {
    mapping(address => uint256) public gasCredits;
    uint256 public constant MAX_CREDIT = 5 ether;
    uint256 public totalDistributed;
    address public sponsor;
    
    event GasSponsored(address indexed user, uint256 amount, uint256 timestamp);
    event GasUsed(address indexed user, uint256 gasCost, address indexed target);
    
    constructor(address trustedForwarder) ERC2771Context(trustedForwarder) {
        sponsor = msg.sender;
    }
    
    function addCredit(address user, uint256 amount) external {
        require(msg.sender == sponsor, "Only sponsor");
        require(gasCredits[user] + amount <= MAX_CREDIT, "Exceeds max");
        gasCredits[user] += amount;
        totalDistributed += amount;
        emit GasSponsored(user, amount, block.timestamp);
    }
    
    function relayCall(address target, bytes calldata data) external nonReentrant {
        address user = _msgSender();
        uint256 gasStart = gasleft();
        (bool ok,) = target.call(data);
        require(ok, "Relay failed");
        uint256 gasCost = (gasStart - gasleft() + 21000) * tx.gasprice;
        require(gasCredits[user] >= gasCost, "Insufficient credit");
        gasCredits[user] -= gasCost;
        emit GasUsed(user, gasCost, target);
        payable(msg.sender).transfer(gasCost);
    }
}
