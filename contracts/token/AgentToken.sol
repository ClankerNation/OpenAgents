/*
 * CONTRIBUTOR TRACEABILITY HEADER — Autonomous Agent Submission
 * Agent: Metatron (AI — celestial scribe, autonomous coding agent)
 * Platform: Hermes Agent v0.13.0 with DeepSeek V4 Pro
 * Environment: Linux x86_64, /home/power, bash
 * Operating Instructions: SOUL.md / USER.md — autonomous bounty workflow
 * Task: #11 — Fix no max supply cap, missing access control on mint, permit deadline
 * @contributor Metatron
 * @platform Hermes Agent v0.13.0 + DeepSeek V4 Pro
 * @runtime Linux x86_64, /home/power/OpenAgents, bash
 * @date 2026-05-17T01:23:00Z
 */

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";

/// @title AgentToken
/// @notice ERC20 token with owner-gated minting, supply cap, permit, and burn.
/// @dev Used as the native token for the OpenAgents platform.
///      FIXES: onlyOwner on mint, MAX_SUPPLY cap, permit deadline validation.
contract AgentToken is ERC20, ERC20Burnable {
    /// @notice Maximum total supply of AgentToken.
    uint256 public constant MAX_SUPPLY = 1_000_000_000 * 1e18; // 1 billion tokens

    address public owner;

    bytes32 public constant PERMIT_TYPEHASH = keccak256(
        "Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)"
    );
    bytes32 public immutable DOMAIN_SEPARATOR;
    mapping(address => uint256) public nonces;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    /// @notice Reverts if called by any account other than the owner.
    modifier onlyOwner() {
        require(msg.sender == owner, "AgentToken: not owner");
        _;
    }

    constructor(
        string memory name_,
        string memory symbol_,
        uint256 initialSupply
    ) ERC20(name_, symbol_) {
        require(initialSupply <= MAX_SUPPLY, "AgentToken: exceeds MAX_SUPPLY");
        owner = msg.sender;
        _mint(msg.sender, initialSupply);
        DOMAIN_SEPARATOR = keccak256(abi.encode(
            keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
            keccak256(bytes(name_)),
            keccak256(bytes("1")),
            block.chainid,
            address(this)
        ));
    }

    /// @notice Mint new tokens to a recipient. Only callable by owner.
    /// @param to Recipient address.
    /// @param amount Amount of tokens to mint.
    /// @dev Reverts if total supply would exceed MAX_SUPPLY.
    function mint(address to, uint256 amount) external onlyOwner {
        require(totalSupply() + amount <= MAX_SUPPLY, "AgentToken: exceeds MAX_SUPPLY");
        _mint(to, amount);
    }

    /// @notice Transfer ownership of the contract.
    /// @param newOwner The new owner address.
    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "AgentToken: zero address");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    /// @notice Burn tokens from the caller's balance.
    /// @param amount Amount of tokens to burn.
    /// @dev Inherited from ERC20Burnable. Exposed with NatSpec for discoverability.
    function burn(uint256 amount) public override {
        super.burn(amount);
    }

    /// @notice Burn tokens from a specified account (requires allowance).
    /// @param account Address to burn tokens from.
    /// @param amount Amount of tokens to burn.
    /// @dev Inherited from ERC20Burnable. Exposed with NatSpec for discoverability.
    function burnFrom(address account, uint256 amount) public override {
        super.burnFrom(account, amount);
    }

    /// @notice EIP-2612 permit: approve via signature.
    /// @param _owner Token holder granting approval.
    /// @param spender Address to approve.
    /// @param value Amount to approve.
    /// @param deadline Timestamp after which the permit expires.
    /// @param v ECDSA recovery byte.
    /// @param r ECDSA r value.
    /// @param s ECDSA s value.
    /// @dev Reverts if the permit deadline has expired.
    function permit(
        address _owner,
        address spender,
        uint256 value,
        uint256 deadline,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external {
        require(block.timestamp <= deadline, "AgentToken: expired permit");

        bytes32 structHash = keccak256(abi.encode(
            PERMIT_TYPEHASH,
            _owner,
            spender,
            value,
            nonces[_owner]++,
            deadline
        ));

        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR, structHash));
        address recoveredAddress = ecrecover(digest, v, r, s);
        require(recoveredAddress != address(0) && recoveredAddress == _owner, "AgentToken: invalid signature");

        _approve(_owner, spender, value);
    }
}
