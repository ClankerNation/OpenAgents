// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract AgentToken is ERC20, Ownable {
    uint256 public immutable chainId;  // Fix #162: chain-specific permits
    mapping(address => uint256) public nonces;
    
    constructor(string memory name, string memory symbol, uint256 initialSupply) 
        ERC20(name, symbol) Ownable(msg.sender) {
        _mint(msg.sender, initialSupply);
        chainId = block.chainid;
    }
    
    function permit(address owner, address spender, uint256 value, uint256 deadline, 
                    uint8 v, bytes32 r, bytes32 s) external {
        require(block.timestamp <= deadline, "Expired");
        // Fix #162: include chainId in hash to prevent cross-chain replay
        bytes32 structHash = keccak256(abi.encode(
            keccak256("Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)"),
            owner, spender, value, nonces[owner]++, deadline
        ));
        bytes32 hash = keccak256(abi.encodePacked("\x19\x01", 
            keccak256(abi.encode(block.chainid, address(this))), structHash));
        address signer = ecrecover(hash, v, r, s);
        require(signer == owner, "Invalid signature");
        _approve(owner, spender, value);
    }
}
