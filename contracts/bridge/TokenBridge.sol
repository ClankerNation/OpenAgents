// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract TokenBridge is Ownable {
    mapping(address => bool) public supportedTokens;
    mapping(uint256 => bool) public processedNonces;
    
    event BridgeInitiated(address indexed sender, address indexed token, uint256 amount, uint256 targetChain, uint256 nonce);
    event BridgeCompleted(address indexed recipient, address indexed token, uint256 amount, uint256 nonce);
    
    constructor() Ownable(msg.sender) {}
    
    function addSupportedToken(address token) external onlyOwner {
        require(token != address(0), "Zero address");  // Fix #152
        require(token.code.length > 0, "Not a contract");  // Fix #152: validate
        supportedTokens[token] = true;
    }
    
    function bridge(address token, uint256 amount, uint256 targetChain) external {
        require(supportedTokens[token], "Token not supported");  // Fix #152
        require(amount > 0, "Zero amount");
        IERC20(token).transferFrom(msg.sender, address(this), amount);
        emit BridgeInitiated(msg.sender, token, amount, targetChain, block.number);
    }
    
    function completeBridge(address recipient, address token, uint256 amount, uint256 nonce) external onlyOwner {
        require(!processedNonces[nonce], "Already processed");
        require(supportedTokens[token], "Token not supported");
        processedNonces[nonce] = true;
        IERC20(token).transfer(recipient, amount);
        emit BridgeCompleted(recipient, token, amount, nonce);
    }
}
