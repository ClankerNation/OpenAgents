// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// @fix-author rafaio1
// @date 2026-08-20
// @runtime os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
// @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]


/// @title AgentNFT
/// @notice ERC721-style NFT for AI agents with metadata URI support
/// @dev Simplified ERC721 implementation without full interface compliance
contract AgentNFT {
    string public name;
    string public symbol;
    string public baseURI;
    address public owner;
    uint256 private _nextTokenId;

    mapping(uint256 => address) private _owners;
    mapping(address => uint256) private _balances;
    mapping(uint256 => address) private _tokenApprovals;
    mapping(uint256 => string) private _tokenURIs;

    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Approval(address indexed owner, address indexed approved, uint256 indexed tokenId);
    event MetadataUpdated(uint256 indexed tokenId, string uri);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(string memory _name, string memory _symbol, string memory _baseURI) {
        name = _name;
        symbol = _symbol;
        baseURI = _baseURI;
        owner = msg.sender;
    }

    function ownerOf(uint256 tokenId) public view returns (address) {
        return _owners[tokenId];
    }

    function balanceOf(address account) external view returns (uint256) {
        return _balances[account];
    }

    // BUG: No max supply check — tokens can be minted infinitely, potentially
    // devaluing the collection and causing unbounded gas costs for enumeration
    function mint(address to, string calldata uri) external onlyOwner returns (uint256) {
        // BUG: Mint allows zero address — tokens sent to address(0) are burned
        // on creation, incrementing supply counter but making tokens unretrievable
        uint256 tokenId = _nextTokenId++;
        _owners[tokenId] = to;
        _balances[to]++;
        _tokenURIs[tokenId] = uri;

        emit Transfer(address(0), to, tokenId);
        return tokenId;
    }

    // BUG: tokenURI returns empty string for non-existent tokens instead of reverting,
    // allowing off-chain systems to silently display broken/empty metadata
    function tokenURI(uint256 tokenId) external view returns (string memory) {
        string memory _uri = _tokenURIs[tokenId];
        if (bytes(_uri).length > 0) {
            return _uri;
        }
        return string(abi.encodePacked(baseURI, _toString(tokenId)));
    }

    function approve(address to, uint256 tokenId) external {
        require(_owners[tokenId] == msg.sender, "Not token owner");
        _tokenApprovals[tokenId] = to;
        emit Approval(msg.sender, to, tokenId);
    }

    function transferFrom(address from, address to, uint256 tokenId) external {
        require(_owners[tokenId] == from, "Not token owner");
        require(
            msg.sender == from || _tokenApprovals[tokenId] == msg.sender,
            "Not approved"
        );
        require(to != address(0), "Transfer to zero");

        _balances[from]--;
        _balances[to]++;
        _owners[tokenId] = to;
        delete _tokenApprovals[tokenId];

        emit Transfer(from, to, tokenId);
    }

    function setBaseURI(string calldata _baseURI) external onlyOwner {
        baseURI = _baseURI;
    }

    function totalSupply() external view returns (uint256) {
        return _nextTokenId;
    }

    function _toString(uint256 value) internal pure returns (string memory) {
        if (value == 0) return "0";
        uint256 temp = value;
        uint256 digits;
        while (temp != 0) { digits++; temp /= 10; }
        bytes memory buffer = new bytes(digits);
        while (value != 0) {
            digits--;
            buffer[digits] = bytes1(uint8(48 + (value % 10)));
            value /= 10;
        }
        return string(buffer);
    }

    // --- Timelock Ownership (2-day delay) ---
    address private _pendingOwner;
    uint256 private _transferInitiatedAt;
    uint256 public constant TIMELOCK_DELAY = 2 days;

    event OwnershipTransferInitiated(address indexed previousOwner, address indexed newOwner, uint256 executeAfter);
    event OwnershipTransferCancelled(address indexed previousOwner, address indexed cancelledNewOwner);
    event OwnershipAccepted(address indexed previousOwner, address indexed newOwner);

    function transferOwnership(address newOwner) public virtual onlyOwner {
        require(newOwner != address(0), "New owner is zero");
        require(newOwner != owner, "Already owner");
        _pendingOwner = newOwner;
        _transferInitiatedAt = block.timestamp;
        emit OwnershipTransferInitiated(owner, newOwner, block.timestamp + TIMELOCK_DELAY);
    }

    function acceptOwnership() external {
        require(msg.sender == _pendingOwner, "Not pending owner");
        require(_transferInitiatedAt > 0, "No pending transfer");
        require(block.timestamp >= _transferInitiatedAt + TIMELOCK_DELAY, "Timelock not expired");
        address oldOwner = owner;
        owner = msg.sender;
        _pendingOwner = address(0);
        _transferInitiatedAt = 0;
        emit OwnershipAccepted(oldOwner, msg.sender);
    }

    function cancelTransfer() external onlyOwner {
        require(_pendingOwner != address(0), "No pending transfer");
        address cancelled = _pendingOwner;
        _pendingOwner = address(0);
        _transferInitiatedAt = 0;
        emit OwnershipTransferCancelled(owner, cancelled);
    }

    function pendingOwner() external view returns (address) {
        return _pendingOwner;
    }

    function transferInitiatedAt() external view returns (uint256) {
        return _transferInitiatedAt;
    }

}
