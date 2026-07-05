// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

contract AgentRegistry is Ownable {
    mapping(address => string) public agentMetadata;
    mapping(address => bool) public registered;
    address[] public allAgents;
    
    event AgentRegistered(address indexed agent, string metadata);
    event AgentDeregistered(address indexed agent);
    
    constructor() Ownable(msg.sender) {}
    
    function register(address agent, string calldata metadata) external onlyOwner {
        _register(agent, metadata);
    }
    
    function batchRegister(address[] calldata agents, string[] calldata metadatas) external onlyOwner {
        require(agents.length == metadatas.length, "Length mismatch");
        require(agents.length <= 100, "Batch too large");  // Fix #182
        for (uint i = 0; i < agents.length; i++) {
            _register(agents[i], metadatas[i]);
        }
    }
    
    function batchDeregister(address[] calldata agents) external onlyOwner {
        for (uint i = 0; i < agents.length; i++) {
            _deregister(agents[i]);
        }
    }
    
    function _register(address agent, string calldata metadata) internal {
        require(!registered[agent], "Already registered");
        registered[agent] = true;
        agentMetadata[agent] = metadata;
        allAgents.push(agent);
        emit AgentRegistered(agent, metadata);
    }
    
    function _deregister(address agent) internal {
        require(registered[agent], "Not registered");
        registered[agent] = false;
        delete agentMetadata[agent];
        emit AgentDeregistered(agent);
    }
}
