// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/Ownable.sol";

contract AgentRegistry is Ownable {
    struct Agent {
        uint256 id;
        string name;
        string endpoint;
    }

    mapping(uint256 => Agent) public agents;
    uint256 public nextAgentId;
    uint256 public registrationFee;

    event AgentRegistered(uint256 indexed agentId, string name, string endpoint);

    constructor(uint256 _registrationFee) {
        registrationFee = _registrationFee;
    }

    function batchRegister(string[] memory names, string[] memory endpoints) external payable {
        require(msg.value == registrationFee * names.length, "Insufficient fee");
        require(names.length <= 50 && endpoints.length <= 50, "Too many agents");

        for (uint256 i = 0; i < names.length; i++) {
            _registerAgent(names[i], endpoints[i]);
        }
    }

    function _registerAgent(string memory name, string memory endpoint) internal {
        require(agents[nextAgentId].id == 0, "Agent ID already in use");

        agents[nextAgentId] = Agent(nextAgentId, name, endpoint);
        emit AgentRegistered(nextAgentId, name, endpoint);
        nextAgentId++;
    }

    function setRegistrationFee(uint256 _registrationFee) external onlyOwner {
        registrationFee = _registrationFee;
    }
}