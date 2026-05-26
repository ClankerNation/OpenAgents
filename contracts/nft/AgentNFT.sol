// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title AgentNFT
/// @notice ERC721-style NFT for AI agents with metadata URI support
/// @dev Simplified ERC721 implementation without full interface compliance
contract AgentNFT {
    string public name;
    string public symbol;
    string public baseURI;
    address public owner;
    uint256 public constant MAX_SUPPLY = 10000;
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
        require(_owners[tokenId] != address(0), "Token does not exist");
        return _owners[tokenId];
    }

    function balanceOf(address account) external view returns (uint256) {
        return _balances[account];
    }

    // BUG: No max supply check — tokens can be minted infinitely, potentially
    // devaluing the collection and causing unbounded gas costs for enumeration
    function mint(address to, string calldata uri) external onlyOwner returns (uint256) {
        require(to != address(0), "Mint to zero address");
        require(_nextTokenId < MAX_SUPPLY, "Max supply reached");
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
        require(_owners[tokenId] != address(0), "Token does not exist");
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
}
