// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author rafaio1
// @date 2026-08-20
// @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
// @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";

/// @title AgentToken
/// @notice ERC20 token with minting, burning, and EIP-2612 permit functionality.
/// @dev Used as the native token for the OpenAgents platform.
///      Domain separator is computed dynamically to handle chain forks safely.
contract AgentToken is ERC20, ERC20Burnable {
    address public owner;
    uint256 public constant MAX_SUPPLY = 1_000_000_000e18; // 1 billion tokens

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
        require(initialSupply <= MAX_SUPPLY, "AgentToken: exceeds max supply");
        owner = msg.sender;
        _mint(msg.sender, initialSupply);
        
        // Initialize domain separator
        _domainChainId = block.chainid;
        _domainSeparator = _computeDomainSeparator(name_);
    }

    /// @notice Compute the EIP-712 domain separator dynamically.
    function _computeDomainSeparator(string memory name_) internal view returns (bytes32) {
        return keccak256(abi.encode(
            keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
            keccak256(bytes(name_)),
            keccak256(bytes("1")),
            block.chainid,
            address(this)
        ));
    }

    /// @notice Returns the current domain separator, recomputing if chain ID changed.
    function DOMAIN_SEPARATOR() external view returns (bytes32) {
        if (block.chainid == _domainChainId) {
            return _domainSeparator;
        }
        return _computeDomainSeparator(name());
    }

    /// @notice Mint new tokens to a recipient. Only owner.
    /// @param to Recipient address.
    /// @param amount Amount of tokens to mint.
    function mint(address to, uint256 amount) external {
        require(msg.sender == owner, "AgentToken: not owner");
        require(totalSupply() + amount <= MAX_SUPPLY, "AgentToken: exceeds max supply");
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
        require(block.timestamp <= deadline, "AgentToken: expired permit");
        
        // Use dynamic domain separator to handle forks
        bytes32 domainSep;
        if (block.chainid == _domainChainId) {
            domainSep = _domainSeparator;
        } else {
            domainSep = _computeDomainSeparator(name());
        }

        bytes32 structHash = keccak256(abi.encode(
            PERMIT_TYPEHASH,
            _owner,
            spender,
            value,
            nonces[_owner]++,
            deadline
        ));

        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSep, structHash));
        address recoveredAddress = ecrecover(digest, v, r, s);
        require(recoveredAddress != address(0) && recoveredAddress == _owner, "AgentToken: invalid signature");

        _approve(_owner, spender, value);
    }
}
