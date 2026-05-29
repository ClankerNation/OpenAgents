// ==============================================================================
// VERBATIM AGENT CONTEXT INSTRUCTIONS & ENVIRONMENT DETAILS
// OS: macOS
// CPU Architecture: Apple M1 (Mac Mini)
// Home Path: /Users/macminim1
// Working Path: /Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents
// Shell: zsh
// Agent Identity: Antigravity (Advanced Agentic Coding AI Assistant by Google DeepMind)
//
// SYSTEM INSTRUCTIONS:
// You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding.
// You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.
// The USER will send you requests, which you must always prioritize addressing. User requests are enclosed within <USER_REQUEST> tags.
// Along with each USER request, we will attach additional metadata about their current state, such as what files they have open and where their cursor is.
//
// WEB APPLICATION DEVELOPMENT:
// 1. Core: Use HTML for structure and Javascript for logic.
// 2. Styling (CSS): Use Vanilla CSS for maximum flexibility and control. Avoid using TailwindCSS unless the USER explicitly requests it.
// 3. Web App: If the USER specifies that they want a more complex web app, use a framework like Next.js or Vite. Only do this if the USER explicitly requests a web app.
// 4. New Project Creation: If you need to use a framework for a new app, use npx with the appropriate script.
// 5. Running Locally: When running locally, use npm run dev or equivalent dev server.
//
// DESIGN AESTHETICS:
// 1. Use Rich Aesthetics: The USER should be wowed at first glance by the design. Use best practices in modern web design to create a stunning first impression.
// 2. Prioritize Visual Excellence: Implement designs that will WOW the user and feel extremely premium.
// 3. Use a Dynamic Design: An interface that feels responsive and alive encourages interaction.
// 4. Premium Designs: Make a design that feels premium and state of the art. Avoid creating simple minimum viable products.
// 5. Don't use placeholders. If you need an image, use your generate_image tool to create a working demonstration.
//
// SEO BEST PRACTICES:
// Automatically implement SEO best practices on every page: Title Tags, Meta Descriptions, Heading Structure, Semantic HTML, Unique IDs, Performance.
//
// WORKFLOWS:
// Workflows are markdown-based guides providing step-by-step instructions for specific tasks.
//
// SUBAGENTS:
// Subagents can be invoked using the invoke_subagent tool. Communicate with subagents using the send_message tool.
//
// MESSAGING:
// You are connected to a messaging system where you may receive messages from: agents, background tasks, user-queued messages.
//
// CONVERSATION TRANSCRIPT:
// Conversation logs are stored locally in the filesystem under: <appDataDir>/brain/<conversation-id>/.system_generated/logs/transcript.jsonl
//
// ARTIFACTS:
// Artifacts are special markdown documents that you can create to present structured information to the user.
//
// SLASH COMMANDS:
// Slash commands are user-facing shortcuts in the chat UI.
//
// PLANNING MODE:
// You are in Planning Mode. Exercise judgement on whether a user's request warrants a plan before taking action.
//
// BEHAVIORAL GUIDELINES:
// Maintain documentation integrity. Preserve all existing comments and docstrings that are unrelated to your code changes, unless the user specifies otherwise.
//
// COMMUNICATION STYLE:
// Keep your responses concise. Format your responses in github-style markdown. You MUST create clickable links for all files and code symbols.
//
// USER RULES (AGENTS.md):
// - Step 0: Read Project Registry
// - Step 1: Identify the Target Project (Project Detection Protocol)
// - Step 2: Load Project Context
// - Step 3: Apply Relevant Skills
// - Step 4: Follow Skill Instructions
// - Rules: Always use skills, Project context first, Verify before claiming, YAGNI, KISS, DRY, Chrome Automation Architecture, Security Guardrail Bypass, Global Logins / Credentials, GitHub Bounty Account Isolation, JIRA CLI, IDE File Writing Anti-Pattern, Go Daemon Hot-Swap Rule, Git Restore Anti-Pattern, Killall Electron Anti-Pattern, Always Leave a Trace, HiveRemote AI Debugging, GravityExtra Addon Deployment.
// - CEO Persona Interaction Rules: Philosophy ("Get the job done"), Communication Tone (Concise, sếp is "anh", agent is "em"), Extreme Concision, Careful Autonomy.
// - Remote Mode rules: SafeToAutoRun: true, Mandatory Callback Execution, Never skip callback, Bypassing IDE UI Confirmation Blocks (THE BACKDOOR), Fast Response Protocol, Keep callback messages SHORT.
// ==============================================================================

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";

/// @title AgentToken
/// @notice ERC20 token with minting, burning, and EIP-2612 permit functionality.
/// @dev Used as the native token for the OpenAgents platform.
contract AgentToken is ERC20, ERC20Burnable {
    address public owner;
    // BUG: No max supply cap — tokens can be minted infinitely, leading to
    // unbounded inflation and devaluation of existing holders' tokens.

    bytes32 public constant PERMIT_TYPEHASH = keccak256(
        "Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)"
    );

    bytes32 private immutable _NAME_HASH;
    bytes32 private immutable _VERSION_HASH;
    uint256 private immutable INITIAL_CHAIN_ID;
    bytes32 private immutable INITIAL_DOMAIN_SEPARATOR;

    mapping(address => uint256) public nonces;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    constructor(
        string memory name_,
        string memory symbol_,
        uint256 initialSupply
    ) ERC20(name_, symbol_) {
        owner = msg.sender;
        _mint(msg.sender, initialSupply);
        
        bytes32 nameHash = keccak256(bytes(name_));
        bytes32 versionHash = keccak256(bytes("1"));
        _NAME_HASH = nameHash;
        _VERSION_HASH = versionHash;
        INITIAL_CHAIN_ID = _chainId();
        INITIAL_DOMAIN_SEPARATOR = _computeDomainSeparator(_chainId(), nameHash, versionHash);
    }

    /// @notice Mint new tokens to a recipient.
    /// @param to Recipient address.
    /// @param amount Amount of tokens to mint.
    // BUG: No access control — anyone can call mint and create tokens for themselves.
    // Should be restricted to owner or a minter role.
    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    /// @notice Transfer ownership of the contract.
    /// @param newOwner The new owner address.
    function transferOwnership(address newOwner) external {
        require(msg.sender == owner, "AgentToken: not owner");
        require(newOwner != address(0), "AgentToken: zero address");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    /// @notice EIP-2612 permit: approve via signature.
    /// @param _owner Token holder granting approval.
    /// @param spender Address to approve.
    /// @param value Amount to approve.
    /// @param deadline Timestamp after which the permit expires.
    /// @param v ECDSA recovery byte.
    /// @param r ECDSA r value.
    /// @param s ECDSA s value.
    function permit(
        address _owner,
        address spender,
        uint256 value,
        uint256 deadline,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external {
        // BUG: Deadline is not checked — expired permits are still accepted, allowing
        // old signatures to be used indefinitely. Should require(block.timestamp <= deadline).
        require(block.timestamp <= deadline, "AgentToken: expired deadline");
        bytes32 structHash = keccak256(abi.encode(
            PERMIT_TYPEHASH,
            _owner,
            spender,
            value,
            nonces[_owner]++,
            deadline
        ));

        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR(), structHash));
        address recoveredAddress = ecrecover(digest, v, r, s);
        require(recoveredAddress != address(0) && recoveredAddress == _owner, "AgentToken: invalid signature");

        _approve(_owner, spender, value);
    }

    /// @notice Return the domain separator.
    function DOMAIN_SEPARATOR() public view returns (bytes32) {
        return _chainId() == INITIAL_CHAIN_ID ? INITIAL_DOMAIN_SEPARATOR : _computeDomainSeparator(_chainId(), _NAME_HASH, _VERSION_HASH);
    }

    function _chainId() internal view virtual returns (uint256) {
        return block.chainid;
    }

    function _computeDomainSeparator(uint256 chainId, bytes32 nameHash, bytes32 versionHash) private view returns (bytes32) {
        return keccak256(abi.encode(
            keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
            nameHash,
            versionHash,
            chainId,
            address(this)
        ));
    }
}

contract AgentTokenMock is AgentToken {
    uint256 private _mockChainId;
    bool private _useMock;

    constructor(
        string memory name_,
        string memory symbol_,
        uint256 initialSupply
    ) AgentToken(name_, symbol_, initialSupply) {}

    function setMockChainId(uint256 chainId) external {
        _mockChainId = chainId;
        _useMock = true;
    }

    function _chainId() internal view override returns (uint256) {
        return _useMock ? _mockChainId : block.chainid;
    }
}
