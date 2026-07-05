// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IPermit2 {
    function permit(address owner, address token, uint160 amount, uint48 expiration, uint48 nonce, bytes calldata sig) external;
    function transferFrom(address from, address to, uint160 amount, address token) external;
}

contract Permit2Adapter {
    IPermit2 public immutable permit2;
    mapping(address => mapping(address => uint256)) public allowances;
    
    event Permit2Transfer(address indexed from, address indexed to, address indexed token, uint256 amount);
    
    constructor(address _permit2) { permit2 = IPermit2(_permit2); }
    
    function depositWithPermit(address token, uint256 amount) external {
        permit2.transferFrom(msg.sender, address(this), uint160(amount), token);
        allowances[msg.sender][token] += amount;
        emit Permit2Transfer(msg.sender, address(this), token, amount);
    }
    
    function withdraw(address token, uint256 amount) external {
        require(allowances[msg.sender][token] >= amount, "Insufficient allowance");
        allowances[msg.sender][token] -= amount;
        IPermit2(permit2).transferFrom(address(this), msg.sender, uint160(amount), token);
        emit Permit2Transfer(address(this), msg.sender, token, amount);
    }
}
