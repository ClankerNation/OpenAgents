import re

with open('contracts/AgentRegistry.sol', 'r') as f:
    content = f.read()

# Add contributor header at the very top
header = """// @contributor-info ARO-Agentic
// @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
// @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
"""
if not content.startswith("// @contributor-info"):
    content = header + content

# Add batchRegister function before the last closing brace
batch_fn = """
    /**
     * @notice Register multiple agents in a single transaction for gas efficiency.
     * @param names Array of agent names (max 50)
     * @param endpoints Array of agent endpoints (must match names length)
     * @return agentIds Array of generated agent IDs
     */
    function batchRegister(
        string[] calldata names,
        string[] calldata endpoints
    ) external payable returns (bytes32[] memory) {
        require(names.length == endpoints.length, "Array length mismatch");
        require(names.length > 0 && names.length <= 50, "Invalid batch size");
        
        uint256 totalFee = registrationFee * names.length;
        require(msg.value >= totalFee, "Insufficient fee for batch");
        
        bytes32[] memory newAgentIds = new bytes32[](names.length);
        
        for (uint256 i = 0; i < names.length; i++) {
            require(bytes(names[i]).length > 0 && bytes(names[i]).length <= 64, "Invalid name");
            
            // Generate unique ID using index to avoid collisions within same block
            bytes32 agentId = keccak256(abi.encodePacked(msg.sender, names[i], block.timestamp, i));
            
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
            newAgentIds[i] = agentId;
            
            emit AgentRegistered(agentId, msg.sender, names[i]);
        }
        
        return newAgentIds;
    }
"""

# Insert before the final }
content = content.rstrip()
if content.endswith("}"):
    content = content[:-1] + batch_fn + "\n}\n"

with open('contracts/AgentRegistry.sol', 'w') as f:
    f.write(content)

print("Patched AgentRegistry.sol")
