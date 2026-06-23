// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Permit.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// @title AgentToken
/// @notice ERC20 token with minting, burning, EIP-2612 permit, and governance voting/delegation.
/// @dev Extends ERC20Votes to support on-chain governance with delegation snapshots.
contract AgentToken is ERC20, ERC20Burnable, ERC20Permit, ERC20Votes, Ownable {
    uint256 public constant MAX_SUPPLY = 1_000_000_000 * 10 ** 18;

    mapping(bytes32 => uint256) private _snapshotIndex;
    mapping(uint256 => DelegationSnapshot) private _snapshots;
    uint256 private _snapshotCount;

    struct DelegationSnapshot {
        uint256 blockNumber;
        uint256 timestamp;
        address delegator;
        address delegatee;
        uint256 totalVotes;
    }

    event DelegationSnapshotCreated(
        uint256 indexed snapshotId,
        address indexed delegator,
        address indexed delegatee,
        uint256 totalVotes,
        uint256 blockNumber,
        uint256 timestamp
    );

    event SnapshotCheckpoint(uint256 indexed id, bytes32 checkpointHash);

    constructor(
        string memory name_,
        string memory symbol_,
        uint256 initialSupply
    ) ERC20(name_, symbol_) ERC20Permit(name_) Ownable(msg.sender) {
        _mint(msg.sender, initialSupply);
        DOMAIN_SEPARATOR = keccak256(abi.encode(
            keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
            keccak256(bytes(name_)),
            keccak256(bytes("1")),
            block.chainid,
            address(this)
        ));
    }

    /// @notice Mint new tokens to a recipient (owner-only).
    function mint(address to, uint256 amount) external onlyOwner {
        require(totalSupply() + amount <= MAX_SUPPLY, "AgentToken: exceeds max supply");
        _mint(to, amount);
    }

    /// @notice Transfer ownership of the contract.
    /// @param newOwner The new owner address.
    function transferOwnership(address newOwner) public override onlyOwner {
        require(newOwner != address(0), "AgentToken: zero address");
        super.transferOwnership(newOwner);
    }

    /// @notice Create a delegation snapshot for governance vote weighting.
    /// @dev Captures the current delegation state at the calling block.
    ///      This allows governance proposals to reference a deterministic
    ///      snapshot of voting power independent of later delegation changes.
    function createDelegationSnapshot() external returns (uint256 snapshotId) {
        snapshotId = _snapshotCount++;
        uint256 totalVotes = _totalSupply();

        DelegationSnapshot storage snap = _snapshots[snapshotId];
        snap.blockNumber = block.number;
        snap.timestamp = block.timestamp;
        snap.delegator = msg.sender;
        snap.delegatee = _getDelegatee(msg.sender);
        snap.totalVotes = totalVotes;

        _snapshotIndex[keccak256(abi.encode(snapshotId, msg.sender))] = snapshotId;

        emit DelegationSnapshotCreated(
            snapshotId,
            msg.sender,
            snap.delegatee,
            totalVotes,
            block.number,
            block.timestamp
        );

        emit SnapshotCheckpoint(snapshotId, _checkpointHash(snapshotId));
    }

    /// @notice Get the number of delegation snapshots recorded.
    function snapshotCount() external view returns (uint256) {
        return _snapshotCount;
    }

    /// @notice Retrieve a specific delegation snapshot by ID.
    /// @param snapshotId The snapshot identifier.
    /// @return DelegationSnapshot struct with block-level delegation data.
    function getSnapshot(uint256 snapshotId) external view returns (DelegationSnapshot memory) {
        require(snapshotId < _snapshotCount, "AgentToken: snapshot not found");
        return _snapshots[snapshotId];
    }

    /// @notice Get all snapshots for a given delegatee address.
    /// @param delegatee The address whose snapshots are queried.
    /// @return snapshotIds Array of snapshot IDs associated with the delegatee.
    function getSnapshotsFor(address delegatee) external view returns (uint256[] memory snapshotIds) {
        uint256 count = _snapshotCount;
        uint256[] memory ids = new uint256[](count);
        uint256 idx = 0;
        for (uint256 i = 0; i < count; i++) {
            if (_snapshots[i].delegatee == delegatee || _snapshots[i].delegator == delegatee) {
                ids[idx++] = i;
            }
        }
        snapshotIds = new uint256[](idx);
        for (uint256 i = 0; i < idx; i++) {
            snapshotIds[i] = ids[i];
        }
    }

    /// @notice Compute a deterministic hash for a snapshot.
    /// @param snapshotId The snapshot identifier.
    /// @return Hash of the snapshot's core fields.
    function _checkpointHash(uint256 snapshotId) internal view returns (bytes32) {
        DelegationSnapshot storage s = _snapshots[snapshotId];
        return keccak256(abi.encode(
            s.blockNumber,
            s.timestamp,
            s.delegator,
            s.delegatee,
            s.totalVotes
        ));
    }

    /// @notice Resolve the effective delegatee for an account.
    /// @param account The account to resolve.
    /// @return The delegate address, or the account itself if none.
    function _getDelegatee(address account) internal view returns (address) {
        (bool ok, address del) = tryGetDelegatee(account);
        return ok ? del : account;
    }

    /// @notice Safely retrieve the delegate for an account.
    /// @param account The account to query.
    /// @return ok Whether a delegate exists.
    /// @return del The delegate address.
    function tryGetDelegatee(address account) internal view returns (bool ok, address del) {
        del = getDelegate(account);
        ok = del != address(0);
    }

    /// @notice EIP-2612 permit: approve via signature.
    function permit(
        address _owner,
        address spender,
        uint256 value,
        uint256 deadline,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external override(ERC20Permit) {
        require(block.timestamp <= deadline, "AgentToken: permit expired");
        super.permit(_owner, spender, value, deadline, v, r, s);
    }

    /// @notice Internal hook called by ERC20Votes after a transfer or delegation.
    function _update(address from, address to, uint256 amount) internal override(ERC20, ERC20Votes) {
        super._update(from, to, amount);
    }

    /// @notice Nonce helper for permit.
    function nonces(address owner) public view override(ERC20Permit, IERC20Permit) returns (uint256) {
        return super.nonces(owner);
    }
}
