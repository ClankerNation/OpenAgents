// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @contributor rafaio1
 * @timestamp 2026-08-20T01:00:00Z
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */


/**
 * @fix-author rafaio1
 * @date 2026-08-20T00:00:00Z
 * @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-instructions [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */

import "@openzeppelin/contracts/access/Ownable.sol";

contract AgentRegistry is Ownable {
    struct Agent {
        address owner;
        string name;
        string endpoint;
        uint256 reputation;
        uint256 tasksCompleted;
        uint256 registeredAt;
        bool active;
    }

    mapping(bytes32 => Agent) public agents;
    mapping(address => bytes32[]) public ownerAgents;
    bytes32[] public agentIds;

    uint256 public registrationFee;
    uint256 public minReputation;
    uint256 public constant MAX_BATCH_SIZE = 50;
    
    // Monotonic counter for unique agent IDs to prevent frontrunning/collision
    uint256 private _nextAgentId;

    event AgentRegistered(bytes32 indexed agentId, address indexed owner, string name);
    event AgentDeactivated(bytes32 indexed agentId);
    event ReputationUpdated(bytes32 indexed agentId, uint256 newReputation);

    constructor(uint256 _registrationFee) Ownable(msg.sender) {
        registrationFee = _registrationFee;
        minReputation = 0;
    }

    function registerAgent(string calldata name, string calldata endpoint) external payable returns (bytes32) {
        require(msg.value >= registrationFee, "Insufficient fee");
        require(bytes(name).length > 0 && bytes(name).length <= 64, "Invalid name");

        // Use incrementing counter + sender + name for guaranteed uniqueness
        bytes32 agentId = keccak256(abi.encodePacked(_nextAgentId++, msg.sender, name));

        require(agents[agentId].registeredAt == 0, "Agent exists");

        agents[agentId] = Agent({
            owner: msg.sender,
            name: name,
            endpoint: endpoint,
            reputation: 100,
            tasksCompleted: 0,
            registeredAt: block.timestamp,
            active: true
        });

        ownerAgents[msg.sender].push(agentId);
        agentIds.push(agentId);

        emit AgentRegistered(agentId, msg.sender, name);
        return agentId;
    }

    /// @notice Register multiple agents in a single transaction for gas efficiency.
    /// @param names Array of agent names (max 50).
    /// @param endpoints Array of agent endpoints (must match names length).
    function batchRegister(
        string[] calldata names,
        string[] calldata endpoints
    ) external payable returns (bytes32[] memory ids) {
        uint256 count = names.length;
        require(count > 0 && count <= MAX_BATCH_SIZE, "Invalid batch size");
        require(endpoints.length == count, "Length mismatch");
        require(msg.value >= registrationFee * count, "Insufficient total fee");

        ids = new bytes32[](count);

        for (uint256 i = 0; i < count; i++) {
            require(bytes(names[i]).length > 0 && bytes(names[i]).length <= 64, "Invalid name");

            // Counter guarantees uniqueness even within same tx/block
            bytes32 agentId = keccak256(abi.encodePacked(_nextAgentId++, msg.sender, names[i]));
            require(agents[agentId].registeredAt == 0, "Agent exists");

            agents[agentId] = Agent({
                owner: msg.sender,
                name: names[i],
                endpoint: endpoints[i],
                reputation: 100,
                tasksCompleted: 0,
                registeredAt: block.timestamp,
                active: true
            });

            ownerAgents[msg.sender].push(agentId);
            agentIds.push(agentId);

            ids[i] = agentId;
            emit AgentRegistered(agentId, msg.sender, names[i]);
        }

        return ids;
    }

    function deactivateAgent(bytes32 agentId) external {
        require(agents[agentId].owner == msg.sender, "Not agent owner");
        agents[agentId].active = false;
        emit AgentDeactivated(agentId);
    }

    function updateReputation(bytes32 agentId, int256 delta) external onlyOwner {
        Agent storage agent = agents[agentId];
        require(agent.registeredAt > 0, "Agent not found");

        if (delta > 0) {
            agent.reputation += uint256(delta);
        } else {
            uint256 decrease = uint256(-delta);
            agent.reputation = agent.reputation > decrease ? agent.reputation - decrease : 0;
        }

        emit ReputationUpdated(agentId, agent.reputation);
    }

    function getAgent(bytes32 agentId) external view returns (Agent memory) {
        return agents[agentId];
    }

    function getActiveAgentCount() external view returns (uint256 count) {
        for (uint256 i = 0; i < agentIds.length; i++) {
            if (agents[agentIds[i]].active) count++;
        }
    }

    function setRegistrationFee(uint256 _fee) external onlyOwner {
        registrationFee = _fee;
    }

    function withdrawFees() external onlyOwner {
        (bool success, ) = owner().call{value: address(this).balance}("");
        require(success, "Withdraw failed");
    }

    // Timelock ownership transfer
    address private _pendingOwner;
    uint256 private _ownershipTransferDeadline;
    uint256 public constant OWNERSHIP_TIMELOCK = 2 days;

    event OwnershipTransferStarted(address indexed previousOwner, address indexed newOwner, uint256 deadline);
    event OwnershipTransferAccepted(address indexed previousOwner, address indexed newOwner);
    event OwnershipTransferCancelled(address indexed previousOwner, address indexed cancelledOwner);

    /// @notice Start ownership transfer with 2-day timelock.
    /// @param newOwner Address of the pending owner.
    function transferOwnership(address newOwner) public override onlyOwner {
        require(newOwner != address(0), "Ownable: zero address");
        require(newOwner != owner(), "Ownable: same owner");
        _pendingOwner = newOwner;
        _ownershipTransferDeadline = block.timestamp + OWNERSHIP_TIMELOCK;
        emit OwnershipTransferStarted(owner(), newOwner, _ownershipTransferDeadline);
    }

    /// @notice Accept ownership after timelock period.
    function acceptOwnership() external {
        require(msg.sender == _pendingOwner, "Ownable: not pending owner");
        require(block.timestamp >= _ownershipTransferDeadline, "Ownable: timelock active");
        
        address oldOwner = owner();
        _transferOwnership(_pendingOwner);
        _pendingOwner = address(0);
        _ownershipTransferDeadline = 0;
        emit OwnershipTransferAccepted(oldOwner, msg.sender);
    }

    /// @notice Cancel pending ownership transfer.
    function cancelOwnershipTransfer() external onlyOwner {
        require(_pendingOwner != address(0), "Ownable: no pending transfer");
        address cancelled = _pendingOwner;
        _pendingOwner = address(0);
        _ownershipTransferDeadline = 0;
        emit OwnershipTransferCancelled(owner(), cancelled);
    }

    /// @notice Get pending owner address.
    function pendingOwner() external view returns (address) {
        return _pendingOwner;
    }

    /// @notice Get ownership transfer deadline.
    function ownershipTransferDeadline() external view returns (uint256) {
        return _ownershipTransferDeadline;
    }

}
