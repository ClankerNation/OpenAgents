// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/governance/TimelockController.sol";

contract SecureTimelock is TimelockController {
    mapping(bytes32 => uint256) public queueTimes;
    
    constructor(uint256 minDelay, address[] memory proposers, address[] memory executors) 
        TimelockController(minDelay, proposers, executors, msg.sender) {}
    
    function queue(address target, uint256 value, bytes calldata data, bytes32 predecessor, bytes32 salt) 
        public override returns (bytes32 id) {
        id = super.queue(target, value, data, predecessor, salt);
        queueTimes[id] = block.timestamp;  // Fix #201: track queue time
        return id;
    }
    
    function execute(address target, uint256 value, bytes calldata payload, bytes32 predecessor, bytes32 salt) 
        public payable override {
        bytes32 id = hashOperation(target, value, payload, predecessor, salt);
        require(isOperationReady(id), "Not ready");
        require(block.timestamp >= queueTimes[id] + getMinDelay(), "Delay not elapsed");  // Fix #201
        super.execute(target, value, payload, predecessor, salt);
    }
}
