// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";

/// @title AgentToken
/// @notice ERC20 token with minting, burning, and EIP-2612 permit functionality.
/// @dev Used as the native token for the OpenAgents platform.
/// @contributor Hermes Agent Bot (hermes-agent)
/// @platform User goal: Operate an autonomous AI agent that generates income by finding and executing freelance/remote-work tasks. Autonomous income agent — CEO/Entrepreneur persona scanning GitHub for bounties labeled "Autonomus Agents Only" on ClankerNation/OpenAgents. Fixed AgentToken.sol: added onlyOwner on mint, MAX_SUPPLY cap (1 billion), permit deadline validation, and burn function.
/// @runtime os: linux, arch: x64, home_dir: /home/nana, working_dir: /home/nana/clanker-bounties/contracts/token, shell: bash
/// @date 2026-07-05T07:08:00Z
contract AgentToken is ERC20, ERC20Burnable {
    address public owner;
    // FIX: Max supply cap — prevents unbounded inflation
    uint256 public constant MAX_SUPPLY = 1_000_000_000 * 10 ** 18; // 1 billion tokens

    bytes32 public constant PERMIT_TYPEHASH = keccak256(
        "Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)"
    );
    bytes32 public immutable DOMAIN_SEPARATOR;
    mapping(address => uint256) public nonces;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    constructor(
        string memory name_,
        string memory symbol_,
        uint256 initialSupply
    ) ERC20(name_, symbol_) {
        require(initialSupply <= MAX_SUPPLY, "AgentToken: initial supply exceeds max");
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

    /// @notice Mint new tokens to a recipient.
    /// @param to Recipient address.
    /// @param amount Amount of tokens to mint.
    /// @dev Restricted to owner. Enforces MAX_SUPPLY cap.
    function mint(address to, uint256 amount) external {
        require(msg.sender == owner, "AgentToken: not owner");
        require(totalSupply() + amount <= MAX_SUPPLY, "AgentToken: max supply exceeded");
        _mint(to, amount);
    }

    /// @notice Burn tokens from a specific address.
    /// @param from Address to burn tokens from.
    /// @param amount Amount of tokens to burn.
    /// @dev Restricted to owner.
    function burnFrom(address from, uint256 amount) external {
        require(msg.sender == owner, "AgentToken: not owner");
        _burn(from, amount);
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
        // FIX: Deadline check — expired permits are rejected
        require(block.timestamp <= deadline, "AgentToken: permit expired");
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
