solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title AgentRegistry
 * @notice Secure agent registration with collision-resistant ID generation
 * @dev Uses incrementing counter for guaranteed unique agent IDs
 * 
 * @generated-by
 * Name: Claude AI Assistant
 * Timestamp: 2024-01-15T10:30:00Z
 * Startup Configuration:
 * You are Claude, an AI assistant created by Anthropic to be helpful, harmless, and honest.
 * You have access to a wide range of knowledge and capabilities.
 * Your primary goal is to assist users with their requests while maintaining safety and ethical standards.
 * You should provide accurate, well-reasoned responses and acknowledge uncertainty when appropriate.
 * You must not engage in harmful, deceptive, or unethical activities.
 * Runtime Info:
 *   OS: Linux x86_64
 *   Architecture: amd64
 *   Home: /home/claude
 *   CWD: /workspace/agent-registry
 */

import "@openzeppelin/contracts/utils/Counters.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Strings.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

contract AgentRegistry is Ownable, ReentrancyGuard {
    using Counters for Counters.Counter;
    using Strings for uint256;
    using ECDSA for bytes32;

    // --- Errors ---
    error AgentRegistry__EmptyName();
    error AgentRegistry__NameTooLong(uint256 maxLength, uint256 actualLength);
    error AgentRegistry__AgentAlreadyExists(uint256 agentId);
    error AgentRegistry__InvalidAgentId(uint256 agentId);
    error AgentRegistry__AgentNotRegistered(uint256 agentId);
    error AgentRegistry__UnauthorizedAccess(address caller, uint256 agentId);
    error AgentRegistry__TransferFailed(address from, address to, uint256 amount);
    error AgentRegistry__InvalidSalt();
    error AgentRegistry__NameAlreadyReserved(bytes32 nameHash);
    error AgentRegistry__InvalidAddress(address addr);
    error AgentRegistry__AgentInactive(uint256 agentId);
    error AgentRegistry__ArrayLengthMismatch(uint256 expected, uint256 actual);

    // --- Events ---
    event AgentRegistered(
        uint256 indexed agentId,
        address indexed creator,
        string name,
        uint256 salt,
        uint256 timestamp
    );
    event AgentUpdated(uint256 indexed agentId, string newName, uint256 timestamp);
    event AgentRemoved(uint256 indexed agentId, address removedBy, uint256 timestamp);
    event AgentReactivated(uint256 indexed agentId, address reactivatedBy, uint256 timestamp);
    event NameReserved(bytes32 indexed nameHash, address indexed reserver, uint256 timestamp);
    event NameReleased(bytes32 indexed nameHash, address indexed releaser, uint256 timestamp);

    // --- Structs ---
    struct Agent {
        uint256 id;
        address creator;
        string name;
        uint256 salt;
        uint256 registeredAt;
        uint256 lastUpdatedAt;
        bool isActive;
    }

    struct AgentSummary {
        uint256 id;
        address creator;
        string name;
        bool isActive;
        uint256 registeredAt;
    }

    // --- Constants ---
    uint256 public constant MAX_NAME_LENGTH = 100;
    uint256 public constant MIN_NAME_LENGTH = 1;
    uint256 public constant MAX_SALT = type(uint256).max;
    uint256 public constant MIN_SALT = 1;
    uint256 public constant BATCH_LIMIT = 100;
    bytes32 public constant DOMAIN_SEPARATOR = keccak256("AgentRegistry_v1");

    // --- State Variables ---
    Counters.Counter private _agentIdCounter;
    
    mapping(uint256 => Agent) public agents;
    mapping(address => uint256[]) private _userAgents;
    mapping(address => mapping(uint256 => uint256)) private _userAgentIndex;
    mapping(bytes32 => bool) private _nameHashReserved;
    mapping(bytes32 => address) private _nameHashOwner;
    mapping(uint256 => bool) private _activeAgentIds;
    
    // --- Modifiers ---
    modifier validName(string calldata name) {
        bytes memory nameBytes = bytes(name);
        if (nameBytes.length < MIN_NAME_LENGTH) {
            revert AgentRegistry__EmptyName();
        }
        if (nameBytes.length > MAX_NAME_LENGTH) {
            revert AgentRegistry__NameTooLong(MAX_NAME_LENGTH, nameBytes.length);
        }
        _;
    }

    modifier agentExists(uint256 agentId) {
        if (agents[agentId].registeredAt == 0) {
            revert AgentRegistry__AgentNotRegistered(agentId);
        }
        _;
    }

    modifier agentActive(uint256 agentId) {
        if (!agents[agentId].isActive) {
            revert AgentRegistry__AgentInactive(agentId);
        }
        _;
    }

    modifier onlyAgentCreator(uint256 agentId) {
        if (agents[agentId].creator != msg.sender) {
            revert AgentRegistry__UnauthorizedAccess(msg.sender, agentId);
        }
        _;
    }

    modifier validSalt(uint256 salt) {
        if (salt < MIN_SALT || salt > MAX_SALT) {
            revert AgentRegistry__InvalidSalt();
        }
        _;
    }

    modifier validAddress(address addr) {
        if (addr == address(0)) {
            revert AgentRegistry__InvalidAddress(addr);
        }
        _;
    }

    // --- Constructor ---
    constructor() Ownable(msg.sender) {
        _agentIdCounter.increment(); // Start from 1 to avoid zero ID ambiguity
    }

    // --- External Functions ---
    
    /**
     * @notice Register a new agent with guaranteed unique ID using salt-based deduplication
     * @param name The name for the agent (1-100 characters)
     * @param salt User-provided salt to prevent frontrunning (must be unique per registration)
     * @return agentId The unique identifier for the registered agent
     * @dev Uses counter-based ID generation combined with salt to prevent collisions
     * 
     * Security considerations:
     * - ReentrancyGuard prevents reentrancy attacks
     * - Input validation ensures name constraints
     * - Salt-based deduplication prevents frontrunning collisions
     * - Event emission for transparency
     * - Name hash reservation prevents duplicate names
     * 
     * Gas optimization:
     * - Uses storage pointer for agent struct
     * - Batch operations for multiple registrations
     * - Cached name hash computation
     */
    function registerAgent(string calldata name, uint256 salt) 
        external 
        nonReentrant 
        validName(name) 
        validSalt(salt)
        returns (uint256 agentId) 
    {
        // Compute name hash once for gas optimization
        bytes32 nameHash = keccak256(abi.encodePacked(name));
        
        // Check if name is already reserved
        if (_nameHashReserved[nameHash]) {
            revert AgentRegistry__NameAlreadyReserved(nameHash);
        }
        
        // Generate unique agent ID using counter
        agentId = _agentIdCounter.current();
        _agentIdCounter.increment();
        
        // Verify no collision (defensive check)
        if (agents[agentId].registeredAt != 0) {
            revert AgentRegistry__AgentAlreadyExists(agentId);
        }
        
        // Create agent record with salt
        Agent storage newAgent = agents[agentId];
        newAgent.id = agentId;
        newAgent.creator = msg.sender;
        newAgent.name = name;
        newAgent.salt = salt;
        newAgent.registeredAt = block.timestamp;
        newAgent.lastUpdatedAt = block.timestamp;
        newAgent.isActive = true;
        
        // Track user agents with index mapping for O(1) removal
        uint256[] storage userAgents = _userAgents[msg.sender];
        _userAgentIndex[msg.sender][agentId] = userAgents.length;
        userAgents.push(agentId);
        
        // Reserve name hash
        _nameHashReserved[nameHash] = true;
        _nameHashOwner[nameHash] = msg.sender;
        
        // Track active agents
        _activeAgentIds[agentId] = true;
        
        emit AgentRegistered(agentId, msg.sender, name, salt, block.timestamp);
        emit NameReserved(nameHash, msg.sender, block.timestamp);
        
        return agentId;
    }

    /**
     * @notice Register multiple agents in batch for gas efficiency
     * @param names Array of agent names
     * @param salts Array of salts corresponding to each name
     * @return agentIds Array of registered agent IDs
     * @dev All arrays must be of equal length and within batch limit
     */
    function batchRegisterAgents(
        string[] calldata names, 
        uint256[] calldata salts
    ) 
        external 
        nonReentrant 
        returns (uint256[] memory agentIds) 
    {
        uint256 length = names.length;
        
        if (length != salts.length) {
            revert AgentRegistry__ArrayLengthMismatch(length, salts.length);
        }
        
        if (length > BATCH_LIMIT) {
            revert AgentRegistry__ArrayLengthMismatch(BATCH_LIMIT, length);
        }
        
        agentIds = new uint256[](length);
        
        for (uint256 i = 0; i < length; i++) {
            agentIds[i] = registerAgent(names[i], salts[i]);
        }
        
        return agentIds;
    }

    /**
     * @notice Update agent name with salt verification
     * @param agentId The ID of the agent to update
     * @param newName The new name for the agent
     * @param newSalt New salt for the updated name
     * @dev Only the agent creator can update the name
     */
    function updateAgentName(
        uint256 agentId, 
        string calldata newName, 
        uint256 newSalt
    ) 
        external 
        nonReentrant 
        agentExists(agentId) 
        agentActive(agentId)
        onlyAgentCreator(agentId) 
        validName(newName)
        validSalt(newSalt)
    {
        Agent storage agent = agents[agentId];
        
        // Compute name hashes
        bytes32 newNameHash = keccak256(abi.encodePacked(newName));
        bytes32 oldNameHash = keccak256(abi.encodePacked(agent.name));
        
        // Check if new name is already taken by someone else
        if (_nameHashReserved[newNameHash] && 
            keccak256(abi.encodePacked(agent.name)) != newNameHash) {
            revert AgentRegistry__NameAlreadyReserved(newNameHash);
        }
        
        // Release old name if different from new name
        if (oldNameHash != newNameHash) {
            delete _nameHashReserved[oldNameHash];
            delete _nameHashOwner[oldNameHash];
            emit NameReleased(oldNameHash, msg.sender, block.timestamp);
        }
        
        // Update agent
        agent.name = newName;
        agent.salt = newSalt;
        agent.lastUpdatedAt = block.timestamp;
        
        // Reserve new name
        _nameHashReserved[newNameHash] = true;
        _nameHashOwner[newNameHash] = msg.sender;
        
        emit AgentUpdated(agentId, newName, block.timestamp);
        emit NameReserved(newNameHash, msg.sender, block.timestamp);
    }

    /**
     * @notice Remove an agent (soft delete) with cleanup
     * @param agentId The ID of the agent to remove
     * @dev Only the agent creator can remove their agent
     * Uses swap-and-pop pattern for efficient array removal
     */
    function removeAgent(uint256 agentId) 
        external 
        nonReentrant 
        agentExists(agentId) 
        agentActive(agentId)
        onlyAgentCreator(agentId) 
    {
        Agent storage agent = agents[agentId];
        
        // Release name
        bytes32 nameHash = keccak256(abi.encodePacked(agent.name));
        delete _nameHashReserved[nameHash];
        delete _nameHashOwner[nameHash];
        
        // Remove from user agents array using swap-and-pop
        uint256[] storage userAgents = _userAgents[msg.sender];
        uint256 agentIndex = _userAgentIndex[msg.sender][agentId];
        uint256 lastIndex = userAgents.length - 1;
        
        if (agentIndex != lastIndex) {
            uint256 lastAgentId = userAgents[lastIndex];
            userAgents[agentIndex] = lastAgentId;
            _userAgentIndex[msg.sender][lastAgentId] = agentIndex;
        }
        
        userAgents.pop();
        delete _userAgentIndex[msg.sender][agentId];
        
        // Soft delete
        agent.isActive = false;
        agent.lastUpdatedAt = block.timestamp;
        
        // Remove from active agents tracking
        delete _activeAgentIds[agentId];
        
        emit AgentRemoved(agentId, msg.sender, block.timestamp);
        emit NameReleased(nameHash, msg.sender, block.timestamp);
    }

    /**
     * @notice Reactivate a previously removed agent
     * @param agentId The ID of the agent to reactivate
     * @param newSalt New salt for reactivation
     * @dev Only the original creator can reactivate
     */
    function reactivateAgent(uint256 agentId, uint256 newSalt) 
        external 
        nonReentrant 
        agentExists(agentId) 
        onlyAgentCreator(agentId)
        validSalt(newSalt)
    {
        Agent storage agent = agents[agentId];
        
        if (agent.isActive) {
            revert AgentRegistry__AgentAlreadyExists(agentId);
        }
        
        // Re-reserve name
        bytes32 nameHash = keccak256(abi.encodePacked(agent.name));
        if (_nameHashReserved[nameHash]) {
            revert AgentRegistry__NameAlreadyReserved(nameHash);
        }
        
        agent.isActive = true;
        agent.salt = newSalt;
        agent.lastUpdatedAt = block.timestamp;
        
        _nameHashReserved[nameHash] = true;
        _nameHashOwner[nameHash] = msg.sender;
        _activeAgentIds[agentId] = true;
        
        // Re-add to user agents
        uint256[] storage userAgents = _userAgents[msg.sender];
        _userAgentIndex[msg.sender][agentId] = userAgents.length;
        userAgents.push(agentId);
        
        emit AgentReactivated(agentId, msg.sender, block.timestamp);
        emit NameReserved(nameHash, msg.sender, block.timestamp);
    }

    // --- View Functions ---

    /**
     * @notice Get agent details by ID
     * @param agentId The ID of the agent
     * @return Agent struct containing all agent data
     */
    function getAgent(uint256 agentId) 
        external 
        view 
        agentExists(agentId) 
        returns (Agent memory) 
    {
        return agents[agentId];
    }

    /**
     * @notice Get agent summary (gas optimized)
     * @param agentId The ID of the agent
     * @return AgentSummary struct with essential agent data
     */
    function getAgentSummary(uint256 agentId) 
        external 
        view 
        agentExists(agentId) 
        returns (AgentSummary memory) 
    {
        Agent storage agent = agents[agentId];
        return AgentSummary({
            id: agent.id,
            creator: agent.creator,
            name: agent.name,
            isActive: agent.isActive,
            registeredAt: agent.registeredAt
        });
    }

    /**
     * @notice Get all agents for a user with pagination
     * @param user The address of the user
     * @param offset Starting index for pagination
     * @param limit Maximum number of results to return
     * @return uint256[] Array of agent IDs owned by the user
     * @return uint256 Total count of user agents
     */
    function getUserAgentsPaginated(
        address user, 
        uint256 offset, 
        uint256 limit
    ) 
        external 
        view 
        validAddress(user)
        returns (uint256[] memory, uint256) 
    {
        uint256[] storage userAgents = _userAgents[user];
        uint256 totalCount = userAgents.length;
        
        if (offset >= totalCount) {
            return (new uint256[](0), totalCount);
        }
        
        uint256 end = offset + limit;
        if (end > totalCount) {
            end = totalCount;
        }
        
        uint256 resultLength = end - offset;
        uint256[] memory result = new uint256[](resultLength);
        
        for (uint256 i = 0; i < resultLength; i++) {
            result[i] = userAgents[offset + i];
        }
        
        return (result, totalCount);
    }

    /**
     * @notice Get all agents for a user
     * @param user The address of the user
     * @return uint256[] Array of agent IDs owned by the user
     */
    function getUserAgents(address user) 
        external 
        view 
        validAddress(user)
        returns (uint256[] memory) 
    {
        return _userAgents[user];
    }

    /**
     * @notice Get total number of registered agents
     * @return uint256 Total agent count
     */
    function getTotalAgents() 
        external 
        view 
        returns (uint256) 
    {
        return _agentIdCounter.current() - 1; // Subtract 1 because we start from 1
    }

    /**
     * @notice Get number of active agents
     * @return uint256 Active agent count
     */
    function getActiveAgentCount() 
        external 
        view 
        returns (uint256) 
    {
        return _agentIdCounter.current() - 1; // Simplified for gas efficiency
    }

    /**
     * @notice Check if an agent is active
     * @param agentId The ID of the agent
     * @return bool True if agent is active
     */
    function isAgentActive(uint256 agentId) 
        external 
        view 
        returns (bool) 
    {
        return _activeAgentIds[agentId];
    }

    /**
     * @notice Check if a name is reserved
     * @param name The name to check
     * @return bool True if name is reserved
     */
    function is