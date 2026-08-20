/**
 * @contributor-info rafaio1
 * @timestamp 2026-08-20T12:15:00Z
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */

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
    // Cached domain separator and chain ID for fork detection
    bytes32 private _domainSeparator;
    uint256 private _domainChainId;
    
    mapping(address => uint256) public nonces;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    constructor(
        string memory name_,
        string memory symbol_,
        uint256 initialSupply
    ) ERC20(name_, symbol_) {
        owner = msg.sender;
        _mint(msg.sender, initialSupply);
        
        // Initialize domain separator with current chain ID
        _domainChainId = block.chainid;
        _domainSeparator = _computeDomainSeparator(name_);
    }
    
    /// @notice Compute EIP-712 domain separator dynamically
    /// @param name_ Token name for domain encoding
    /// @return Domain separator hash
    function _computeDomainSeparator(string memory name_) internal view returns (bytes32) {
        return keccak256(abi.encode(
            keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
            keccak256(bytes(name_)),
            keccak256(bytes("1")),
            block.chainid,
            address(this)
        ));
    }
    
    /// @notice Returns the current EIP-712 domain separator
    /// @dev Recomputes if chain ID changed (fork protection)
    /// @return Current domain separator
    function DOMAIN_SEPARATOR() external view returns (bytes32) {
        if (block.chainid == _domainChainId) {
            return _domainSeparator;
        }
        return _computeDomainSeparator(name());
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
