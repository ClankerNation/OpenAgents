solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title AgentRegistry
 * @notice Production-grade agent registry with collision-resistant ID generation
 * @dev Uses incrementing counter for unique agent IDs, immune to mempool frontrunning
 * 
 * @generated-by
 * Author: AI Assistant
 * Timestamp: 2024-01-15T10:30:00Z
 * Startup Configuration:
 * You are an expert software engineer and technical writer. Your task is to generate production-ready content for the specified file. Follow the instructions precisely. Do NOT write code fences around your output unless the file type requires them (e.g., .sol, .js, .json). For markdown files, write plain markdown. For JSON files, write valid JSON. For Solidity files, write valid Solidity code. Always output the complete file content. Do not truncate or summarize. If the file requires a specific structure, follow it exactly. Include all required metadata, documentation blocks, and contributor records as specified. Validate your output against the acceptance criteria before finalizing.
 * Runtime:
 *   OS: Linux x86_64
 *   Architecture: amd64
 *   Home: /home/developer
 *   CWD: /home/developer/projects/agent-registry
 */

import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";
import "@openzeppelin/contracts/utils/Strings.sol";

/**
 * @dev Custom errors for gas-efficient error handling
 */
error AgentRegistry__NameEmpty();
error AgentRegistry__NameTooLong(uint256 maxLength);
error AgentRegistry__AgentAlreadyExists(uint256 agentId);
error AgentRegistry__InvalidAgentId(uint256 agentId);
error AgentRegistry__AgentNotRegistered(uint256 agentId);
error AgentRegistry__AgentNotActive(uint256 agentId);
error AgentRegistry__UnauthorizedAccess(address caller);
error AgentRegistry__TransferFailed();
error AgentRegistry__Paused();
error AgentRegistry__InvalidAddress();
error AgentRegistry__NameAlreadyTaken();
error AgentRegistry__ArrayIndexOutOfBounds();

/**
 * @title AgentRegistry
 * @notice Manages agent registration with unique, collision-resistant IDs
 * @dev Uses incrementing counter to prevent mempool frontrunning attacks
 */
contract AgentRegistry is ReentrancyGuard, Ownable, Pausable {
    using Strings for uint256;

    // ---------- Type Declarations ----------
    
    /**
     * @dev Agent struct containing all registration metadata
     */
    struct Agent {
        uint256 id;
        address owner;
        string name;
        uint256 registeredAt;
        uint256 updatedAt;
        bool active;
    }

    // ---------- State Variables ----------
    
    /// @notice Maximum allowed name length
    uint256 public constant MAX_NAME_LENGTH = 100;
    
    /// @notice Minimum allowed name length
    uint256 public constant MIN_NAME_LENGTH = 1;
    
    /// @notice Counter for generating unique agent IDs
    uint256 private _nextAgentId;
    
    /// @notice Mapping from agent ID to Agent struct
    mapping(uint256 => Agent) private _agents;
    
    /// @notice Mapping from owner address to list of agent IDs
    mapping(address => uint256[]) private _ownerAgents;
    
    /// @notice Mapping from (owner, name) to agent ID for quick lookup
    mapping(bytes32 => uint256) private _nameHashToAgentId;
    
    /// @notice Total number of registered agents
    uint256 private _totalAgents;
    
    /// @notice Total number of active agents
    uint256 private _activeAgents;

    // ---------- Events ----------
    
    event AgentRegistered(
        uint256 indexed agentId,
        address indexed owner,
        string name,
        uint256 timestamp
    );
    
    event AgentUpdated(
        uint256 indexed agentId,
        string oldName,
        string newName,
        uint256 timestamp
    );
    
    event AgentDeactivated(
        uint256 indexed agentId,
        uint256 timestamp
    );
    
    event AgentReactivated(
        uint256 indexed agentId,
        uint256 timestamp
    );
    
    event AgentTransferred(
        uint256 indexed agentId,
        address indexed from,
        address indexed to,
        uint256 timestamp
    );

    // ---------- Constructor ----------
    
    /**
     * @notice Initializes the contract with counter starting at 1
     * @dev Agent ID 0 is reserved for invalid/unregistered agents
     */
    constructor() Ownable(msg.sender) {
        _nextAgentId = 1;
        _totalAgents = 0;
        _activeAgents = 0;
    }

    // ---------- Modifiers ----------
    
    /**
     * @dev Ensures the contract is not paused
     */
    modifier whenNotPaused() {
        if (paused()) {
            revert AgentRegistry__Paused();
        }
        _;
    }

    /**
     * @dev Validates that an address is not zero
     * @param addr Address to validate
     */
    modifier validAddress(address addr) {
        if (addr == address(0)) {
            revert AgentRegistry__InvalidAddress();
        }
        _;
    }

    /**
     * @dev Ensures the caller is the owner of the agent
     * @param agentId The ID of the agent
     */
    modifier onlyAgentOwner(uint256 agentId) {
        if (_agents[agentId].owner != msg.sender) {
            revert AgentRegistry__UnauthorizedAccess(msg.sender);
        }
        _;
    }

    /**
     * @dev Ensures the agent exists
     * @param agentId The ID of the agent
     */
    modifier agentExists(uint256 agentId) {
        if (_agents[agentId].registeredAt == 0) {
            revert AgentRegistry__AgentNotRegistered(agentId);
        }
        _;
    }

    /**
     * @dev Ensures the agent is active
     * @param agentId The ID of the agent
     */
    modifier agentActive(uint256 agentId) {
        if (!_agents[agentId].active) {
            revert AgentRegistry__AgentNotActive(agentId);
        }
        _;
    }

    // ---------- External Functions ----------
    
    /**
     * @notice Registers a new agent with a unique ID
     * @dev Uses incrementing counter to prevent ID collisions from mempool frontrunning
     * @param name The name of the agent (must be non-empty and within length limits)
     * @return agentId The unique ID assigned to the new agent
     * 
     * Requirements:
     * - Name must not be empty
     * - Name must not exceed MAX_NAME_LENGTH
     * - Agent with same name by same owner must not already exist
     * - Contract must not be paused
     * 
     * Emits a {AgentRegistered} event.
     */
    function registerAgent(
        string calldata name
    ) 
        external 
        whenNotPaused 
        nonReentrant 
        returns (uint256 agentId) 
    {
        // Input validation
        _validateName(name);
        
        // Check for duplicate name by same owner
        bytes32 nameHash = _computeNameHash(msg.sender, name);
        if (_nameHashToAgentId[nameHash] != 0) {
            revert AgentRegistry__NameAlreadyTaken();
        }
        
        // Generate unique ID using counter (collision-resistant)
        agentId = _nextAgentId;
        _nextAgentId++;
        
        // Create agent struct
        Agent storage agent = _agents[agentId];
        agent.id = agentId;
        agent.owner = msg.sender;
        agent.name = name;
        agent.registeredAt = block.timestamp;
        agent.updatedAt = block.timestamp;
        agent.active = true;
        
        // Update mappings
        _nameHashToAgentId[nameHash] = agentId;
        _ownerAgents[msg.sender].push(agentId);
        
        // Update counters
        _totalAgents++;
        _activeAgents++;
        
        // Emit event
        emit AgentRegistered(agentId, msg.sender, name, block.timestamp);
        
        return agentId;
    }

    /**
     * @notice Registers multiple agents in batch
     * @dev More gas efficient than individual calls
     * @param names Array of agent names to register
     * @return agentIds Array of assigned agent IDs
     * 
     * Requirements:
     * - All names must be valid
     * - No duplicate names for the same owner
     * - Contract must not be paused
     */
    function registerAgentsBatch(
        string[] calldata names
    )
        external
        whenNotPaused
        nonReentrant
        returns (uint256[] memory agentIds)
    {
        uint256 length = names.length;
        agentIds = new uint256[](length);
        
        for (uint256 i = 0; i < length; i++) {
            agentIds[i] = this.registerAgent(names[i]);
        }
        
        return agentIds;
    }

    /**
     * @notice Updates an existing agent's name
     * @param agentId The ID of the agent to update
     * @param newName The new name for the agent
     * 
     * Requirements:
     * - Agent must exist and be active
     * - Caller must be the agent owner
     * - New name must be valid
     * - New name must not be taken by another agent of the same owner
     * 
     * Emits a {AgentUpdated} event.
     */
    function updateAgentName(
        uint256 agentId,
        string calldata newName
    ) 
        external 
        whenNotPaused 
        nonReentrant 
        agentExists(agentId)
        agentActive(agentId)
        onlyAgentOwner(agentId)
    {
        Agent storage agent = _agents[agentId];
        
        // Validate new name
        _validateName(newName);
        
        // Compute name hashes
        bytes32 oldNameHash = _computeNameHash(msg.sender, agent.name);
        bytes32 newNameHash = _computeNameHash(msg.sender, newName);
        
        // Check if new name is already taken by same owner (different agent)
        if (_nameHashToAgentId[newNameHash] != 0 && _nameHashToAgentId[newNameHash] != agentId) {
            revert AgentRegistry__NameAlreadyTaken();
        }
        
        // Update mappings
        delete _nameHashToAgentId[oldNameHash];
        _nameHashToAgentId[newNameHash] = agentId;
        
        // Store old name for event
        string memory oldName = agent.name;
        
        // Update agent
        agent.name = newName;
        agent.updatedAt = block.timestamp;
        
        emit AgentUpdated(agentId, oldName, newName, block.timestamp);
    }

    /**
     * @notice Deactivates an agent (soft delete)
     * @param agentId The ID of the agent to deactivate
     * 
     * Requirements:
     * - Agent must exist and be active
     * - Caller must be the agent owner
     * 
     * Emits a {AgentDeactivated} event.
     */
    function deactivateAgent(
        uint256 agentId
    ) 
        external 
        whenNotPaused 
        nonReentrant 
        agentExists(agentId)
        agentActive(agentId)
        onlyAgentOwner(agentId)
    {
        Agent storage agent = _agents[agentId];
        agent.active = false;
        agent.updatedAt = block.timestamp;
        _activeAgents--;
        
        emit AgentDeactivated(agentId, block.timestamp);
    }

    /**
     * @notice Reactivates a deactivated agent
     * @param agentId The ID of the agent to reactivate
     * 
     * Requirements:
     * - Agent must exist and be inactive
     * - Caller must be the agent owner
     * 
     * Emits a {AgentReactivated} event.
     */
    function reactivateAgent(
        uint256 agentId
    ) 
        external 
        whenNotPaused 
        nonReentrant 
        agentExists(agentId)
        onlyAgentOwner(agentId)
    {
        Agent storage agent = _agents[agentId];
        
        if (agent.active) {
            revert AgentRegistry__AgentAlreadyExists(agentId);
        }
        
        agent.active = true;
        agent.updatedAt = block.timestamp;
        _activeAgents++;
        
        emit AgentReactivated(agentId, block.timestamp);
    }

    /**
     * @notice Transfers agent ownership to a new address
     * @param agentId The ID of the agent to transfer
     * @param newOwner The address of the new owner
     * 
     * Requirements:
     * - Agent must exist and be active
     * - Caller must be the current owner
     * - New owner must be a valid address
     * - New owner must not already have an agent with the same name
     * 
     * Emits a {AgentTransferred} event.
     */
    function transferAgent(
        uint256 agentId,
        address newOwner
    )
        external
        whenNotPaused
        nonReentrant
        agentExists(agentId)
        agentActive(agentId)
        onlyAgentOwner(agentId)
        validAddress(newOwner)
    {
        Agent storage agent = _agents[agentId];
        
        // Check if new owner already has an agent with the same name
        bytes32 nameHash = _computeNameHash(newOwner, agent.name);
        if (_nameHashToAgentId[nameHash] != 0) {
            revert AgentRegistry__NameAlreadyTaken();
        }
        
        // Remove from old owner's list
        _removeFromOwnerList(agent.owner, agentId);
        
        // Update name hash mapping
        bytes32 oldNameHash = _computeNameHash(agent.owner, agent.name);
        delete _nameHashToAgentId[oldNameHash];
        _nameHashToAgentId[nameHash] = agentId;
        
        // Update agent
        address oldOwner = agent.owner;
        agent.owner = newOwner;
        agent.updatedAt = block.timestamp;
        
        // Add to new owner's list
        _ownerAgents[newOwner].push(agentId);
        
        emit AgentTransferred(agentId, oldOwner, newOwner, block.timestamp);
    }

    // ---------- View Functions ----------
    
    /**
     * @notice Returns agent details by ID
     * @param agentId The ID of the agent
     * @return Agent struct containing all agent data
     * 
     * Requirements:
     * - Agent must exist
     */
    function getAgent(uint256 agentId) 
        external 
        view 
        agentExists(agentId) 
        returns (Agent memory) 
    {
        return _agents[agentId];
    }

    /**
     * @notice Returns all agents owned by an address
     * @param owner The address of the owner
     * @return agents Array of Agent structs owned by the address
     */
    function getOwnerAgents(address owner) 
        external 
        view 
        returns (Agent[] memory agents) 
    {
        uint256[] storage agentIds = _ownerAgents[owner];
        uint256 length = agentIds.length;
        agents = new Agent[](length);
        
        for (uint256 i = 0; i < length; i++) {
            agents[i] = _agents[agentIds[i]];
        }
        
        return agents;
    }

    /**
     * @notice Returns agent IDs owned by an address
     * @param owner The address of the owner
     * @return agentIds Array of agent IDs owned by the address
     */
    function getOwnerAgentIds(address owner) 
        external 
        view 
        returns (uint256[] memory agentIds) 
    {
        return _ownerAgents[owner];
    }

    /**
     * @notice Returns the total number of registered agents
     * @return uint256 Total agent count
     */
    function getTotalAgents() external view returns (uint256) {
        return _totalAgents;
    }

    /**
     * @notice Returns the number of active agents
     * @return uint256 Active agent count
     */
    function getActiveAgents() external view returns (uint256) {
        return _activeAgents;
    }

    /**
     * @notice Returns the next available agent ID
     * @return uint256 Next agent ID
     */
    function getNextAgentId() external view returns (uint256) {
        return _nextAgentId;
    }

    /**
     * @notice Checks if an agent exists
     * @param agentId The ID of the agent
     * @return bool True if the agent exists
     */
    function agentExists(uint256 agentId) external view returns (bool) {
        return _agents[agentId].registeredAt != 0;
    }

    /**
     * @notice Checks if an agent is active
     * @param agentId The ID of the agent
     * @return bool True if the agent is active
     */
    function isAgentActive(uint256 agentId) external view returns (bool) {
        return _agents[agentId].active;
    }

    /**
     * @notice Finds agent ID by owner and name
     * @param owner The address of the owner
     * @param name The name of the agent
     * @return agentId The agent ID (0 if not found)
     */
    function findAgentByOwnerAndName(
        address owner, 
        string calldata name
    ) 
        external 
        view 
        returns (uint256 agentId) 
    {
        bytes32 nameHash = _computeNameHash(owner, name);
        return _nameHashToAgentId[nameHash];
    }

    // ---------- Internal Functions ----------
    
    /**
     * @notice Validates agent name
     * @param name The name to validate
     * 
     * Requirements:
     * - Name must not be empty
     * - Name must not exceed MAX_NAME_LENGTH
     */
    function _validateName(string calldata name) internal pure {
        bytes memory nameBytes = bytes(name);
        
        if (nameBytes.length < MIN_NAME_LENGTH) {
            revert AgentRegistry__NameEmpty();
        }
        
        if (nameBytes.length > MAX_NAME_LENGTH) {
            revert AgentRegistry__NameTooLong(MAX_NAME_LENGTH);
        }
    }

    /**
     * @notice Computes the hash for (owner, name) pair
     * @param owner The address of the owner
     * @param name The name of the agent
     * @return bytes32 The computed hash
     */
    function _computeNameHash(address owner, string memory name) internal pure returns (bytes32) {
        return keccak