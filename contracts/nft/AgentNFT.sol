// @contributor rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
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
    uint256 public constant MAX_SUPPLY = 10_000;
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

    /// @notice Mint a new AgentNFT to the specified address.
    /// @param to Recipient address.
    /// @param uri Metadata URI for the token.
    /// @return tokenId The newly minted token ID.
    function mint(address to, string calldata uri) external onlyOwner returns (uint256) {
        require(to != address(0), "AgentNFT: mint to zero");
        require(_nextTokenId < MAX_SUPPLY, "AgentNFT: max supply reached");

        uint256 tokenId = _nextTokenId++;
        _owners[tokenId] = to;
        _balances[to]++;
        _tokenURIs[tokenId] = uri;

        emit Transfer(address(0), to, tokenId);
        return tokenId;
    }

    /// @notice Batch mint multiple NFTs to a single recipient.
    /// @param to Recipient address.
    /// @param uris Array of metadata URIs.
    /// @return tokenIds Array of newly minted token IDs.
    function batchMint(address to, string[] calldata uris) external onlyOwner returns (uint256[] memory tokenIds) {
        require(to != address(0), "AgentNFT: mint to zero");
        require(uris.length > 0, "AgentNFT: empty batch");
        require(_nextTokenId + uris.length <= MAX_SUPPLY, "AgentNFT: exceeds max supply");

        tokenIds = new uint256[](uris.length);
        for (uint256 i = 0; i < uris.length; i++) {
            uint256 tokenId = _nextTokenId++;
            _owners[tokenId] = to;
            _balances[to]++;
            _tokenURIs[tokenId] = uris[i];
            tokenIds[i] = tokenId;
            emit Transfer(address(0), to, tokenId);
        }
    }

    /// @notice Returns the metadata URI for a given token.
    /// @param tokenId The token to query.
    /// @return The metadata URI string.
    function tokenURI(uint256 tokenId) external view returns (string memory) {
        require(_owners[tokenId] != address(0), "AgentNFT: nonexistent token");
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
