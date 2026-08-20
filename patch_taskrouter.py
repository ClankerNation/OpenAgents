import re

with open('contracts/TaskRouter.sol', 'r') as f:
    content = f.read()

# Add contributor header at the very top
header = """// @contributor-info ARO-Agentic
// @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
// @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
"""
if not content.startswith("// @contributor-info"):
    content = header + content

# Add imports for signature verification if not present
if "import \"@openzeppelin/contracts/utils/cryptography/ECDSA.sol\";" not in content:
    content = content.replace(
        'import "./AgentRegistry.sol";',
        'import "./AgentRegistry.sol";\nimport "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";\nimport "@openzeppelin/contracts/utils/cryptography/EIP712.sol";'
    )

# Update contract declaration to inherit EIP712
content = content.replace(
    "contract TaskRouter {",
    "contract TaskRouter is EIP712 {"
)

# Add state variables and events after platformFee
state_addition = """
    // Gas sponsorship relay state
    mapping(bytes32 => uint256) public nonces;
    mapping(bytes32 => uint256) public agentStake; // Simplified stake tracking for gas reimbursement
    
    bytes32 private constant EXECUTE_TYPEHASH = keccak256("ExecuteOnBehalf(address agent,bytes calldata,uint256 nonce)");
    
    event GasSponsored(bytes32 indexed agentId, address indexed relayer, uint256 gasUsed);
    event StakeDeposited(bytes32 indexed agentId, uint256 amount);
"""
content = content.replace(
    "event TaskDisputed(uint256 indexed taskId);",
    "event TaskDisputed(uint256 indexed taskId);" + state_addition
)

# Update constructor to initialize EIP712
old_constructor = """    constructor(address _registry, uint256 _platformFee) {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }"""
new_constructor = """    constructor(address _registry, uint256 _platformFee) EIP712("OpenAgentsTaskRouter", "1") {
        registry = AgentRegistry(_registry);
        platformFee = _platformFee;
    }"""
content = content.replace(old_constructor, new_constructor)

# Add executeOnBehalf and helper functions before the final closing brace
relay_functions = """
    /// @notice Deposit stake for gas sponsorship reimbursement.
    /// @param agentId The agent ID to credit stake to.
    function depositStake(bytes32 agentId) external payable {
        require(msg.value > 0, "Zero stake");
        agentStake[agentId] += msg.value;
        emit StakeDeposited(agentId, msg.value);
    }

    /// @notice Execute a transaction on behalf of an agent using meta-transaction.
    /// @param agent Address of the agent who signed the request.
    /// @param data Encoded calldata to execute.
    /// @param nonce Replay protection nonce.
    /// @param signature ECDSA signature from the agent.
    function executeOnBehalf(
        address agent,
        bytes calldata data,
        uint256 nonce,
        bytes calldata signature
    ) external returns (bytes memory) {
        // Verify nonce
        bytes32 agentId = keccak256(abi.encodePacked(agent));
        require(nonce == nonces[agentId], "Invalid nonce");
        
        // Verify signature using EIP-712
        bytes32 structHash = keccak256(abi.encode(EXECUTE_TYPEHASH, agent, keccak256(data), nonce));
        bytes32 digest = _hashTypedDataV4(structHash);
        address signer = ECDSA.recover(digest, signature);
        require(signer == agent, "Invalid signature");
        
        // Increment nonce to prevent replay
        nonces[agentId]++;
        
        // Execute the call
        uint256 gasBefore = gasleft();
        (bool success, bytes memory result) = address(this).call(data);
        uint256 gasUsed = gasBefore - gasleft();
        
        require(success, "Execution failed");
        
        // Reimburse relayer from agent's stake (simplified: fixed gas price estimate)
        // In production, use block.basefee or oracle price
        uint256 reimbursement = gasUsed * tx.gasprice;
        require(agentStake[agentId] >= reimbursement, "Insufficient stake for gas");
        agentStake[agentId] -= reimbursement;
        
        (bool paid, ) = msg.sender.call{value: reimbursement}("");
        require(paid, "Reimbursement failed");
        
        emit GasSponsored(agentId, msg.sender, gasUsed);
        return result;
    }
"""

# Insert before the last }
content = content.rstrip()
if content.endswith("}"):
    content = content[:-1] + relay_functions + "\n}\n"

with open('contracts/TaskRouter.sol', 'w') as f:
    f.write(content)

print("Patched TaskRouter.sol with gas sponsorship relay")
