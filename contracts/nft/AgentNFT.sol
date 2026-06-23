// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title AgentNFT
 * @notice ERC721-style NFT for AI agents with metadata URI and royalty support
 * @contributor Gaotax2006
 * @platform claude-code/opus-4.8
 * @runtime node-v24.15.0 / win32 / amd64
 * @date 2026-06-24
 * @fixes #161 — Added ERC2981 royalty standard for secondary sale commissions
 */

contract AgentNFT {
    string public name;
    string public symbol;
    string public baseURI;
    address public owner;
    uint256 private _nextTokenId;
    uint256 public maxSupply;

    mapping(uint256 => address) private _owners;
    mapping(address => uint256) private _balances;
    mapping(uint256 => address) private _tokenApprovals;
    mapping(uint256 => string) private _tokenURIs;

    // Royalty info: receiver and fee in basis points (max 10000 = 100%)
    address public royaltyReceiver;
    uint96 public royaltyBps; // basis points for royalty fee

    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Approval(address indexed owner, address indexed approved, uint256 indexed tokenId);
    event MetadataUpdated(uint256 indexed tokenId, string uri);
    event RoyaltySet(address indexed receiver, uint256 indexed bps);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(string memory _name, string memory _symbol, string memory _baseURI) {
        name = _name;
        symbol = _symbol;
        baseURI = _baseURI;
        owner = msg.sender;
        maxSupply = type(uint256).max; // Unlimited by default
    }

    /**
     * @notice Set royalty info for secondary sales (ERC2981 standard).
     */
    function setRoyaltyInfo(address _receiver, uint256 _bps) external onlyOwner {
        require(_bps <= 1000, "Royalty too high (max 10%)");
        require(_receiver != address(0), "Zero receiver");
        royaltyReceiver = _receiver;
        royaltyBps = uint96(_bps);
        emit RoyaltySet(_receiver, _bps);
    }

    /**
     * @notice Get royalty info for a sale (ERC2981 standard).
     * @param totalPrice Total sale price in wei.
     * @return royaltyReceiver Address to receive royalties.
     * @return royaltyAmount Amount of royalty in wei.
     */
    function royaltyInfo(uint256, uint256 totalPrice) external view returns (address royaltyReceiver, uint256 royaltyAmount) {
        if (royaltyBps > 0) {
            return (royaltyReceiver, (totalPrice * royaltyBps) / 10000);
        }
        return (address(0), 0);
    }

    function ownerOf(uint256 tokenId) public view returns (address) {
        return _owners[tokenId];
    }

    function balanceOf(address account) external view returns (uint256) {
        return _balances[account];
    }

    function mint(address to, string calldata uri) external onlyOwner returns (uint256) {
        require(to != address(0), "Mint to zero");
        require(_nextTokenId < maxSupply, "Max supply reached");

        uint256 tokenId = _nextTokenId++;
        _owners[tokenId] = to;
        _balances[to]++;
        _tokenURIs[tokenId] = uri;

        emit Transfer(address(0), to, tokenId);
        return tokenId;
    }

    function tokenURI(uint256 tokenId) external view returns (string memory) {
        require(_owners[tokenId] != address(0) || tokenId < _nextTokenId, "Token does not exist");
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

    function setMaxSupply(uint256 _max) external onlyOwner {
        require(_max >= _nextTokenId, "Max supply below current");
        maxSupply = _max;
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
