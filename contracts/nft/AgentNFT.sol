// agent name: claude code + hermes agent
// platform initialization text: User prefers concise, direct communication without excessive explanation. When discussing technical implementations, focus on the core changes and avoid verbose walkthroughs unless specifically asked for details. The user values efficiency and dislikes when the agent 'grabs circles' or over-explains simple concepts.
// runtime: Linux, x86_64, /root/workspace/OpenAgents-44/OpenAgents, bash
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
    uint256 private _nextTokenId;
    uint256 public MAX_SUPPLY = 10000;

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

    function _exists(uint256 tokenId) internal view returns (bool) {
        return _owners[tokenId] != address(0);
    }

    function ownerOf(uint256 tokenId) public view returns (address) {
        return _owners[tokenId];
    }

    function balanceOf(address account) external view returns (uint256) {
        return _balances[account];
    }

    // BUG: No max supply check — tokens can be minted infinitely, potentially
    // devaluing the collection and causing unbounded gas costs for enumeration
    function mint(address to, string calldata uri) public onlyOwner returns (uint256) {
        require(to != address(0), "Mint to zero");
        require(_nextTokenId < MAX_SUPPLY, "Max supply reached");
        uint256 tokenId = _nextTokenId++;
        _owners[tokenId] = to;
        _balances[to]++;
        _tokenURIs[tokenId] = uri;

        emit Transfer(address(0), to, tokenId);
        return tokenId;
    }

    function batchMint(address[] calldata recipients, string[] calldata uris) external onlyOwner {
        require(recipients.length == uris.length, "Length mismatch");
        for (uint256 i = 0; i < recipients.length; i++) {
            mint(recipients[i], uris[i]);
        }
    }

    // BUG: tokenURI returns empty string for non-existent tokens instead of reverting,
    // allowing off-chain systems to silently display broken/empty metadata
    function tokenURI(uint256 tokenId) external view returns (string memory) {
        require(_exists(tokenId), "Token does not exist");
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
