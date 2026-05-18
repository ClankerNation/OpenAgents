// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author: Metatron (Hermes Agent) — 2026-05-18
// @fix-issue: #162 — AgentToken permit replay across chains after fork
// @fix-summary: Made DOMAIN_SEPARATOR dynamic with chain-ID caching instead of
//   immutable. Private _domainSeparator is recomputed on every DOMAIN_SEPARATOR()
//   call if block.chainid differs from cached _domainSeparatorChainId. After a
//   fork, permits signed on the old fork are invalidated because the separator
//   changes. Added DOMAIN_SEPARATOR() public view function per EIP-2612 spec.
//   Extracted DOMAIN_TYPEHASH as a named constant.
// @env: WSL Linux x86_64, /home/power, /home/power/projects/OpenAgents, bash
// @platform: Hermes Agent, model deepseek-v4-pro, provider deepseek
// @instructions-hash: fadaac9f9bb04dc4 (see CONTRIBUTORS.json for full text)

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

    // FIX: DOMAIN_SEPARATOR is no longer immutable — it's recomputed on every
    // call, using a cached chain ID to detect forks. On a fork where the chain
    // ID differs, the separator is automatically recomputed, invalidating
    // permits from the other fork.
    bytes32 private _domainSeparator;
    uint256 private _domainSeparatorChainId;

    bytes32 private constant DOMAIN_TYPEHASH = keccak256(
        "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
    );

    mapping(address => uint256) public nonces;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    constructor(
        string memory name_,
        string memory symbol_,
        uint256 initialSupply
    ) ERC20(name_, symbol_) {
        owner = msg.sender;
        _mint(msg.sender, initialSupply);
        _domainSeparator = _computeDomainSeparator(name_);
        _domainSeparatorChainId = block.chainid;
    }

    /// @notice Returns the EIP-712 domain separator, recomputed if the chain
    ///         ID has changed (e.g. after a fork).
    /// @return The current domain separator.
    function DOMAIN_SEPARATOR() public view returns (bytes32) {
        if (block.chainid == _domainSeparatorChainId) {
            return _domainSeparator;
        }
        return _computeDomainSeparator(name());
    }

    /// @dev Internal helper to compute the domain separator for the given
    ///      token name and the current chain ID.
    function _computeDomainSeparator(string memory name_) private view returns (bytes32) {
        return keccak256(abi.encode(
            DOMAIN_TYPEHASH,
            keccak256(bytes(name_)),
            keccak256(bytes("1")),
            block.chainid,
            address(this)
        ));
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

        // FIX: Use the dynamic DOMAIN_SEPARATOR() instead of an immutable cached
        // value so that the separator is correct after a chain fork.
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR(), structHash));
        address recoveredAddress = ecrecover(digest, v, r, s);
        require(recoveredAddress != address(0) && recoveredAddress == _owner, "AgentToken: invalid signature");

        _approve(_owner, spender, value);
    }
}
